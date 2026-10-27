"""MAKİNE KİMLİĞİ — iki kaynak, tek kural (27 Ekim i5 kilitlenmesinin regresyon kilidi).

ARIZA: kimlik yalnız ROOT sahipli `/etc/yourkiosk-makine-kimligi` dosyasından okunuyordu. i5'te
sudo parolası yoktu → dosya hiç kurulamadı → karar kapısı HER kararı "makine kimliği geçersiz"
diye reddetti → i5 incelemesi hiç yazılamadı, PR kuyruğu 39 saat kilitlendi (13 red kaydı).

ÇÖZÜM: dosya yoksa `/etc/machine-id` (root sahipli, makineye özgü, sudo gerektirmez) + depodaki
rol eşlemesi (`otomasyon/makine-kimlikleri.json`, GIT'te temiz olmak zorunda) kullanılır. Rol yine
ajanın beyanından okunmaz; eşlemeyi değiştirmek PR incelemesine bağlıdır.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BETIK_DIZINI = Path(__file__).resolve().parents[1]
KOK = BETIK_DIZINI.parents[1]
sys.path.insert(0, str(BETIK_DIZINI))

import yaz  # noqa: E402

GIT_ENV = {
    "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
}

MID_I5 = "249752107923446f99bcca45a66c19dd"
MID_I3 = "11111111222233334444555566667777"


class MakineIdKimligiTesti(unittest.TestCase):
    def setUp(self):
        self.dizin = tempfile.TemporaryDirectory()
        self.kok = Path(self.dizin.name)
        self.depo = self.kok / "depo"
        self.depo.mkdir()
        for arg in (["init", "--initial-branch=main"],):
            subprocess.run(["git", *arg], cwd=str(self.depo), capture_output=True, text=True,
                           env={**os.environ, **GIT_ENV}, timeout=60)
        self.esleme = self.depo / "otomasyon" / "makine-kimlikleri.json"
        self.esleme.parent.mkdir(parents=True)
        self.mid_dosya = self.kok / "machine-id"
        self.mid_dosya.write_text(MID_I5 + "\n", encoding="utf-8")
        # yaz.py'nin birincil kaynağı YOK (i5'in gerçek durumu)
        self.yok_dosya = self.kok / "yourkiosk-makine-kimligi"

    def tearDown(self):
        self.dizin.cleanup()

    def _esleme_yaz(self, veri: dict, *, commit: bool = True) -> None:
        self.esleme.write_text(json.dumps(veri, indent=2) + "\n", encoding="utf-8")
        if commit:
            subprocess.run(["git", "add", "-A"], cwd=str(self.depo), capture_output=True,
                           env={**os.environ, **GIT_ENV}, timeout=60)
            subprocess.run(["git", "commit", "-m", "eşleme"], cwd=str(self.depo),
                           capture_output=True, env={**os.environ, **GIT_ENV}, timeout=60)

    def _denetle(self):
        with mock.patch.object(yaz, "KIMLIK_VARSAYILAN", self.yok_dosya):
            return yaz.makine_kimligi_denetle(
                makine_id=self.mid_dosya, depo=self.depo,
                sahip_denetimi=lambda st: True, dizin_denetimi=lambda st: True)

    def test_esleme_ile_rol_bulunur(self):
        self._esleme_yaz({"i5": {"hostname": "casperi5", "machine_id": MID_I5}})
        kimlik, neden = self._denetle()
        self.assertEqual(kimlik, "i5", neden)

    def test_eslemede_olmayan_makine_reddedilir_ve_kaydet_onerilir(self):
        self._esleme_yaz({"i3": {"hostname": "casperi3", "machine_id": MID_I3}})
        kimlik, neden = self._denetle()
        self.assertEqual(kimlik, "")
        self.assertIn("eşlemesinde YOK", neden)
        self.assertIn("--kaydet", neden)

    def test_esleme_degistirilmisse_reddedilir(self):
        """Ajan eşlemeyi kendi lehine düzenlerse kapı kapanır (değişiklik PR ister)."""
        self._esleme_yaz({"i5": {"hostname": "casperi5", "machine_id": MID_I5}})
        self.esleme.write_text(json.dumps({"i3": {"hostname": "casperi5",
                                                  "machine_id": MID_I5}}) + "\n", encoding="utf-8")
        kimlik, neden = self._denetle()
        self.assertEqual(kimlik, "")
        self.assertIn("DEĞİŞTİRİLMİŞ", neden)

    def test_ayni_machine_id_iki_rolde_reddedilir(self):
        self._esleme_yaz({"i5": {"machine_id": MID_I5}, "i3": {"machine_id": MID_I5}})
        kimlik, neden = self._denetle()
        self.assertEqual(kimlik, "")
        self.assertIn("birden çok role", neden)

    def test_machine_id_root_sahipli_degilse_reddedilir(self):
        self._esleme_yaz({"i5": {"machine_id": MID_I5}})
        with mock.patch.object(yaz, "KIMLIK_VARSAYILAN", self.yok_dosya):
            kimlik, neden = yaz.makine_kimligi_denetle(
                makine_id=self.mid_dosya, depo=self.depo,
                sahip_denetimi=lambda st: False, dizin_denetimi=lambda st: True)
        self.assertEqual(kimlik, "")
        self.assertIn("root sahipli değil", neden)

    def test_esleme_yoksa_acik_mesaj(self):
        with mock.patch.object(yaz, "KIMLIK_VARSAYILAN", self.yok_dosya):
            kimlik, neden = yaz.makine_kimligi_denetle(
                makine_id=self.mid_dosya, depo=self.depo,
                sahip_denetimi=lambda st: True, dizin_denetimi=lambda st: True)
        self.assertEqual(kimlik, "")
        self.assertIn("kimlik eşlemesi yok", neden)

    def test_root_dosyasi_varsa_esleme_yok_sayilir(self):
        """Birincil kaynak varsa yedek devreye girmez (fail-closed: bozuk dosya kabul edilmez)."""
        self._esleme_yaz({"i5": {"machine_id": MID_I5}})
        birincil = self.kok / "kimlik-root"
        birincil.write_text("i3\n", encoding="utf-8")
        with mock.patch.object(yaz, "KIMLIK_VARSAYILAN", birincil):
            kimlik, neden = yaz.makine_kimligi_denetle(
                makine_id=self.mid_dosya, depo=self.depo,
                sahip_denetimi=lambda st: True, dizin_denetimi=lambda st: True)
        self.assertEqual(kimlik, "i3", neden)

    def test_kimlik_modu_kaynagi_soyler(self):
        with mock.patch.object(yaz, "KIMLIK_VARSAYILAN", self.yok_dosya):
            self.assertEqual(yaz.kimlik_modu(makine_id=self.mid_dosya,
                                             sahip_denetimi=lambda st: True), "machine-id")
        birincil = self.kok / "kimlik-root"
        birincil.write_text("i5\n", encoding="utf-8")
        with mock.patch.object(yaz, "KIMLIK_VARSAYILAN", birincil):
            self.assertEqual(yaz.kimlik_modu(), "root-dosya")

    def test_depo_haritasi_yazim_kararinda_kullanilir(self):
        """Uçtan uca: makine-id modunda kimlik doğru rolü veriyorsa beyan uyuşur."""
        self._esleme_yaz({"i5": {"hostname": "casperi5", "machine_id": MID_I5}})
        with mock.patch.object(yaz, "KIMLIK_VARSAYILAN", self.yok_dosya), \
             mock.patch.object(yaz, "MAKINE_ID_YOLU", self.mid_dosya), \
             mock.patch.object(yaz, "makine_id_sahibi_denetimi", lambda st: True), \
             mock.patch.object(yaz, "kimlik_eslemesi",
                               lambda depo=None: ({"i5": {"machine_id": MID_I5,
                                                          "hostname": "casperi5"}}, "")):
            kimlik, neden = yaz.makine_kimligi_denetle()
        self.assertEqual(kimlik, "i5", neden)


class KaydetBetigiTesti(unittest.TestCase):
    """`makine-kimligi-kur.sh --kaydet` — sudo GEREKTİRMEYEN kayıt yolu."""

    BETIK = KOK / "otomasyon" / "betik" / "makine-kimligi-kur.sh"

    def setUp(self):
        self.dizin = tempfile.TemporaryDirectory()
        self.kok = Path(self.dizin.name)
        self.depo = self.kok / "depo"
        self.depo.mkdir()
        subprocess.run(["git", "init", "--initial-branch=main"], cwd=str(self.depo),
                       capture_output=True, env={**os.environ, **GIT_ENV}, timeout=60)
        hedef = self.depo / "otomasyon" / "betik"
        hedef.mkdir(parents=True)
        (hedef / "makine-kimligi-kur.sh").write_text(self.BETIK.read_text(encoding="utf-8"),
                                                     encoding="utf-8")

    def tearDown(self):
        self.dizin.cleanup()

    def _calistir(self, *arg: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(self.depo / "otomasyon" / "betik" / "makine-kimligi-kur.sh"),
                               *arg], capture_output=True, text=True, timeout=90,
                              env={**os.environ, **GIT_ENV})

    def test_kaydet_sudo_istemez_ve_machine_id_yazar(self):
        s = self._calistir("--kaydet", "i5")
        self.assertEqual(s.returncode, 0, s.stderr)
        gercek = Path("/etc/machine-id").read_text(encoding="utf-8").strip().lower()
        self.assertIn(gercek, s.stdout)
        self.assertIn('"i5"', s.stdout)
        self.assertNotIn("root gerekli", s.stderr)

    def test_kaydet_yaz_eslemeyi_olusturur(self):
        s = self._calistir("--kaydet", "i3", "--yaz")
        self.assertEqual(s.returncode, 0, s.stderr + s.stdout)
        veri = json.loads((self.depo / "otomasyon" / "makine-kimlikleri.json").read_text(encoding="utf-8"))
        self.assertIn("i3", veri)
        self.assertEqual(len(veri["i3"]["machine_id"]), 32)

    def test_kaydet_gecersiz_rol_reddedilir(self):
        s = self._calistir("--kaydet", "i9")
        self.assertEqual(s.returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
