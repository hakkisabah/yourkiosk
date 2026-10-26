"""hermes_komutu / butce_hesapla — nöbetçi oturumunun komut satırı sözleşmesi.

İki hata sınıfını makineyle kilitler:
1. **Tur tavanı ↔ duvar saati tutarsızlığı** (25 Ekim): 120 tur yazıp 9,5 sn/tur bütçe vermek
   incelemeyi yarıda kesiyordu. Bütçe darsa tavan KISILIR ve bu görünür olur.
2. **Ayrı profil** (26 Ekim i5 mimarisi): nöbetçi Open WebUI ile aynı gateway'i paylaşırsa aynı
   CPU/kota/oturum tavanını yer. `NOBETCI_PROFIL` verilince komut `hermes -p <ad> chat …` olmalı.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nobetci  # noqa: E402


class ButceTesti(unittest.TestCase):
    def test_varsayilan_zaman_asimi_tavana_yeter(self):
        b = nobetci.butce_hesapla(nobetci.VARSAYILAN_ZAMAN_ASIMI)
        self.assertTrue(b["yeterli"])
        self.assertEqual(b["tur"], nobetci.OTURUM_TUR_TAVANI)
        self.assertGreaterEqual(b["tur_basi_sn"], nobetci.EN_AZ_TUR_SURESI_S)

    def test_dar_butcede_tavan_kisilir_ve_gorunur(self):
        b = nobetci.butce_hesapla(600)          # 540 sn / 120 tur = 4,5 sn → tavan kısılmalı
        self.assertLess(b["tur"], nobetci.OTURUM_TUR_TAVANI)
        self.assertFalse(b["yeterli"])
        self.assertGreaterEqual(b["tur_basi_sn"], nobetci.EN_AZ_TUR_SURESI_S)

    def test_duvar_saati_asilmaz(self):
        for zaman in (300, 900, 1860, 7200):
            b = nobetci.butce_hesapla(zaman)
            self.assertLessEqual(b["butce"] + nobetci.KAPANIS_PAYI_S, max(zaman, 180))
            self.assertLessEqual(b["tur"] * b["tur_basi_sn"], b["butce"])


class ProfilTesti(unittest.TestCase):
    def setUp(self):
        self.eski = nobetci.NOBETCI_PROFIL

    def tearDown(self):
        nobetci.NOBETCI_PROFIL = self.eski

    def test_profil_yoksa_komut_degismez(self):
        nobetci.NOBETCI_PROFIL = ""
        komut = nobetci.hermes_komutu(Path("/depo"), Path("/gorev.md"), 1860)
        self.assertEqual(komut[:2], ["hermes", "chat"])

    def test_profil_varsa_p_argumani_oneklenir(self):
        nobetci.NOBETCI_PROFIL = "guvenlik"
        komut = nobetci.hermes_komutu(Path("/depo"), Path("/gorev.md"), 1860)
        self.assertEqual(komut[:4], ["hermes", "-p", "guvenlik", "chat"])
        self.assertIn("--oneshot", komut)
        # profil, tur tavanını ya da bütçeyi DEĞİŞTİRMEMELİ
        self.assertEqual(komut[komut.index("--max-turns") + 1], str(nobetci.OTURUM_TUR_TAVANI))

    def test_ortam_degiskeni_okunur(self):
        import importlib
        import os
        eski = os.environ.get("NOBETCI_PROFIL")
        os.environ["NOBETCI_PROFIL"] = "guvenlik"
        try:
            yeni = importlib.reload(nobetci)
            self.assertEqual(yeni.NOBETCI_PROFIL, "guvenlik")
        finally:
            if eski is None:
                os.environ.pop("NOBETCI_PROFIL", None)
            else:
                os.environ["NOBETCI_PROFIL"] = eski
            importlib.reload(nobetci)
            nobetci.NOBETCI_PROFIL = self.eski


if __name__ == "__main__":
    unittest.main(verbosity=2)
