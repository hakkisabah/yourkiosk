"""cron_temizle: `hermes cron list` çıktısını doğru ayrıştırıyor mu? (regresyon testi)"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cron_temizle  # noqa: E402

ORNEK = """
  7275cdd6cb4b [active]
    Name:      i3 karar
    Schedule:  every 30m
    Workdir:   /home/hakki/projeler/yourkiosk
    Script:    otomasyon-topla.sh

  aaaaaaaaaaaa [active]
    Name:      başka proje
    Schedule:  every 2h
    Workdir:   /home/baska/proje
"""


class AyristirmaTesti(unittest.TestCase):
    def test_bloklari_ayirir(self):
        with mock.patch.object(cron_temizle.subprocess, "run",
                               return_value=mock.Mock(stdout=ORNEK, returncode=0)):
            gorevler = cron_temizle.liste()
        self.assertEqual([g["id"] for g in gorevler], ["7275cdd6cb4b", "aaaaaaaaaaaa"])
        self.assertEqual(gorevler[0]["ad"], "i3 karar")
        self.assertEqual(gorevler[0]["workdir"], "/home/hakki/projeler/yourkiosk")

    def test_workdir_ile_proje_eslesir(self):
        gorev = {"id": "7275cdd6cb4b", "ad": "i3 karar", "workdir": str(cron_temizle.KOK), "script": ""}
        self.assertTrue(cron_temizle.projeye_ait(gorev))

    def test_baska_proje_eslesmez(self):
        gorev = {"id": "aaaaaaaaaaaa", "ad": "başka proje", "workdir": "/home/baska/proje", "script": ""}
        self.assertFalse(cron_temizle.projeye_ait(gorev))

    def test_ad_eslesmesi_workdir_olmasa_da(self):
        # kullanıcının yaşadığı durum: ad "i3 karar", workdir alanı okunamadı
        gorev = {"id": "7275cdd6cb4b", "ad": "i3 karar", "workdir": "", "script": ""}
        self.assertTrue(cron_temizle.projeye_ait(gorev))


if __name__ == "__main__":
    unittest.main()
