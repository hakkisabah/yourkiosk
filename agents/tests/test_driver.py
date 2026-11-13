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

import config  # noqa: E402
import state  # noqa: E402
import systemd  # noqa: E402


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
