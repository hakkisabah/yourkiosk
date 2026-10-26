"""makine-kimligi-kur.sh — operatör kurulum betiğinin kilitleri (26 Ekim i5 bulgusunun devamı).

Kimlik kuralı `yaz.py`de TEK yerde durur; bu betik yalnız yazar ve doğrular. Testler üç şeyi
makineyle doğrular:

1. Root olmayan kullanıcı YAZAMAZ (ajan kendi rolünü seçemez) — çıkış 3.
2. Geçersiz rol reddedilir (çıkış 2), yazma yolu `/dev/null` gibi sanal FS hedeflerinde
   `yaz.py` kuralı gereği reddedilir (çıkış 4) — yani doğrulama gerçekten kuralı çağırıyor.
3. Betik kendi kimlik kuralını KOPYALAMAZ (kaynakta root/uid denetimi yok, `yaz.py` çağrılır).
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

BETIK_DIZINI = Path(__file__).resolve().parents[1]
KUR = BETIK_DIZINI / "makine-kimligi-kur.sh"


def _calistir(*argumanlar: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(KUR), *argumanlar],
                          capture_output=True, text=True, timeout=120)


class MakineKimligiKurTesti(unittest.TestCase):
    def test_root_degilse_yazmaz(self):
        if os.geteuid() == 0:  # pragma: no cover - CI root ise senaryo kurulamaz
            self.skipTest("test root olarak koşuyor: 'root değil' senaryosu kurulamaz")
        with tempfile.TemporaryDirectory() as d:
            hedef = Path(d) / "kimlik"
            s = _calistir("i5", str(hedef))
            self.assertEqual(s.returncode, 3, s.stdout + s.stderr)
            self.assertIn("root gerekli", s.stderr)
            self.assertFalse(hedef.exists(), "root olmayan kullanıcı dosyayı yazdı!")

    def test_gecersiz_rol_reddedilir(self):
        s = _calistir("i9")
        self.assertEqual(s.returncode, 2, s.stdout + s.stderr)
        self.assertIn("geçersiz rol", s.stderr)

    def test_kontrol_sanal_dosya_sistemini_reddeder(self):
        """Doğrulama `yaz.py` kuralını çağırır: /dev/null kimlik sayılmaz."""
        s = _calistir("--kontrol", "/dev/null")
        self.assertEqual(s.returncode, 4, s.stdout + s.stderr)
        self.assertIn("sanal dosya sisteminde", s.stdout)

    def test_kontrol_gecersiz_dosya_bildirir(self):
        """Sahipliği/içeriği geçersiz dosya ✗ ile bildirilir (root olmayan test dosyası: uid≠0)."""
        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "kimlik"
            yol.write_text("i9\n", encoding="utf-8")
            os.chmod(yol, 0o644)
            s = _calistir("--kontrol", str(yol))
            self.assertEqual(s.returncode, 4, s.stdout + s.stderr)
            self.assertIn("✗ kimlik geçersiz", s.stdout)
            if os.geteuid() != 0:
                # root olmayan dosya İLK kapıda reddedilir: sahiplik içerikten önce denetlenir
                self.assertIn("root sahipli değil", s.stdout)

    def test_kural_kopyalanmaz(self):
        kaynak = KUR.read_text(encoding="utf-8")
        self.assertIn("makine_kimligi_denetle", kaynak)
        self.assertNotIn("st_uid", kaynak, "kimlik kuralı betikte kopyalanmış: yaz.py'den çağırın")

    def test_yurutulebilir(self):
        self.assertTrue(os.access(KUR, os.X_OK), "makine-kimligi-kur.sh yürütülemez")


if __name__ == "__main__":
    unittest.main(verbosity=2)
