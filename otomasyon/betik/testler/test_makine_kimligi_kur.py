"""makine-kimligi-kur.sh — operatör kurulum betiğinin kilitleri (26 Ekim i5 bulguları).

Tasarım kararı (26 Ekim): kimlik kuralı betiğin İÇİNDE, ama betik ROOT olarak DEPO KODU
ÇALIŞTIRMAZ. Önceki sürüm `python3 - yaz.py` ile çalışma ağacındaki kodu root ayrıcalığıyla
import ediyordu; ajanın yazabildiği dosya root olarak çalışıyordu. Bu dosya şunları kilitler:

1. Root olmayan kullanıcı YAZAMAZ (ajan kendi rolünü seçemez) — çıkış 3.
2. Geçersiz rol reddedilir (çıkış 2).
3. `--kontrol` gerçekten denetler: root sahipli olmayan dosya ✗, normal dosya olmayan hedef ✗.
4. Betik depo kodu çalıştırmaz (kaynakta python/importlib/yaz.py ÇAĞRISI yok).
5. Rol listesi `yaz.py`deki MAKINE_AYARI ile AYNI (kural ile yazım ayrışmasın).
6. Güvenilmez ağaç koruması: root ayrıcalığı kullanan YAZMA yolunda, yazmadan ÖNCE çağrılır.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BETIK_DIZINI = Path(__file__).resolve().parents[1]
KUR = BETIK_DIZINI / "makine-kimligi-kur.sh"

sys.path.insert(0, str(BETIK_DIZINI))
import yaz  # noqa: E402


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

    def test_kontrol_normal_dosya_olmayani_reddeder(self):
        """`/dev/null` bir aygıt dosyasıdır: kimlik normal dosya olmalı."""
        s = _calistir("--kontrol", "/dev/null")
        self.assertEqual(s.returncode, 4, s.stdout + s.stderr)
        self.assertIn("normal dosya değil", s.stderr)
        self.assertNotIn("✓ kimlik geçerli", s.stdout)

    def test_kontrol_root_sahipli_olmayan_dosyayi_reddeder(self):
        """Ajan kendi kimlik dosyasını üretemez: root sahipli olmayan dosya ✗."""
        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "kimlik"
            yol.write_text("i5\n", encoding="utf-8")
            os.chmod(yol, 0o644)
            s = _calistir("--kontrol", str(yol))
            self.assertEqual(s.returncode, 4, s.stdout + s.stderr)
            self.assertNotIn("✓ kimlik geçerli", s.stdout)
            if os.geteuid() != 0:
                self.assertIn("root sahipli değil", s.stderr)

    def test_kontrol_yazilabilir_dosyayi_reddeder(self):
        """root sahipli olmasa bile grup/dünya-yazılabilir dosya kimlik sayılmaz."""
        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "kimlik"
            yol.write_text("i3\n", encoding="utf-8")
            os.chmod(yol, 0o666)
            s = _calistir("--kontrol", str(yol))
            self.assertEqual(s.returncode, 4, s.stdout + s.stderr)
            self.assertNotIn("✓ kimlik geçerli", s.stdout)

    def test_depo_kodu_calistirmaz(self):
        """ROOT ayrıcalığıyla çalışan betik depodaki kodu ÇAĞIRMAZ (26 Ekim i5, orta).

        Yorum satırları sayılmaz: yasak, KODDA python/importlib çağrısı ya da yaz.py yolunun
        hesaplanmasıdır.
        """
        kod = [s for s in KUR.read_text(encoding="utf-8").splitlines()
               if s.strip() and not s.lstrip().startswith("#")]
        metin = "\n".join(kod)
        for yasak in ("python3", "importlib", "spec_from_file_location", "yaz_py"):
            self.assertNotIn(yasak, metin,
                             f"betik depo koduna bağlı: '{yasak}' kodda geçiyor (root olarak çalışır)")
        self.assertNotIn("/yaz.py", metin)

    def test_rol_listesi_yaz_py_ile_ayni(self):
        """Betiğin kabul ettiği roller `yaz.py` MAKINE_AYARI ile aynı olmalı (kural ayrışmasın)."""
        kaynak = KUR.read_text(encoding="utf-8")
        satir = next(s for s in kaynak.splitlines() if s.startswith("ROLE_IZINLI="))
        roller = set(satir.split("=", 1)[1].strip().strip('"').split())
        self.assertEqual(roller, set(yaz.MAKINE_AYARI))

    def test_guvenilmez_agac_korumasi_yazmadan_once(self):
        """Yazma yolu root ayrıcalığı kullanır: ağaç denetimi mktemp/mv'den ÖNCE çağrılmalı."""
        kaynak = KUR.read_text(encoding="utf-8")
        self.assertIn("GÜVENİLMEYEN AĞAÇ", kaynak)
        agac = kaynak.index("agac_guvenilir || exit 4")
        yazim = kaynak.index('GECICI="$(mktemp')
        self.assertLess(agac, yazim, "ağaç denetimi yazımdan sonra: root olarak kirli ağaç çalışır")
        # --kontrol ayrıcalık kullanmaz; yazma yolunda root kapısından sonra çağrılır
        self.assertLess(kaynak.index("root_mu ||"), agac)

    def test_yurutulebilir(self):
        self.assertTrue(os.access(KUR, os.X_OK), "makine-kimligi-kur.sh yürütülemez")


if __name__ == "__main__":
    unittest.main(verbosity=2)
