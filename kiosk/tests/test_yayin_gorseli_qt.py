"""Qt yayın görseli: cihazın DAR izin listesi yayınları düşürmemeli.

GERÇEK HATA (kullanıcı): tarayıcı kiosk yayınları gösteriyor, **Qt kiosk göstermiyordu**.
Neden: cihazın `ayarlar.json` içindeki `ag.izinli_hostlar` config varsayılanlarını EZİYOR; yalnız
veri kaynağı (CloudFront) kalmıştı. Qt `dogrula_url` ile `hakkisabah.com`'u reddediyor, görsel
yüklenemeyince `show_next_broadcast()` hepsini atlayıp modu kapatıyordu (ekranda hiç yayın yok).
Tarayıcı tarafında bu istisna (`gorsel_icin_ayarlar`) zaten vardı; Qt'de yoktu.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication  # noqa: E402

import config  # noqa: E402
from security.network import AgAyarlari, AgHatasi, gorsel_icin_ayarlar, indir  # noqa: E402
from security.safe_image import piksel_yukle  # noqa: E402

UYGULAMA = QApplication.instance() or QApplication([])

YAYIN_URL = "https://hakkisabah.com/api/havuzlu-bahce.png"


def _dar_ayarlar() -> AgAyarlari:
    """Cihazdaki durum: izin listesinde YALNIZ veri kaynağı var."""
    return AgAyarlari(
        izinli_hostlar=("d2dnrvsx5eevod.cloudfront.net",),
        en_buyuk_bayt=config.MAX_GORSEL_BAYT,
        izinli_portlar=(443,),
    )


class YayinGorseliTesti(unittest.TestCase):
    def test_dar_liste_yayin_hostunu_reddeder(self):
        """Kök neden: dar liste + istisna yok → görsel reddedilir (Qt yayını atlar)."""
        with self.assertRaises(AgHatasi):
            _dar_ayarlar().dogrula_url(YAYIN_URL)

    def test_istisna_herkese_acik_hostu_kabul_eder(self):
        genis = gorsel_icin_ayarlar(_dar_ayarlar(), YAYIN_URL)
        self.assertIn("hakkisabah.com", genis.izinli_hostlar)
        self.assertEqual(genis.dogrula_url(YAYIN_URL).hostname, "hakkisabah.com")

    def test_loopback_istisnadan_gecmez(self):
        with self.assertRaises(AgHatasi):
            gorsel_icin_ayarlar(_dar_ayarlar(), "https://127.0.0.1/x.png")

    def test_gercek_gorsel_indirilir_ve_piksele_donusur(self):
        """Ağ varsa: gerçek yayın görseli indirilip QPixmap'e dönüşmeli (Qt yolu)."""
        ayarlar = gorsel_icin_ayarlar(_dar_ayarlar(), YAYIN_URL)
        try:
            baytlar, tur = indir(YAYIN_URL, ayarlar)
        except AgHatasi as hata:
            self.skipTest(f"ağ yok / görsel erişilemedi: {hata}")
        self.assertGreater(len(baytlar), 1000)
        pixmap, karar = piksel_yukle(
            baytlar,
            en_buyuk_bayt=config.MAX_GORSEL_BAYT,
            en_buyuk_piksel=config.MAX_GORSEL_PIKSEL,
            icerik_turu=tur,
        )
        self.assertIsNotNone(pixmap, f"görsel reddedildi: {karar.sebep}")
        self.assertFalse(pixmap.isNull())


if __name__ == "__main__":
    unittest.main()
