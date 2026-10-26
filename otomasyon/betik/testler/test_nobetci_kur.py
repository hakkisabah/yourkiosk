"""nobetci-kur.sh — systemd unit üretimi (profil ayrımı + düşük öncelik).

26 Ekim i5 mimarisi: nöbetçi kendi profiliyle (`hermes -p guvenlik`) ve düşük CPU önceliğiyle
çalışmalı ki Open WebUI yükü PR incelemesini aç bırakmasın. Bu sözleşme unit dosyasında görünür
olmak zorunda — yoksa "ayırdım" sanılır ama aynı gateway'de çalışmaya devam eder.
"""

from __future__ import annotations

import os
import re
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

    def test_profil_degeri_birime_enjeksiyon_yapamaz(self):
        """26 Ekim i5 bulgusu: --profil doğrulanmıyordu → satır sonu birime yönerge ekliyordu."""
        kotu = ["a\nExecStartPre=/bin/touch /tmp/pwn", "guvenlik\n", "Guvenlik", "gu venlik",
                "a" * 40, "-x", "guvenlik;rm", "../../etc"]
        for deger in kotu:
            ortam = {**os.environ, "HOME": self.home}
            s = subprocess.run(["bash", str(BETIK), "i5", "--kuru", "--profil", deger],
                               capture_output=True, text=True, timeout=60, env=ortam)
            self.assertEqual(s.returncode, 2, f"kabul edildi: {deger!r} → {s.stdout}")
            self.assertNotIn("ExecStartPre", s.stdout)
            self.assertIn("geçersiz --profil", s.stderr)

    def test_gecerli_profil_kabul_edilir(self):
        for deger in ("guvenlik", "guvenlik-2", "guvenlik_2", "g"):
            metin = unit_uret("--profil", deger, home=self.home)
            self.assertIn(f"--profil {deger}", metin)

    # ── BELLEK TAVANI (26 Ekim: birim cgroup'unda node OOM/core dump) ──────────────────────────
    @staticmethod
    def _ram_mb() -> int:
        for satir in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if satir.startswith("MemTotal:"):
                return int(satir.split()[1]) // 1024
        return 0

    def test_bellek_tavani_birimde_ve_makineyle_uyumlu(self):
        """Tavanlar sabit değil, KURULUM ANINDA makineden ölçülür; 4 GB'lık i5'e 16 GB tavan yazılmaz."""
        ram = self._ram_mb()
        metin = unit_uret(home=self.home)
        self.assertIn("MemoryAccounting=yes", metin)
        self.assertIn("MemoryHigh=", metin)
        self.assertIn("MemoryMax=", metin)
        self.assertIn("OOMPolicy=stop", metin)
        yuksek = int(re.search(r"^MemoryHigh=(\d+)M$", metin, re.M).group(1))
        tavan = int(re.search(r"^MemoryMax=(\d+)M$", metin, re.M).group(1))
        self.assertLess(yuksek, tavan, "MemoryHigh < MemoryMax olmalı (yumuşak eşik önce)")
        if ram > 1024:
            self.assertAlmostEqual(tavan, ram * 75 // 100, delta=2,
                                   msg="MemoryMax makine RAM'inin %75'i olmalı")
            self.assertAlmostEqual(yuksek, ram * 60 // 100, delta=2)
            self.assertLess(tavan, ram, "bellek tavanı makine RAM'ini aşamaz")

    def test_node_v8_tavani_olculu(self):
        """Node çocukları RAM'in 1/4'ü kadar V8 tavanı devralır (512–2048 arası sınırlı)."""
        ram = self._ram_mb()
        metin = unit_uret(home=self.home)
        m = re.search(r"^Environment=NODE_OPTIONS=--max-old-space-size=(\d+)$", metin, re.M)
        self.assertIsNotNone(m, "NODE_OPTIONS tavansız → V8 'FatalProcessOutOfMemory' riski")
        heap = int(m.group(1))
        self.assertGreaterEqual(heap, 512)
        self.assertLessEqual(heap, 2048)
        if ram > 2048:
            self.assertLessEqual(heap, ram, "V8 tavanı makine RAM'ini aşamaz")

    def test_cokme_dongusu_freni_var(self):
        """Restart=always tek başına çökme döngüsünü sonsuzlaştırır (her tur = token + core dump)."""
        metin = unit_uret(home=self.home)
        self.assertIn("StartLimitIntervalSec=300", metin)
        self.assertIn("StartLimitBurst=5", metin)
        self.assertIn("TasksMax=", metin)
        self.assertIn("TimeoutStopSec=", metin)


if __name__ == "__main__":
    unittest.main(verbosity=2)
