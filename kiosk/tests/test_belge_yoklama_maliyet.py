"""Yoklama süresi belgesi KODLA aynı olmalı (26 Ekim i5 bulgusunun kilidi).

NEDEN: `docs/GORSEL-MIMARISI.md` §8.3 uzun süre "MQTT bağlı → 1800 sn, koptu → 60→300 sn"
diyordu; kod ise `DAMGA_KONTROL_MS_PUSH`=120 sn ve `DAMGA_KONTROL_MS_PUSH_YOK`=30 sn.
Belge 600 cihaz maliyetini ~$1/ay gösterirken gerçek tablo ~$15-60/ay'dı. Bu sınıf hata
(elle yazılmış süre/maliyet tablosu koddan kopuyor) yalnız metin düzeltmeyle kapanmaz:
aşağıdaki test değerleri KODDAN okur, belgedeki tabloyla karşılaştırır.

Kural: bir süre/maliyet tablosu belgeye elle yazılıyorsa, testi koddan türetilir.
"""

from __future__ import annotations

import re
from pathlib import Path

KIOSK = Path(__file__).resolve().parents[1]
BELGE = KIOSK.parent / "docs" / "GORSEL-MIMARISI.md"
AY = 30.44          # ortalama ay (gün)
CIHAZ = 600


def _config_sabit(ad: str) -> int:
    """`kiosk/config.py` içinden sabit değeri oku (import etmeden: Qt bağımlılığı yok)."""
    kaynak = (KIOSK / "config.py").read_text(encoding="utf-8")
    m = re.search(rf"^{ad}\s*=\s*(\d+)\s*\*\s*1000\s*$", kaynak, re.MULTILINE)
    assert m, f"{ad} config.py içinde '<sayı> * 1000' biçiminde bulunamadı"
    return int(m.group(1))


def _milyon(aralik_sn: int) -> str:
    """Aylık istek sayısı (M), belgedeki Türkçe ondalık biçimiyle: '13,15 M'."""
    return f"{CIHAZ * 86400 * AY / aralik_sn / 1_000_000:.2f}".replace(".", ",") + " M"


def test_83_tablosu_koddaki_sureleri_yazar() -> None:
    itme = _config_sabit("DAMGA_KONTROL_MS_PUSH")
    kopuk = _config_sabit("DAMGA_KONTROL_MS_PUSH_YOK")
    belge = BELGE.read_text(encoding="utf-8")

    assert f"**{itme} sn**" in belge, f"§8.3 MQTT bağlı süresi {itme} sn yazmıyor"
    assert f"**{kopuk} sn**" in belge, f"§8.3 push kapalı/kopuk süresi {kopuk} sn yazmıyor"
    assert "`DAMGA_KONTROL_MS_PUSH`" in belge and "`DAMGA_KONTROL_MS_PUSH_YOK`" in belge, (
        "§8.3 tablosu sürenin hangi sabitten geldiğini yazmıyor"
    )


def test_maliyet_tablosu_koddan_turetilen_istek_sayilarini_yazar() -> None:
    belge = BELGE.read_text(encoding="utf-8")
    for aralik in (_config_sabit("DAMGA_KONTROL_MS_PUSH_YOK"), _config_sabit("DAMGA_KONTROL_MS_PUSH"),
                   300, 1800):
        assert _milyon(aralik) in belge, (
            f"§9 maliyet tablosunda {aralik} sn için {_milyon(aralik)} yok — "
            "tablo koddan türetilmiş istek sayısıyla uyuşmuyor"
        )


def test_1800_sn_varsayilan_gibi_sunulmaz() -> None:
    """1800 sn yalnız 'elle ayarlanırsa' bağlamında geçebilir; 'bağlı/varsayılan' diyemez."""
    for satir in BELGE.read_text(encoding="utf-8").splitlines():
        if "1800" not in satir:
            continue
        kucuk = satir.lower()
        assert "varsayılan" not in kucuk or "eski" in kucuk, (
            f"1800 sn varsayılan gibi sunuluyor: {satir.strip()[:120]}"
        )
        if kucuk.lstrip().startswith("|"):
            assert "elle" in kucuk, f"1800 sn tablo satırı 'elle' ile nitelenmemiş: {satir.strip()[:120]}"
            assert "bağlı" not in kucuk, (
                f"1800 sn hâlâ 'MQTT bağlı' aralığı olarak yazılı: {satir.strip()[:120]}"
            )


def test_bugunku_varsayilan_30_sn_olarak_isaretli() -> None:
    """`TETIK_PUSH_AKTIF` varsayılanı false → sahada etkin aralık PUSH_YOK sabitidir."""
    kaynak = (KIOSK / "config.py").read_text(encoding="utf-8")
    m = re.search(r"^TETIK_PUSH_AKTIF\s*=\s*(True|False)", kaynak, re.MULTILINE)
    assert m, "TETIK_PUSH_AKTIF config.py içinde bulunamadı"
    if m.group(1) == "True":
        return  # push varsayılan açıksa 'bugünkü varsayılan' satırı gerekmez
    kopuk = _config_sabit("DAMGA_KONTROL_MS_PUSH_YOK")
    belge = BELGE.read_text(encoding="utf-8")
    assert "BUGÜNKÜ VARSAYILAN" in belge, (
        "push varsayılan kapalı ama belge 'bugünkü varsayılan' maliyet satırını işaretlemiyor"
    )
    assert f"**{kopuk} sn — BUGÜNKÜ VARSAYILAN**" in belge, (
        f"'bugünkü varsayılan' satırı {kopuk} sn değil"
    )
