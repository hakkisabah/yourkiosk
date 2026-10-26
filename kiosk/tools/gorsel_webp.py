#!/usr/bin/env python3
"""Görselleri WebP'ye çevir (içerik adlı) — panelden yükleme gelene kadar toplu dönüştürme.

NEDEN: ölçüm (gerçek yayın görseli) 2473 KB PNG → 211 KB WebP q82; 1280 px'te 130 KB.
S3 statik dosyayı sıkıştırmaz, CloudFront yalnız metin türlerini sıkıştırır → tek yol dönüştürme.

Kullanım:
    # yalnız ölçüm (dosya yazmaz)
    .venv/bin/python tools/gorsel_webp.py a.png b.jpg
    # dönüştür + çıktı klasörüne yaz
    .venv/bin/python tools/gorsel_webp.py a.png b.jpg --cikti /tmp/webp
    # S3'e yükle (immutable önbellek) + adresleri yazdır
    .venv/bin/python tools/gorsel_webp.py a.png --s3 kova=kiosk/yayin-gorselleri/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

#: Betik `python3 tools/gorsel_webp.py` ile çalıştırıldığında sys.path[0] = tools/ olur;
#: `security/` ve `core/` paketleri kiosk kökünde olduğu için kökü başa ekliyoruz.
_KOK = Path(__file__).resolve().parent.parent
if str(_KOK) not in sys.path:
    sys.path.insert(0, str(_KOK))

MAX_KENAR = 1920
KALITE = 82

# PyQt6 zorunlu değil: varsa hızlı ve bağımlılıksız dönüştürme yapar (kiosk venv'inde var).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _qt() -> tuple:
    from PyQt6.QtGui import QGuiApplication, QImage  # noqa: PLC0415

    uygulama = QGuiApplication.instance() or QGuiApplication([])
    return QImage, uygulama


def donustur(yol: Path, max_kenar: int = MAX_KENAR, kalite: int = KALITE) -> tuple[bytes, dict]:
    QImage, _ = _qt()
    resim = QImage(str(yol))
    if resim.isNull():
        raise SystemExit(f"✗ açılamadı: {yol}")
    giris = {"genislik": resim.width(), "yukseklik": resim.height(), "bayt": yol.stat().st_size}
    en_buyuk = max(resim.width(), resim.height())
    if en_buyuk > max_kenar:
        oran = max_kenar / en_buyuk
        resim = resim.scaled(
            max(1, round(resim.width() * oran)), max(1, round(resim.height() * oran)),
            aspectRatioMode=1,  # KeepAspectRatio
            transformMode=1,    # SmoothTransformation
        )
    gecici = yol.with_suffix(".webp.tmp")
    if not resim.save(str(gecici), "WEBP", kalite):
        raise SystemExit(f"✗ WebP yazılamadı: {yol}")
    govde = gecici.read_bytes()
    gecici.unlink(missing_ok=True)
    return govde, {**giris, "cikti_genislik": resim.width(), "cikti_yukseklik": resim.height(), "cikti_bayt": len(govde)}


YAYIN_ALANLARI = ("contentUrl", "contentURL", "url", "gorsel", "görsel")


def adresleri_bul(belge: object) -> list[tuple[str, str]]:
    """`lastSystemData.json` içindeki yayın adreslerini `(yol, adres)` olarak döner.

    Yol, belge içindeki konumu gösterir (`Yayinlar.12.contentUrl`) — geri yazarken aynı yer
    kullanılır, böylece belge yapısı korunur.
    """
    bulunan: list[tuple[str, str]] = []
    yayinlar = (belge or {}).get("Yayinlar") if isinstance(belge, dict) else None
    if not isinstance(yayinlar, dict):
        return bulunan
    for anahtar, kayit in yayinlar.items():
        if not isinstance(kayit, dict):
            continue
        for alan in YAYIN_ALANLARI:
            deger = kayit.get(alan)
            if isinstance(deger, str) and deger.strip():
                bulunan.append((f"Yayinlar.{anahtar}.{alan}", deger.strip()))
    return bulunan


def adresi_degistir(belge: dict, yol: str, yeni: str) -> bool:
    """`Yayinlar.<anahtar>.<alan>` yolundaki adresi değiştirir (bulunamazsa False)."""
    parcalar = yol.split(".")
    hedef: object = belge
    for parca in parcalar[:-1]:
        if not isinstance(hedef, dict) or parca not in hedef:
            return False
        hedef = hedef[parca]
    if not isinstance(hedef, dict) or parcalar[-1] not in hedef:
        return False
    hedef[parcalar[-1]] = yeni
    return True


def yeni_adres(taban: str, anahtar: str) -> str:
    """Yeni görsel adresi: `<taban>/<sha16>.webp` (taban sonundaki `/` normalize edilir)."""
    return f"{str(taban or '').rstrip('/')}/{anahtar}.webp"


def _yerel_dosya(adres: str, klasorler: list[Path]) -> Path | None:
    """Adresin dosya adını verilen klasörlerde arar (sorgu dizesi/parça atılır)."""
    from urllib.parse import unquote, urlparse

    ad = Path(unquote(urlparse(adres).path)).name
    if not ad:
        return None
    for klasor in klasorler:
        aday = klasor / ad
        if aday.is_file():
            return aday
    return None


def adres_cihaz_kapisindan_gecer(adres: str, *,
                                 baytlar: bytes | None = None,
                                 onbellek: dict[str, tuple[bool, str]] | None = None) -> tuple[bool, str]:
    """Üretilen adresi cihazın GÖRSEL KAPISINDAN geçirir (i5 bulgusu 7).

    NEDEN: `--veri --yaz` adresi veri dosyasına yazıyordu ama cihazın `security/network`
    (yalnız https + 443 + herkese açık host) ve `security/image_policy` (biçim/bayt/piksel)
    denetimlerinden geçirmiyordu. `--url-taban http://…` verildiğinde veri dosyası cihazda
    HER görseli reddettiren bir adresle yazılabiliyordu (sessiz boş ekran).
    """
    if onbellek is not None:
        bilinen = onbellek.get(adres)
        if bilinen is not None:
            return bilinen

    from urllib.parse import urlparse

    from security.image_policy import dogrula as gorsel_dogrula
    from security.network import AgAyarlari, AgHatasi, gorsel_icin_ayarlar

    sonuc: tuple[bool, str]
    try:
        host = (urlparse(adres).hostname or "").rstrip(".").lower()
        ayarlar = AgAyarlari(izinli_hostlar=(host,) if host else ())
        gorsel_icin_ayarlar(ayarlar, adres)  # https / port / kullanıcı bilgisi / herkese açık host
        sonuc = (True, "")
    except AgHatasi as hata:
        sonuc = (False, str(hata))
    except Exception as hata:  # noqa: BLE001 - politika dışı adres yazılmasın
        sonuc = (False, f"adres doğrulanamadı: {hata}")

    if sonuc[0] and baytlar is not None:
        karar = gorsel_dogrula(baytlar, icerik_turu="image/webp")
        if not karar.kabul:
            sonuc = (False, f"görsel politikası reddetti: {karar.sebep}")

    if onbellek is not None:
        onbellek[adres] = sonuc
    return sonuc


def gecici_webp_yaz(govde: bytes) -> Path:
    """0600 izinli, TAHMİN EDİLEMEZ geçici dosya (i5 bulgusu 6).

    Önceki hâl `/tmp/<sha>.webp` sabit yolunu kullanıyordu: `/tmp`'ye sembolik bağ kurabilen
    yerel bir kullanıcı, `aws s3 cp` çağrısını başka bir dosyaya yönlendirebiliyordu.
    """
    fd, ad = tempfile.mkstemp(prefix="yourkiosk-gorsel-", suffix=".webp")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as dosya:
            dosya.write(govde)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        Path(ad).unlink(missing_ok=True)
        raise
    return Path(ad)


def veri_dosyasini_optimize(
    veri_yolu: Path,
    klasorler: list[Path],
    url_taban: str,
    *,
    yaz: bool = False,
    cikti: Path | None = None,
    max_kenar: int = MAX_KENAR,
    kalite: int = KALITE,
) -> dict:
    """`lastSystemData.json` içindeki yayın görsellerini WebP'ye çevirip adresleri günceller.

    `yaz=False` (varsayılan) KURU çalışmadır: hiçbir dosya değişmez, yalnız plan basılır.
    Dönüş: {"degisen": [...], "bulunamayan": [...], "kazanc": {...}}
    """
    from security.veri_dogrulama import atomik_yaz, json_yukle

    belge = json_yukle(veri_yolu.read_bytes(), etiket=veri_yolu.name, en_buyuk_bayt=64 * 1024 * 1024,
                       en_buyuk_derinlik=64, en_buyuk_dugum=5_000_000)
    if not isinstance(belge, dict):
        raise SystemExit(f"✗ {veri_yolu}: sözlük değil")
    sonuc: dict = {"degisen": [], "bulunamayan": [], "gecersiz": [],
                   "kazanc": {"giris": 0, "cikis": 0}, "yazildi": False,
                   "cikti_klasoru": None}
    # VARSAYILAN ÇIKTI (i5 bulgusu 5): `--yaz` üretilen WebP baytlarını bir klasöre YAZMALI.
    # Aksi hâlde veri dosyasındaki yeni adresler S3'te HİÇ var olmayan nesnelere işaret eder;
    # cihaz 404 alır ve yayın sessizce boş kalır. `--cikti` verilmezse veri dosyasının yanına yaz.
    if cikti is None and yaz:
        cikti = veri_yolu.parent / "yayin-gorselleri"
    if cikti is not None:
        sonuc["cikti_klasoru"] = str(cikti)
    yeni_belge: dict = belge
    adres_onbellek: dict[str, tuple[bool, str]] = {}
    for yol, adres in adresleri_bul(belge):
        yerel = _yerel_dosya(adres, klasorler)
        if yerel is None:
            sonuc["bulunamayan"].append((yol, adres))
            continue
        govde, bilgi = donustur(yerel, max_kenar, kalite)
        anahtar = hashlib.sha256(govde).hexdigest()[:16]
        yeni = yeni_adres(url_taban, anahtar)
        # CİHAZ KAPISI (i5 bulgusu 7): üretilen adres + baytlar cihazın görsel politikasından
        # geçmiyorsa veri dosyasına YAZILMAZ (cihazda her görsel sessizce reddedilirdi).
        uygun, neden = adres_cihaz_kapisindan_gecer(yeni, baytlar=govde, onbellek=adres_onbellek)
        if not uygun:
            sonuc["gecersiz"].append((yol, yeni, neden))
            continue
        if cikti:
            cikti.mkdir(parents=True, exist_ok=True)
            (cikti / f"{anahtar}.webp").write_bytes(govde)
        sonuc["degisen"].append((yol, adres, yeni, bilgi["bayt"], bilgi["cikti_bayt"]))
        sonuc["kazanc"]["giris"] += bilgi["bayt"]
        sonuc["kazanc"]["cikis"] += bilgi["cikti_bayt"]
        if yaz:
            adresi_degistir(yeni_belge, yol, yeni)
    if yaz and sonuc["degisen"]:
        yedek = veri_yolu.with_suffix(veri_yolu.suffix + ".bak")
        yedek.write_bytes(veri_yolu.read_bytes())
        atomik_yaz(veri_yolu, (json.dumps(yeni_belge, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
        sonuc["yazildi"] = True
        sonuc["yedek"] = str(yedek)
    return sonuc


def main() -> int:
    a = argparse.ArgumentParser(description="görselleri içerik adlı WebP'ye çevir")
    a.add_argument("dosyalar", nargs="*", type=Path)
    a.add_argument("--cikti", type=Path, default=None, help="WebP dosyalarını bu klasöre yaz")
    a.add_argument("--max-kenar", type=int, default=MAX_KENAR)
    a.add_argument("--kalite", type=int, default=KALITE)
    a.add_argument("--s3", default="", help="kova=önek (ör. yourkiosk-veri=kiosk/yayin-gorselleri/)")
    # --- veri dosyası modu: yayın görsellerini topluca optimize edip adresleri günceller ---
    a.add_argument("--veri", type=Path, default=None, help="lastSystemData.json")
    a.add_argument("--klasor", action="append", type=Path, default=[], help="yerel görsellerin aranacağı klasör (tekrarlanabilir)")
    a.add_argument("--url-taban", default="", help="yeni adreslerin tabanı (ör. https://d....cloudfront.net/kiosk/yayin-gorselleri)")
    a.add_argument("--yaz", action="store_true", help="veri dosyasını gerçekten güncelle (varsayılan: kuru çalışma)")
    secim = a.parse_args()

    if secim.veri:
        if not secim.url_taban:
            print("✗ --veri ile --url-taban zorunlu (yeni adreslerin tabanı)", file=sys.stderr)
            return 2
        if not secim.veri.is_file():
            print(f"✗ veri dosyası yok: {secim.veri}", file=sys.stderr)
            return 2
        klasorler = secim.klasor or [secim.veri.parent, secim.veri.parent / "yayin-gorselleri"]
        sonuc = veri_dosyasini_optimize(
            secim.veri, klasorler, secim.url_taban, yaz=secim.yaz, cikti=secim.cikti,
            max_kenar=secim.max_kenar, kalite=secim.kalite,
        )
        print(f"{'yol':<34}{'eski':>8}{'yeni':>7}  adres")
        for yol, eski, yeni, gb, cb in sonuc["degisen"]:
            print(f"{yol:<34}{gb/1024:>7.0f}K{cb/1024:>6.0f}K  {eski}\n{'':<34}{'':>7}{'':>7}  → {yeni}")
        for yol, adres in sonuc["bulunamayan"]:
            print(f"! yerel dosya bulunamadı: {yol} → {adres}")
        for yol, adres, neden in sonuc["gecersiz"]:
            print(f"✗ CİHAZ KAPISI reddetti: {yol} → {adres} ({neden})", file=sys.stderr)
        k = sonuc["kazanc"]
        if k["giris"]:
            print(f"\ntoplam: {k['giris']/1024:.0f} KB → {k['cikis']/1024:.0f} KB "
                  f"(%{100 - k['cikis']/max(1,k['giris'])*100:.0f} küçüldü)")
        if sonuc["yazildi"]:
            print(f"✓ {secim.veri} güncellendi (yedek: {sonuc['yedek']})")
            if sonuc.get("cikti_klasoru"):
                print(f"  WebP dosyaları: {sonuc['cikti_klasoru']}")
                print("  Sıradaki adım: ÖNCE bu klasörü S3'e yükleyin "
                      f"(cd deploy && ./gorseller-yukle.sh --kova <kova> {sonuc['cikti_klasoru']}/*.webp),")
                print("  SONRA veri dosyasını yükleyip `lastupdate.json` damgasını tazeleyin.")
            else:
                print("  Sıradaki adım: dosyayı S3'e yükleyin + `lastupdate.json` damgasını tazeleyin.")
        else:
            print("KURU çalışma — hiçbir dosya değişmedi (yazmak için --yaz).")
        # CİHAZ KAPISINDAN GEÇMEYEN ADRES VARSA: hiçbir şey yazılmadı ve çıkış kodu != 0
        if sonuc["gecersiz"]:
            print(f"✗ {len(sonuc['gecersiz'])} adres cihazın görsel politikasından geçmedi — "
                  "veri dosyası DEĞİŞTİRİLMEDİ (--url-taban https ve herkese açık host olmalı).",
                  file=sys.stderr)
            return 3
        return 0 if sonuc["degisen"] else 1

    if not secim.dosyalar:
        print("✗ en az bir dosya ya da --veri verin", file=sys.stderr)
        return 2

    toplam_giris = toplam_cikti = 0
    print(f"{'dosya':<28}{'giriş':>10}{'çıkış':>9}{'kazanç':>9}  {'boyut':>12}  anahtar")
    for yol in secim.dosyalar:
        if not yol.is_file():
            print(f"✗ yok: {yol}")
            continue
        govde, bilgi = donustur(yol, secim.max_kenar, secim.kalite)
        anahtar = hashlib.sha256(govde).hexdigest()[:16]
        kazanc = 100 - bilgi["cikti_bayt"] / max(1, bilgi["bayt"]) * 100
        toplam_giris += bilgi["bayt"]
        toplam_cikti += bilgi["cikti_bayt"]
        print(
            f"{yol.name:<28}{bilgi['bayt']/1024:>9.0f}K{bilgi['cikti_bayt']/1024:>8.0f}K"
            f"{kazanc:>8.0f}%  {bilgi['cikti_genislik']}×{bilgi['cikti_yukseklik']:<8}  {anahtar}.webp"
        )
        if secim.cikti:
            secim.cikti.mkdir(parents=True, exist_ok=True)
            (secim.cikti / f"{anahtar}.webp").write_bytes(govde)

    if toplam_giris:
        print(
            f"\ntoplam: {toplam_giris/1024:.0f} KB → {toplam_cikti/1024:.0f} KB "
            f"(%{100 - toplam_cikti/max(1,toplam_giris)*100:.0f} küçüldü)"
        )

    if secim.s3:
        if "=" not in secim.s3:
            print("✗ --s3 biçimi: kova=önek", file=sys.stderr)
            return 2
        kova, onek = secim.s3.split("=", 1)
        onek = onek.strip("/")
        for yol in secim.dosyalar:
            if not yol.is_file():
                continue
            govde, _ = donustur(yol, secim.max_kenar, secim.kalite)
            anahtar = hashlib.sha256(govde).hexdigest()[:16]
            hedef = f"s3://{kova}/{onek}/{anahtar}.webp"
            gecici = gecici_webp_yaz(govde)
            try:
                kod = subprocess.run(
                    ["aws", "s3", "cp", str(gecici), hedef,
                     "--cache-control", "public,max-age=31536000,immutable",
                     "--content-type", "image/webp", "--only-show-errors"],
                    capture_output=True, text=True,
                )
            finally:
                gecici.unlink(missing_ok=True)
            if kod.returncode != 0:
                print(f"✗ yüklenemedi: {hedef} — {kod.stderr.strip()[:120]}", file=sys.stderr)
            else:
                print(f"✓ yüklendi: {hedef}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
