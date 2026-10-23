"""Görsel ağ politikası: yayın görselleri izin listesi dışındaki HERKESE AÇIK hostlardan geleblir.

NEDEN: yayın görselleri panelde serbest adreslenir (ör. https://hakkisabah.com/api/x.png).
600 cihazda her görsel alan adını veri izin listesine eklemek sürdürülemez. Bu yüzden:
  • veri dosyaları → sıkı izin listesi (değişmedi),
  • görseller → herkese açık https host kabul, özel/loopback/ayrılmış IP RED (SSRF).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from security.network import AgAyarlari, AgHatasi, gorsel_icin_ayarlar  # noqa: E402


class GorselPolitikaTesti(unittest.TestCase):
    def test_izin_listesindeki_host_korunur(self):
        a = AgAyarlari(izinli_hostlar=("ornek.com",))
        yeni = gorsel_icin_ayarlar(a, "https://hakkisabah.com/api/x.png")
        self.assertIn("ornek.com", yeni.izinli_hostlar)
        self.assertIn("hakkisabah.com", yeni.izinli_hostlar)

    def test_loopback_reddedilir(self):
        with self.assertRaises(AgHatasi):
            gorsel_icin_ayarlar(AgAyarlari(), "https://127.0.0.1/x.png")

    def test_localhost_adi_reddedilir(self):
        with self.assertRaises(AgHatasi):
            gorsel_icin_ayarlar(AgAyarlari(), "https://localhost/x.png")

    def test_ozel_ag_reddedilir(self):
        for adres in ("https://10.0.0.5/x.png", "https://192.168.1.20/x.png", "https://169.254.169.254/latest"):
            with self.assertRaises(AgHatasi, msg=adres):
                gorsel_icin_ayarlar(AgAyarlari(), adres)

    def test_http_reddedilir(self):
        # https zorunlu: doğrulama şeması ayrıca kontrol edilir
        with self.assertRaises(AgHatasi):
            gorsel_icin_ayarlar(AgAyarlari(), "http://hakkisabah.com/x.png")


if __name__ == "__main__":
    unittest.main()
