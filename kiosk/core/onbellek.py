"""CİHAZ ÖNBELLEĞİ — veri dosyaları ve yayın görselleri diskte tutulur.

Amaç (kullanıcı isteği): **maliyet + performans**. İnternetten bir kez indirilen
içerik (nöbet JSON'u ve yayın görseli) cihazda saklanır; sonraki gösterimlerde
ağ kullanılmaz.

Kurallar
--------
* **Geçersizleşme:** `lastupdate.json` değeri değiştiğinde veri önbelleği geçersiz
  sayılır (içerik yeniden alınır). `ONBELLEK_GORSEL_LASTUPDATE_YENILER` açıkken
  görseller de bir kez tazelenir (aynı adresteki içerik değişmiş olabilir).
* **Süre sonu (son gösterim tarihi):** yayının `end` alanı geçtikten ve
  `ONBELLEK_GORSEL_SAKLAMA_GUN` gün boyunca hiç gösterilmediyse görsel cihazdan
  silinir (`bakim()`); artık veride geçmeyen görseller de anında atılır.
* **Kota:** toplam boyut `ONBELLEK_MAKS_BAYT`'ı aşarsa en eski kullanılanlar silinir.
* **Bütünlük:** her kaydın sha256'sı saklanır; okurken doğrulanır (bozulmuş/oynanmış
  kayıt sessizce kullanılmaz, atılır).

Güvenlik: okumalar `security.veri_dogrulama.dosya_oku_guvenli` ile (sembolik bağ ve
kök dışına çıkma denetimi), yazmalar `atomik_yaz` + 0600 izniyle yapılır.
Görseller yine `security.image_policy` + `safe_image` kapısından geçer (önbellekten
gelse de yeniden doğrulanır — bayt sınırı, biçim beyaz listesi, piksel bütçesi).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

import config
from security.veri_dogrulama import atomik_yaz, dosya_oku_guvenli

log = logging.getLogger("kiosk.onbellek")

KOK = Path(__file__).resolve().parent.parent
DIZIN_ADI = "dizin.json"
SURUM = 1

#: URL'den türetilen dosya adlarında kullanılabilecek uzantılar
_UZANTILAR = {".png", ".jpg", ".jpeg", ".webp", ".ico", ".bmp", ".gif"}


# ------------------------------------------------------------------ yollar/ayar
def kok_klasoru() -> Path:
    """Önbellek kökü: proje kökü altında TEK bir klasör (ayardan gelen ad temizlenir).

    Ad, yol ayırıcısı/üst dizin içeremez; böylece dosya güvenlik denetimlerinin
    (sembolik bağ ve kök dışına çıkma yasağı) sınırı anlamlı kalır.
    """
    ad = re.sub(r"[^A-Za-z0-9._-]", "_", str(getattr(config, "ONBELLEK_KLASORU", "onbellek"))).strip()
    if not ad or ad in {".", ".."}:
        ad = "onbellek"
    return KOK / ad


def veri_klasoru() -> Path:
    return kok_klasoru() / "veri"


def gorsel_klasoru() -> Path:
    return kok_klasoru() / "gorsel"


def aktif() -> bool:
    return bool(getattr(config, "ONBELLEK_AKTIF", True))


def maks_bayt() -> int:
    return int(getattr(config, "ONBELLEK_MAKS_BAYT", 512 * 1024 * 1024))


def saklama_gun() -> int:
    return int(getattr(config, "ONBELLEK_GORSEL_SAKLAMA_GUN", 2))


def _simdi() -> datetime:
    return datetime.now()


def _zaman(metin) -> datetime | None:
    if not isinstance(metin, str) or not metin:
        return None
    try:
        return datetime.fromisoformat(metin)
    except ValueError:
        return None


# ------------------------------------------------------------------ dizin
def _dizin_yolu() -> Path:
    return kok_klasoru() / DIZIN_ADI


def _dizin_oku() -> dict:
    """Önbellek dizinini okur (bozuksa boş kabul eder ve uyarır)."""
    yol = _dizin_yolu()
    if not yol.is_file():
        return {"surum": SURUM, "veri": {}, "gorsel": {}}
    try:
        ham = dosya_oku_guvenli(yol, kok=KOK, etiket="onbellek dizini", en_buyuk_bayt=2 * 1024 * 1024)
        veri = json.loads(ham.decode("utf-8-sig"))
        if not isinstance(veri, dict) or veri.get("surum") != SURUM:
            raise ValueError("bilinmeyen dizin sürümü")
        veri.setdefault("veri", {})
        veri.setdefault("gorsel", {})
        return veri
    except (OSError, ValueError, json.JSONDecodeError) as hata:
        log.warning("önbellek dizini okunamadı (%s) — sıfırdan kurulacak", hata)
        return {"surum": SURUM, "veri": {}, "gorsel": {}}


def _dizin_yaz(dizin: dict) -> None:
    atomik_yaz(_dizin_yolu(), json.dumps(dizin, ensure_ascii=False, indent=1), mod=0o600)


def _sha256(govde: bytes) -> str:
    return hashlib.sha256(govde).hexdigest()


def _guvenli_oku(yol: Path) -> bytes | None:
    try:
        return dosya_oku_guvenli(yol, kok=KOK, etiket=yol.name, en_buyuk_bayt=maks_bayt())
    except OSError:
        return None


# ------------------------------------------------------------------ VERİ (JSON)
def _veri_yolu(dosya: str) -> Path:
    guvenli = re.sub(r"[^A-Za-z0-9._-]", "_", str(dosya))[:64]
    return veri_klasoru() / guvenli


def veri_lastupdate(dosya: str) -> str:
    """Bu dosyanın hangi `lastupdate` değeriyle saklandığı (yoksa "")."""
    return str(_dizin_oku()["veri"].get(dosya, {}).get("lastupdate", ""))


def veri_oku(dosya: str, lastupdate: str = "") -> bytes | None:
    """Önbellekten okur. `lastupdate` verilmişse eşleşmiyorsa None (geçersiz)."""
    if not aktif():
        return None
    kayit = _dizin_oku()["veri"].get(dosya)
    if not isinstance(kayit, dict):
        return None
    if lastupdate and str(kayit.get("lastupdate", "")) != str(lastupdate):
        log.info("önbellek geçersiz (%s): lastupdate değişti (%s → %s)", dosya, kayit.get("lastupdate"), lastupdate)
        return None
    govde = _guvenli_oku(_veri_yolu(dosya))
    if govde is None:
        return None
    if kayit.get("sha256") and _sha256(govde) != kayit["sha256"]:
        log.warning("önbellekteki '%s' bozulmuş — atılıyor", dosya)
        veri_temizle(dosya)
        return None
    return govde


def veri_yaz(dosya: str, govde: bytes, lastupdate: str = "") -> None:
    if not aktif() or not govde:
        return
    veri_klasoru().mkdir(parents=True, exist_ok=True)
    atomik_yaz(_veri_yolu(dosya), govde, mod=0o600)
    dizin = _dizin_oku()
    dizin["veri"][dosya] = {
        "lastupdate": str(lastupdate or ""),
        "alindi": _simdi().isoformat(timespec="seconds"),
        "bayt": len(govde),
        "sha256": _sha256(govde),
    }
    _dizin_yaz(dizin)
    log.info("veri önbelleğe alındı: %s (%d bayt, lastupdate=%s)", dosya, len(govde), lastupdate or "-")


def veri_temizle(dosya: str | None = None) -> int:
    """Veri önbelleğini siler (tek dosya ya da tümü). Silinen dosya sayısı döner."""
    dizin = _dizin_oku()
    hedefler = [dosya] if dosya else list(dizin["veri"])
    silinen = 0
    for ad in hedefler:
        kayit = dizin["veri"].pop(ad, None)
        if kayit is None:
            continue
        yol = _veri_yolu(ad)
        if yol.is_file():
            yol.unlink(missing_ok=True)
            silinen += 1
    _dizin_yaz(dizin)
    return silinen


# ------------------------------------------------------------------ GÖRSEL
def gorsel_anahtari(url: str) -> str:
    """URL'den kararlı, dosya sistemine uygun anahtar üretir (içerik adrese bağlı)."""
    adres = str(url or "").strip()
    uzanti = ""
    eslesme = re.search(r"(\.[A-Za-z0-9]{2,5})(?:$|\?)", adres)
    if eslesme and eslesme.group(1).lower() in _UZANTILAR:
        uzanti = eslesme.group(1).lower()
    return hashlib.sha256(adres.encode("utf-8")).hexdigest()[:32] + (uzanti or ".bin")


def _gorsel_yolu(anahtar: str) -> Path:
    return gorsel_klasoru() / anahtar


def gorsel_gosterildi(url: str) -> None:
    """Görsel ekranda kullanıldı: son gösterim zamanını günceller (süre sonu için)."""
    if not aktif():
        return
    anahtar = gorsel_anahtari(url)
    dizin = _dizin_oku()
    kayit = dizin["gorsel"].get(anahtar)
    if not isinstance(kayit, dict):
        return
    kayit["son_gosterim"] = _simdi().isoformat(timespec="seconds")
    kayit["gosterim"] = int(kayit.get("gosterim", 0)) + 1
    _dizin_yaz(dizin)


def gorsel_oku(url: str) -> bytes | None:
    """Görseli önbellekten okur (yoksa/bozuksa None)."""
    if not aktif():
        return None
    anahtar = gorsel_anahtari(url)
    kayit = _dizin_oku()["gorsel"].get(anahtar)
    if not isinstance(kayit, dict) or kayit.get("bayat"):
        return None
    govde = _guvenli_oku(_gorsel_yolu(anahtar))
    if govde is None:
        return None
    if kayit.get("sha256") and _sha256(govde) != kayit["sha256"]:
        log.warning("önbellekteki görsel bozulmuş — atılıyor: %s", anahtar)
        gorsel_temizle(url)
        return None
    return govde


def gorsel_yaz(url: str, govde: bytes, icerik_turu: str = "") -> None:
    """Görseli önbelleğe yazar (aynı adres tekrar gelirse üzerine yazar)."""
    if not aktif() or not govde:
        return
    gorsel_klasoru().mkdir(parents=True, exist_ok=True)
    anahtar = gorsel_anahtari(url)
    atomik_yaz(_gorsel_yolu(anahtar), govde, mod=0o600)
    dizin = _dizin_oku()
    onceki = dizin["gorsel"].get(anahtar, {})
    dizin["gorsel"][anahtar] = {
        "url": str(url),
        "alindi": _simdi().isoformat(timespec="seconds"),
        "son_gosterim": onceki.get("son_gosterim") or _simdi().isoformat(timespec="seconds"),
        "gosterim": int(onceki.get("gosterim", 0)),
        "bayt": len(govde),
        "icerik_turu": str(icerik_turu or ""),
        "sha256": _sha256(govde),
        "bayat": False,
    }
    _dizin_yaz(dizin)
    log.info("görsel önbelleğe alındı: %s (%d bayt)", anahtar, len(govde))


def gorsel_temizle(url: str) -> None:
    anahtar = gorsel_anahtari(url)
    dizin = _dizin_oku()
    if dizin["gorsel"].pop(anahtar, None) is not None:
        _gorsel_yolu(anahtar).unlink(missing_ok=True)
        _dizin_yaz(dizin)


def gorselleri_bayat_isaretle(gecerli_url_kumesi: set[str] | None = None) -> int:
    """Görselleri 'bayat' işaretler (veri değiştiğinde bir kez tazelensin).

    `gecerli_url_kumesi` verilirse yalnızca o adresler işaretlenir; verilmezse tümü.
    """
    if not aktif() or not bool(getattr(config, "ONBELLEK_GORSEL_LASTUPDATE_YENILER", True)):
        return 0
    dizin = _dizin_oku()
    sayi = 0
    for anahtar, kayit in dizin["gorsel"].items():
        if not isinstance(kayit, dict):
            continue
        if gecerli_url_kumesi is not None and str(kayit.get("url", "")) not in gecerli_url_kumesi:
            continue
        if not kayit.get("bayat"):
            kayit["bayat"] = True
            sayi += 1
    if sayi:
        _dizin_yaz(dizin)
        log.info("veri değişti: %d görsel tazelenecek", sayi)
    return sayi


# ------------------------------------------------------------------ bakım
def _dosyalari_say(klasor: Path) -> tuple[int, int]:
    if not klasor.is_dir():
        return 0, 0
    adet = bayt = 0
    for dosya in klasor.iterdir():
        if dosya.is_file():
            adet += 1
            try:
                bayt += dosya.stat().st_size
            except OSError:
                pass
    return adet, bayt


def istatistik() -> dict:
    """Önbellek durumu (panelde/teşhiste gösterilir)."""
    return {
        "aktif": aktif(),
        "klasor": str(kok_klasoru()),
        "veri_adet": len(_dizin_oku()["veri"]),
        "gorsel_adet": len(_dizin_oku()["gorsel"]),
        "veri_bayt": _dosyalari_say(veri_klasoru())[1],
        "gorsel_bayt": _dosyalari_say(gorsel_klasoru())[1],
        "maks_bayt": maks_bayt(),
        "saklama_gun": saklama_gun(),
    }


def bakim(an: datetime | None = None, gecerli_url_kumesi: set[str] | None = None) -> dict:
    """Süresi geçen/artık kullanılmayan görselleri siler, kotayı uygular.

    * `gecerli_url_kumesi` dışındaki görseller (veride artık geçmiyor) SİLİNİR,
    * son gösterimi `saklama_gun` günü geçen görseller silinir,
    * toplam boyut sınırı aşılırsa en eski kullanılanlar silinir,
    * dizinde kaydı olmayan dosyalar ve dosyası olmayan kayıtlar temizlenir.
    """
    if not aktif():
        return {"aktif": False, "silinen": 0, "silinen_bayt": 0}
    an = an or _simdi()
    dizin = _dizin_oku()
    silinen = silinen_bayt = 0
    son_gecerlilik = an - timedelta(days=saklama_gun())

    def _sil(anahtar: str) -> None:
        nonlocal silinen, silinen_bayt
        kayit = dizin["gorsel"].pop(anahtar, {})
        yol = _gorsel_yolu(anahtar)
        boyut = int(kayit.get("bayt", 0) or 0)
        if yol.is_file():
            try:
                boyut = boyut or yol.stat().st_size
                yol.unlink()
            except OSError as hata:
                log.warning("görsel silinemedi (%s): %s", anahtar, hata)
                return
        silinen += 1
        silinen_bayt += boyut

    # 1) veride geçmeyen artık görseller
    if gecerli_url_kumesi is not None:
        for anahtar, kayit in list(dizin["gorsel"].items()):
            if isinstance(kayit, dict) and str(kayit.get("url", "")) not in gecerli_url_kumesi:
                _sil(anahtar)

    # 2) süresi geçenler (son gösterim + saklama süresi)
    for anahtar, kayit in list(dizin["gorsel"].items()):
        if not isinstance(kayit, dict):
            _sil(anahtar)
            continue
        son = _zaman(kayit.get("son_gosterim")) or _zaman(kayit.get("alindi"))
        if son is not None and son < son_gecerlilik:
            log.info("süresi geçen görsel silindi: %s (son gösterim %s)", anahtar, kayit.get("son_gosterim"))
            _sil(anahtar)

    # 3) kota: en eski kullanılanlar önce
    def _toplam() -> int:
        return _dosyalari_say(gorsel_klasoru())[1] + _dosyalari_say(veri_klasoru())[1]

    if _toplam() > maks_bayt():
        kayitlar = sorted(
            (a for a in dizin["gorsel"]),
            key=lambda a: str(dizin["gorsel"].get(a, {}).get("son_gosterim", "")),
        )
        for anahtar in kayitlar:
            if _toplam() <= maks_bayt():
                break
            _sil(anahtar)

    # 4) öksüz dosyalar (dizinde kaydı yok) ve dosyası olmayan kayıtlar
    oksuz = 0
    beklenen_gorsel = set(dizin["gorsel"])
    beklenen_veri = {re.sub(r"[^A-Za-z0-9._-]", "_", ad)[:64] for ad in dizin["veri"]}
    for klasor, beklenen in ((gorsel_klasoru(), beklenen_gorsel), (veri_klasoru(), beklenen_veri)):
        if not klasor.is_dir():
            continue
        for dosya in klasor.iterdir():
            if dosya.is_file() and dosya.name not in beklenen:
                try:
                    dosya.unlink()
                    oksuz += 1
                except OSError:
                    pass
    # dosyası silinmiş kayıtları dizinden düşür
    for anahtar in [a for a in dizin["gorsel"] if not _gorsel_yolu(a).is_file()]:
        dizin["gorsel"].pop(anahtar, None)
    for ad in [a for a in dizin["veri"] if not _veri_yolu(a).is_file()]:
        dizin["veri"].pop(ad, None)

    _dizin_yaz(dizin)
    sonuc = {
        "aktif": True,
        "silinen": silinen,
        "silinen_bayt": silinen_bayt,
        "oksuz_dosya": oksuz,
        "kalan_bayt": _toplam(),
    }
    if silinen or oksuz:
        log.info(
            "önbellek bakımı: %d görsel silindi (%.1f MB), %d öksüz dosya; kalan %.1f MB",
            silinen,
            silinen_bayt / 1024 / 1024,
            oksuz,
            sonuc["kalan_bayt"] / 1024 / 1024,
        )
    return sonuc


# ------------------------------------------------------------------ veri damgası
def damgayi_kaydet(damga: str) -> bool:
    """`lastupdate` damgasını saklar; **değiştiyse True** döner.

    Hem uygulama çalışırken hem de yeniden başlatma sonrası geçersizleşmeyi yakalar:
    kayıtlı damga ile gelen damga farklıysa içerik değişmiştir (ilk çalıştırmada,
    kayıt yokken False döner — o an zaten taze veri indirilir).
    """
    if not aktif() or not damga:
        return False
    dizin = _dizin_oku()
    onceki = str(dizin.get("lastupdate", "") or "")
    if onceki == str(damga):
        return False
    dizin["lastupdate"] = str(damga)
    _dizin_yaz(dizin)
    log.info("lastupdate damgası: %s → %s", onceki or "(yok)", damga)
    return bool(onceki)


def kayitli_damga() -> str:
    return str(_dizin_oku().get("lastupdate", "") or "")


def onbellegi_bosalt() -> dict:
    """Tüm önbelleği siler (panelden 'önbelleği temizle' için)."""
    dizin = _dizin_oku()
    silinen = 0
    for klasor in (gorsel_klasoru(), veri_klasoru()):
        if not klasor.is_dir():
            continue
        for dosya in klasor.iterdir():
            if dosya.is_file():
                try:
                    dosya.unlink()
                    silinen += 1
                except OSError:
                    pass
    _dizin_yaz({"surum": SURUM, "veri": {}, "gorsel": {}})
    log.info("önbellek boşaltıldı (%d dosya)", silinen)
    return {"silinen_dosya": silinen}
