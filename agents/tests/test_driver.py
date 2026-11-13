"""agents driver — config, state, systemd."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "driver"))
sys.path.insert(0, str(KOK / "install"))
sys.path.insert(0, str(KOK.parents[1]))

import config  # noqa: E402
import state  # noqa: E402
import systemd  # noqa: E402
from agents.driver import worker  # noqa: E402


class ConfigTesti(unittest.TestCase):
    def test_env_ve_instance_genisler(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as d:
            t = Path(d)
            cfg = t / "i.toml"
            cfg.write_text("""
instance = "deneme"
repo = "sahip/proje"
base_branch = "main"
state_dir = "${XDG_STATE_HOME}/a/${instance}"
workdir = "${XDG_STATE_HOME}/a/${instance}/w"
skills_root = "${XDG_DATA_HOME}/a/${instance}"
[[agents]]
name = "dev"
role = "developer"
machine = "yerel"
token_file = "${XDG_CONFIG_HOME}/a/${instance}/t"
""", encoding="utf-8")
            with mock.patch.dict(os.environ, {
                "XDG_STATE_HOME": str(t / "state"),
                "XDG_DATA_HOME": str(t / "data"),
                "XDG_CONFIG_HOME": str(t / "cfg"),
            }):
                v = config.yukle(cfg)
            self.assertEqual(v["instance"], "deneme")
            self.assertEqual(v["state_dir"], str(t / "state" / "a" / "deneme"))
            self.assertEqual(v["agents"][0]["token_file"], str(t / "cfg" / "a" / "deneme" / "t"))

    def test_sabit_yol_yok(self):
        bulgular = config.sabit_yol_denetle(KOK / "driver")
        self.assertEqual(bulgular, [])


class StateTesti(unittest.TestCase):
    def test_atomik_yaz_ve_kilit(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as d:
            with state.Durum(Path(d), "dev") as s:
                s.yaz({"durum": "GELISTIR", "pr": 5})
                self.assertEqual(s.oku()["durum"], "GELISTIR")
            with state.Durum(Path(d), "dev") as s2:
                self.assertEqual(s2.oku()["pr"], 5)


class SystemdTesti(unittest.TestCase):
    def test_dayaniklilik_ve_sabit_yol_yok(self):
        metin = systemd.servis_metni("deneme", "developer", "/usr/bin/agents run",
                                     Path("/tmp/x"), {"A": "b"})
        self.assertIn("Restart=on-failure", metin)
        self.assertIn("StartLimitIntervalSec=0", metin)
        self.assertIn("OnFailure=agents-notify@deneme.service", metin)
        self.assertNotIn("/home/", metin)
        self.assertEqual(systemd.birim_adi("deneme", "developer"),
                         "agents@deneme-developer.service")

class WizardTesti(unittest.TestCase):
    def test_n1_tek_gelistirici(self):
        import wizard
        v = wizard.uret("d", "s/p", 1, ["yerel"], Path("/tmp/t"))
        self.assertEqual([a["role"] for a in v["agents"]], ["developer"])

    def test_n3_roller(self):
        import wizard
        v = wizard.uret("d", "s/p", 3, ["a", "b", "c"], Path("/tmp/t"))
        self.assertEqual([a["role"] for a in v["agents"]],
                         ["developer", "reviewer", "decision"])
        self.assertIn('instance = "d"', wizard.toml(v))

    def test_n4_iki_reviewer(self):
        import wizard
        v = wizard.uret("d", "s/p", 4, [], Path("/tmp/t"))
        self.assertEqual([a["role"] for a in v["agents"]],
                         ["developer", "reviewer", "reviewer", "decision"])


class DshTesti(unittest.TestCase):
    def test_komut_bin_js(self):
        import dsh
        k = dsh.komut("profil")
        self.assertIn("bin.js", k[1])
        self.assertEqual(k[-1], "-")

class WizardTesti(unittest.TestCase):
    def test_n1_tek_gelistirici(self):
        import wizard
        v = wizard.uret("d", "s/p", 1, ["yerel"], Path("/tmp/t"))
        self.assertEqual([a["role"] for a in v["agents"]], ["developer"])

    def test_n3_roller(self):
        import wizard
        v = wizard.uret("d", "s/p", 3, ["a", "b", "c"], Path("/tmp/t"))
        self.assertEqual([a["role"] for a in v["agents"]],
                         ["developer", "reviewer", "decision"])
        self.assertIn('instance = "d"', wizard.toml(v))

    def test_n4_iki_reviewer(self):
        import wizard
        v = wizard.uret("d", "s/p", 4, [], Path("/tmp/t"))
        self.assertEqual([a["role"] for a in v["agents"]],
                         ["developer", "reviewer", "reviewer", "decision"])


class DshTesti(unittest.TestCase):
    def test_komut_bin_js(self):
        import dsh
        k = dsh.komut("profil")
        self.assertIn("bin.js", k[1])
        self.assertEqual(k[-1], "-")

class SandboxTesti(unittest.TestCase):
    def test_izolasyon_bayraklari(self):
        import sandbox
        a = sandbox.bwrap_argumanlari(Path("/tmp/repo"), "read-only", Path("/tmp/home"))
        for bayrak in ("--unshare-net", "--unshare-pid", "--die-with-parent", "--proc"):
            self.assertIn(bayrak, a)
        self.assertIn("--ro-bind", a)
        self.assertEqual(a[-1], "--")

class RolPlanTesti(unittest.TestCase):
    def test_gecisler(self):
        import roles
        self.assertEqual(roles.gecis(roles.GELISTIR, "push"), roles.KARAR_BEKLE)
        self.assertEqual(roles.gecis(roles.KARAR_BEKLE, "ret"), roles.GELISTIR)
        self.assertEqual(roles.gecis(roles.KARAR_BEKLE, "merge"), roles.GELISTIR)

    def test_gelistirici_ret_duzeltir(self):
        import roles
        pr = {"number": 1, "merged_at": None}
        eylem, _ = roles.gelistirici_plani(roles.GELISTIR, pr, {roles.INCELEME: "failure"}, False)
        self.assertEqual(eylem, "duzelt")

    def test_gelistirici_merge_bitti(self):
        import roles
        pr = {"number": 1, "merged_at": "2026-01-01"}
        eylem, _ = roles.gelistirici_plani(roles.KARAR_BEKLE, pr, {roles.INCELEME: "success"}, False)
        self.assertEqual(eylem, "bitti")

    def test_inceleme_yeni_head(self):
        import roles
        pr = {"number": 5}
        self.assertEqual(len(roles.inceleme_plani([pr], {})), 1)
        self.assertEqual(len(roles.inceleme_plani([pr], {5: {roles.INCELEME: "success"}})), 0)

    def test_karar_iki_onay(self):
        import roles
        pr = {"number": 5}
        d = {5: {roles.INCELEME: "success"}}
        self.assertEqual(len(roles.karar_plani([pr], d)), 1)
        d[5][roles.KARAR] = "success"
        self.assertEqual(len(roles.karar_plani([pr], d)), 0)

class GithubTesti(unittest.TestCase):
    def test_status_en_yeni(self):
        import github
        g = github.Github("s/p", "/tmp/yok")
        veri = {"statuses": [
            {"context": "guvenlik/inceleme", "state": "failure"},
            {"context": "guvenlik/inceleme", "state": "success"},
        ]}
        with mock.patch.object(g, "_istek", return_value=veri):
            d = g.durumlar("abc")
        self.assertEqual(d["guvenlik/inceleme"], "failure")

class WorkerTesti(unittest.TestCase):
    def test_slug(self):
        self.assertEqual(worker.slug("Merhaba Dünya!"), "merhaba-d-nya")
        self.assertEqual(worker.slug("   "), "gorev")

    def test_dal_adi(self):
        d = worker.dal_adi("yourkiosk", "Kapı düzeltmesi")
        self.assertTrue(d.startswith("agents/yourkiosk-"))
        self.assertNotIn(" ", d)

class KararAyiklaTesti(unittest.TestCase):
    def test_gecerli_blok(self):
        metin = ("KARAR_JSON_BEGIN abc123" + chr(10) +
                 '{"pr": 1, "sha": "x", "karar": "onay"}' + chr(10) +
                 "KARAR_JSON_END abc123")
        self.assertEqual(worker.karar_ayikla(metin, "abc123")["karar"], "onay")

    def test_nonce_uyusmazsa_none(self):
        metin = ("KARAR_JSON_BEGIN abc" + chr(10) + "{}" + chr(10) + "KARAR_JSON_END abc")
        self.assertIsNone(worker.karar_ayikla(metin, "baska"))

    def test_bozuk_json_none(self):
        metin = ("KARAR_JSON_BEGIN n" + chr(10) + "{bozuk" + chr(10) + "KARAR_JSON_END n")
        self.assertIsNone(worker.karar_ayikla(metin, "n"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
