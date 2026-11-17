"""CLI doctor/install testleri."""

from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK.parents[1]))
from agents.driver import cli, config  # noqa: E402


class CliTesti(unittest.TestCase):
    def _cfg(self, t: Path) -> Path:
        tok = t / "a.token"
        tok.write_text("x" * 20, encoding="utf-8")
        tok.chmod(0o600)
        cfg = t / "i.toml"
        cfg.write_text(f"""
instance = "test"
repo = "s/p"
base_branch = "main"
state_dir = "{t}/state"
workdir = "{t}/work"
skills_root = "{t}/skills"
[[agents]]
name = "dev"
role = "developer"
machine = "yerel"
token_file = "{tok}"
""", encoding="utf-8")
        return cfg

    def test_doctor_ve_install(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as d:
            t = Path(d)
            cfg = self._cfg(t)
            with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(t / "cfg")}):
                out = io.StringIO()
                with redirect_stdout(out):
                    self.assertEqual(cli.doctor(str(cfg)), 0, out.getvalue())
                    self.assertEqual(cli.install(str(cfg), kuru=True), 0)
                metin = out.getvalue()
            self.assertIn("Restart=on-failure", metin)
            self.assertIn("StartLimitIntervalSec=0", metin)
            self.assertIn("OnFailure=agents-notify@test.service", metin)


if __name__ == "__main__":
    unittest.main(verbosity=2)
