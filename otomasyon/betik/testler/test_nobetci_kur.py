"""nobetci-kur.sh — systemd unit üretimi (profil ayrımı + düşük öncelik).

26 Ekim i5 mimarisi: nöbetçi kendi profiliyle (`hermes -p guvenlik`) ve düşük CPU önceliğiyle
çalışmalı ki Open WebUI yükü PR incelemesini aç bırakmasın. Bu sözleşme unit dosyasında görünür
olmak zorunda — yoksa "ayırdım" sanılır ama aynı gateway'de çalışmaya devam eder.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

BETIK = Path(__file__).resolve().parents[2] / "nobetci-kur.sh"


def unit_uret(*argumanlar: str, home: str) -> str:
    ortam = {**os.environ, "HOME": home}
    s = subprocess.run(["bash", str(BETIK), "i5", "--kuru", *argumanlar],
                       capture_output=True, text=True, timeout=60, env=ortam)
    assert s.returncode == 0, s.stderr
    return s.stdout


class UnitTesti(unittest.TestCase):
    def setUp(self):
        self.dizin = tempfile.TemporaryDirectory()
        self.home = self.dizin.name

    def tearDown(self):
        self.dizin.cleanup()

    def test_profilsizken_ayri_profil_yazilmaz(self):
        metin = unit_uret(home=self.home)
        self.assertNotIn("NOBETCI_PROFIL=", metin)
        self.assertNotIn("--profil", metin)
        self.assertIn("--rol i5", metin)

    def test_profil_hem_ortam_hem_arguman_olarak_yazilir(self):
        metin = unit_uret("--profil", "guvenlik", home=self.home)
        self.assertIn("Environment=NOBETCI_PROFIL=guvenlik", metin)
        self.assertIn("--profil guvenlik", metin)

    def test_dusuk_oncelik_zorunlu(self):
        metin = unit_uret("--profil", "guvenlik", home=self.home)
        self.assertIn("Nice=10", metin)
        self.assertIn("CPUWeight=50", metin)

    def test_rol_adi_profil_olamaz(self):
        ortam = {**os.environ, "HOME": self.home}
        s = subprocess.run(["bash", str(BETIK), "i5", "--kuru", "--profil", "i5"],
                           capture_output=True, text=True, timeout=60, env=ortam)
        self.assertEqual(s.returncode, 2)
        self.assertIn("rol adıyla aynı", s.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
