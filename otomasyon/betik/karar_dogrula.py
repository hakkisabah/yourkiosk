#!/usr/bin/env python3
"""KARAR KAPISI — i5/i3 kararını yayınlamadan ÖNCE makineyle doğrula (fail-closed).

NEDEN: Ajan "baktım" der, ama gerçekten baktığını hiçbir şey doğrulamıyordu. 25 Ekim'de i5
iki turda aynı üç bulguyu "KAPANMADI" diye tekrarladı; i3 de bulguları elle doğrulamak zorunda
kaldı. Kararsızlık ise sessizce `onay`a dönüşebiliyordu (en tehlikeli sonuç). Bu betik kararı
yayınlanmadan önce şu kurallarla süzer:

  1. Şema: `makine`/`karar`/`onem`/`ozet`/`bulgular`/`denetlenen` alanları ve değer kümeleri.
  2. KAPSAM: i5 kararı 12 denetim alanının TAMAMINI, i3 en az 8'ini (3'ü zorunlu) listelemeli.
  3. TUTARLILIK: `yuksek` önemli bulgu varken `onay` verilemez; `sorun/red/duzeltme` boş
     bulgu listesiyle verilemez.
  4. FAIL-CLOSED: özet/notta "emin değilim", "doğrulanmalı", "karar veremedim" gibi bir
     kararsızlık işareti varsa karar `onay`/`kabul` OLAMAZ (→ `sorun`).
  5. KANIT (ağ): her bulgunun `dosya:satir`'ı PR head'inde gerçekten var mı, satır numarası
     dosyanın içinde mi? (dosya PR'da değişmemişse "değişen dosya değil" uyarısı)
  6. KAPANIŞ ÖLÇÜTÜ: `sorun`/`red`/`duzeltme` kararlarında her bulgu `kabul` alanında "neyi
     yapınca bu bulgu KAPANIR" yazmalı. Ölçütsüz düzeltme reçetesi iki tur sonra aynı bulguyla
     geri döner (25 Ekim'de yaşandı).

Kullanım:
    python3 otomasyon/betik/karar_dogrula.py /tmp/karar-83.json
    python3 otomasyon/betik/karar_dogrula.py /tmp/karar-83.json --kanit-yok   # ağ kontrolü kapalı
    python3 otomasyon/betik/karar_dogrula.py /tmp/karar-83.json --json

Çıkış kodları: 0 geçti · 1 reddedildi · 2 kullanım/okuma hatası
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

#: i5'in denetlemesi gereken 12 alan (otomasyon/prompt/i5-guvenlik.md ile AYNI olmalı).
DENETIM_ALANLARI = (
    "gömülü sır",
    "komut çalıştırma",
    "dosya/yol",
    "ağ/tls",
    "kimlik/yetki",
    "girdi doğrulama",
    "sır sızıntısı",
    "bağımlılık",
    "dos/maliyet",
    "kalıcılık/geri dönüş",
    "kapsayıcı/servis",
    "test kanıtı",
)

#: Ajanın yazabileceği kısa adlar → kanonik alan
ES_ANLAMLILAR = {
    "gomulu sir": "gömülü sır", "gömülü sir": "gömülü sır", "sır": "gömülü sır",
    "komut": "komut çalıştırma", "komut çalıştırma": "komut çalıştırma", "rce": "komut çalıştırma",
    "dosya": "dosya/yol", "yol": "dosya/yol", "dosya/yol": "dosya/yol",
    "tls": "ağ/tls", "ağ": "ağ/tls", "ağ/tls": "ağ/tls", "https": "ağ/tls",
    "kimlik": "kimlik/yetki", "yetki": "kimlik/yetki", "iam": "kimlik/yetki",
    "iam en az yetki": "kimlik/yetki", "kimlik/yetki": "kimlik/yetki",
    "girdi": "girdi doğrulama", "girdi doğrulama": "girdi doğrulama",
    "sır sızıntısı": "sır sızıntısı", "log": "sır sızıntısı", "günlük": "sır sızıntısı",
    "bağımlılık": "bağımlılık", "cve": "bağımlılık", "osv": "bağımlılık",
    "dos": "dos/maliyet", "dos/maliyet": "dos/maliyet", "maliyet": "dos/maliyet",
    "kalıcılık": "kalıcılık/geri dönüş", "geri dönüş": "kalıcılık/geri dönüş",
    "kalıcılık/geri dönüş": "kalıcılık/geri dönüş",
    "kapsayıcı": "kapsayıcı/servis", "docker": "kapsayıcı/servis", "systemd": "kapsayıcı/servis",
    "kapsayıcı/servis": "kapsayıcı/servis",
    "test": "test kanıtı", "test kanıtı": "test kanıtı",
    # ASCII karşılıklar (26 Ekim i5 bulgusu): dürüst bir inceleme Türkçe harf yazmadan alan
    # bildirebilmeli. Aksi hâlde "12 alanın TAMAMI bildirilmeli" hatası doğru kararı reddediyordu.
    "gomulu sir": "gömülü sır", "gomulu sır": "gömülü sır", "gömülü sir": "gömülü sır",
    "komut calistirma": "komut çalıştırma", "komut çaliştirma": "komut çalıştırma",
    "ag/tls": "ağ/tls", "ag": "ağ/tls", "ağ/tls": "ağ/tls",
    "kimlik/yetki": "kimlik/yetki", "girdi dogrulama": "girdi doğrulama",
    "sir sizintisi": "sır sızıntısı",
    "bagimlilik": "bağımlılık", "dos/maliyet": "dos/maliyet",
    "kalicilik/geri donus": "kalıcılık/geri dönüş", "kalicilik": "kalıcılık/geri dönüş",
    "geri donus": "kalıcılık/geri dönüş", "kapsayici/servis": "kapsayıcı/servis",
    "test kaniti": "test kanıtı", "kapsayici": "kapsayıcı/servis",
}

KARARLAR_I5 = {"onay", "sorun", "red"}
KARARLAR_I3 = {"kabul", "duzeltme", "red", "sorun"}
ONAY_KARARLARI = {"onay", "kabul"}
ONEMLER = {"yuksek", "orta", "dusuk"}
ONEM_ES = {"yüksek": "yuksek", "orta": "orta", "düşük": "dusuk", "low": "dusuk", "high": "yuksek"}

#: i3'ün kendi taramasında görmesi ZORUNLU alanlar (i5'in kaçırdığını yakalayan üç alan)
I3_ZORUNLU = ("gömülü sır", "kimlik/yetki", "test kanıtı")
I3_ASGARI_ALAN = 8

KARARSIZLIK = ("emin değilim", "emin degilim", "doğrulanmalı", "dogrulanmali", "karar veremedim",
               "bilmiyorum", "kontrol edemedim", "bakamadım", "bakamadim", "şüpheli", "supheli",
               "tam emin", "kesin değil", "kesin degil")

YER_TUTUCU = ("yol/dosya.py", "örnek bulgu", "buraya", "şablon", "sablon")


def alan_normal(ad: str) -> str:
    anahtar = re.sub(r"\s+", " ", str(ad).strip().strip("`").casefold())
    return ES_ANLAMLILAR.get(anahtar, anahtar)


def dosya_normal(yol: str) -> str:
    """`kiosk/core/x.py:37` veya `` `kiosk/core/x.py` `` → `kiosk/core/x.py`"""
    temiz = str(yol).strip().strip("`").strip()
    temiz = re.sub(r":\d+(-\d+)?$", "", temiz)
    return temiz


def satir_no(deger) -> int:
    """37 · "37" · "37-40" · 0 → ilk satır numarası (0 = belirtilmemiş)."""
    if isinstance(deger, bool):
        return 0
    if isinstance(deger, int):
        return max(0, deger)
    m = re.search(r"\d+", str(deger or ""))
    return int(m.group(0)) if m else 0


@dataclass
class Sonuc:
    hatalar: list[str] = field(default_factory=list)
    uyarilar: list[str] = field(default_factory=list)

    @property
    def gecti(self) -> bool:
        return not self.hatalar

    def rapor(self) -> str:
        satirlar = []
        for h in self.hatalar:
            satirlar.append(f"✗ {h}")
        for u in self.uyarilar:
            satirlar.append(f"⚠ {u}")
        satirlar.append("✓ karar kapısı: geçti" if self.gecti else f"✗ karar kapısı: {len(self.hatalar)} hata")
        return "\n".join(satirlar)


# ---------------------------------------------------------------- ağ (kanıt) kontrolü


def _api(yol: str, token: str, depo: str):
    url = f"https://api.github.com/repos/{depo}{yol}"
    istek = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "yourkiosk-karar-kapisi",
    })
    try:
        with urllib.request.urlopen(istek, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as hata:
        return hata.code, None
    except (urllib.error.URLError, TimeoutError):
        return 0, None


def kanit_denetle(karar: dict, sonuc: Sonuc, token: str, depo: str) -> None:
    """Her bulgunun `dosya:satir` kanıtı PR head'inde gerçekten var mı?"""
    bulgular = [b for b in (karar.get("bulgular") or []) if isinstance(b, dict)]
    if not bulgular:
        return
    #: Bulgu taşıyan karar "sorun/red/duzeltme" ise dosya:satır ZORUNLU; onay/kabul kararında değil.
    satir_zorunlu = str(karar.get("karar", "")).strip().lower() not in ONAY_KARARLARI
    pr_no, sha = karar.get("pr"), str(karar.get("sha") or "").strip()

    degisen: set[str] | None = None
    if pr_no:
        kod, dosyalar = _api(f"/pulls/{pr_no}/files?per_page=100", token, depo)
        if kod == 200 and isinstance(dosyalar, list):
            degisen = {d.get("filename", "") for d in dosyalar if isinstance(d, dict)}
    # ── SHA ↔ PR HEAD ──────────────────────────────────────────────────────────────
    # 26 Ekim i5 bulgusu: kapı, karar dosyasındaki sha'yı olduğu gibi kullanıyordu. Bayat/yanlış
    # sha ile "kanıt var" denebiliyordu (bulgu başka commit'te doğrulanır, karar başka commit'e
    # yazılır). Artık sha PR'ın GERÇEK head'i ile karşılaştırılır; farklıysa karar reddedilir.
    head_sha = ""
    if pr_no:
        kod, pr_veri = _api(f"/pulls/{pr_no}", token, depo)
        if kod == 200 and isinstance(pr_veri, dict):
            head_sha = str((pr_veri.get("head") or {}).get("sha", "")).strip()
        elif not head_sha:
            # FAIL-CLOSED (26 Ekim i5 bulgusu): head okunamayınca (0/403/429/…) eski sürüm yalnız
            # UYARI yazıp sha karşılaştırmasını atlıyordu → karar dosyasındaki bayat sha ile
            # "kanıt var" denebiliyordu. Head doğrulanamıyorsa tazelik denetimi de yapılamaz;
            # karar geçmez (yaz.py bu satırı kapi-red.log'a yazar).
            sonuc.hatalar.append(
                f"kanıt tazeliği doğrulanamadı: PR #{pr_no} head okunamadı (HTTP {kod}) — fail-closed")
            return
    if head_sha:
        if not sha:
            sha = head_sha
        elif sha != head_sha:
            sonuc.hatalar.append(
                f"kanıt BAYAT: karar sha'sı {sha[:12]} ama PR #{pr_no} head {head_sha[:12]} "
                f"— karar güncel commit'e yazılmalı")
            return
    if not sha:
        sonuc.uyarilar.append("kanıt denetimi atlandı: sha yok (ayrıntı doğrulanamadı)")
        return

    onbellek: dict[str, int | None] = {}
    for b in bulgular:
        dosya, satir = dosya_normal(b.get("dosya", "")), satir_no(b.get("satir"))
        if not dosya:
            sonuc.hatalar.append("bulgu 'dosya' alanı boş")
            continue
        if dosya not in onbellek:
            kod, icerik = _api(f"/contents/{urllib.parse.quote(dosya)}?ref={sha}", token, depo)
            if kod == 200 and isinstance(icerik, dict) and icerik.get("content"):
                metin = base64.b64decode(icerik["content"]).decode("utf-8", "replace")
                # `count("\n") + 1` sonu yeni satırla biten dosyada bir FAZLA veriyordu:
                # dosyanın son satırı + 1 numaralı satır "var" görünüyordu (26 Ekim i5 bulgusu).
                onbellek[dosya] = len(metin.splitlines()) or (1 if metin else 0)
            else:
                onbellek[dosya] = None
        satir_sayisi = onbellek[dosya]
        if satir_sayisi is None:
            sonuc.hatalar.append(f"kanıt yok: `{dosya}` bu commit'te bulunamadı (head {sha[:12]})")
            continue
        if satir == 0:
            # 26 Ekim i5 bulgusu: satır numarası olmayan bulgu yalnız UYARI alıyordu → kapının
            # temel iddiası ("dosya:satır kanıtı") dosyanın var olmasına indirgeniyordu. Kanıt
            # kapısı fail-closed: bulgu taşıyan sorun/red/duzeltme kararında satır numarası
            # YOKSA karar reddedilir. Onay/kabul kararlarında bulgu yoktur; varsa da satır
            # numarası istenmez (onayın kanıtı bulgu değil, denetlenen alan listesidir).
            if satir_zorunlu:
                sonuc.hatalar.append(
                    f"kanıt eksik: `{dosya}` için satır numarası verilmemiş (dosya:satır zorunlu)")
            else:
                sonuc.uyarilar.append(f"`{dosya}` için satır numarası verilmemiş")
        elif satir > satir_sayisi:
            sonuc.hatalar.append(
                f"kanıt yanlış: `{dosya}:{satir}` — dosya yalnız {satir_sayisi} satır (head {sha[:12]})")
        if degisen is not None and dosya not in degisen:
            sonuc.uyarilar.append(f"`{dosya}` PR'da değişen dosyalar arasında değil (bağlam olabilir)")


# ---------------------------------------------------------------- şema + tutarlılık


def dogrula_karar(karar: dict, makine: str | None = None, *, token: str | None = None,
                  depo: str = "hakkisabah/yourkiosk", kanit: bool = True) -> Sonuc:
    sonuc = Sonuc()
    if not isinstance(karar, dict):
        sonuc.hatalar.append("karar bir JSON nesnesi olmalı")
        return sonuc

    makine = str(makine or karar.get("makine") or "i5").lower()
    if makine not in ("i5", "i3"):
        sonuc.hatalar.append(f"makine 'i5' ya da 'i3' olmalı (gelen: {makine!r})")

    karar_metni = str(karar.get("karar") or "").strip().lower()
    gecerli = KARARLAR_I3 if makine == "i3" else KARARLAR_I5
    if karar_metni not in gecerli:
        sonuc.hatalar.append(f"{makine} için karar {sorted(gecerli)} olmalı (gelen: {karar_metni!r})")

    onem = ONEM_ES.get(str(karar.get("onem") or "").strip().lower(), str(karar.get("onem") or "").lower())
    if onem not in ONEMLER:
        sonuc.hatalar.append(f"onem {sorted(ONEMLER)} olmalı (gelen: {karar.get('onem')!r})")

    ozet = str(karar.get("ozet") or "").strip()
    if len(ozet) < 20:
        sonuc.hatalar.append("ozet çok kısa (en az 20 karakter: ne bakıldı, ne bulundu)")
    if len(ozet) > 1200:
        sonuc.uyarilar.append("ozet 1200 karakterden uzun (PR yorumu okunaksız olur)")
    if any(y in ozet.casefold() for y in YER_TUTUCU):
        sonuc.hatalar.append("ozet şablon metni içeriyor (doldurulmamış)")

    bulgular = karar.get("bulgular")
    if not isinstance(bulgular, list):
        sonuc.hatalar.append("bulgular bir liste olmalı (bulgu yoksa [])")
        bulgular = []
    yuksek = 0
    for i, b in enumerate(bulgular, 1):
        if not isinstance(b, dict):
            sonuc.hatalar.append(f"bulgu #{i} nesne değil")
            continue
        dosya = dosya_normal(b.get("dosya", ""))
        if not dosya:
            sonuc.hatalar.append(f"bulgu #{i}: 'dosya' boş")
        elif any(y in dosya.casefold() for y in YER_TUTUCU):
            sonuc.hatalar.append(f"bulgu #{i}: 'dosya' şablon değeri ({dosya})")
        b_onem = ONEM_ES.get(str(b.get("onem") or "").lower(), str(b.get("onem") or "").lower())
        if b_onem not in ONEMLER:
            sonuc.hatalar.append(f"bulgu #{i}: onem {sorted(ONEMLER)} olmalı (gelen: {b.get('onem')!r})")
        if b_onem == "yuksek":
            yuksek += 1
        aciklama = str(b.get("aciklama") or "").strip()
        if len(aciklama) < 15:
            sonuc.hatalar.append(f"bulgu #{i}: 'aciklama' çok kısa (<15) — neden sömürülebilir yazılmalı")
        if any(y in aciklama.casefold() for y in YER_TUTUCU):
            sonuc.hatalar.append(f"bulgu #{i}: 'aciklama' şablon metni")
        # KABUL ÖLÇÜTÜ (yeni): bulguyu neyin KAPATACAĞI makine-okunur yazılmalı.
        # Neden: 25 Ekim'de i3'ün verdiği reçete ("kökü depo köküne al") çürük çıktı; geliştirici
        # uyguladı, aynı sınıf hata açık kaldı. Ölçüt yazılmayan düzeltme kararı, iki tur sonra
        # aynı bulguyla geri döner. Karar "onay/kabul" değilse her bulgu kapanış ölçütü taşır.
        kabul = str(b.get("kabul") or b.get("kapanis") or "").strip()
        if karar_metni in {"sorun", "red", "duzeltme"}:
            if len(kabul) < 15:
                sonuc.hatalar.append(
                    f"bulgu #{i}: 'kabul' (kapanış ölçütü) zorunlu ve ≥15 karakter — "
                    "'neyi yapınca bu bulgu KAPANIR' yazılmalı")
            elif any(y in kabul.casefold() for y in YER_TUTUCU):
                sonuc.hatalar.append(f"bulgu #{i}: 'kabul' şablon metni")

    # kapsam (denetlenen)
    ham_alanlar = karar.get("denetlenen") or []
    if not isinstance(ham_alanlar, list):
        sonuc.hatalar.append("denetlenen bir liste olmalı")
        ham_alanlar = []
    denetlenen = {alan_normal(a) for a in ham_alanlar if str(a).strip()}
    eksik = [a for a in DENETIM_ALANLARI if a not in denetlenen]
    bilinmeyen = sorted(d for d in denetlenen if d not in DENETIM_ALANLARI)
    if makine == "i3":
        if len(denetlenen & set(DENETIM_ALANLARI)) < I3_ASGARI_ALAN:
            sonuc.hatalar.append(
                f"denetlenen: i3 en az {I3_ASGARI_ALAN} alan bildirmeli "
                f"(bildirilen {len(denetlenen & set(DENETIM_ALANLARI))}: {sorted(denetlenen)})")
        for z in I3_ZORUNLU:
            if z not in denetlenen:
                sonuc.hatalar.append(f"denetlenen: i3 için zorunlu alan eksik → '{z}'")
    else:
        if eksik:
            sonuc.hatalar.append(
                "denetlenen: 12 alanın TAMAMI bildirilmeli; eksik → "
                + ", ".join(f"'{a}'" for a in eksik))
    if bilinmeyen:
        sonuc.uyarilar.append("denetlenen: tanınmayan alan adları → " + ", ".join(bilinmeyen))

    # tutarlılık
    if karar_metni in ONAY_KARARLARI:
        if yuksek:
            sonuc.hatalar.append(
                f"'yüksek' önemde {yuksek} bulgu varken '{karar_metni}' verilemez (→ sorun/duzeltme)")
        if not denetlenen:
            sonuc.hatalar.append(f"'{karar_metni}' için denetlenen alanlar zorunlu (neye bakmadan onay yok)")
    if karar_metni in {"sorun", "red", "duzeltme"} and not bulgular:
        sonuc.hatalar.append(f"'{karar_metni}' kararı en az 1 kanıtlı bulgu ister")

    # fail-closed: kararsızlık onaya dönüşemez
    if karar_metni in ONAY_KARARLARI:
        metin = (ozet + " " + str(karar.get("not") or "")).casefold()
        bulunan = [k for k in KARARSIZLIK if k in metin]
        if bulunan:
            sonuc.hatalar.append(
                "FAIL-CLOSED: özet/notta kararsızlık işareti var (" + ", ".join(bulunan)
                + ") → karar 'onay'/'kabul' olamaz; 'sorun' + 'doğrulanmalı' yazın")

    if kanit and token:
        kanit_denetle(karar, sonuc, token, depo)
    elif kanit and not token:
        # FAIL-CLOSED: "token yok" bir mazeret değil, kanıt katmanının çalışmadığı anlamına gelir.
        # Eski davranış yalnız uyarı üretip kararı geçiriyordu → sır/izin sorunu olan bir makinede
        # dosya:satır kanıtı hiç denetlenmeden "onay" yazılabiliyordu (26 Ekim i5 bulgusu).
        sonuc.hatalar.append(
            "kanıt denetimi YAPILAMADI: token okunamadı (fail-closed). "
            "Token dosyasını düzeltin (0600) ya da bilinçli olarak '--kanit-yok' kullanın")
    return sonuc


def main() -> int:
    ap = argparse.ArgumentParser(description="i5/i3 karar kapısı (yayın öncesi doğrulama)")
    ap.add_argument("karar", help="karar JSON dosyası")
    ap.add_argument("--makine", choices=["i5", "i3"], default=None, help="varsayılan: dosyadaki")
    ap.add_argument("--kanit-yok", action="store_true", help="ağ üzerinden dosya:satır kanıtı denetleme")
    ap.add_argument("--json", action="store_true", help="makine-okunabilir çıktı")
    ap.add_argument("--depo-adresi", default="hakkisabah/yourkiosk")
    ap.add_argument("--token-dosya", default=str(Path.home() / ".config/hermes-secrets/github-yourkiosk.token"))
    a = ap.parse_args()

    yol = Path(a.karar).expanduser()
    try:
        karar = json.loads(yol.read_text(encoding="utf-8-sig"))
    except OSError as hata:
        print(f"karar okunamadı: {hata}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as hata:
        print(f"GEÇERSİZ JSON: {hata.msg} (satır {hata.lineno})", file=sys.stderr)
        return 2

    token = None
    try:
        token = Path(a.token_dosya).expanduser().read_text(encoding="utf-8").strip() or None
    except OSError:
        token = None

    # 27 Ekim i5 bulgusu (düşük): `--kanit-yok` HİÇBİR operatör koruması olmadan kanıt katmanını
    # kapatıyor ve "✓ karar kapısı: geçti" yazıyordu (yaz.py'de aynı bayrak bilet+anahtar isterken).
    # Artık aynı kapı: operatör anahtarı + root sahipli TTL'li bilet yoksa kanıt denetimi KAPATILAMAZ.
    kanit = True
    if a.kanit_yok:
        try:
            import sys as _sys
            _sys.path.insert(0, str(Path(__file__).resolve().parent))
            import yaz as _yaz
            izin, ret_uzun, _ret_kisa = _yaz.operator_izi_denetle()
        except Exception as hata:  # noqa: BLE001 — kapı açılamıyorsa kanıt denetimi KAPALI kalmaz
            izin, ret_uzun = False, f"operatör kapısı yüklenemedi: {hata}"
        if not izin:
            print(f"✗ kanıt denetimi YAPILAMADI — --kanit-yok reddedildi: {ret_uzun}", file=sys.stderr)
            print("  Kanıt katmanını kapatmak operatör anahtarı (YAZ_KAPI_ATLA_ONAY=1) + TTL'li bilet "
                  "ister; ajan tek başına kapatamaz.", file=sys.stderr)
            return 1
        kanit = False

    sonuc = dogrula_karar(karar, a.makine, token=token, depo=a.depo_adresi, kanit=kanit)
    if a.json:
        print(json.dumps({"gecti": sonuc.gecti, "hatalar": sonuc.hatalar,
                          "uyarilar": sonuc.uyarilar}, ensure_ascii=False, indent=1))
    else:
        print(sonuc.rapor())
    return 0 if sonuc.gecti else 1


if __name__ == "__main__":
    raise SystemExit(main())
