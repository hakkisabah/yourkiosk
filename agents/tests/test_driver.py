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
        self.assertEqual(wizard.roller(1), ["developer"])

    def test_n3_roller(self):
        import wizard
        self.assertEqual(wizard.roller(3), ["developer", "reviewer", "decision"])

    def test_n4_iki_reviewer(self):
        import wizard
        self.assertEqual(wizard.roller(4),
                         ["developer", "reviewer", "reviewer", "decision"])

    def test_config_metni(self):
        import wizard
        metin = wizard.config_metni("d", "s/p", [{"ad": "dev", "rol": "developer",
                                                  "makine": "m", "token": "t"}])
        self.assertIn('instance = "d"', metin)
        self.assertIn("token_file", metin)

class DshTesti(unittest.TestCase):
    def test_komut_bin_js(self):
        import dsh
        k = dsh.komut("profil")
        self.assertIn("bin.js", k[1])
        self.assertEqual(k[-1], "-")

class WizardTesti(unittest.TestCase):
    def test_n1_tek_gelistirici(self):
        import wizard
        self.assertEqual(wizard.roller(1), ["developer"])

    def test_n3_roller(self):
        import wizard
        self.assertEqual(wizard.roller(3), ["developer", "reviewer", "decision"])

    def test_n4_iki_reviewer(self):
        import wizard
        self.assertEqual(wizard.roller(4),
                         ["developer", "reviewer", "reviewer", "decision"])

    def test_config_metni(self):
        import wizard
        metin = wizard.config_metni("d", "s/p", [{"ad": "dev", "rol": "developer",
                                                  "makine": "m", "token": "t"}])
        self.assertIn('instance = "d"', metin)


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
        # İnceleme onayı yoksa PR karara sunulmaz (kapı koşulsuz).
        self.assertEqual(len(roles.karar_plani([pr], {})), 0)

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


class KararKapisiTesti(unittest.TestCase):
    ALANLAR = list(worker.DENETIM_ALANLARI)

    def _karar(self, **kw):
        veri = {"pr": 7, "sha": "a" * 40, "nonce": "n1", "karar": "onay",
                "onem": "dusuk", "ozet": "ok", "bulgular": [], "denetlenen": list(self.ALANLAR)}
        veri.update(kw)
        return veri

    def test_onay_gecer(self):
        self.assertEqual(worker._karar_kapisi(self._karar(), 7, "a" * 40, "n1"), [])

    def test_nonce_ve_kapsam_zorunlu(self):
        h = worker._karar_kapisi(self._karar(nonce="yanlis", denetlenen=["test kaniti"]),
                                 7, "a" * 40, "n1")
        self.assertTrue(any("nonce" in x for x in h))
        self.assertTrue(any("denetlenen" in x for x in h))

    def test_yuksek_bulgu_onay_olamaz(self):
        h = worker._karar_kapisi(self._karar(bulgular=[{"onem": "yuksek", "dosya": "a.py",
                                                         "satir": 1, "aciklama": "x",
                                                         "kabul": "y"}]),
                                 7, "a" * 40, "n1")
        self.assertTrue(any("yuksek" in x for x in h))

    def test_sorun_bulgusuz_ve_kabulsuz_olamaz(self):
        h = worker._karar_kapisi(self._karar(karar="sorun", bulgular=[]), 7, "a" * 40, "n1")
        self.assertTrue(any("bulgu" in x for x in h))


class YorumTesti(unittest.TestCase):
    class G:
        def __init__(self):
            self.yorum = []
        def yorumlar(self, no):
            return []
        def yorum_yaz(self, no, govde):
            self.yorum.append((no, govde))
        def etiket_ekle(self, no, e):
            pass
        def pr_dosyalari(self, no):
            return [{"filename": "a.py"}]

    def test_i5_yorumu_eski_bicim(self):
        from agents.driver import yorum
        g = self.G()
        yorum.inceleme_yorumu(g, 5, "a" * 40, {
            "karar": "onay", "onem": "orta", "ozet": "ozet", "bulgular": [],
            "denetlenen": ["test kaniti"]})
        govde = g.yorum[0][1]
        self.assertIn("i5 — güvenlik incelemesi", govde)
        self.assertIn("makine-okunabilir karar", govde)
        self.assertIn("test kaniti", govde)

    def test_i3_yorumu_eski_bicim(self):
        from agents.driver import yorum
        g = self.G()
        yorum.karar_yorumu(g, 5, "a" * 40, {"karar": "onay", "onem": "orta",
                                            "bulgular": [], "denetlenen": ["test kaniti"]},
                           {"durum": "success"})
        govde = g.yorum[0][1]
        self.assertIn("i3 — karar / ikinci görüş", govde)
        self.assertIn('"makine": "i3"', govde)


if __name__ == "__main__":
    unittest.main(verbosity=2)
