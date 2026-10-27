"""Nöbetçinin kendini onarması — 26 Ekim i5 arızasının regresyon kilidi.

ARIza: i5'te servis İNSAN deposundan çalışıyordu. Kod güncellemesi insanın `git pull` yapmasına
bağlıydı; i5'in .git/config'inde onlarca `[branch]` bölümü olduğu için pull çalışmıyordu →
bellek tavanlı yeni kod makineye hiç ulaşmadı → `node-MainThread` V8 FatalProcessOutOfMemory ile
core dump. Bu dosya üç sözleşmeyi kilitler:

  1) `depo_guncelle()` makine kopyasında `reset --hard`, insan deposunda yalnız `merge --ff-only`
     yapar; hiçbir durumda sessizce "güncelledim" demez (durum sözcüğü kanıttır).
  2) `nobetci-bakim.sh` ayrı bir klon kurar ve onu origin/main'e çeker — insan deposunun dalı,
     kirli ağacı ve bozuk `[branch]` bölümleri bu işe KARIŞMAZ.
  3) Birim artık klondan çalışır: `--depo <klon> --guncelle` ve `--klon` yolu birimde GÖRÜNÜR.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BETIK_DIZINI = Path(__file__).resolve().parents[1]
KOK = BETIK_DIZINI.parents[1]
sys.path.insert(0, str(BETIK_DIZINI))

import nobetci  # noqa: E402

GIT_ENV = {
    "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
}


def git(*arguman: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *arguman], cwd=str(cwd), capture_output=True, text=True,
                          timeout=120, env={**os.environ, **GIT_ENV})


class DepoKurulumu:
    """Geçici `origin` (bare) + tohum klon: gerçek git, ağ YOK."""

    def __init__(self, kok: Path):
        self.kok = kok
        self.origin = kok / "origin.git"
        self.tohum = kok / "tohum"
        git("init", "--bare", "--initial-branch=main", str(self.origin), cwd=kok)
        git("init", "--initial-branch=main", str(self.tohum), cwd=kok)
        (self.tohum / "otomasyon" / "betik").mkdir(parents=True)
        (self.tohum / "otomasyon" / "betik" / "surum.txt").write_text("v1\n", encoding="utf-8")
        git("add", "-A", cwd=self.tohum)
        git("commit", "-m", "v1", cwd=self.tohum)
        git("remote", "add", "origin", str(self.origin), cwd=self.tohum)
        git("push", "-u", "origin", "main", cwd=self.tohum)

    def yeni_commit(self, icerik: str = "v2") -> str:
        # tohum her zaman origin/main'in tepesinde olmalı: başka bir klon ilerletmiş olabilir
        git("fetch", "origin", cwd=self.tohum)
        git("reset", "--hard", "origin/main", cwd=self.tohum)
        (self.tohum / "otomasyon" / "betik" / "surum.txt").write_text(icerik + "\n", encoding="utf-8")
        git("add", "-A", cwd=self.tohum)
        git("commit", "-m", icerik, cwd=self.tohum)
        s = git("push", "origin", "main", cwd=self.tohum)
        if s.returncode != 0:
            raise AssertionError(f"push başarısız: {s.stderr}")
        return git("rev-parse", "--short=10", "HEAD", cwd=self.tohum).stdout.strip()

    def origin_sha(self) -> str:
        git("fetch", "origin", cwd=self.tohum)
        return git("rev-parse", "--short=10", "origin/main", cwd=self.tohum).stdout.strip()


class DepoGuncelleTesti(unittest.TestCase):
    def setUp(self):
        self.dizin = tempfile.TemporaryDirectory()
        self.kok = Path(self.dizin.name)
        self.kurulum = DepoKurulumu(self.kok)

    def tearDown(self):
        self.dizin.cleanup()

    def _klon(self, ad: str, kopya: bool) -> Path:
        klon = self.kok / ad
        s = git("clone", "--branch", "main", str(self.kurulum.origin), str(klon), cwd=self.kok)
        self.assertEqual(s.returncode, 0, s.stderr)
        if kopya:
            (klon / ".git" / nobetci.KOPYA_ISARETI).touch()
        return klon

    def test_makine_kopyasi_origin_main_e_cekiliyor(self):
        klon = self._klon("kopya", kopya=True)
        self.assertTrue(nobetci.kopya_mi(klon))
        yeni = self.kurulum.yeni_commit("v2")
        durum, ayrinti = nobetci.depo_guncelle(klon)
        self.assertEqual(durum, "guncellendi", ayrinti)
        self.assertIn(yeni, ayrinti)
        self.assertEqual(nobetci.kod_sha(klon), yeni)
        self.assertEqual((klon / "otomasyon" / "betik" / "surum.txt").read_text(encoding="utf-8"),
                         "v2\n")

    def test_degisiklik_yoksa_ayni(self):
        klon = self._klon("kopya", kopya=True)
        durum, _ = nobetci.depo_guncelle(klon)
        self.assertEqual(durum, "ayni")

    def test_insan_deposu_ff_ile_guncellenir_ama_ezilmez(self):
        klon = self._klon("insan", kopya=False)
        self.assertFalse(nobetci.kopya_mi(klon))
        # insan deposunda izlenmeyen dosya var: yalnız ff-merge olur, silinmez
        (klon / "notlar.txt").write_text("benim işim\n", encoding="utf-8")
        self.kurulum.yeni_commit("v3")
        durum, ayrinti = nobetci.depo_guncelle(klon)
        self.assertEqual(durum, "guncellendi", ayrinti)
        self.assertTrue((klon / "notlar.txt").is_file(), "insan deposundaki dosya korunmalı")

    def test_insan_deposu_ileri_gitmisse_atlanir(self):
        klon = self._klon("insan", kopya=False)
        (klon / "yerel.txt").write_text("yerel\n", encoding="utf-8")
        git("add", "-A", cwd=klon)
        git("commit", "-m", "yerel iş", cwd=klon)      # uzakla ıraksadı
        self.kurulum.yeni_commit("v4")
        durum, ayrinti = nobetci.depo_guncelle(klon)
        self.assertEqual(durum, "atlandi", ayrinti)
        self.assertIn("nobetci-bakim.sh", ayrinti)
        self.assertTrue((klon / "yerel.txt").is_file(), "yerel commit korunmalı")

    def test_git_deposu_degilse_hata(self):
        bos = self.kok / "bos"
        bos.mkdir()
        durum, ayrinti = nobetci.depo_guncelle(bos)
        self.assertEqual(durum, "hata")
        self.assertIn("git deposu değil", ayrinti)


class BakimBetigiTesti(unittest.TestCase):
    """`nobetci-bakim.sh` — pull/checkout GEREKMEDEN makine kopyasını kurar ve günceller."""

    def setUp(self):
        self.dizin = tempfile.TemporaryDirectory()
        self.kok = Path(self.dizin.name)
        self.kurulum = DepoKurulumu(self.kok)
        # Bakım betiğinin ihtiyaç duyduğu ağaç: gerçek depodan klonlanacak asgari iskelet
        self.kaynak = self.kok / "insan-deposu"
        git("clone", "--branch", "main", str(self.kurulum.origin), str(self.kaynak), cwd=self.kok)
        (self.kaynak / "otomasyon" / "betik").mkdir(parents=True, exist_ok=True)
        for ad in ("nobetci-bakim.sh",):
            shutil.copy2(BETIK_DIZINI / ad, self.kaynak / "otomasyon" / "betik" / ad)
        shutil.copy2(KOK / "otomasyon" / "nobetci-kur.sh", self.kaynak / "otomasyon" / "nobetci-kur.sh")
        git("add", "-A", cwd=self.kaynak)
        git("commit", "-m", "iskelet", cwd=self.kaynak)
        git("push", "origin", "main", cwd=self.kaynak)
        self.kod_depo = self.kok / "makine-kopyasi" / "depo"
        self.ev = self.kok / "ev"
        (self.ev / ".local" / "state").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.dizin.cleanup()

    def _calistir(self, *ek: str, atla: bool = True) -> subprocess.CompletedProcess:
        ortam = {**os.environ, **GIT_ENV, "HOME": str(self.ev),
                 "NOBETCI_UZAK": str(self.kurulum.origin),
                 "NOBETCI_KOD_DEPO": str(self.kod_depo)}
        if atla:
            ortam["NOBETCI_SISTEMD_ATLA"] = "1"
        return subprocess.run(["bash", str(self.kaynak / "otomasyon" / "betik" / "nobetci-bakim.sh"),
                               "i5", *ek], capture_output=True, text=True, timeout=180, env=ortam)

    def test_kuru_hicbir_sey_olusturmaz(self):
        s = self._calistir("--kuru", atla=False)
        self.assertEqual(s.returncode, 0, s.stderr)
        self.assertIn("git clone", s.stdout)
        self.assertIn("kuru:", s.stdout)
        self.assertFalse(self.kod_depo.exists(), "--kuru klon oluşturmamalı")

    def test_klon_kurulur_ve_isaretlenir(self):
        s = self._calistir()
        self.assertEqual(s.returncode, 0, s.stderr + s.stdout)
        self.assertTrue((self.kod_depo / ".git").is_dir())
        self.assertTrue(nobetci.kopya_mi(self.kod_depo), "makine kopyası işareti yok")
        self.assertEqual(nobetci.kod_sha(self.kod_depo), self.kurulum.origin_sha())

    def test_ikinci_calisma_klonu_origin_main_e_ceker(self):
        self.assertEqual(self._calistir().returncode, 0)
        yeni = self.kurulum.yeni_commit("v5")
        s = self._calistir()
        self.assertEqual(s.returncode, 0, s.stderr + s.stdout)
        self.assertIn("güncellendi", s.stdout)
        self.assertEqual(nobetci.kod_sha(self.kod_depo), yeni)

    def test_insan_deposunun_dali_onemsiz(self):
        """i5'in asıl derdi: insan deposunun bozuk `[branch]` bölümleri bakımı ENGELLEMEZ."""
        git("checkout", "-b", "eski-dal", cwd=self.kaynak)
        git("config", "branch.eski-dal.remote", "origin", cwd=self.kaynak)
        git("config", "branch.eski-dal.merge", "refs/heads/baska-bir-dal", cwd=self.kaynak)
        (self.kaynak / "kirli.txt").write_text("kirli ağaç\n", encoding="utf-8")
        s = self._calistir()
        self.assertEqual(s.returncode, 0, s.stderr + s.stdout)
        self.assertTrue(nobetci.kopya_mi(self.kod_depo))

    def test_klon_yolu_git_deposu_degilse_reddeder(self):
        self.kod_depo.mkdir(parents=True)
        (self.kod_depo / "yabanci.txt").write_text("dokunma\n", encoding="utf-8")
        s = self._calistir()
        self.assertEqual(s.returncode, 4)
        self.assertIn("git deposu değil", s.stderr)
        self.assertTrue((self.kod_depo / "yabanci.txt").is_file(), "yabancı dizin silinmemeli")

    def test_bellek_tavani_dropin_ve_birim_ayni_formulu_kullanir(self):
        """İki yerde ölçülen tavan (drop-in ↔ birim) AYNI olmalı: formül kayması = sessiz OOM."""
        self.assertEqual(self._calistir().returncode, 0)
        dropin = (self.ev / ".config/systemd/user/yourkiosk-nobetci.service.d/50-bellek.conf")
        self.assertTrue(dropin.is_file(), "bellek drop-in'i yazılmadı")
        metin = dropin.read_text(encoding="utf-8")
        self.assertIn("[Service]", metin)

        unit = subprocess.run(["bash", str(self.kod_depo / "otomasyon" / "nobetci-kur.sh"), "i5",
                               "--kuru", "--klon", str(self.kod_depo)],
                              capture_output=True, text=True, timeout=90,
                              env={**os.environ, "HOME": str(self.ev)})
        self.assertEqual(unit.returncode, 0, unit.stderr)

        def deger(metin_: str, anahtar: str) -> str:
            for satir in metin_.splitlines():
                if satir.strip().startswith(anahtar):
                    return satir.strip()
            return ""

        for anahtar in ("MemoryHigh=", "MemoryMax="):
            self.assertEqual(deger(metin, anahtar), deger(unit.stdout, anahtar),
                             f"{anahtar} drop-in ile birim arasında farklı")
        self.assertIn("NODE_OPTIONS=--max-old-space-size=", metin)
        self.assertIn("--max-old-space-size=", unit.stdout)

    def test_kuru_dropin_yazmaz(self):
        s = self._calistir("--kuru", atla=False)
        self.assertEqual(s.returncode, 0, s.stderr)
        self.assertIn("50-bellek.conf", s.stdout)
        self.assertFalse((self.ev / ".config/systemd/user/yourkiosk-nobetci.service.d").exists(),
                         "--kuru hiçbir dosya yazmamalı")

    def test_bilinmeyen_secenek_reddedilir(self):
        s = self._calistir("--yok-boyle-secenek", atla=False)
        self.assertEqual(s.returncode, 2)


class BirimKlonTesti(unittest.TestCase):
    """Servis birimi klondan çalışmalı: `--klon` + `--depo` + `--guncelle` birimde görünür."""

    def setUp(self):
        self.dizin = tempfile.TemporaryDirectory()
        self.kok = Path(self.dizin.name)
        self.klon = self.kok / "depo"
        self.klon.mkdir()
        s = git("init", "--initial-branch=main", str(self.klon), cwd=self.kok)
        self.assertEqual(s.returncode, 0, s.stderr)
        self.ev = self.kok / "ev"
        (self.ev / ".local" / "state").mkdir(parents=True)

    def tearDown(self):
        self.dizin.cleanup()

    def _unit(self, *ek: str) -> str:
        s = subprocess.run(["bash", str(KOK / "otomasyon" / "nobetci-kur.sh"), "i5", "--kuru",
                            "--klon", str(self.klon), *ek],
                           capture_output=True, text=True, timeout=90,
                           env={**os.environ, "HOME": str(self.ev)})
        self.assertEqual(s.returncode, 0, s.stderr)
        return s.stdout

    def test_birim_klondan_calisir(self):
        metin = self._unit()
        self.assertIn(f"WorkingDirectory={self.klon}", metin)
        self.assertIn(f"ExecStart=/usr/bin/python3 {self.klon}/otomasyon/betik/nobetci.py", metin)
        self.assertIn(f"--depo {self.klon}", metin)
        self.assertIn("--guncelle", metin)
        # kendini güncelleme olmadan klon sessizce bayatlar → kontrol noktası da bunu arar
        self.assertIn("Restart=always", metin)

    def test_klon_yoksa_kurulum_reddedilir(self):
        yok = self.kok / "olmayan"
        s = subprocess.run(["bash", str(KOK / "otomasyon" / "nobetci-kur.sh"), "i5", "--kuru",
                            "--klon", str(yok)], capture_output=True, text=True, timeout=90,
                           env={**os.environ, "HOME": str(self.ev)})
        self.assertEqual(s.returncode, 2)
        self.assertIn("git deposu olmalı", s.stderr)


class KontrolNoktasiTesti(unittest.TestCase):
    """13-14 numaralı kontrol noktaları sessizce silinmesin (görünürlük sözleşmesi)."""

    def test_kod_tazeligi_kontrolleri_var(self):
        kaynak = (BETIK_DIZINI / "nobetci.py").read_text(encoding="utf-8")
        self.assertIn("kod origin/main ile aynı", kaynak)
        self.assertIn("kod deposu makine kopyası", kaynak)
        # ağ yoksa kontrol "temiz" sayılmamalı, uyarı olarak görünmeli
        self.assertIn("⚠ kod origin/main ile aynı", kaynak)


if __name__ == "__main__":
    unittest.main(verbosity=2)
