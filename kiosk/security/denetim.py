"""Güvenlik denetimi: cihazdaki gerçek durumu ölçen (Qt'siz çalışan) öz kontrol.

`python3 main.py --guvenlik-denetimi` ile çalıştırılır. Kod okumadan, ölçümle
"bu cihazda güvenlik ayarları gerçekten devrede mi?" sorusunu yanıtlar.
Her madde: (ad, durum, ayrıntı) — durum: "tamam" / "uyari" / "hata".
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import config

log = logging.getLogger("kiosk.denetim")

KOK = Path(__file__).resolve().parent.parent

VERI_DOSYALARI = (
    "LASTUPDATE_DOSYASI",
    "MATCH_DOSYASI",
    "SISTEM_VERI_DOSYASI",
    "MAKINE_DOSYASI",
)


def _qt_surumu() -> tuple[str, str]:
    try:
        from PyQt6.QtCore import PYQT_VERSION_STR, qVersion
    except ImportError as hata:
        return "hata", f"PyQt6 içe aktarılamadı: {hata}"
    surum = qVersion()
    parcalar = [int(p) for p in surum.split(".") if p.isdigit()]
    while len(parcalar) < 3:
        parcalar.append(0)
    # VNC CVE-2026-79680 düzeltmesi 6.11.3+
    if tuple(parcalar) < (6, 11, 3):
        return "uyari", f"Qt {surum} / PyQt {PYQT_VERSION_STR} (VNC CVE-2026-79680 düzeltmesi 6.11.3+)"
    return "tamam", f"Qt {surum} / PyQt {PYQT_VERSION_STR}"


def _qt_eklentileri() -> tuple[str, str]:
    from security.qt_sertlestirme import durum

    bilgi = durum(KOK)
    riskli = list(bilgi.get("riskli_eklenti", [])) + list(bilgi.get("riskli_modul", []))
    if riskli:
        ozet = ", ".join(riskli[:6]) + ("…" if len(riskli) > 6 else "")
        return "uyari", f"kaldırılmamış Qt parçası var ({len(riskli)}): {ozet}"
    return "tamam", f"riskli eklenti/kütüphane yok ({len(bilgi['eklenti_dizini'])} dizin tarandı)"


def _ag_politikasi() -> tuple[str, str]:
    from security.network import AgAyarlari, _tls_baglami

    izinli = tuple(config.ALLOWED_HOSTS)
    if not izinli:
        return "hata", "ALLOWED_HOSTS boş: hiçbir adres indirilemez (izin listesi tanımlayın)"
    ayarlar = AgAyarlari(
        izinli_hostlar=izinli,
        izinli_portlar=tuple(getattr(config, "AG_IZINLI_PORTLAR", (443,))),
        yonlendirme_izinli=bool(getattr(config, "AG_YONLENDIRME_IZINLI", False)),
    )
    baglam = _tls_baglami()
    ayrinti = (
        f"izinli host: {', '.join(izinli)} · port: {ayarlar.izinli_portlar} · "
        f"yönlendirme: {'açık' if ayarlar.yonlendirme_izinli else 'yalnızca aynı host'} · "
        f"TLS min: {baglam.minimum_version.name} · sertifika doğrulama: "
        f"{'açık' if baglam.verify_mode.name == 'CERT_REQUIRED' else 'KAPALI'}"
    )
    return "tamam", ayrinti


def _vekiller() -> tuple[str, str]:
    bulunan = [a for a in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy") if os.environ.get(a)]
    if bulunan:
        return "uyari", f"ortamda vekil sunucu tanımlı: {', '.join(bulunan)} — uygulama bunları YOK SAYAR"
    return "tamam", "ortam vekil sunucusu yok"


def _veri_dosyalari() -> tuple[str, str]:
    from security.veri_dogrulama import dosya_izni_uyari

    satirlar: list[str] = []
    durum = "tamam"
    for ad in VERI_DOSYALARI:
        dosya = getattr(config, ad, None)
        if not dosya:
            continue
        yol = KOK / dosya
        if yol.is_symlink():
            satirlar.append(f"{dosya}: SEMBOLİK BAĞ (reddedilir)")
            durum = "hata"
            continue
        if not yol.is_file():
            satirlar.append(f"{dosya}: yok")
            durum = "uyari" if durum == "tamam" else durum
            continue
        boyut = yol.stat().st_size
        uyari = dosya_izni_uyari(yol)
        if boyut > config.MAX_JSON_BAYT:
            satirlar.append(f"{dosya}: {boyut} bayt (sınır {config.MAX_JSON_BAYT})")
            durum = "hata"
        elif uyari:
            satirlar.append(f"{dosya}: {boyut} bayt — {uyari}")
            durum = "uyari" if durum == "tamam" else durum
        else:
            satirlar.append(f"{dosya}: {boyut} bayt, izinler uygun")
    return durum, " · ".join(satirlar) if satirlar else "tanımlı veri dosyası yok"


def _kaynak() -> tuple[str, str]:
    kaynak = (getattr(config, "KAYNAK", "dosya") or "dosya").lower()
    if kaynak == "https":
        adres = getattr(config, "DOSYA_ADRESI", "")
        if not adres:
            return "hata", "KAYNAK=https ama DOSYA_ADRESI tanımlı değil"
        return "tamam", f"kaynak: https ({adres})"
    return "uyari", "kaynak: yerel dosya (üretimde https + DOSYA_ADRESI önerilir)"


def _sinirlar() -> tuple[str, str]:
    return "tamam", (
        f"JSON: ≤{config.MAX_JSON_BAYT} bayt, derinlik ≤{config.MAX_JSON_DERINLIK}, "
        f"düğüm ≤{config.MAX_JSON_DUGUM} · metin ≤{config.MAX_METIN_UZUNLUK} · "
        f"kayıt ≤{config.MAX_GOSTERILEN_ECZANE} · yayın ≤{config.MAX_AKTIF_YAYIN} · "
        f"yayın süresi {config.YAYIN_SURE_EN_AZ_S}-{config.YAYIN_SURE_EN_COK_S} sn"
    )


def _gunluk() -> tuple[str, str]:
    from logging_setup import gunluk_kur

    dosya = KOK / config.LOG_DOSYASI
    try:
        gunluk_kur(dosya)
        log.info("güvenlik denetimi: günlük yazma sınaması")
        return "tamam", f"günlük yazılabiliyor: {dosya}"
    except OSError as hata:
        return "hata", f"günlük yazılamıyor: {hata}"


def _ozellikler() -> tuple[str, str]:
    import ayarlar

    ozet = ayarlar.ozet()
    acik = [ad for ad, deger in ozet["ozellikler"].items() if deger]
    kapali = [ad for ad, deger in ozet["ozellikler"].items() if not deger]
    ayrinti = f"açık: {', '.join(acik) or '-'}"
    if kapali:
        ayrinti += f" · KAPALI: {', '.join(kapali)}"
    return "tamam", f"{ayrinti} (ayar dosyası: {ozet['dosya']})"


def denetim_raporu() -> list[tuple[str, str, str]]:
    """[(madde, durum, ayrıntı)] döner."""
    return [
        ("Qt sürümü", *_qt_surumu()),
        ("Qt eklentileri (CVE sınıfı)", *_qt_eklentileri()),
        ("Ağ politikası (https/izin listesi/TLS)", *_ag_politikasi()),
        ("Ortam vekil sunucuları", *_vekiller()),
        ("Veri kaynağı", *_kaynak()),
        ("Genel kullanım (özellikler)", *_ozellikler()),
        ("Veri dosyaları", *_veri_dosyalari()),
        ("Sınırlar (DoS)", *_sinirlar()),
        ("Günlük", *_gunluk()),
    ]


def rapor_metni(rapor: list[tuple[str, str, str]] | None = None) -> str:
    rapor = rapor if rapor is not None else denetim_raporu()
    imlec = {"tamam": "[ OK ]", "uyari": "[UYARI]", "hata": "[HATA]"}
    satirlar = ["", "=============== GÜVENLİK DENETİMİ ==============="]
    for ad, durum, ayrinti in rapor:
        satirlar.append(f"{imlec.get(durum, '[ ? ]')} {ad}")
        satirlar.append(f"          {ayrinti}")
    hata = sum(1 for _a, d, _s in rapor if d == "hata")
    uyari = sum(1 for _a, d, _s in rapor if d == "uyari")
    satirlar.append(f"================= {len(rapor) - hata - uyari} tamam · {uyari} uyarı · {hata} hata =================")
    return "\n".join(satirlar)


def denetim_kodu(rapor: list[tuple[str, str, str]] | None = None) -> int:
    rapor = rapor if rapor is not None else denetim_raporu()
    return 1 if any(d == "hata" for _a, d, _s in rapor) else 0
