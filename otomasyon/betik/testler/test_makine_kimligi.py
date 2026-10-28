"""MAKİNE KİMLİĞİ — iki kaynak, tek kural (27 Ekim i5 kilidi).

ARIZA 1: kimlik yalnız ROOT sahipli `/etc/yourkiosk-makine-kimligi` dosyasından okunuyordu. i5'te
sudo parolası yoktu → dosya hiç kurulamadı → karar kapısı HER kararı "makine kimliği geçersiz"
diye reddetti → i5 incelemesi hiç yazılamadı, PR kuyruğu 39 saat kilitlendi.

ARIZA 2 (i5 bulgusu, yüksek): yedek kaynak rolü depodaki eşlemeden okurken yalnız ÇALIŞMA AĞACI
temizliğine bakıyordu. Yerel commit atabilen bir ajan eşlemeyi kendi machine-id'sine çevirip i5
iken i3 kimliği alabiliyordu → iki kapılı düzen tek makinede çöküyordu.

ARIZA 3 (i5 bulgusu, düşük): depo herkese açık ve eşleme HAM machine-id yayınlıyordu (kalıcı cihaz
tanımlayıcısı). Artık yalnız ayrımlı sha256 özeti yayınlanır.

Bu dosya üç sözleşmeyi kilitler:
  1) Rol, `/etc/machine-id` (root sahipli, sudo gerektirmez) + YAYINLANMIŞ eşlemeden çözülür.
  2) Yerel eşleme yayınlanmış blob ile BAYT BAYT eşit değilse kimlik boş döner (fail-closed).
  3) Depoda ham machine-id bulunmaz; yalnız `kimlik_ozet` (sha256) bulunur.
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
OZET_I5 = yaz.kimlik_ozeti(MID_I5)
OZET_I3 = yaz.kimlik_ozeti(MID_I3)


class MakineIdKimligiTesti(unittest.TestCase):
    def setUp(self):
        self.dizin = tempfile.TemporaryDirectory()
        self.kok = Path(self.dizin.name)
        self.depo = self.kok / "depo"
        self.depo.mkdir()
        subprocess.run(["git", "init", "--initial-branch=main"], cwd=str(self.depo),
                       capture_output=True, text=True, env={**os.environ, **GIT_ENV}, timeout=60)
        self.esleme = self.depo / "otomasyon" / "makine-kimlikleri.json"
        self.esleme.parent.mkdir(parents=True)
        self.mid_dosya = self.kok / "machine-id"
        self.mid_dosya.write_text(MID_I5 + "\n", encoding="utf-8")
        # yaz.py'nin birincil kaynağı YOK (i5'in gerçek durumu)
        self.yok_dosya = self.kok / "yourkiosk-makine-kimligi"

    def tearDown(self):
        self.dizin.cleanup()

    def _esleme_yaz(self, veri: dict, *, commit: bool = True) -> None:
        self.esleme.write_text(json.dumps(veri, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if commit:
            subprocess.run(["git", "add", "-A"], cwd=str(self.depo), capture_output=True,
                           env={**os.environ, **GIT_ENV}, timeout=60)
            subprocess.run(["git", "commit", "-m", "eşleme"], cwd=str(self.depo),
                           capture_output=True, env={**os.environ, **GIT_ENV}, timeout=60)

    def _denetle(self, *, yayin: bytes | None = None, sahip: bool = True):
        """Kimlik denetimi. `yayin` verilmezse yerel dosya yayınlanmış sayılır."""
        if yayin is None:
            yayin_bayt = self.esleme.read_bytes() if self.esleme.is_file() else b""
        else:
            yayin_bayt = yayin
        with mock.patch.object(yaz, "KIMLIK_VARSAYILAN", self.yok_dosya), \
             mock.patch.object(yaz, "_yayinlanmis_esleme",
                               lambda depo, dal="": (yayin_bayt, "origin/main")):
            return yaz.makine_kimligi_denetle(
                makine_id=self.mid_dosya, depo=self.depo,
                sahip_denetimi=lambda st: sahip, dizin_denetimi=lambda st: True)

    # ---- 1) mutlu yol ----
    def test_esleme_ile_rol_bulunur(self):
        self._esleme_yaz({"i5": {"hostname": "casperi5", "kimlik_ozet": OZET_I5}})
        kimlik, neden = self._denetle()
        self.assertEqual(kimlik, "i5", neden)

    def test_eslemede_olmayan_makine_reddedilir_ve_kaydet_onerilir(self):
        self._esleme_yaz({"i3": {"hostname": "casperi3", "kimlik_ozet": OZET_I3}})
        kimlik, neden = self._denetle()
        self.assertEqual(kimlik, "")
        self.assertIn("eşlemesinde YOK", neden)
        self.assertIn("--kaydet", neden)

    # ---- 2) yayınlanmış içerik denetimi (yüksek bulgu) ----
    def test_yerel_commit_ile_rol_taklidi_reddedilir(self):
        """Ajan eşlemeyi değiştirip YEREL commit atarsa: ağaç temiz ama yayın farklı → reddedilir."""
        self._esleme_yaz({"i5": {"hostname": "casperi5", "kimlik_ozet": OZET_I5}})
        yayinlanmis = self.esleme.read_bytes()
        self._esleme_yaz({"i3": {"hostname": "casperi5", "kimlik_ozet": OZET_I5}})
        kimlik, neden = self._denetle(yayin=yayinlanmis)
        self.assertEqual(kimlik, "")
        self.assertIn("FARKLI", neden)

    def test_degistirilmis_calisma_agaci_reddedilir(self):
        self._esleme_yaz({"i5": {"hostname": "casperi5", "kimlik_ozet": OZET_I5}})
        self.esleme.write_text(json.dumps({"i3": {"kimlik_ozet": OZET_I5}}) + "\n", encoding="utf-8")
        kimlik, neden = self._denetle()
        self.assertEqual(kimlik, "")
        self.assertIn("DEĞİŞTİRİLMİŞ", neden)

    def test_yayin_okunamazsa_reddedilir(self):
        self._esleme_yaz({"i5": {"hostname": "casperi5", "kimlik_ozet": OZET_I5}})
        kimlik, neden = self._denetle(yayin=b"")
        self.assertEqual(kimlik, "")
        self.assertIn("YAYINLANMIŞ sürümden doğrulanamadı", neden)

    # ---- 3) ham machine-id yayınlanmaz ----
    def test_ham_machine_id_iceren_esleme_reddedilir(self):
        self._esleme_yaz({"i5": {"hostname": "casperi5", "machine_id": MID_I5}})
        kimlik, neden = self._denetle()
        self.assertEqual(kimlik, "")
        self.assertIn("HAM machine_id", neden)

    # ---- diğer sözleşmeler ----
    def test_ayni_machine_id_iki_rolde_reddedilir(self):
        self._esleme_yaz({"i5": {"kimlik_ozet": OZET_I5}, "i3": {"kimlik_ozet": OZET_I5}})
        kimlik, neden = self._denetle()
        self.assertEqual(kimlik, "")
        self.assertIn("birden çok role", neden)

    def test_machine_id_root_sahipli_degilse_reddedilir(self):
        self._esleme_yaz({"i5": {"hostname": "casperi5", "kimlik_ozet": OZET_I5}})
        kimlik, neden = self._denetle(sahip=False)
        self.assertEqual(kimlik, "")
        self.assertIn("root sahipli değil", neden)

    def test_esleme_yoksa_acik_mesaj(self):
        kimlik, neden = self._denetle()
        self.assertEqual(kimlik, "")
        self.assertIn("kimlik eşlemesi yok", neden)

    def test_root_dosyasi_varsa_esleme_yok_sayilir(self):
        """Birincil kaynak varsa yedek devreye girmez (fail-closed)."""
        self._esleme_yaz({"i5": {"hostname": "casperi5", "kimlik_ozet": OZET_I5}})
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

    def test_kimlik_ozeti_ayrac_kullanir_ve_ham_degeri_sizdirmaz(self):
        ozet = yaz.kimlik_ozeti(MID_I5)
        self.assertEqual(len(ozet), 64)
        self.assertNotIn(MID_I5, ozet)
        self.assertEqual(ozet, yaz.kimlik_ozeti(" " + MID_I5.upper() + "\n"))

    def test_depo_haritasi_yazim_kararinda_kullanilir(self):
        """Uçtan uca: makine-id modunda kimlik doğru rolü veriyorsa beyan uyuşur."""
        self._esleme_yaz({"i5": {"hostname": "casperi5", "kimlik_ozet": OZET_I5}})
        with mock.patch.object(yaz, "KIMLIK_VARSAYILAN", self.yok_dosya), \
             mock.patch.object(yaz, "MAKINE_ID_YOLU", self.mid_dosya), \
             mock.patch.object(yaz, "makine_id_sahibi_denetimi", lambda st: True), \
             mock.patch.object(yaz, "_yayinlanmis_esleme",
                               lambda depo, dal="": (self.esleme.read_bytes(), "origin/main")):
            kimlik, neden = yaz.makine_kimligi_denetle(depo=self.depo)
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

    def test_kaydet_sudo_istemez_ve_ozet_yazar(self):
        s = self._calistir("--kaydet", "i5")
        self.assertEqual(s.returncode, 0, s.stderr)
        gercek = Path("/etc/machine-id").read_text(encoding="utf-8").strip().lower()
        self.assertIn(yaz.kimlik_ozeti(gercek), s.stdout, "eşleme özeti yazdırılmalı")
        self.assertIn("kimlik_ozet", s.stdout)
        self.assertNotIn("root gerekli", s.stderr)

    def test_kaydet_yaz_ham_machine_id_yazmaz(self):
        s = self._calistir("--kaydet", "i3", "--yaz")
        self.assertEqual(s.returncode, 0, s.stderr + s.stdout)
        veri = json.loads((self.depo / "otomasyon" / "makine-kimlikleri.json").read_text(encoding="utf-8"))
        self.assertIn("i3", veri)
        self.assertNotIn("machine_id", json.dumps(veri), "depoya HAM machine-id yazılmamalı")
        self.assertEqual(len(veri["i3"]["kimlik_ozet"]), 64)

    def test_kaydet_gecersiz_rol_reddedilir(self):
        s = self._calistir("--kaydet", "i9")
        self.assertEqual(s.returncode, 2)


class UzakCapaTesti(unittest.TestCase):
    """27 Ekim i5 bulgusu: kimlik çapası YEREL ref'ten okunuyordu → `update-ref` ile taklit.

    Kapanış ölçütü: yerel `origin/<dal>` sha'sı `git ls-remote` ile birebir eşleşmiyorsa eşleme
    YAYINLANMIŞ sayılmaz (boş döner, kimlik reddedilir).
    """

    def setUp(self):
        self.dizin = tempfile.TemporaryDirectory()
        self.kok = Path(self.dizin.name)
        self.depo = self.kok / "depo"
        self.depo.mkdir()
        self._git("init", "--initial-branch=main")
        self.esleme = self.depo / "otomasyon" / "makine-kimlikleri.json"
        self.esleme.parent.mkdir(parents=True)
        self.esleme.write_text(json.dumps({"i5": {"hostname": "casperi5",
                                                  "kimlik_ozet": OZET_I5}}, indent=2) + "\n",
                               encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-m", "esleme")
        self.sha = self._git("rev-parse", "HEAD").stdout.strip()
        # gerçek uzağın yerel aynası: origin/main bu commit'i gösteriyor
        self._git("update-ref", "refs/remotes/origin/main", self.sha)

    def tearDown(self):
        self.dizin.cleanup()

    def _git(self, *arg: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(self.depo), *arg], capture_output=True,
                              text=True, env={**os.environ, **GIT_ENV}, timeout=60)

    def _uzak(self, sha: str | None = None):
        return lambda depo: ({("main" if sha is None else "main"): (sha or self.sha)}, "")

    def test_uzak_sha_ile_eslesen_ref_yayinlanmis_sayilir(self):
        bayt, ref = yaz._yayinlanmis_esleme(self.depo, "main", uzak_oku=self._uzak())
        self.assertEqual(bayt, self.esleme.read_bytes())
        self.assertEqual(ref, "origin/main")

    def test_oynanmis_yerel_ref_yayinlanmis_sayilmaz(self):
        """Ajan `update-ref refs/remotes/origin/main <kendi commit'i>` yazarsa çapa çöker."""
        self._git("checkout", "-b", "sahte")
        self.esleme.write_text(json.dumps({"i3": {"kimlik_ozet": OZET_I3}}) + "\n", encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-m", "taklit")
        taklit = self._git("rev-parse", "HEAD").stdout.strip()
        self._git("update-ref", "refs/remotes/origin/main", taklit)
        bayt, ref = yaz._yayinlanmis_esleme(self.depo, "main", uzak_oku=self._uzak())
        self.assertEqual(bayt, b"", "uzak sha ile eşleşmeyen yerel ref kabul edilmemeli")
        self.assertEqual(ref, "")

    def test_uzak_okunamazsa_fail_closed(self):
        bayt, ref = yaz._yayinlanmis_esleme(self.depo, "main",
                                            uzak_oku=lambda depo: ({}, "ağ yok"))
        self.assertEqual((bayt, ref), (b"", ""))

    def test_bayat_ref_icin_fetch_onerilir(self):
        """Uzak ilerlemiş (yerel ref bayat) → yayınlanmış sayılmaz; kimlik reddi fetch önerir."""
        ileri = "f" * 40
        bayt, ref = yaz._yayinlanmis_esleme(self.depo, "main",
                                            uzak_oku=lambda depo: ({"main": ileri}, ""))
        self.assertEqual((bayt, ref), (b"", ""))
        with mock.patch.object(yaz, "KIMLIK_VARSAYILAN", self.depo / "yok"), \
             mock.patch.object(yaz, "_yayinlanmis_esleme",
                               lambda depo, dal="": (b"", "")):
            kimlik, neden = yaz.makine_kimligi_denetle(
                makine_id=Path("/etc/machine-id"), depo=self.depo,
                sahip_denetimi=lambda st: True, dizin_denetimi=lambda st: True)
        self.assertEqual(kimlik, "")
        self.assertIn("git ls-remote", neden)


class DurumDosyasiCipaTesti(unittest.TestCase):
    """28 Ekim i5 bulgusu (orta): çıpa ADAYLARI arasında ajanın yazabildiği durum dosyası vardı.

    `~/.local/state/yourkiosk-otomasyon/nobetci-dal` `--dal` ile yazıldığı için tek makine kendini
    `i3` ilan eden eşlemeyi bir düzeltme dalına koyup çıpayı oraya çevirebiliyor, iki zorunlu kapıyı
    (inceleme + karar) tek başına yeşile çeviriyordu. Kapanış ölçütü: çıpa yalnız depo VARSAYILAN
    dalıdır; durum dosyası ve `dal` argümanı onu değiştiremez.
    """

    def setUp(self):
        self.dizin = tempfile.TemporaryDirectory()
        self.kok = Path(self.dizin.name)
        self.depo = self.kok / "depo"
        self.depo.mkdir()
        self._git("init", "--initial-branch=main")
        self.esleme = self.depo / "otomasyon" / "makine-kimlikleri.json"
        self.esleme.parent.mkdir(parents=True)
        # main: i5 — doğru/operatör onaylı eşleme
        self.esleme.write_text(json.dumps({"i5": {"kimlik_ozet": OZET_I5}}) + "\n", encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-m", "esleme")
        self.main_sha = self._git("rev-parse", "HEAD").stdout.strip()
        # düzeltme dalı: i3 — ajanın kendi yazdığı "faydalı" eşleme taklidi
        self._git("checkout", "-b", "duzeltme/sahte")
        self.esleme.write_text(json.dumps({"i3": {"kimlik_ozet": OZET_I3}}) + "\n", encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-m", "taklit")
        self.kol_sha = self._git("rev-parse", "HEAD").stdout.strip()
        self._git("update-ref", "refs/remotes/origin/main", self.main_sha)
        self._git("update-ref", "refs/remotes/origin/duzeltme/sahte", self.kol_sha)
        # ajanın yazabildiği durum dosyası: çıpayı düzeltme dalına çevirmeye çalışıyor
        self.durum_dizin = self.kok / "state"
        self.durum_dizin.mkdir()
        (self.durum_dizin / "nobetci-dal").write_text("duzeltme/sahte\n", encoding="utf-8")

    def tearDown(self):
        self.dizin.cleanup()

    def _git(self, *arg: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(self.depo), *arg], capture_output=True,
                              text=True, env={**os.environ, **GIT_ENV}, timeout=60)

    def _uzak(self, depo):
        return ({"main": self.main_sha, "duzeltme/sahte": self.kol_sha}, "")

    def test_durum_dosyasi_cipayi_degistirmez(self):
        """`nobetci-dal` düzeltme dalını gösterse bile eşleme MAIN'den okunur."""
        ev = self.kok / "home"
        (ev / ".local" / "state" / "yourkiosk-otomasyon").mkdir(parents=True)
        (ev / ".local" / "state" / "yourkiosk-otomasyon" / "nobetci-dal").write_text(
            "duzeltme/sahte\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"HOME": str(ev)}):
            bayt, ref = yaz._yayinlanmis_esleme(self.depo, uzak_oku=self._uzak)
        self.assertEqual(ref, "origin/main", "çıpa yalnız varsayılan dal olmalı")
        self.assertEqual(json.loads(bayt.decode()), {"i5": {"kimlik_ozet": OZET_I5}})
        self.assertNotIn("i3", bayt.decode(), "ajanın kolundaki taklit eşleme okunmamalı")

    def test_baska_dal_argumani_reddedilir(self):
        bayt, ref = yaz._yayinlanmis_esleme(self.depo, "duzeltme/sahte", uzak_oku=self._uzak)
        self.assertEqual((bayt, ref), (b"", ""), "varsayılan dal dışı çıpa isteği fail-closed")

    def test_durum_dosyasi_kaynakta_okunmuyor(self):
        """Kaynak taraması: durum dosyası yolu yaz.py'de GEÇMEMELİ (sınıf geri gelmesin)."""
        kaynak = Path(yaz.__file__).read_text(encoding="utf-8")
        self.assertNotIn("nobetci-dal", kaynak)
        self.assertIn("KIMLIK_ESLEME_DALI", kaynak)

    def test_varsayilan_dalda_esleme_yoksa_fail_closed(self):
        """main'de eşleme yoksa başka dal denenmez (fail-closed)."""
        self._git("checkout", "main")
        (self.esleme).unlink()
        self._git("add", "-A")
        self._git("commit", "-m", "esleme-yok")
        bos_main = self._git("rev-parse", "HEAD").stdout.strip()
        self._git("update-ref", "refs/remotes/origin/main", bos_main)
        bayt, ref = yaz._yayinlanmis_esleme(
            self.depo, uzak_oku=lambda d: ({"main": bos_main, "duzeltme/sahte": self.kol_sha}, ""))
        self.assertEqual((bayt, ref), (b"", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
