"""otonom_bekci — koordinatör bekçisi testleri."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

BETIK_DIZIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BETIK_DIZIN))
import otonom_bekci as ob  # noqa: E402

AN = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


class KararTesti(unittest.TestCase):
    def test_timer_kapali_onar(self):
        self.assertEqual(ob.karar_ver(False, False, AN, AN)["eylem"], "onar")

    def test_tik_suruyorsa_dokunma(self):
        self.assertEqual(ob.karar_ver(True, True, AN, AN)["eylem"], "bekle")

    def test_kalp_atisi_yok_onar(self):
        self.assertEqual(ob.karar_ver(True, False, None, AN)["eylem"], "onar")

    def test_bayat_kalp_onar(self):
        eski = AN - timedelta(minutes=ob.SESSIZ_DK + 5)
        karar = ob.karar_ver(True, False, eski, AN)
        self.assertEqual(karar["eylem"], "onar")
        self.assertIn("dk önce", karar["neden"])

    def test_saglikli_bekle(self):
        yeni = AN - timedelta(minutes=5)
        self.assertEqual(ob.karar_ver(True, False, yeni, AN)["eylem"], "bekle")

    def test_son_tik_ayristirilir(self):
        self.assertIsNotNone(ob.son_tik_zamani({"son_tik": "2026-01-01T12:00:00Z"}))
        self.assertIsNone(ob.son_tik_zamani({"son_tik": "bozuk"}))
        self.assertIsNone(ob.son_tik_zamani({}))


class OnarTesti(unittest.TestCase):
    def test_once_reset_sonra_start(self):
        with mock.patch.object(ob, "systemctl", return_value=0) as sc:
            self.assertTrue(ob.onar())
        cagrilar = [c.args for c in sc.call_args_list]
        self.assertIn(("reset-failed", ob.TIK_SERVIS), cagrilar)
        self.assertIn(("reset-failed", ob.TIK_TIMER), cagrilar)
        self.assertIn(("start", ob.TIK_TIMER), cagrilar)

    def test_start_basarisizsa_false(self):
        with mock.patch.object(ob, "systemctl", side_effect=[0, 0, 1]):
            self.assertFalse(ob.onar())


class TikTesti(unittest.TestCase):
    def setUp(self):
        self.dizin = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.dizin.cleanup)
        self.kok = Path(self.dizin.name)
        self.ev = self.kok / "ev"
        self.ev.mkdir()
        self.home = self.kok / "home"
        (self.home / ".config" / "systemd" / "user").mkdir(parents=True)
        (self.home / ".config" / "systemd" / "user" / ob.TIK_TIMER).write_text("")
        self.yamalar = [
            mock.patch.object(ob, "EV", self.ev),
            mock.patch.object(ob, "DURUM", self.ev / "durum.json"),
            mock.patch.object(ob, "BEKCI_DURUM", self.ev / "bekci-durum.json"),
            mock.patch.object(ob, "GUNLUK", self.ev / "bekci.log"),
            mock.patch("pathlib.Path.home", return_value=self.home),
        ]
        for yama in self.yamalar:
            yama.start()
            self.addCleanup(yama.stop)

    def _systemctl(self, timer: int = 0, servis: int = 4):
        def sc(*arg):
            if arg[:2] == ("is-active", "--quiet"):
                return timer if arg[2] == ob.TIK_TIMER else servis
            return 0
        return sc

    def test_kuru_saglikli(self):
        (self.ev / "durum.json").write_text(
            json.dumps({"son_tik": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}))
        with mock.patch.object(ob, "systemctl", side_effect=self._systemctl()):
            self.assertEqual(ob.tik(kuru=True), 0)

    def test_bayat_tik_onarilir(self):
        (self.ev / "durum.json").write_text(json.dumps({"son_tik": "2000-01-01T00:00:00Z"}))
        with mock.patch.object(ob, "systemctl", side_effect=self._systemctl()), \
             mock.patch.object(ob, "onar", return_value=True) as onar:
            self.assertEqual(ob.tik(kuru=False), 0)
        onar.assert_called_once()
        self.assertTrue((self.ev / "bekci-durum.json").exists())

    def test_onarim_sikligi(self):
        (self.ev / "durum.json").write_text(json.dumps({"son_tik": "2000-01-01T00:00:00Z"}))
        (self.ev / "bekci-durum.json").write_text(json.dumps(
            {"son_onar": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}))
        with mock.patch.object(ob, "systemctl", side_effect=self._systemctl()), \
             mock.patch.object(ob, "onar", return_value=True) as onar:
            self.assertEqual(ob.tik(kuru=False), 0)
        onar.assert_not_called()

    def test_birim_yoksa_onarmaz(self):
        (self.home / ".config" / "systemd" / "user" / ob.TIK_TIMER).unlink()
        with mock.patch.object(ob, "systemctl") as sc:
            self.assertEqual(ob.tik(kuru=False), 2)
        sc.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
