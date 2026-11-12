"""otonom_tik — koordinatör karar ve commit doğrulama testleri (ağ/bwrap gerekmez)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import io
import unittest
from pathlib import Path
from unittest import mock

BETIK_DIZIN = Path(__file__).resolve().parents[1]
KOK = BETIK_DIZIN.parents[1]
sys.path.insert(0, str(BETIK_DIZIN))
import otonom_tik  # noqa: E402


def _pr(sha: str = "a" * 40, no: int = 97) -> dict:
    return {"number": no, "head": {"sha": sha, "ref": "dsh/test", "repo": {"full_name": "hakkisabah/yourkiosk"}},
            "base": {"ref": "main"}, "title": "test"}


def _durum(state: str) -> dict:
    return {"state": state, "description": "[v2] test"}


class KararTesti(unittest.TestCase):
    def test_i5_yoksa_bekle(self):
        k = otonom_tik.karar_ver(_pr(), {}, {})
        self.assertEqual(k["eylem"], "bekle")

    def test_i5_sorun_duzelt(self):
        k = otonom_tik.karar_ver(_pr(), {"guvenlik/inceleme": _durum("failure")}, {})
        self.assertEqual((k["eylem"], k["kaynak"]), ("duzelt", "i5"))

    def test_i5_onay_i3_yoksa_bekle(self):
        k = otonom_tik.karar_ver(_pr(), {"guvenlik/inceleme": _durum("success")}, {})
        self.assertEqual(k["eylem"], "bekle")

    def test_i3_duzeltme_duzelt(self):
        k = otonom_tik.karar_ver(_pr(), {"guvenlik/inceleme": _durum("success"),
                                         "guvenlik/karar": _durum("failure")}, {})
        self.assertEqual((k["eylem"], k["kaynak"]), ("duzelt", "i3"))

    def test_i3_kabul_bitti(self):
        k = otonom_tik.karar_ver(_pr(), {"guvenlik/inceleme": _durum("success"),
                                         "guvenlik/karar": _durum("success")}, {})
        self.assertEqual(k["eylem"], "bitti")

    def test_head_deneme_siniri_engel(self):
        pr = _pr()
        kayit = {"sha": "a" * 40, "sayi": 5}
        k = otonom_tik.karar_ver(pr, {"guvenlik/inceleme": _durum("failure")}, kayit)
        self.assertEqual(k["eylem"], "engel")

    def test_toplam_deneme_siniri_engel(self):
        pr = _pr()
        kayit = {"sha": "b" * 40, "sayi": 0, "toplam": 8}
        k = otonom_tik.karar_ver(pr, {"guvenlik/inceleme": _durum("failure")}, kayit)
        self.assertEqual(k["eylem"], "engel")

    def test_head_guncel_mi(self):
        a = _pr("a" * 40)
        b = _pr("b" * 40)
        self.assertTrue(otonom_tik.head_guncel_mi(a, a))
        self.assertFalse(otonom_tik.head_guncel_mi(a, b))
        self.assertFalse(otonom_tik.head_guncel_mi(a, {}))

    def test_damgasiz_i5_bekle(self):
        k = otonom_tik.karar_ver(
            _pr(), {"guvenlik/inceleme": {"state": "failure", "description": ""}}, {})
        self.assertEqual(k["eylem"], "bekle")

    def test_eski_damgali_i5_bekle(self):
        k = otonom_tik.karar_ver(
            _pr(), {"guvenlik/inceleme": {"state": "failure", "description": "[v1] sorun"}}, {})
        self.assertEqual(k["eylem"], "bekle")

    def test_durumlar_en_yeni_statusu_tutar(self):
        govde = {"statuses": [
            {"context": "guvenlik/inceleme", "state": "failure", "description": "[v2] sorun"},
            {"context": "guvenlik/inceleme", "state": "success", "description": "[v2] onay"},
        ]}
        with mock.patch.object(otonom_tik, "api", return_value=(200, govde)):
            d = otonom_tik.durumlar("t", "sha")
        self.assertEqual(d["guvenlik/inceleme"]["state"], "failure")

    def test_varsayilan_token_kapi_tokeni_degil(self):
        self.assertEqual(otonom_tik.TOKEN_YOLU.name, "github-otonom.token")

    def test_kayit_sifirlama_sha_degisince(self):
        kayit = {"sha": "a" * 40, "sayi": 4, "toplam": 4}
        otonom_tik._kayit_sifirla(kayit, "b" * 40)
        self.assertEqual(kayit["sayi"], 0)
        self.assertEqual(kayit["toplam"], 4)


class PrFiltresiTesti(unittest.TestCase):
    def test_virgullu_liste(self):
        with mock.patch.dict(os.environ, {"OTONOM_SADECE_PR": "97, 99"}):
            self.assertEqual(otonom_tik.sadece_pr_kumesi(), {97, 99})

    def test_bos_liste_tumu(self):
        with mock.patch.dict(os.environ, {"OTONOM_SADECE_PR": ""}):
            self.assertEqual(otonom_tik.sadece_pr_kumesi(), set())


class SirtaraTesti(unittest.TestCase):
    def test_eklenen_satirda_token(self):
        diff = '+TOKEN = "abcdefghijklmnop1234"\n-eski\n'
        self.assertTrue(otonom_tik._sir_tara(diff))

    def test_temiz_diff(self):
        self.assertEqual(otonom_tik._sir_tara("+print('merhaba')\n"), "")


class CommitDenetleTesti(unittest.TestCase):
    def setUp(self):
        self.dizin = tempfile.TemporaryDirectory()
        self.addCleanup(self.dizin.cleanup)
        self.depo = Path(self.dizin.name) / "depo"
        self.depo.mkdir()
        self.eski_klon = otonom_tik.KLON
        otonom_tik.KLON = self.depo
        self.addCleanup(lambda: setattr(otonom_tik, "KLON", self.eski_klon))
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "test@local")
        self.git("config", "user.name", "test")
        (self.depo / "ilk.txt").write_text("x\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-qm", "ilk")
        self.bas = self.git("rev-parse", "HEAD").stdout.strip()

    def git(self, *arg: str):
        return subprocess.run(["git", "-C", str(self.depo), *arg],
                              capture_output=True, text=True)

    def _commit(self, dosya: str, icerik: str, mesaj: str = "degisiklik"):
        hedef = self.depo / dosya
        hedef.parent.mkdir(parents=True, exist_ok=True)
        hedef.write_text(icerik, encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-qm", mesaj)

    def test_temiz_commit_gecer(self):
        self._commit("yeni.txt", "merhaba\n")
        self.assertEqual(otonom_tik.commit_denetle(self.bas), "")

    def test_kirli_agac_reddedilir(self):
        self._commit("yeni.txt", "merhaba\n")
        (self.depo / "kaydedilmemis.txt").write_text("x\n", encoding="utf-8")
        self.assertIn("temiz değil", otonom_tik.commit_denetle(self.bas))

    def test_commit_yoksa_reddedilir(self):
        self.assertIn("yeni commit yok", otonom_tik.commit_denetle(self.bas))

    def test_merge_commit_reddedilir(self):
        self.git("checkout", "-qb", "yan")
        self._commit("yan.txt", "y\n")
        self.git("checkout", "-q", "main")
        self._commit("ana.txt", "a\n")
        self.git("merge", "--no-ff", "-m", "merge", "yan")
        self.assertIn("merge commit", otonom_tik.commit_denetle(self.bas))

    def test_yasak_yol_reddedilir(self):
        self._commit(".github/workflows/ci.yml", "on: push\n")
        self.assertIn("yasak yol", otonom_tik.commit_denetle(self.bas))

    def test_sir_dosyasi_reddedilir(self):
        self._commit(".env", "X=1\n")
        self.assertIn("sır dosyası", otonom_tik.commit_denetle(self.bas))

    def test_sir_satiri_reddedilir(self):
        self._commit("ayar.py", 'API_KEY = "abcdefghijklmnop1234"\n')
        self.assertIn("sır benzeri", otonom_tik.commit_denetle(self.bas))


    def _temizle(self):
        self.git("reset", "--hard", self.bas)
        self.git("clean", "-fd", "--quiet")

    def test_git_dizini_degistirilirse_reddedilir(self):
        gd = Path(subprocess.run(
            ["git", "-C", str(self.depo), "rev-parse", "--absolute-git-dir"],
            capture_output=True, text=True).stdout.strip())
        self._commit("yeni.txt", "x")
        eski = self.depo / ".git-eski"
        eski.mkdir()
        try:
            os.rename(self.depo / ".git", eski)
            (self.depo / ".git").write_text("gitdir: /tmp/sahte", encoding="utf-8")
            neden = otonom_tik.commit_denetle(self.bas, gd)
        finally:
            (self.depo / ".git").unlink()
            os.rename(eski, self.depo / ".git")
        self.assertIn("gerçek dizin", neden)

    def test_yasak_yollarin_tamami(self):
        for yol in otonom_tik.YASAK_YOLLAR:
            with self.subTest(yol=yol):
                self._temizle()
                hedef = yol + "x.txt" if yol.endswith("/") else yol
                dosya = self.depo / hedef
                dosya.parent.mkdir(parents=True, exist_ok=True)
                dosya.write_text("x", encoding="utf-8")
                self.git("add", "-A")
                self.git("commit", "-qm", "deneme")
                neden = otonom_tik.commit_denetle(self.bas)
                if yol == ".gitattributes":
                    self.assertIn("gitattributes", neden)
                else:
                    self.assertIn("yasak yol", neden)

    def test_binary_dosyada_sir_yakalanir(self):
        self._commit("sir.bin", "GIZLI" + chr(0) + "ghp_" + "a" * 30 + chr(10))
        self.assertIn("sır benzeri", otonom_tik.commit_denetle(self.bas))

    def test_info_attributes_reddedilir(self):
        self._commit("normal.txt", "x")
        (self.depo / ".git" / "info" / "attributes").write_text("*.bin -diff", encoding="utf-8")
        self.assertIn("attributes", otonom_tik.commit_denetle(self.bas))

    def test_replace_ref_reddedilir(self):
        self._commit("normal.txt", "x")
        subprocess.run(["git", "-C", str(self.depo), "replace", "HEAD", self.bas], check=True)
        self.assertIn("replace ref", otonom_tik.commit_denetle(self.bas))

    def test_ic_ice_gitattributes_reddedilir(self):
        self._commit("sub/.gitattributes", "*.py -diff")
        self.assertIn("gitattributes", otonom_tik.commit_denetle(self.bas))

    def test_satir_sonu_iceren_yasak_yol_reddedilir(self):
        dosya = self.depo / ".github" / "workflows" / ("a" + chr(10) + "b.yml")
        dosya.parent.mkdir(parents=True, exist_ok=True)
        dosya.write_text("on: push", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-qm", "satir sonu")
        self.assertIn("yasak yol", otonom_tik.commit_denetle(self.bas))

    def test_git_meta_uyusmazsa_reddedilir(self):
        gd = Path(subprocess.run(
            ["git", "-C", str(self.depo), "rev-parse", "--absolute-git-dir"],
            capture_output=True, text=True).stdout.strip())
        self._commit("yeni.txt", "x")
        neden = otonom_tik.commit_denetle(self.bas, gd, (0, 0, "yanlis"))
        self.assertIn("inode", neden)

    def test_yeniden_adlandirma_yasak_yolu_kacirmaz(self):
        hedef = self.depo / "otomasyon" / "betik" / "otonom_tik.py"
        hedef.parent.mkdir(parents=True, exist_ok=True)
        hedef.write_text("x", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-qm", "ekle")
        bas2 = self.git("rev-parse", "HEAD").stdout.strip()
        self.git("mv", "otomasyon/betik/otonom_tik.py", "foo.py")
        self.git("commit", "-qm", "rename")
        self.assertIn("yasak yol", otonom_tik.commit_denetle(bas2))

    def test_calisma_agacini_temizler(self):
        (self.depo / "ilk.txt").write_text("degisti", encoding="utf-8")
        (self.depo / "artik.txt").write_text("x", encoding="utf-8")
        otonom_tik.calisma_agacini_temizle("HEAD")
        self.assertEqual(self.git("status", "--porcelain").stdout.strip(), "")
        self.assertEqual((self.depo / "ilk.txt").read_text(encoding="utf-8"), "x" + chr(10))

    def test_ara_committeki_sir_yakalanir(self):
        self._commit("sir.txt", "ghp_" + "a" * 30)
        self.git("rm", "-q", "sir.txt")
        self.git("commit", "-qm", "sirri sil")
        self.assertIn("sır benzeri", otonom_tik.commit_denetle(self.bas))

    def test_buyuk_diff_reddedilir(self):
        self._commit("buyuk.txt", "x" * 500)
        with mock.patch.object(otonom_tik, "AZAMI_DIFF_BAYT", 100):
            neden = otonom_tik.commit_denetle(self.bas)
        self.assertIn("çok büyük", neden)

    def test_buyuk_commit_mesaji_reddedilir(self):
        self.git("commit", "--allow-empty", "-qm", "a" * 5000)
        with mock.patch.object(otonom_tik, "AZAMI_MESAJ_BAYT", 100):
            neden = otonom_tik.commit_denetle(self.bas)
        self.assertIn("commit mesajı çok büyük", neden)

    def test_commit_mesajinda_sir_reddedilir(self):
        self._commit("normal.txt", "x", mesaj="ghp_" + "a" * 30)
        self.assertIn("commit mesajında", otonom_tik.commit_denetle(self.bas))

class GelistiriciRunnerTesti(unittest.TestCase):
    """Geliştirici runner: repo rw, ev/sır gizli, ağ/systemd kapalı, FD ve PID temiz."""

    @unittest.skipUnless(shutil.which("bwrap"), "bwrap yok")
    def test_repo_rw_home_gizli_ag_kapali_fd_temiz(self):
        runner = KOK / "otomasyon" / "dsh-bwrap-gelistirici"
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as d:
            home = Path(d) / "home"
            home.mkdir()
            depo = home / "clone"
            depo.mkdir(parents=True)
            subprocess.run(["git", "-C", str(depo), "init", "-q"], check=True)
            (depo / ".git" / "otonom-kopya").write_text("1", encoding="utf-8")
            (depo / "ok").write_text("OK", encoding="utf-8")
            (depo / "AGENTS.md").write_text("PR_RULES", encoding="utf-8")
            kurallar = Path(d) / "trusted-AGENTS.md"
            kurallar.write_text("TRUSTED_RULES", encoding="utf-8")
            (home / ".bashrc").write_text("CANARY", encoding="utf-8")
            gizli = home / ".config" / "hermes-secrets"
            gizli.mkdir(parents=True)
            (gizli / "token").write_text("CANARY_TOKEN", encoding="utf-8")
            paket = Path(d) / "paket"
            paket.mkdir()
            (paket / "p").write_text("P", encoding="utf-8")
            hedef = depo / "yeni.txt"
            komut = [
                str(runner), "--ro-bind", "/", "/", "--dev", "/dev",
                "--die-with-parent", "--",
                "bash", "-c",
                'cd "$HOME/clone"; '
                'test -r "$HOME/.bashrc" && echo HOME_OK || echo HOME_GIZLI; '
                'test -r "$HOME/.config/hermes-secrets/token" && echo TOKEN_OK || echo TOKEN_YOK; '
                f'cat {depo}/ok >/dev/null && echo REPO_OK; '
                f'echo yeni > {hedef} && echo REPO_YAZ_OK; '
                'cat AGENTS.md 2>/dev/null || echo AGENTS_YOK; '
                'cat "$PAKET_DIR/p" 2>/dev/null || echo PAKET_YOK; '
                'timeout 3 systemd-run --user --scope true >/dev/null 2>&1; echo SYSTEMD=$?; '
                'test -S /run/docker.sock && echo DOCKER_SOCK || echo DOCKER_YOK; '
                'for f in /proc/self/fd/*; do h=$(readlink -f "$f/.." 2>/dev/null || true); '
                'case "$h" in /home/*|/var/tmp/*) echo FD_SIZINTI:$h;; esac; done; echo FD_CHECK; '
                'env | grep -E "SECRET_CANARY|DEEPSEEK_API_KEY" && echo ENV_SIZINTI || echo ENV_TEMIZ; '
                'test -n "$PAKET_DIR" && echo PAKET_ENV_OK || echo PAKET_ENV_YOK; '
                'mv .git .git-x 2>/dev/null; echo GIT_RENAME=$?; '
                'echo x > .git/config 2>/dev/null; echo CONFIG_YAZ2=$?; '
                'echo x > .git/hooks/pre-push 2>/dev/null; echo HOOK_YAZ=$?; '
                'git config user.email x@y 2>/dev/null; echo CONFIG_YAZ=$?; '
                'git add yeni.txt && git commit -qm "sandbox commit" && echo COMMIT_OK || echo COMMIT_YOK',
            ]
            env = {k: v for k, v in os.environ.items()
                   if k not in ("KARAR_DIR", "DSH_KARAR_DIR", "DSH_HOME")}
            env.update({"HOME": str(home), "GELISTIRICI_DEPO": str(depo),
                        "PAKET_DIR": str(paket), "DSH_SHADOW_DIR": d,
                        "GELISTIRICI_KURALLAR": str(kurallar),
                        "SECRET_CANARY": "canary-123",
                        "DEEPSEEK_API_KEY": "sk-test-123"})
            s = subprocess.run(komut, capture_output=True, text=True, timeout=40,
                               env=env, cwd=str(home))
            self.assertIn("REPO_OK", s.stdout, s.stderr[:400])
            self.assertIn("REPO_YAZ_OK", s.stdout)
            self.assertTrue(hedef.exists())
            self.assertNotIn("HOME_OK", s.stdout)
            self.assertNotIn("TOKEN_OK", s.stdout)
            self.assertNotRegex(s.stdout, r"SYSTEMD=0")
            self.assertNotIn("DOCKER_SOCK", s.stdout)
            self.assertIn("FD_CHECK", s.stdout)
            self.assertNotIn("FD_SIZINTI", s.stdout)
            self.assertIn("P", s.stdout)
            self.assertIn("TRUSTED_RULES", s.stdout)
            self.assertNotIn("PR_RULES", s.stdout)
            self.assertIn("ENV_TEMIZ", s.stdout)
            self.assertNotIn("ENV_SIZINTI", s.stdout)
            self.assertIn("PAKET_ENV_OK", s.stdout)
            self.assertIn("HOOK_YAZ=1", s.stdout)
            self.assertNotIn("GIT_RENAME=0", s.stdout)
            self.assertNotIn("CONFIG_YAZ2=0", s.stdout)
            self.assertNotIn("CONFIG_YAZ=0", s.stdout)
            self.assertIn("COMMIT_OK", s.stdout)

    @unittest.skipUnless(shutil.which("bwrap"), "bwrap yok")
    def test_eksik_pid_ve_proc_eklenir(self):
        runner = KOK / "otomasyon" / "dsh-bwrap-gelistirici"
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as d:
            t = Path(d)
            home = t / "home"
            home.mkdir()
            depo = home / "clone"
            depo.mkdir(parents=True)
            subprocess.run(["git", "-C", str(depo), "init", "-q"], check=True)
            (depo / ".git" / "otonom-kopya").write_text("1", encoding="utf-8")
            (depo / "AGENTS.md").write_text("PR", encoding="utf-8")
            kurallar = t / "trusted-AGENTS.md"
            kurallar.write_text("TRUSTED", encoding="utf-8")
            sahte = t / "bin"
            sahte.mkdir()
            kayit = t / "bwrap-args.txt"
            bwrap = sahte / "bwrap"
            bwrap.write_text("#!/bin/sh" + chr(10) + 'printf "%s" "$@" > ' + str(kayit) + chr(10),
                             encoding="utf-8")
            bwrap.chmod(0o755)
            env = {"PATH": str(sahte) + ":/usr/bin:/bin", "HOME": str(home),
                   "GELISTIRICI_DEPO": str(depo), "GELISTIRICI_KURALLAR": str(kurallar),
                   "DSH_SHADOW_DIR": str(t)}
            s = subprocess.run([str(runner), "--ro-bind", "/", "/", "--dev", "/dev", "--"],
                               env=env, cwd=str(home), capture_output=True, text=True, timeout=30)
            self.assertEqual(s.returncode, 0, s.stderr)
            args = kayit.read_text(encoding="utf-8")
            self.assertIn("--unshare-pid", args)
            self.assertIn("--proc", args)
            self.assertIn("/proc", args)
            self.assertIn("--clearenv", args)
            self.assertIn("--setenv", args)


class AjanCalistirTesti(unittest.TestCase):
    """ajan_calistir, Popen'e güvenilir kurallar ve depo yolu içeren env vermeli."""

    @unittest.skipUnless((Path.home() / ".dsh" / "profiles" / "headless" / "cordis.patch.yml").is_file(),
                         "headless profili yok")
    def test_popen_env_gelistirici_kurallar(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as d:
            t = Path(d)
            ev = t / "ev"
            ev.mkdir()
            klon = t / "klon"
            klon.mkdir()
            paket = t / "paket"
            paket.mkdir()
            (paket / "pr-97.md").write_text("x", encoding="utf-8")
            dsh = t / "dsh"
            (dsh / "apps" / "cli" / "lib").mkdir(parents=True)
            (dsh / "apps" / "cli" / "lib" / "bin.js").write_text("", encoding="utf-8")
            with mock.patch.multiple(otonom_tik, KLON=klon, EV=ev, PAKET_KLASORU=paket,
                                     DSH_CHECKOUT=dsh, PROFIL="headless"),                  mock.patch.object(otonom_tik, "dsh_home_hazirla", return_value=ev),                  mock.patch.object(otonom_tik.os, "access", return_value=True),                  mock.patch.object(otonom_tik.subprocess, "Popen") as popen:
                class SahteSurec:
                    def __init__(self):
                        self.stdout = io.StringIO("rapor")
                        self.stderr = io.StringIO("")
                        self.stdin = io.StringIO()
                        self.returncode = 0
                        self.pid = 1234

                    def wait(self, timeout=None):
                        return 0

                popen.return_value = SahteSurec()
                kod, cikti, asim = otonom_tik.ajan_calistir(paket)
        self.assertEqual((kod, cikti, asim), (0, "rapor", False))
        komut = popen.call_args.args[0]
        env = popen.call_args.kwargs["env"]
        self.assertIn("--profile", komut)
        self.assertIn("headless", komut)
        self.assertEqual(env["GELISTIRICI_KURALLAR"], str(otonom_tik.KOK / "AGENTS.md"))
        self.assertEqual(env["PAKET_DIR"], str(paket))


class KancaTesti(unittest.TestCase):
    """Güvenilir git komutları repo hook'larını çalıştırmamalı."""

    def test_guvenilir_git_hook_calistirmaz(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as d:
            depo = Path(d)
            subprocess.run(["git", "-C", str(depo), "init", "-q", "-b", "main"], check=True)
            subprocess.run(["git", "-C", str(depo), "-c", "user.email=t@t",
                            "-c", "user.name=t", "commit", "--allow-empty", "-qm", "x"], check=True)
            isaret = depo / "kanca-calisti"
            kanca = depo / ".git" / "hooks" / "post-checkout"
            kanca.write_text("#!/bin/sh" + chr(10) + "touch " + str(isaret) + chr(10),
                             encoding="utf-8")
            kanca.chmod(0o755)
            eski = otonom_tik.KLON
            otonom_tik.KLON = depo
            try:
                otonom_tik.git("checkout", "-B", "yeni-dal")
            finally:
                otonom_tik.KLON = eski
            self.assertFalse(isaret.exists(), "hook güvenilir git komutunda çalıştı")

    def test_aktif_hook_commit_denetiminde_reddedilir(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as d:
            depo = Path(d)
            subprocess.run(["git", "-C", str(depo), "init", "-q", "-b", "main"], check=True)
            subprocess.run(["git", "-C", str(depo), "-c", "user.email=t@t",
                            "-c", "user.name=t", "commit", "--allow-empty", "-qm", "x"], check=True)
            bas = subprocess.run(["git", "-C", str(depo), "rev-parse", "HEAD"],
                                 capture_output=True, text=True).stdout.strip()
            (depo / "yeni.txt").write_text("x", encoding="utf-8")
            subprocess.run(["git", "-C", str(depo), "add", "-A"], check=True)
            subprocess.run(["git", "-C", str(depo), "-c", "user.email=t@t",
                            "-c", "user.name=t", "commit", "-qm", "y"], check=True)
            kanca = depo / ".git" / "hooks" / "evil"
            kanca.write_text("#!/bin/sh" + chr(10), encoding="utf-8")
            kanca.chmod(0o755)
            eski = otonom_tik.KLON
            otonom_tik.KLON = depo
            try:
                neden = otonom_tik.commit_denetle(bas)
            finally:
                otonom_tik.KLON = eski
            self.assertIn("git hook", neden)


class PushTesti(unittest.TestCase):
    def test_main_dalina_push_reddedilir(self):
        with self.assertRaises(otonom_tik.TikHatasi):
            otonom_tik.push_et("main")

    def test_pre_push_hook_calistirmaz(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as d:
            t = Path(d)
            uzak = t / "uzak.git"
            subprocess.run(["git", "init", "--bare", "-q", str(uzak)], check=True)
            klon = t / "klon"
            subprocess.run(["git", "clone", "-q", str(uzak), str(klon)], check=True)
            subprocess.run(["git", "-C", str(klon), "-c", "user.email=t@t",
                            "-c", "user.name=t", "commit", "--allow-empty", "-qm", "ilk"], check=True)
            isaret = t / "push-kanca"
            kanca = klon / ".git" / "hooks" / "pre-push"
            kanca.write_text("#!/bin/sh" + chr(10) + "touch " + str(isaret) + chr(10),
                             encoding="utf-8")
            kanca.chmod(0o755)
            token = t / "token"
            token.write_text("x", encoding="utf-8")
            eski = (otonom_tik.KLON, otonom_tik.PUSH_TABANI, otonom_tik.TOKEN_YOLU)
            otonom_tik.KLON, otonom_tik.PUSH_TABANI, otonom_tik.TOKEN_YOLU = klon, str(uzak), token
            try:
                sha = otonom_tik.push_et("dsh/test")
            finally:
                otonom_tik.KLON, otonom_tik.PUSH_TABANI, otonom_tik.TOKEN_YOLU = eski
            self.assertFalse(isaret.exists(), "pre-push hook çalıştı")
            self.assertEqual(len(sha), 40)
            kontrol = subprocess.run(["git", "--git-dir", str(uzak), "rev-parse",
                                      "refs/heads/dsh/test"], capture_output=True, text=True)
            self.assertEqual(kontrol.returncode, 0)


class KotaTesti(unittest.TestCase):
    def test_gunluk_sifirlama_ve_tavan(self):
        durum = {}
        gunluk = otonom_tik.gunluk_kota(durum)
        self.assertEqual(gunluk["oturum"], 0)
        gunluk["oturum"] = otonom_tik.GUNLUK_AZAMI - 1
        self.assertFalse(otonom_tik.kota_doldu(durum))
        gunluk["oturum"] = otonom_tik.GUNLUK_AZAMI
        self.assertTrue(otonom_tik.kota_doldu(durum))
        eski = {"gunluk": {"tarih": "2000-01-01", "oturum": 99}}
        self.assertEqual(otonom_tik.gunluk_kota(eski)["oturum"], 0)


class KapiYorumuTesti(unittest.TestCase):
    """Yalnız izinli kapı hesabının, imzayla başlayan yorumu pakete girer."""

    @staticmethod
    def _yorum(login, body):
        return {"user": {"login": login}, "body": body}

    def test_izinli_hesap_alınır(self):
        lst = [self._yorum("yabanci", "🔍 **i5 — güvenlik incelemesi** — sahte"),
               self._yorum("hakkisabah", "🔍 **i5 — güvenlik incelemesi** — gerçek")]
        self.assertIn("gerçek", otonom_tik.son_kapi_yorumu(lst, "i5", "hakkisabah"))

    def test_sahte_hesap_alinmaz(self):
        lst = [self._yorum("yabanci", "🔍 **i5 — güvenlik incelemesi** — sahte")]
        self.assertEqual(otonom_tik.son_kapi_yorumu(lst, "i5", "hakkisabah"), "")

    def test_imza_basta_degilse_alinmaz(self):
        lst = [self._yorum("hakkisabah", "önce laf, sonra 🔍 **i5 — güvenlik incelemesi**")]
        self.assertEqual(otonom_tik.son_kapi_yorumu(lst, "i5", "hakkisabah"), "")


class KurulumTesti(unittest.TestCase):
    def test_kuru_dsh_yokken_uyarir(self):
        ortam = {**os.environ, "DSH_CHECKOUT": "/nonexistent-dsh"}
        s = subprocess.run(["bash", str(KOK / "otomasyon" / "otonom-kur.sh"), "--kuru"],
                           capture_output=True, text=True, timeout=120, env=ortam)
        self.assertEqual(s.returncode, 0, s.stderr)
        self.assertIn("UYARI", s.stdout)

    def test_kuru_cikti_profil_runner_timer_icerir(self):
        s = subprocess.run(["bash", str(KOK / "otomasyon" / "otonom-kur.sh"), "--kuru"],
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(s.returncode, 0, s.stderr)
        self.assertIn("dsh-bwrap-gelistirici", s.stdout)
        self.assertIn("otonom-gelistirici", s.stdout)
        self.assertIn("OnUnitInactiveSec=20min", s.stdout)
        self.assertIn("otonom koordinator bekci zamanlayici", s.stdout)
        self.assertIn("OnUnitActiveSec=10min", s.stdout)
        for _satir in ("PrivateTmp=true", "ProtectSystem=strict",
                          "ProtectHome=read-only", "ReadWritePaths=",
                          "RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX"):
            self.assertIn(_satir, s.stdout)
        for satir in ("PrivateTmp=true", "ProtectSystem=strict", "ProtectHome=read-only",
                      "ReadWritePaths=", "RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX"):
            self.assertIn(satir, s.stdout)


    def test_bilinmeyen_secenek_reddedilir(self):
        s = subprocess.run(["bash", str(KOK / "otomasyon" / "otonom-kur.sh"), "--yok"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(s.returncode, 2)

    def test_gecersiz_aralik_reddedilir(self):
        for deger in ("abc", "0", "4", "1441"):
            s = subprocess.run(["bash", str(KOK / "otomasyon" / "otonom-kur.sh"),
                                f"--aralik={deger}", "--kuru"],
                               capture_output=True, text=True, timeout=60)
            self.assertEqual(s.returncode, 2, deger)


class SurumTesti(unittest.TestCase):
    def test_tirnakli_ve_tirnaksiz_surum(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as d:
            t = Path(d)
            (t / "otomasyon" / "betik").mkdir(parents=True)
            eski = otonom_tik.KOK
            otonom_tik.KOK = t
            try:
                for metin, beklenen in (('INCELEME_SURUMU = "3"', 3),
                                        ("INCELEME_SURUMU = 4", 4)):
                    (t / "otomasyon" / "betik" / "nobetci.py").write_text(
                        metin, encoding="utf-8")
                    self.assertEqual(otonom_tik.denetim_surumu(), beklenen)
            finally:
                otonom_tik.KOK = eski


if __name__ == "__main__":
    unittest.main(verbosity=2)
