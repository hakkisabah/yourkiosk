"""agir-komut.sh — bellek tavanlı ağır komut koşucusu.

26 Ekim kanıtı: `yourkiosk-nobetci` biriminin cgroup'unda `node-MainThread` V8
`FatalProcessOutOfMemory` ile core dump aldı (3,8 GB RAM'li makine; V8 tavanı makine RAM'inden
bağımsız kurulunca takas dolar ve süreç abort eder). Bu testler korumanın DÖRT ayağını ayrı ayrı
kilitler: boş RAM eşiği (reddet), V8 tavanı (ölçülü), cgroup tavanı (yalıtım), sıra (flock).
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

BETIK = Path(__file__).resolve().parents[1] / "agir-komut.sh"


def sahte_meminfo(dizin: str, toplam_mb: int, bos_mb: int, takas_mb: int = 0,
                  takas_bos_mb: int = 0) -> Path:
    yol = Path(dizin) / "meminfo"
    yol.write_text(
        f"MemTotal:       {toplam_mb * 1024} kB\n"
        f"MemAvailable:   {bos_mb * 1024} kB\n"
        f"SwapTotal:      {takas_mb * 1024} kB\n"
        f"SwapFree:       {takas_bos_mb * 1024} kB\n",
        encoding="utf-8")
    return yol


class AgirKomutTesti(unittest.TestCase):
    def setUp(self):
        self.dizin = tempfile.TemporaryDirectory()
        self.home = Path(self.dizin.name) / "home"
        self.home.mkdir()
        self.calisma = Path(self.dizin.name) / "run"
        self.calisma.mkdir()

    def tearDown(self):
        self.dizin.cleanup()

    def kos(self, *argumanlar: str, meminfo: Path | None = None,
            ek_ortam: dict | None = None) -> subprocess.CompletedProcess:
        ortam = {**os.environ, "HOME": str(self.home), "XDG_RUNTIME_DIR": str(self.calisma),
                 "AGIR_ESIK_MB": "700"}
        if meminfo is not None:
            ortam["AGIR_MEMINFO"] = str(meminfo)
        ortam.update(ek_ortam or {})
        return subprocess.run(["bash", str(BETIK), *argumanlar],
                              capture_output=True, text=True, timeout=120, env=ortam)

    # ── plan (kuru) ─────────────────────────────────────────────────────────────────────────────
    def test_kuru_plan_tavan_ve_v8_heap_yazar(self):
        """4 GB makinede 2 GB boş: cgroup tavanı = boş-400 = 1600 MB, V8 tavanı = %60 = 960 MB."""
        mem = sahte_meminfo(self.dizin.name, toplam_mb=3886, bos_mb=2000)
        s = self.kos("--kuru", "--", "npm", "test", meminfo=mem)
        self.assertEqual(s.returncode, 0, s.stderr)
        self.assertIn("cgroup tavanı  : 1600 MB", s.stdout)
        self.assertIn("--max-old-space-size=960", s.stdout)
        self.assertIn("npm test", s.stdout)

    def test_kuru_plan_komutu_calistirmaz(self):
        mem = sahte_meminfo(self.dizin.name, toplam_mb=8000, bos_mb=4000)
        isaret = Path(self.dizin.name) / "calisti"
        s = self.kos("--kuru", "--", "touch", str(isaret), meminfo=mem)
        self.assertEqual(s.returncode, 0, s.stderr)
        self.assertFalse(isaret.exists())

    def test_tavan_ust_siniri_asilmaz(self):
        """64 GB makinede bile tek komut 4 GB'ı geçmemeli (boş RAM kadar tavan anlamsız)."""
        mem = sahte_meminfo(self.dizin.name, toplam_mb=65536, bos_mb=60000)
        s = self.kos("--kuru", "--", "/bin/true", meminfo=mem)
        self.assertIn("cgroup tavanı  : 4096 MB", s.stdout)
        self.assertIn("--max-old-space-size=2048", s.stdout)

    def test_max_mb_verilirse_olculen_deger_kullanilir(self):
        mem = sahte_meminfo(self.dizin.name, toplam_mb=3886, bos_mb=2000)
        s = self.kos("--kuru", "--max-mb", "900", "--", "/bin/true", meminfo=mem)
        self.assertIn("cgroup tavanı  : 900 MB", s.stdout)
        self.assertIn("--max-old-space-size=540", s.stdout)

    # ── boş RAM eşiği ───────────────────────────────────────────────────────────────────────────
    def test_bos_ram_esigin_altindaysa_reddeder(self):
        mem = sahte_meminfo(self.dizin.name, toplam_mb=3886, bos_mb=300, takas_mb=1943,
                            takas_bos_mb=143)
        s = self.kos("--", "/bin/true", meminfo=mem)
        self.assertEqual(s.returncode, 7)
        self.assertIn("REDDEDİLDİ", s.stderr)
        self.assertIn("300 MB", s.stderr)
        self.assertIn("FatalProcessOutOfMemory", s.stderr)

    def test_zorla_esigi_yok_sayar(self):
        mem = sahte_meminfo(self.dizin.name, toplam_mb=3886, bos_mb=300)
        s = self.kos("--zorla", "--", "/bin/true", meminfo=mem)
        self.assertEqual(s.returncode, 0, s.stderr)

    def test_esik_ortam_degiskeniyle_ayarlanir(self):
        mem = sahte_meminfo(self.dizin.name, toplam_mb=3886, bos_mb=1200)
        s = self.kos("--", "/bin/true", meminfo=mem, ek_ortam={"AGIR_ESIK_MB": "2000"})
        self.assertEqual(s.returncode, 7, "eşik 2000 MB iken 1200 MB boş RAM reddedilmeliydi")

    # ── kullanım hataları ───────────────────────────────────────────────────────────────────────
    def test_komut_yoksa_kullanim_hatasi(self):
        s = self.kos()
        self.assertEqual(s.returncode, 2)
        self.assertIn("komut verilmedi", s.stderr)

    def test_sayisal_olmayan_max_mb_reddedilir(self):
        s = self.kos("--max-mb", "çok", "--", "/bin/true")
        self.assertEqual(s.returncode, 2)

    # ── sıra (flock) ────────────────────────────────────────────────────────────────────────────
    def test_ikinci_agir_komut_siraya_girer(self):
        mem = sahte_meminfo(self.dizin.name, toplam_mb=3886, bos_mb=2000)
        ilk = subprocess.Popen(["bash", str(BETIK), "--", "sleep", "3"],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               env={**os.environ, "HOME": str(self.home),
                                    "XDG_RUNTIME_DIR": str(self.calisma), "AGIR_MEMINFO": str(mem)})
        try:
            time.sleep(1.2)
            ikinci = self.kos("--", "/bin/true", meminfo=mem)
            self.assertEqual(ikinci.returncode, 8, ikinci.stderr)
            self.assertIn("başka bir ağır komut sürüyor", ikinci.stderr)
        finally:
            ilk.communicate(timeout=30)
        self.assertEqual(ilk.returncode, 0)
        # kilit bırakıldı → sonraki çağrı geçer
        self.assertEqual(self.kos("--", "/bin/true", meminfo=mem).returncode, 0)

    # ── davranış: env + çıkış kodu ──────────────────────────────────────────────────────────────
    def test_v8_tavani_alt_surece_gecer(self):
        mem = sahte_meminfo(self.dizin.name, toplam_mb=3886, bos_mb=2000)  # heap 960 MB
        s = self.kos("--", "node", "-e",
                     "console.log(Math.round(require('v8').getHeapStatistics().heap_size_limit/1048576))",
                     meminfo=mem)
        if s.returncode != 0:
            self.skipTest(f"node yok: {s.stderr[:120]}")
        mb = int(s.stdout.strip().splitlines()[-1])
        self.assertGreaterEqual(mb, 900)
        self.assertLessEqual(mb, 1100, f"V8 tavanı uygulanmadı: {mb} MB")

    def test_cagiranin_node_options_tavani_korunur(self):
        mem = sahte_meminfo(self.dizin.name, toplam_mb=3886, bos_mb=2000)
        s = self.kos("--", "node", "-e",
                     "console.log(Math.round(require('v8').getHeapStatistics().heap_size_limit/1048576))",
                     meminfo=mem, ek_ortam={"NODE_OPTIONS": "--max-old-space-size=448"})
        if s.returncode != 0:
            self.skipTest(f"node yok: {s.stderr[:120]}")
        mb = int(s.stdout.strip().splitlines()[-1])
        self.assertLessEqual(mb, 600, f"çağıranın tavanı ezildi: {mb} MB")

    def test_komutun_cikis_kodu_iletilir(self):
        mem = sahte_meminfo(self.dizin.name, toplam_mb=8000, bos_mb=4000)
        s = self.kos("--", "sh", "-c", "exit 42", meminfo=mem)
        self.assertEqual(s.returncode, 42)

    def test_gunluge_yazar(self):
        mem = sahte_meminfo(self.dizin.name, toplam_mb=3886, bos_mb=2000)
        self.kos("--", "/bin/true", meminfo=mem)
        gunluk = self.home / ".local" / "state" / "yourkiosk-otomasyon" / "agir-komut.log"
        self.assertTrue(gunluk.is_file(), "günlük yazılmadı")
        metin = gunluk.read_text(encoding="utf-8")
        self.assertIn("tavan=1600MB", metin)
        self.assertIn("çıkış=0", metin)


    # ── sır sızması (28 Ekim i5 bulgusu, düşük) ─────────────────────────────────────────────────
    def test_gunluk_argv_maskeler_ve_0600(self):
        """argv günlüğe MASKELENEREK yazılır; dosya 0600, dizin 0700.

        Eski hâlde tam argv `>> agir-komut.log` ile 0644 bir dosyaya düz yazılıyordu: `--token …`,
        `Authorization: Bearer …`, `..._authToken=…` gibi her çağrı sırrı kalıcı olarak sızdırıyordu.
        """
        mem = sahte_meminfo(self.dizin.name, toplam_mb=3886, bos_mb=2000)
        s = self.kos("--", "/bin/true", "--token", "gizli-abc-123",
                     "GH_TOKEN=ghp_ABCDEFGHIJKLMNOPQRSTUV", meminfo=mem)
        self.assertEqual(s.returncode, 0, s.stderr)
        gunluk = self.home / ".local" / "state" / "yourkiosk-otomasyon" / "agir-komut.log"
        metin = gunluk.read_text(encoding="utf-8")
        self.assertNotIn("gizli-abc-123", metin, "sır günlüğe düz yazıldı")
        self.assertNotIn("ghp_ABCDEFGHIJKLMNOPQRSTUV", metin, "jeton günlüğe düz yazıldı")
        self.assertIn("***", metin, "maskeleme izi yok")
        self.assertEqual(gunluk.stat().st_mode & 0o777, 0o600, "günlük 0600 olmalı")
        self.assertEqual(gunluk.parent.stat().st_mode & 0o777, 0o700, "günlük dizini 0700 olmalı")

    def test_kuru_cikti_da_maskeli(self):
        mem = sahte_meminfo(self.dizin.name, toplam_mb=3886, bos_mb=2000)
        s = self.kos("--kuru", "--", "npm", "test", "--parola", "cok-gizli", meminfo=mem)
        self.assertEqual(s.returncode, 0, s.stderr)
        self.assertNotIn("cok-gizli", s.stdout + s.stderr)
        self.assertIn("***", s.stdout)

    def test_authorization_basligi_maskelenir(self):
        mem = sahte_meminfo(self.dizin.name, toplam_mb=3886, bos_mb=2000)
        s = self.kos("--kuru", "--", "curl", "-H", "Authorization: Bearer zz-top-secret",
                     meminfo=mem)
        self.assertNotIn("zz-top-secret", s.stdout + s.stderr)
        self.assertIn("Authorization: Bearer ***", s.stdout)

    def test_maskeleme_kaynaktan_kaldirilmaz(self):
        """Kaynak taraması: maskele() ve 0700/0600 izinleri betikte kalıcı olmalı."""
        kaynak = BETIK.read_text(encoding="utf-8")
        self.assertIn("maskele()", kaynak)
        self.assertIn("umask 077", kaynak)
        self.assertIn("komut=$(printf '%s ' \"$@\" | maskele)", kaynak)


if __name__ == "__main__":
    unittest.main(verbosity=2)
