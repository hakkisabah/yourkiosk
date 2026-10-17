"""Yönetim paneli — Cognito'suz (Lambda + cookie) kimlik ve imzalı S3 erişimi.

Akış:
    POST /giris   {sifre}                  → doğru ise HttpOnly oturum cookie'si
    GET  /oturum                            → cookie geçerli mi?
    POST /cikis                             → cookie silinir
    POST /imzala  {dosya, islem, etag?}     → presigned GET/PUT URL (beyaz liste)

Güvenlik:
  * şifre düz metin saklanmaz: `PANEL_SIFRE_OZETI` = pbkdf2_sha256$iter$salt$ozet
  * oturum cookie'si HMAC-SHA256 ile imzalı + süreli; değiştirilirse geçersiz
  * yalnızca beyaz listedeki kiosk dosyaları okunur/yazılır, ön ek dışına çıkılamaz
  * basit giriş hız sınırı (örnek başına; Lambda örnekleri paylaşmaz — bkz. README)

Ortam değişkenleri:
    KOVA_ADI            zorunlu  — kiosk verisinin tutulduğu S3 kovası
    ON_EK               seçimli  — ön ek (ör. "kiosk/")
    PANEL_SIFRE_OZETI   zorunlu  — sifre_ozetle.py çıktısı
    OTURUM_ANAHTARI     zorunlu  — cookie imzası için rastgele sır (>= 32 karakter)
    PANEL_ORIGIN        zorunlu  — CORS/CSRF için panelin adresi (ör. https://panel.example.com)
    OTURUM_SURE_S       seçimli  — oturum ömrü saniye (varsayılan 43200 = 12 saat)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any

import boto3
from botocore.config import Config as BotoConfig

# --------------------------------------------------------------------- sabitler
#: Panelin yönetebileceği dosyalar (kiosk ile aynı adlar). Başka ad istemek reddedilir.
IZINLI_DOSYALAR = frozenset(
    {
        "ayarlar.json",
        "kapsam-ayarlari.json",
        "lastSystemData.json",
        "sablon.json",
        "match.json",
        "lastupdate.json",
        "makinebilgileri.json",
    }
)
IZINLI_ISLEMLER = frozenset({"oku", "yaz"})
MAKS_YAZMA_BAYT = 32 * 1024 * 1024  # 32 MB (kullanıcı senaryosu: 20-30 MB veri)
IMZA_GECERLILIK_S = 300  # presigned URL ömrü (5 dk)
COOKIE_ADI = "yk_oturum"
_GIRIS_DENEME_SINIRI = 8  # aynı örnek içinde pencere başına deneme
_GIRIS_PENCERE_S = 300


class YapilandirmaHatasi(RuntimeError):
    """Zorunlu ortam değişkeni eksik/eksik tanımlı."""


# ------------------------------------------------------------------ yapılandırma
def ayar(ad: str, varsayilan: str | None = None) -> str:
    deger = os.environ.get(ad, varsayilan)
    if deger is None or deger == "":
        raise YapilandirmaHatasi(f"ortam değişkeni eksik: {ad}")
    return deger


def kova() -> str:
    return ayar("KOVA_ADI")


def on_ek() -> str:
    ham = os.environ.get("ON_EK", "")
    return (ham if not ham or ham.endswith("/") else f"{ham}/").lstrip("/")


def oturum_suresi() -> int:
    try:
        return max(300, int(os.environ.get("OTURUM_SURE_S", "43200")))
    except ValueError:
        return 43200


def s3_istemcisi():
    return boto3.client("s3", config=BotoConfig(signature_version="s3v4"))


# ------------------------------------------------------------------ şifre özeti
def sifre_dogrula(sifre: str, ozet: str | None = None) -> bool:
    """pbkdf2_sha256$<iterasyon>$<salt>$<özet> biçimini sabit zamanlı karşılaştırır."""
    ozet = ozet if ozet is not None else os.environ.get("PANEL_SIFRE_OZETI", "")
    try:
        algoritma, iterasyon, salt, beklenen = ozet.split("$", 3)
    except ValueError:
        return False
    if algoritma != "pbkdf2_sha256":
        return False
    try:
        ozet_bayt = hashlib.pbkdf2_hmac(
            "sha256", sifre.encode("utf-8"), base64.b64decode(salt), int(iterasyon)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(base64.b64encode(ozet_bayt).decode(), beklenen)


def sifre_ozeti_uret(sifre: str, iterasyon: int = 260_000) -> str:
    """Yönetici şifresinden saklanabilir özet üretir (`sifre_ozetle.py` kullanır)."""
    salt = secrets.token_bytes(16)
    ozet = hashlib.pbkdf2_hmac("sha256", sifre.encode("utf-8"), salt, iterasyon)
    return f"pbkdf2_sha256${iterasyon}${base64.b64encode(salt).decode()}${base64.b64encode(ozet).decode()}"


# ------------------------------------------------------------------ oturum cookie
def _imza(govde: str, anahtar: str) -> str:
    return base64.urlsafe_b64encode(
        hmac.new(anahtar.encode("utf-8"), govde.encode("utf-8"), hashlib.sha256).digest()
    ).decode().rstrip("=")


def oturum_uret(an: float | None = None, sure: int | None = None, anahtar: str | None = None) -> str:
    """`<bitiş-zamanı>.<imza>` biçiminde imzalı oturum değeri."""
    anahtar = anahtar if anahtar is not None else ayar("OTURUM_ANAHTARI")
    sure = sure if sure is not None else oturum_suresi()
    bitis = int((an if an is not None else time.time()) + sure)
    govde = str(bitis)
    return f"{govde}.{_imza(govde, anahtar)}"


def oturum_gecerli(deger: str | None, an: float | None = None, anahtar: str | None = None) -> bool:
    """İmzayı ve süreyi doğrular; değiştirilmiş/eskimiş cookie geçersiz sayılır."""
    if not deger or "." not in deger:
        return False
    anahtar = anahtar if anahtar is not None else os.environ.get("OTURUM_ANAHTARI", "")
    if not anahtar:
        return False
    govde, imza = deger.rsplit(".", 1)
    if not hmac.compare_digest(imza, _imza(govde, anahtar)):
        return False
    try:
        bitis = float(govde)
    except ValueError:
        return False
    return (an if an is not None else time.time()) < bitis


def cookie_uret(deger: str) -> str:
    """HttpOnly + Secure + SameSite=Lax oturum cookie başlığı."""
    return f"{COOKIE_ADI}={deger}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age={oturum_suresi()}"


def cookie_sil() -> str:
    return f"{COOKIE_ADI}=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0"


def cerezden_oturum(cookie_basligi: str | None) -> str | None:
    if not cookie_basligi:
        return None
    for parca in cookie_basligi.split(";"):
        ad, _, deger = parca.strip().partition("=")
        if ad == COOKIE_ADI:
            return deger or None
    return None


# ------------------------------------------------------------------ S3 anahtarı
def nesne_anahtari(dosya: str) -> str:
    """Beyaz listeyi ve ön eki uygular; yol kaçışı (../) engellenir."""
    temiz = (dosya or "").strip().lstrip("/")
    if temiz not in IZINLI_DOSYALAR:
        raise ValueError(f"izin verilmeyen dosya: {dosya!r}")
    if ".." in temiz:
        raise ValueError("geçersiz dosya adı")
    return f"{on_ek()}{temiz}"


def imzala(dosya: str, islem: str, etag: str | None = None, boyut: int | None = None) -> dict[str, Any]:
    """Presigned GET/PUT URL üretir (yalnızca beyaz listedeki dosyalar)."""
    if islem not in IZINLI_ISLEMLER:
        raise ValueError(f"izin verilmeyen işlem: {islem!r}")
    anahtar = nesne_anahtari(dosya)
    if islem == "oku":
        if etag:
            # Koşullu okuma: dosya değiştiyse S3 412 döner (panel yarışı önler)
            parametreler: dict[str, Any] = {"Bucket": kova(), "Key": anahtar, "IfMatch": etag}
        else:
            parametreler = {"Bucket": kova(), "Key": anahtar}
        url = s3_istemcisi().generate_presigned_url(
            "get_object", Params=parametreler, ExpiresIn=IMZA_GECERLILIK_S
        )
        return {"url": url, "islem": islem}

    if boyut is not None and int(boyut) > MAKS_YAZMA_BAYT:
        raise ValueError(f"dosya çok büyük: {boyut} > {MAKS_YAZMA_BAYT}")
    url = s3_istemcisi().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": kova(),
            "Key": anahtar,
            "ContentType": "application/json; charset=utf-8",
            "CacheControl": "no-store",
        },
        ExpiresIn=IMZA_GECERLILIK_S,
    )
    return {"url": url, "islem": islem}


# ------------------------------------------------------------------ hız sınırı
_denemeler: dict[str, list[float]] = {}


def _hiz_siniri_asildi(kimlik: str, an: float | None = None) -> bool:
    an = an if an is not None else time.time()
    gecmis = [t for t in _denemeler.get(kimlik, []) if an - t < _GIRIS_PENCERE_S]
    gecmis.append(an)
    _denemeler[kimlik] = gecmis
    return len(gecmis) > _GIRIS_DENEME_SINIRI


def _denemeleri_sifirla(kimlik: str) -> None:
    _denemeler.pop(kimlik, None)


# ------------------------------------------------------------------ yardımcılar
def _yanit(kod: int, govde: dict[str, Any] | None = None, cookie: str | None = None) -> dict[str, Any]:
    basliklar = {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }
    origin = os.environ.get("PANEL_ORIGIN", "")
    if origin:
        basliklar["Access-Control-Allow-Origin"] = origin
        basliklar["Access-Control-Allow-Credentials"] = "true"
        basliklar["Vary"] = "Origin"
    if cookie:
        basliklar["Set-Cookie"] = cookie
    return {"statusCode": kod, "headers": basliklar, "body": json.dumps(govde or {}, ensure_ascii=False)}


def _govde_coz(olay: dict[str, Any]) -> dict[str, Any]:
    ham = olay.get("body") or ""
    if olay.get("isBase64Encoded"):
        ham = base64.b64decode(ham).decode("utf-8", "replace")
    if not ham.strip():
        return {}
    try:
        veri = json.loads(ham)
    except json.JSONDecodeError:
        return {}
    return veri if isinstance(veri, dict) else {}


def _yol(olay: dict[str, Any]) -> str:
    yol = olay.get("rawPath") or olay.get("path") or "/"
    return "/" + yol.strip("/")


def _istemci_kimligi(olay: dict[str, Any]) -> str:
    basliklar = {k.lower(): v for k, v in (olay.get("headers") or {}).items()}
    return str(basliklar.get("x-forwarded-for", "yerel")).split(",")[0].strip()


def _origin_uygun(olay: dict[str, Any]) -> bool:
    """CSRF: tarayıcıdan gelen isteklerde Origin başlığı panel adresi olmalı."""
    basliklar = {k.lower(): v for k, v in (olay.get("headers") or {}).items()}
    origin = basliklar.get("origin")
    if not origin:  # curl gibi tarayıcı dışı istemciler (cookie yoksa giriş zaten şifre ister)
        return True
    return origin == os.environ.get("PANEL_ORIGIN", "")


# ------------------------------------------------------------------ ana akış
def lambda_handler(olay: dict[str, Any], _baglam: Any = None) -> dict[str, Any]:
    yol = _yol(olay)
    yontem = (olay.get("requestMethod") or olay.get("httpMethod") or "GET").upper()

    if yontem == "OPTIONS":  # CORS ön kontrolü
        return _yanit(204)

    if not _origin_uygun(olay):
        return _yanit(403, {"hata": "Origin uygun değil"})

    if yol == "/giris" and yontem == "POST":
        return _giris(olay)
    if yol == "/oturum" and yontem == "GET":
        return _oturum_kontrol(olay)
    if yol == "/cikis" and yontem == "POST":
        return _yanit(200, {"cikis": True}, cookie=cookie_sil())
    if yol == "/imzala" and yontem == "POST":
        return _imzala_istegi(olay)
    return _yanit(404, {"hata": "bilinmeyen uç nokta"})


def _giris(olay: dict[str, Any]) -> dict[str, Any]:
    kimlik = _istemci_kimligi(olay)
    if _hiz_siniri_asildi(kimlik):
        return _yanit(429, {"hata": "çok fazla deneme; biraz sonra tekrar deneyin"})
    veri = _govde_coz(olay)
    sifre = str(veri.get("sifre") or "")
    if not sifre or not sifre_dogrula(sifre):
        return _yanit(401, {"hata": "şifre hatalı"})
    _denemeleri_sifirla(kimlik)
    return _yanit(200, {"giris": True}, cookie=cookie_uret(oturum_uret()))


def _oturum_kontrol(olay: dict[str, Any]) -> dict[str, Any]:
    basliklar = {k.lower(): v for k, v in (olay.get("headers") or {}).items()}
    gecerli = oturum_gecerli(cerezden_oturum(basliklar.get("cookie")))
    return _yanit(200, {"giris": gecerli})


def _imzala_istegi(olay: dict[str, Any]) -> dict[str, Any]:
    basliklar = {k.lower(): v for k, v in (olay.get("headers") or {}).items()}
    if not oturum_gecerli(cerezden_oturum(basliklar.get("cookie"))):
        return _yanit(401, {"hata": "oturum yok veya süresi doldu"})
    veri = _govde_coz(olay)
    try:
        sonuc = imzala(
            str(veri.get("dosya") or ""),
            str(veri.get("islem") or ""),
            etag=veri.get("etag") if isinstance(veri.get("etag"), str) else None,
            boyut=veri.get("boyut") if isinstance(veri.get("boyut"), int) else None,
        )
    except ValueError as hata:
        return _yanit(400, {"hata": str(hata)})
    return _yanit(200, sonuc)
