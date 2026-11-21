"""Karar kapısı — kapının her modda zorunlu olduğunu kilitleyen testler."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

KOK = Path(__file__).resolve().parents[1]
# Doğrudan (`python3 agents/tests/test_kapi.py`) ve `-m unittest` çalıştırmalarının
# ikisi de çalışsın: depo kökü (KOK = agents, kök = parents[1]).
sys.path.insert(0, str(KOK / "driver"))
sys.path.insert(0, str(KOK.parents[0]))

import config  # noqa: E402
from agents.driver import roles, worker  # noqa: E402

SHA = "a" * 40
GOVDE = """## Ne

- `agents/driver/roles.py`: kapı zorunlu.

## Doğrulama

- `python3 -m unittest discover -s agents/tests -t .` → çıkış 0

## Sır

Yok.
"""


class SahteGithub:
    """GitHub API'sinin kapı için gereken en küçük sahtesi."""

    def __init__(self, durumlar=None, yorumlar=None):
        self._durumlar = dict(durumlar or {})
        self._yorumlar = list(yorumlar or [])
        self.yazilan: list[tuple[str, str]] = []
        self.birlestirilen: list[tuple[int, str]] = []

    def durumlar(self, sha):
        return dict(self._durumlar)

    def durum_yaz(self, sha, baglam, durum, aciklama=""):
        self.yazilan.append((baglam, durum))
        return {}

    def birlestir(self, no, sha):
        self.birlestirilen.append((no, sha))
        return {}

    def yorumlar(self, no):
        return list(self._yorumlar)

    def yorum_yaz(self, no, govde):
        return {}

    def etiket_ekle(self, no, etiketler):
        return {}

    def pr_dosyalari(self, no):
        return []


def _i5_yorumu(sha: str = SHA, karar: str = "onay") -> dict:
    govde = (
        "<details><summary>makine-okunabilir karar</summary>\n\n"
        "```json\n"
        '{"makine": "i5", "karar": "%s", "sha": "%s", "onem": "orta", '
        '"bulgular": [], "denetlenen": []}\n'
        "```\n\n</details>" % (karar, sha)
    )
    return {"body": govde}


class KapiTesti(unittest.TestCase):
    cfg = {"repo": "s/p", "agents": [{"name": "dev", "role": "developer",
                                      "token_file": "/yok"}]}
    pr = {"number": 7, "head": {"sha": SHA, "ref": "agents/agents-test-kapi"},
          "body": GOVDE}

    def _karar(self, sahte: SahteGithub) -> dict:
        with mock.patch.object(worker.github, "Github", return_value=sahte):
            return worker.karar_ver(self.cfg, {"name": "i3", "token_file": "/yok"}, self.pr)

    def test_inceleme_yoksa_merge_yok(self):
        sahte = SahteGithub()
        sonuc = self._karar(sahte)
        self.assertEqual(sonuc["durum"], "bekle")
        self.assertEqual(sahte.birlestirilen, [])

    def test_i5_yorumu_yoksa_failure(self):
        sahte = SahteGithub(durumlar={roles.INCELEME: "success"})
        sonuc = self._karar(sahte)
        self.assertEqual(sonuc["durum"], "failure")
        self.assertEqual(sahte.birlestirilen, [])
        self.assertIn((roles.KARAR, "failure"), sahte.yazilan)

    def test_baska_sha_icin_i5_onayi_gecersiz(self):
        sahte = SahteGithub(durumlar={roles.INCELEME: "success"},
                            yorumlar=[_i5_yorumu("b" * 40)])
        sonuc = self._karar(sahte)
        self.assertEqual(sonuc["durum"], "failure")
        self.assertEqual(sahte.birlestirilen, [])

    def test_i5_reddi_merge_etmez(self):
        sahte = SahteGithub(durumlar={roles.INCELEME: "success"},
                            yorumlar=[_i5_yorumu(karar="ret")])
        sonuc = self._karar(sahte)
        self.assertEqual(sonuc["durum"], "failure")
        self.assertEqual(sahte.birlestirilen, [])

    def test_kapi_tamamsa_merge(self):
        sahte = SahteGithub(durumlar={roles.INCELEME: "success"},
                            yorumlar=[_i5_yorumu()])
        sonuc = self._karar(sahte)
        self.assertEqual(sonuc["durum"], "success")
        self.assertEqual(sahte.birlestirilen, [(7, SHA)])

    def test_govde_eksikse_merge_yok(self):
        sahte = SahteGithub(durumlar={roles.INCELEME: "success"},
                            yorumlar=[_i5_yorumu()])
        pr = {"number": 7, "head": {"sha": SHA, "ref": "agents/agents-test-kapi"},
              "body": "## Ne\n\nvar\n"}
        with mock.patch.object(worker.github, "Github", return_value=sahte):
            sonuc = worker.karar_ver(self.cfg, {"name": "i3", "token_file": "/yok"}, pr)
        self.assertEqual(sonuc["durum"], "bekle")
        self.assertIn("PR gövdesi eksik", sonuc["neden"])
        self.assertEqual(sahte.birlestirilen, [])
        self.assertEqual(sahte.yazilan, [])  # durum yazılmaz, sha kilitlenmesin

    def test_govde_duzeltilince_ayni_sha_merge_edilir(self):
        sahte = SahteGithub(durumlar={roles.INCELEME: "success"},
                            yorumlar=[_i5_yorumu()])
        anahtar = mock.patch.object(worker.github, "Github", return_value=sahte)
        with anahtar:
            e1 = worker.karar_ver(self.cfg, {"name": "i3", "token_file": "/yok"},
                                  {"number": 7, "head": {"sha": SHA, "ref": "agents/agents-test-kapi"},
                                   "body": "## Ne\n"})
        self.assertEqual(e1["durum"], "bekle")
        with anahtar:
            e2 = worker.karar_ver(self.cfg, {"name": "i3", "token_file": "/yok"}, self.pr)
        self.assertEqual(e2["durum"], "success")
        self.assertEqual(sahte.birlestirilen, [(7, SHA)])

    def test_insan_pr_govdesiz_de_merge_edilir(self):
        sahte = SahteGithub(durumlar={roles.INCELEME: "success"},
                            yorumlar=[_i5_yorumu()])
        pr = {"number": 8, "head": {"sha": SHA, "ref": "feat/elle-acilan"},
              "body": "Manually added by human."}
        with mock.patch.object(worker.github, "Github", return_value=sahte):
            sonuc = worker.karar_ver(self.cfg, {"name": "i3", "token_file": "/yok"}, pr)
        self.assertEqual(sonuc["durum"], "success")
        self.assertEqual(sahte.birlestirilen, [(8, SHA)])

    def test_karar_plani_incelemesiz_pr_secmez(self):
        self.assertEqual(roles.karar_plani([self.pr], {}), [])
        self.assertEqual(roles.karar_plani([self.pr], {7: {roles.INCELEME: "success"}}),
                         [self.pr])


class RolDogrulamaTesti(unittest.TestCase):
    def _yaz(self, icerik: str) -> Path:
        d = Path(tempfile.mkdtemp(dir=Path.cwd()))
        # Testin bıraktığı dizin repoyu kirletmesin.
        self.addCleanup(shutil.rmtree, d, True)
        p = d / "i.toml"
        p.write_text(icerik, encoding="utf-8")
        return p

    BAŞLIK = """
instance = "deneme"
repo = "sahip/proje"
base_branch = "main"
state_dir = "/tmp/agents/deneme"
workdir = "/tmp/agents/deneme/w"
skills_root = "/tmp/agents/deneme/s"
"""

    def test_bilinmeyen_rol_reddedilir(self):
        p = self._yaz(self.BAŞLIK + """
[[agents]]
name = "x"
role = "admin"
machine = "m"
token_file = "/tmp/t"
""")
        with self.assertRaises(config.ConfigHatasi):
            config.yukle(p)

    def test_ayni_rol_iki_kez_reddedilir(self):
        p = self._yaz(self.BAŞLIK + """
[[agents]]
name = "a"
role = "reviewer"
machine = "m"
token_file = "/tmp/t1"
[[agents]]
name = "b"
role = "reviewer"
machine = "m2"
token_file = "/tmp/t2"
""")
        with self.assertRaises(config.ConfigHatasi):
            config.yukle(p)

    def test_makine_basi_config_eksik_rol_bildirir(self):
        p = self._yaz(self.BAŞLIK + """
[[agents]]
name = "karar"
role = "decision"
machine = "i3"
token_file = "/tmp/t"
""")
        veri = config.yukle(p)
        self.assertEqual(config.kapi_eksikleri(veri), ["developer", "reviewer"])


if __name__ == "__main__":
    unittest.main()
