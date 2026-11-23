"""PR gövdesi — üretim ve zorunlu kapı testleri."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK.parents[0]))

from agents.driver import cli, config, govde, github  # noqa: E402

IYI = """## Ne

- `agents/driver/govde.py` eklendi.

## Doğrulama

- `python3 -m unittest discover -s agents/tests -t .` → çıkış 0
  - OK

## Sır

Yok.
"""


class GovdeTesti(unittest.TestCase):
    def test_iyi_govde_gecer(self):
        self.assertEqual(govde.eksikler(IYI), [])

    def test_bos_govde_uc_eksik(self):
        eksik = govde.eksikler("")
        self.assertEqual(len(eksik), 3)
        self.assertTrue(all(e.startswith("bölüm yok") for e in eksik))

    def test_bos_bolum_yakalanir(self):
        eksik = govde.eksikler(IYI.replace("Yok.", ""))
        self.assertIn("bölüm boş: ## Sır", eksik)

    def test_kanitsiz_dogrulama_reddedilir(self):
        kotu = IYI.replace("→ çıkış 0", "→ çalıştı")
        self.assertIn("Doğrulama'da 'çıkış 0' kanıtı yok", govde.eksikler(kotu))

    def test_basarisiz_cikis_reddedilir(self):
        kotu = IYI.replace("çıkış 0", "çıkış 1")
        eksik = govde.eksikler(kotu)
        self.assertIn("Doğrulama başarısız çıkış içeriyor", eksik)
        self.assertIn("Doğrulama'da 'çıkış 0' kanıtı yok", eksik)

    def test_olustur_zorunlu_bolumleri_icerir(self):
        metin = govde.olustur(
            "kapıyı sertleştir",
            ["agents/driver/roles.py", "agents/tests/test_kapi.py"],
            ["- `make test` → çıkış 0", "  - OK"],
            sir="Yok.",
            neden="Tek ajanlı kurulumda kendi PR'ini merge edebiliyordu.",
        )
        self.assertEqual(govde.eksikler(metin), [])
        b = govde.bolumler(metin)
        self.assertIn("agents/tests/test_kapi.py", b["Ne"])
        self.assertIn("make test", b["Doğrulama"])
        self.assertIn("kendi PR", b["Neden"])

    def test_olustur_bos_dosya_listesini_acikca_yazar(self):
        metin = govde.olustur("g", [], ["- `x` → çıkış 0"])
        self.assertIn("Değişen dosya yok", metin)

    def test_olustur_basarisiz_dogrulamayi_gizlemez(self):
        metin = govde.olustur("g", ["a.py"], ["- `x` → çıkış 1 (BAŞARISIZ)"])
        self.assertNotEqual(govde.eksikler(metin), [])

    def test_bolumler_ilk_basligi_korur(self):
        metin = "## Ne\n\na\n\n## Ne\n\nb\n"
        self.assertEqual(govde.bolumler(metin)["Ne"], "a")

    def test_gerekli_ajan_dalinda_true(self):
        self.assertTrue(govde.gerekli({"head": {"ref": "agents/i3-gorev"}}))

    def test_gerekli_insan_dalinda_false(self):
        self.assertFalse(govde.gerekli({"head": {"ref": "feat/elle"}}))

    def test_gerekli_etiketle_true(self):
        self.assertTrue(govde.gerekli({"head": {"ref": "x"}, "labels": [{"name": "agents/gorev"}]}))

    def test_gerekli_bozuk_pr_false(self):
        self.assertFalse(govde.gerekli({}))

    def test_cli_eksikte_1_doner(self):
        yol = Path(self.id().replace(".", "_") + ".md")
        yol.write_text("## Ne\n\nx\n", encoding="utf-8")
        self.addCleanup(yol.unlink, True)
        s = subprocess.run([sys.executable, "-m", "agents.driver.govde", "--kontrol", str(yol)],
                           cwd=KOK.parents[0], capture_output=True, text=True)
        self.assertEqual(s.returncode, 1, s.stdout + s.stderr)
        self.assertIn("gövde kapıdan geçmedi", s.stdout)

    def test_cli_tam_govdede_0_doner(self):
        yol = Path(self.id().replace(".", "_") + "_iyi.md")
        yol.write_text(IYI, encoding="utf-8")
        self.addCleanup(yol.unlink, True)
        s = subprocess.run([sys.executable, "-m", "agents.driver.govde", "--kontrol", str(yol)],
                           cwd=KOK.parents[0], capture_output=True, text=True)
        self.assertEqual(s.returncode, 0, s.stdout + s.stderr)


class GovdeKomutuTesti(unittest.TestCase):
    """`agents govde --pr N` — makineyle doğrulanan kontrol noktası."""

    class Sahte:
        def __init__(self, govde_metni):
            self._g = govde_metni

        def pr(self, no):
            return {"number": no, "body": self._g}

    def _calistir(self, govde_metni):
        from unittest import mock
        cfg = {"repo": "s/p", "agents": [{"name": "i3", "token_file": "/yok"}]}
        with mock.patch.object(config, "yukle", return_value=cfg), \
                mock.patch.object(github, "Github", return_value=self.Sahte(govde_metni)):
            return cli.govde_denetle(None, 9)

    def test_eksik_govde_1(self):
        self.assertEqual(self._calistir("## Ne\n\nvar\n"), 1)

    def test_tam_govde_0(self):
        self.assertEqual(self._calistir(IYI), 0)


if __name__ == "__main__":
    unittest.main()
