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

    def test_tek_dal_klonu_baska_dali_gunceller(self):
        """`--single-branch main` klonunda başka dal istenirse `origin/<dal>` yoktur.
        Ref AÇIKÇA yazılmalı, yoksa `reset --hard origin/<dal>` patlar (27 Ekim i5)."""
        klon = self.kok / "tekdal"
        s = git("clone", "--branch", "main", "--single-branch",
                str(self.kurulum.origin), str(klon), cwd=self.kok)
        self.assertEqual(s.returncode, 0, s.stderr)
        (klon / ".git" / nobetci.KOPYA_ISARETI).touch()
        # uzakta ikinci dal
        git("checkout", "-b", "yan", cwd=self.kurulum.tohum)
        (self.kurulum.tohum / "otomasyon" / "betik" / "surum.txt").write_text("yan\n", encoding="utf-8")
        git("add", "-A", cwd=self.kurulum.tohum)
        git("commit", "-m", "yan", cwd=self.kurulum.tohum)
        git("push", "origin", "yan", cwd=self.kurulum.tohum)
        yan_sha = git("rev-parse", "--short=10", "HEAD", cwd=self.kurulum.tohum).stdout.strip()

        durum, ayrinti = nobetci.depo_guncelle(klon, dal="yan")
        self.assertEqual(durum, "guncellendi", ayrinti)
        self.assertEqual(nobetci.kod_sha(klon), yan_sha)
        self.assertEqual((klon / "otomasyon/betik/surum.txt").read_text(encoding="utf-8"), "yan\n")


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

    def test_tek_dal_klonu_baska_dala_cekilir(self):
        """27 Ekim i5 arızası: klon `--single-branch main` idi, `--dal <başka>` istenince
        `fetch origin <dal>` yalnız FETCH_HEAD yazdı → `reset --hard origin/<dal>` patladı ve
        kullanıcı yalnız '✗ reset --hard … başarısız' gördü. Ref AÇIKÇA yazılmalı."""
        self.assertEqual(self._calistir().returncode, 0, "ilk kurulum (main) başarısız")
        # uzakta ikinci dal — iskeleti (nobetci-kur.sh) taşıyan depodan türet
        git("checkout", "-b", "yan", cwd=self.kaynak)
        (self.kaynak / "otomasyon" / "betik" / "surum.txt").write_text("yan\n", encoding="utf-8")
        git("add", "-A", cwd=self.kaynak)
        git("commit", "-m", "yan", cwd=self.kaynak)
        git("push", "origin", "yan", cwd=self.kaynak)
        yan_sha = git("rev-parse", "--short=10", "HEAD", cwd=self.kaynak).stdout.strip()

        s = self._calistir("--dal", "yan")
        self.assertEqual(s.returncode, 0, s.stderr + s.stdout)
        self.assertNotIn("reset --hard origin/yan başarısız", s.stderr)
        self.assertEqual(nobetci.kod_sha(self.kod_depo), yan_sha)
        self.assertEqual((self.kod_depo / "otomasyon/betik/surum.txt").read_text(encoding="utf-8"),
                         "yan\n")
        # izlenen dal TEK kaynaktan okunur (servis, --guncelle, --kendini-denetle)
        self.assertEqual((self.ev / ".local/state/yourkiosk-otomasyon/nobetci-dal")
                         .read_text(encoding="utf-8").strip(), "yan")

    def test_depo_disi_betik_kaynak_saymaz(self):
        """Betik /tmp gibi bir yerden çalışınca `dirname/../..` = "/" oluyordu ve 'kaynak: /'
        yazıyordu (uzak adres de yanlış yere düşüyordu). Depo dışı = kaynak YOK."""
        disarida = self.kok / "disarida" / "otomasyon" / "betik"
        disarida.mkdir(parents=True)
        shutil.copy2(BETIK_DIZINI / "nobetci-bakim.sh", disarida / "nobetci-bakim.sh")
        ortam = {**os.environ, **GIT_ENV, "HOME": str(self.ev),
                 "NOBETCI_UZAK": str(self.kurulum.origin),
                 "NOBETCI_KOD_DEPO": str(self.kod_depo),
                 "NOBETCI_SISTEMD_ATLA": "1"}
        s = subprocess.run(["bash", str(disarida / "nobetci-bakim.sh"), "i5"],
                           capture_output=True, text=True, timeout=180, env=ortam)
        self.assertEqual(s.returncode, 0, s.stderr + s.stdout)
        self.assertNotIn("kaynak      : /\n", s.stdout)
        self.assertIn("kaynak      : yok", s.stdout)
        self.assertTrue(nobetci.kopya_mi(self.kod_depo))


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
        # 27 Ekim: kontrol artık İZLENEN DALA bağlı (main'e merge edilmemiş düzeltme dalı da olabilir)
        self.assertIn("kod origin/{dal} ile aynı", kaynak)
        self.assertIn("kod deposu makine kopyası", kaynak)
        # ağ yoksa kontrol "temiz" sayılmamalı, uyarı olarak görünmeli
        self.assertIn("⚠ kod origin/{dal} ile aynı", kaynak)


class DalTesti(unittest.TestCase):
    """İzlenen dal çözümü — 27 Ekim kilitlenmesi: düzeltme main'e girmeden makineye ulaşamıyordu."""

    def setUp(self):
        self.dizin = tempfile.TemporaryDirectory()
        self.kok = Path(self.dizin.name)
        self.dal_dosyasi = self.kok / "nobetci-dal"
        self._eski_dosya = nobetci.DAL_DOSYASI
        nobetci.DAL_DOSYASI = self.dal_dosyasi
        self._eski_env = os.environ.pop("NOBETCI_DAL", None)

    def tearDown(self):
        nobetci.DAL_DOSYASI = self._eski_dosya
        os.environ.pop("NOBETCI_DAL", None)
        if self._eski_env is not None:
            os.environ["NOBETCI_DAL"] = self._eski_env
        self.dizin.cleanup()

    def test_varsayilan_main(self):
        self.assertEqual(nobetci.dal_coz(), "main")

    def test_dosyadan_okunur(self):
        self.dal_dosyasi.write_text("duzeltme/dal\n", encoding="utf-8")
        self.assertEqual(nobetci.dal_coz(), "duzeltme/dal")

    def test_ortam_degiskeni_dosyayi_ezer(self):
        self.dal_dosyasi.write_text("duzeltme/dal\n", encoding="utf-8")
        os.environ["NOBETCI_DAL"] = "ozellik/baska"
        self.assertEqual(nobetci.dal_coz(), "ozellik/baska")

    def test_acik_arguman_hepsini_ezer(self):
        self.dal_dosyasi.write_text("duzeltme/dal\n", encoding="utf-8")
        os.environ["NOBETCI_DAL"] = "ozellik/baska"
        self.assertEqual(nobetci.dal_coz("main"), "main")

    def test_gecersiz_dal_reddedilir(self):
        for kotu in ("-x", "a..b", "a//b", "a b", "a;rm", "a\nb"):
            with self.subTest(kotu=kotu):
                with self.assertRaises(SystemExit):
                    nobetci.dal_coz(kotu)

    def test_depo_guncelle_verilen_dali_izler(self):
        kurulum = DepoKurulumu(self.kok)
        klon = self.kok / "kopya"
        git("clone", "--branch", "main", str(kurulum.origin), str(klon), cwd=self.kok)
        (klon / ".git" / nobetci.KOPYA_ISARETI).touch()
        # uzakta düzeltme dalı: main'den ayrı commit
        git("checkout", "-b", "duzeltme/dal", cwd=kurulum.tohum)
        (kurulum.tohum / "otomasyon" / "betik" / "surum.txt").write_text("dal-v1\n", encoding="utf-8")
        git("add", "-A", cwd=kurulum.tohum)
        git("commit", "-m", "dal-v1", cwd=kurulum.tohum)
        self.assertEqual(git("push", "origin", "duzeltme/dal", cwd=kurulum.tohum).returncode, 0)
        durum, ayrinti = nobetci.depo_guncelle(klon, None, "duzeltme/dal")
        self.assertEqual(durum, "guncellendi", ayrinti)
        self.assertEqual((klon / "otomasyon" / "betik" / "surum.txt").read_text(encoding="utf-8"),
                         "dal-v1\n")


class BakimHataGorunurluguTesti(unittest.TestCase):
    """27 Ekim i5 arızası: `✗ birim kurulumu başarısız` — NEDEN yazmıyordu (çıktı yutuluyordu).

    İki sözleşme:
      1) Klondaki kod makine kopyası + kendini güncelleme biçimini desteklemiyorsa AÇIK hata (çıkış 8)
         ve çözüm komutu yazılır — "başarısız" deyip susmak yok.
      2) Gerçek kurulum patlarsa alttaki komutun çıktısı AYNEN gösterilir (çıkış 7).
    """

    def setUp(self):
        self.dizin = tempfile.TemporaryDirectory()
        self.kok = Path(self.dizin.name)
        self.kurulum = DepoKurulumu(self.kok)
        self.kaynak = self.kok / "insan-deposu"
        git("clone", "--branch", "main", str(self.kurulum.origin), str(self.kaynak), cwd=self.kok)
        (self.kaynak / "otomasyon" / "betik").mkdir(parents=True, exist_ok=True)
        shutil.copy2(BETIK_DIZINI / "nobetci-bakim.sh", self.kaynak / "otomasyon" / "betik" / "nobetci-bakim.sh")
        shutil.copy2(KOK / "otomasyon" / "nobetci-kur.sh", self.kaynak / "otomasyon" / "nobetci-kur.sh")
        git("add", "-A", cwd=self.kaynak)
        git("commit", "-m", "iskelet", cwd=self.kaynak)
        git("push", "origin", "main", cwd=self.kaynak)
        self.kod_depo = self.kok / "makine-kopyasi" / "depo"
        self.ev = self.kok / "ev"
        (self.ev / ".local" / "state").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.dizin.cleanup()

    def _calistir(self, *ek: str, atla: bool = False) -> subprocess.CompletedProcess:
        ortam = {**os.environ, **GIT_ENV, "HOME": str(self.ev),
                 "NOBETCI_UZAK": str(self.kurulum.origin),
                 "NOBETCI_KOD_DEPO": str(self.kod_depo)}
        if atla:
            ortam["NOBETCI_SISTEMD_ATLA"] = "1"
        return subprocess.run(["bash", str(self.kaynak / "otomasyon" / "betik" / "nobetci-bakim.sh"),
                               "i5", *ek], capture_output=True, text=True, timeout=180, env=ortam)

    def _kur_stub(self, metin: str) -> None:
        (self.kaynak / "otomasyon" / "nobetci-kur.sh").write_text(metin, encoding="utf-8")
        git("add", "-A", cwd=self.kaynak)
        git("commit", "-m", "stub", cwd=self.kaynak)
        self.assertEqual(git("push", "origin", "main", cwd=self.kaynak).returncode, 0)

    def test_eski_kod_acik_hata_verir(self):
        # main'deki ESKİ kur.sh: --klon/--dal bilmiyor (i5'in 26 Ekim durumu)
        self._kur_stub("#!/usr/bin/env bash\n"
                       "echo '--- birim ---'\n"
                       "echo '[Service]'\n"
                       "echo 'WorkingDirectory=/eski/yol'\n"
                       "echo 'ExecStart=/usr/bin/python3 /eski/yol/otomasyon/betik/nobetci.py --rol i5'\n")
        s = self._calistir()
        self.assertEqual(s.returncode, 8, s.stdout + s.stderr)
        self.assertIn("DESTEKLEMİYOR", s.stderr)
        self.assertIn("--dal <düzeltme-dalı>", s.stderr)
        self.assertIn("origin/main", s.stderr)

    def test_kurulum_hatasinin_ciktisi_gosterilir(self):
        self._kur_stub(
            "#!/usr/bin/env bash\n"
            "klon=''; dal=''\n"
            "for a in \"$@\"; do [ \"$a\" = \"--kuru\" ] && kuru=1; done\n"
            "if [ -n \"${kuru:-}\" ]; then\n"
            "  echo '[Service]'\n"
            "  echo 'WorkingDirectory='${NOBETCI_KOD_DEPO}\n"
            "  echo 'ExecStart=/usr/bin/python3 x --depo y --dal main --guncelle'\n"
            "  exit 0\n"
            "fi\n"
            "echo 'SAHTE HATA: birim yazılamadı (disk dolu)' >&2\n"
            "exit 1\n")
        s = self._calistir()
        self.assertEqual(s.returncode, 7, s.stdout + s.stderr)
        self.assertIn("SAHTE HATA: birim yazılamadı (disk dolu)", s.stderr,
                      "alttaki komutun çıktısı gösterilmeli")

    def test_dal_klondan_kurulur_ve_dosyaya_yazilir(self):
        # uzakta düzeltme dalı
        git("checkout", "-b", "duzeltme/dal", cwd=self.kaynak)
        (self.kaynak / "DAL.txt").write_text("dal\n", encoding="utf-8")
        git("add", "-A", cwd=self.kaynak)
        git("commit", "-m", "dal", cwd=self.kaynak)
        self.assertEqual(git("push", "origin", "duzeltme/dal", cwd=self.kaynak).returncode, 0)
        s = self._calistir("--dal", "duzeltme/dal", "--sessiz", atla=True)
        self.assertEqual(s.returncode, 0, s.stdout + s.stderr)
        self.assertEqual((self.ev / ".local/state/yourkiosk-otomasyon/nobetci-dal")
                         .read_text(encoding="utf-8").strip(), "duzeltme/dal")
        self.assertTrue((self.kod_depo / "DAL.txt").is_file(), "klon düzeltme dalından olmalı")

    def test_gecersiz_dal_reddedilir(self):
        for kotu in ("a..b", "a b", "-x"):
            with self.subTest(kotu=kotu):
                s = self._calistir("--dal", kotu)
                self.assertEqual(s.returncode, 2, s.stdout + s.stderr)
                self.assertIn("geçersiz --dal", s.stderr)


class BakimServisTesti(BakimHataGorunurluguTesti):
    """Kurulum sonrası servis GERÇEKTEN yeni koddan kalkmalı.

    27 Ekim: bakım betiği yalnız birim dosyasını yazıyordu; eski ExecStart (insan deposu, tavansız)
    çalışmaya devam ediyor, OOM döngüsü sürüyordu. Artık `reset-failed` + `restart` yapılır ve
    servis ayağa kalkmazsa çıkış 9 + journal/status çıktısı verilir. systemd'ye dokunmamak için
    `systemctl`/`loginctl` sahte (stub) — gerçek makinede hiçbir birim değişmez.
    """

    def setUp(self):
        super().setUp()
        self.stub = self.kok / "stub"
        self.stub.mkdir()
        self.kayit = self.kok / "systemctl.log"
        (self.stub / "systemctl").write_text(
            "#!/usr/bin/env bash\n"
            'echo "$*" >> "' + str(self.kayit) + '"\n'
            # `show -p MainPID --value`: birimin ANA SÜRECİ. Testler `STUB_MAINPID` ile
            # "bu kabuk birimin içinde mi" sorusunu DENETLENEBİLİR hâle getirir (27 Ekim i5 bulgusu:
            # eski ölçüt cgroup metniydi → birim altında koşan her test "içeride" sayılıyordu).
            'case "$*" in *"MainPID"*) echo "${STUB_MAINPID:-999999}"; exit 0 ;; esac\n'
            'for a in "$@"; do\n'
            '  if [ "$a" = "is-active" ]; then\n'
            '    if [ "${STUB_AKTIF:-0}" = "1" ]; then echo active; exit 0; fi\n'
            '    echo inactive; exit 3\n'
            '  fi\n'
            "done\n"
            "exit 0\n", encoding="utf-8")
        (self.stub / "loginctl").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        (self.stub / "systemd-run").write_text(
            "#!/usr/bin/env bash\n"
            'echo "systemd-run $*" >> "' + str(self.kayit) + '"\n'
            "exit 0\n", encoding="utf-8")
        for ad in ("systemctl", "loginctl", "systemd-run"):
            (self.stub / ad).chmod(0o755)

    def _calistir(self, *ek: str, atla: bool = False, aktif: bool = True,
                  mainpid: int | None = None) -> subprocess.CompletedProcess:
        ortam = {**os.environ, **GIT_ENV, "HOME": str(self.ev),
                 "NOBETCI_UZAK": str(self.kurulum.origin),
                 "NOBETCI_KOD_DEPO": str(self.kod_depo),
                 "PATH": f"{self.stub}:{os.environ.get('PATH', '')}",
                 "STUB_AKTIF": "1" if aktif else "0"}
        if mainpid is not None:
            ortam["STUB_MAINPID"] = str(mainpid)
        if atla:
            ortam["NOBETCI_SISTEMD_ATLA"] = "1"
        return subprocess.run(["bash", str(self.kaynak / "otomasyon" / "betik" / "nobetci-bakim.sh"),
                               "i5", *ek], capture_output=True, text=True, timeout=180, env=ortam)

    def test_kurulum_sonrasi_servis_yeniden_baslatilir(self):
        s = self._calistir()
        self.assertEqual(s.returncode, 0, s.stdout + s.stderr)
        kayit = self.kayit.read_text(encoding="utf-8")
        self.assertIn("reset-failed", kayit, "OOM döngüsü start limitini sıfırlamadan restart olmaz")
        self.assertIn("restart", kayit)
        self.assertIn("aktif", s.stdout)

    def test_servis_ayaga_kalkmazsa_hata_verir(self):
        s = self._calistir(aktif=False)
        self.assertEqual(s.returncode, 9, s.stdout + s.stderr)
        self.assertIn("servis başlatılamadı", s.stderr)
        self.assertIn("journalctl --user -u", s.stderr)

    def test_birim_icindeysek_gecikmeli_devralma(self):
        """MainPID soy ağacımızda ise hemen restart KENDİMİZİ öldürür → gecikmeli devralma.

        27 Ekim i5 bulgusu: 'içeride miyim' ölçütü cgroup METNİNDE birim adını aramaktı; birim
        altında koşan HER süreç (i5'in otomasyon testleri) 'içeride' sayılıyordu. Yeni ölçüt:
        MainPID soy ağacında mı? Bu test MainPID'i test sürecinin kendisi verir → atalarında.
        """
        s = self._calistir(mainpid=os.getpid())
        self.assertEqual(s.returncode, 0, s.stdout + s.stderr)
        self.assertIn("gecikmeli devralma", s.stdout)
        kayit = self.kayit.read_text(encoding="utf-8")
        self.assertNotIn(" reset-failed", kayit, "içerideyken hemen restart denenmemeli")
        self.assertIn("systemd-run", kayit)

    def test_birim_disindaysak_hemen_restart(self):
        """MainPID soy ağacımızda DEĞİLSE (terminalden çalıştırma) hemen restart edilir."""
        s = self._calistir(mainpid=999999)
        self.assertEqual(s.returncode, 0, s.stdout + s.stderr)
        self.assertIn("yeni koddan yeniden başlatıldı", s.stdout)
        self.assertNotIn("gecikmeli devralma", s.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
