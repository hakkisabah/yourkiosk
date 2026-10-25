"""Belgelerdeki yoklama süreleri KODDAN türetilmeli (i5 "ifade doğruluğu" sınıfı).

NEDEN: `DAMGA_KONTROL_MS` bir zamanlar 20 sn'ydi; 30/120 sn'ye çekildikten sonra README,
NODET-DEGISIKLIGI.md ve KOMUTLAR.md "varsayılan 20 sn" demeye devam etti. Kullanıcı "bildirdim
ama değişmedi" beklentisini bu yanlış metinden kuruyor. Bu test, sayının belgede sabit
yazılmasını değil, YANLIŞ sabitin belgede kalmamasını ve doğru sabit adlarının geçmesini ister.
"""

from pathlib import Path

import config

KIOSK = Path(__file__).resolve().parents[1]


def _oku(ad: str) -> str:
    return (KIOSK / ad).read_text(encoding="utf-8")


def test_damga_araligi_iki_degerli_kalir():
    """Sabitler: push bağlı 120 sn, kopuk 30 sn (etkin aralık bağlantıya göre seçilir)."""
    assert config.DAMGA_KONTROL_MS_PUSH == 120 * 1000
    assert config.DAMGA_KONTROL_MS_PUSH_YOK == 30 * 1000


def test_belgelerde_bayat_20_sn_iddiasi_yok():
    """`DAMGA_KONTROL_MS` için "varsayılan 20 sn" ifadesi hiçbir belgede kalmamalı."""
    for ad in ("README.md", "NODET-DEGISIKLIGI.md", "KOMUTLAR.md"):
        metin = _oku(ad)
        assert "DAMGA_KONTROL_MS`, 20 sn" not in metin, ad
        assert "DAMGA_KONTROL_MS` (varsayılan 20 sn)" not in metin, ad
        assert "DAMGA_KONTROL_MS` (varsayılan **20 sn**)" not in metin, ad
        assert "DAMGA_KONTROL_MS` (≈20 sn)" not in metin, ad


def test_damga_yoklamasi_anlatilan_belgeler_iki_degeri_de_yazar():
    """Süre yazılan belgeler iki aralığı (120/30) birlikte anlatmalı — tek sayı yanıltıcı."""
    for ad in ("README.md", "NODET-DEGISIKLIGI.md", "KOMUTLAR.md"):
        metin = _oku(ad)
        if "DAMGA_KONTROL_MS" not in metin:
            continue
        assert "120 sn" in metin, ad
        assert "30 sn" in metin, ad
