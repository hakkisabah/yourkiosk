"""topla.py — yedek durum dizini güvenliği."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BETIK_DIZIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BETIK_DIZIN))
import topla  # noqa: E402


class YedekDizinTesti(unittest.TestCase):
    def test_uid_eki_ve_0700(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as d:
            with mock.patch.dict(os.environ, {"TMPDIR": d}):
                yol = topla.yedek_durum_dizini()
            self.assertEqual(yol.name, f"topla-{os.getuid()}")
            self.assertEqual(yol.stat().st_mode & 0o777, 0o700)

    def test_symlink_reddedilir(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as d:
            aday = Path(d) / f"topla-{os.getuid()}"
            hedef = Path(d) / "hedef"
            hedef.mkdir()
            aday.symlink_to(hedef)
            with mock.patch.dict(os.environ, {"TMPDIR": d}):
                with self.assertRaises(SystemExit):
                    topla.yedek_durum_dizini()


if __name__ == "__main__":
    unittest.main(verbosity=2)
