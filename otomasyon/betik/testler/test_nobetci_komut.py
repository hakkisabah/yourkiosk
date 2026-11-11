"""hermes_komutu / butce_hesapla — nöbetçi oturumunun komut satırı sözleşmesi.

İki hata sınıfını makineyle kilitler:
1. **Tur tavanı ↔ duvar saati tutarsızlığı** (25 Ekim): 120 tur yazıp 9,5 sn/tur bütçe vermek
   incelemeyi yarıda kesiyordu. Bütçe darsa tavan KISILIR ve bu görünür olur.
2. **Ayrı profil** (26 Ekim i5 mimarisi): nöbetçi Open WebUI ile aynı gateway'i paylaşırsa aynı
   CPU/kota/oturum tavanını yer. `NOBETCI_PROFIL` verilince komut `hermes -p <ad> chat …` olmalı.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nobetci  # noqa: E402


class OnbellekTesti(unittest.TestCase):
    """27 Ekim i5 bulgusu: ETag önbelleği hiç budanmıyordu → durum dosyası turda şişiyordu.

    Kapanış ölçütü: 500 ayrı sha yoklandığında kayıt sayısı `ONBELLEK_SINIRI`nı aşmaz ve
    güncel iş listesinde olmayan sha'ların durum yanıtları düşer.
    """

    def setUp(self):
        self.dizin = tempfile.TemporaryDirectory()
        self.addCleanup(self.dizin.cleanup)
        self.durum = Path(self.dizin.name) / "durum.json"
        self.gh = nobetci.Github("sahte", "hakkisabah/yourkiosk", self.durum)

    def _sha(self, i: int) -> str:
        return f"{i:040x}"

    def test_500_sha_sonrasi_kayit_sayisi_sinirli(self):
        for i in range(500):
            url = f"https://api.github.com/repos/d/d/commits/{self._sha(i)}/status"
            self.gh.onbellek[url] = {"etag": f'W/"{i}"', "veri": {"statuses": []}}
        self.gh.kaydet({"rol": "i5"})
        veri = json.loads(self.durum.read_text(encoding="utf-8"))
        self.assertLessEqual(len(veri["etag"]), nobetci.ONBELLEK_SINIRI)
        self.assertLess(self.durum.stat().st_size, 200_000)

    def test_guncel_olmayan_sha_budanir(self):
        gecerli = self._sha(1)
        for i in (1, 2, 3):
            url = f"https://api.github.com/repos/d/d/commits/{self._sha(i)}/status"
            self.gh.onbellek[url] = {"etag": f'W/"{i}"', "veri": {}}
        self.gh.onbellek["https://api.github.com/repos/d/d/pulls?state=open"] = {"etag": "W/\"p\"", "veri": []}
        atilan = self.gh.buda({gecerli})
        self.assertEqual(atilan, 2)
        kalan = [u for u in self.gh.onbellek if "/commits/" in u]
        self.assertEqual(len(kalan), 1)
        self.assertIn(gecerli, kalan[0])
        self.assertTrue(any("/pulls" in u for u in self.gh.onbellek), "PR listesi kaydı korunmalı")


class ButceTesti(unittest.TestCase):
    def test_varsayilan_zaman_asimi_tavana_yeter(self):
        b = nobetci.butce_hesapla(nobetci.VARSAYILAN_ZAMAN_ASIMI)
        self.assertTrue(b["yeterli"])
        self.assertEqual(b["tur"], nobetci.OTURUM_TUR_TAVANI)
        self.assertGreaterEqual(b["tur_basi_sn"], nobetci.EN_AZ_TUR_SURESI_S)

    def test_dar_butcede_tavan_kisilir_ve_gorunur(self):
        b = nobetci.butce_hesapla(600)          # 540 sn / 120 tur = 4,5 sn → tavan kısılmalı
        self.assertLess(b["tur"], nobetci.OTURUM_TUR_TAVANI)
        self.assertFalse(b["yeterli"])
        self.assertGreaterEqual(b["tur_basi_sn"], nobetci.EN_AZ_TUR_SURESI_S)

    def test_duvar_saati_asilmaz(self):
        for zaman in (300, 900, 1860, 7200):
            b = nobetci.butce_hesapla(zaman)
            self.assertLessEqual(b["butce"] + nobetci.KAPANIS_PAYI_S, max(zaman, 180))
            self.assertLessEqual(b["tur"] * b["tur_basi_sn"], b["butce"])


class ProfilTesti(unittest.TestCase):
    def setUp(self):
        self.eski = nobetci.NOBETCI_PROFIL

    def tearDown(self):
        nobetci.NOBETCI_PROFIL = self.eski

    def test_profil_yoksa_komut_degismez(self):
        nobetci.NOBETCI_PROFIL = ""
        komut = nobetci.hermes_komutu(Path("/depo"), Path("/gorev.md"), 1860)
        self.assertEqual(komut[:2], ["hermes", "chat"])

    def test_profil_varsa_p_argumani_oneklenir(self):
        nobetci.NOBETCI_PROFIL = "guvenlik"
        komut = nobetci.hermes_komutu(Path("/depo"), Path("/gorev.md"), 1860)
        self.assertEqual(komut[:4], ["hermes", "-p", "guvenlik", "chat"])
        self.assertIn("--oneshot", komut)
        # profil, tur tavanını ya da bütçeyi DEĞİŞTİRMEMELİ
        self.assertEqual(komut[komut.index("--max-turns") + 1], str(nobetci.OTURUM_TUR_TAVANI))

    def test_ortam_degiskeni_okunur(self):
        import importlib
        import os
        eski = os.environ.get("NOBETCI_PROFIL")
        os.environ["NOBETCI_PROFIL"] = "guvenlik"
        try:
            yeni = importlib.reload(nobetci)
            self.assertEqual(yeni.NOBETCI_PROFIL, "guvenlik")
        finally:
            if eski is None:
                os.environ.pop("NOBETCI_PROFIL", None)
            else:
                os.environ["NOBETCI_PROFIL"] = eski
            importlib.reload(nobetci)
            nobetci.NOBETCI_PROFIL = self.eski


class DshKomutTesti(unittest.TestCase):
    """2026-11-08 DSH geçişi: `--arac dsh` Hermes yerine headless komutunu üretmeli.

    Kilit: görev stdin'den gitmeli (argv'ye sığmaz), cwd depo kökü olmalı, karar dosyaları
    için `/tmp` sandbox'a eklenmeli ve `--approval-policy never` başsız oturumda asılı kalmamalı.
    """

    def setUp(self):
        self.eski = (nobetci.NOBETCI_ARAC, nobetci.DSH_CHECKOUT, nobetci.DSH_PERMISSION_MODE)
        self.eski_durum = nobetci.DURUM_KLASORU
        self.dizin = tempfile.TemporaryDirectory()
        self.addCleanup(self.dizin.cleanup)
        nobetci.DURUM_KLASORU = Path(self.dizin.name)
        # Test makinenin ~/.dsh kurulumuna bağlı olmamalı: geçici evi yamala.
        ev_yama = mock.patch.object(nobetci, "dsh_home_hazirla",
                                    return_value=Path(self.dizin.name) / "dsh-home")
        ev_yama.start()
        self.addCleanup(ev_yama.stop)

    def tearDown(self):
        nobetci.NOBETCI_ARAC, nobetci.DSH_CHECKOUT, nobetci.DSH_PERMISSION_MODE = self.eski
        nobetci.DURUM_KLASORU = self.eski_durum

    def test_headless_komutu_ve_sandbox_argumanlari(self):
        nobetci.NOBETCI_ARAC = "dsh"
        nobetci.DSH_CHECKOUT = Path("/opt/dsh")
        nobetci.DSH_PERMISSION_MODE = "read-only"
        komut = nobetci.dsh_komutu(Path("/depo"), Path("/gorev.md"), 1860)
        self.assertEqual(komut[:3], ["node", "/opt/dsh/apps/cli/lib/bin.js", "headless"])
        self.assertEqual(komut[komut.index("--permission-mode") + 1], "read-only")
        self.assertEqual(komut[komut.index("--approval-policy") + 1], "never")
        self.assertNotIn("--add-dir", komut)
        self.assertNotIn("chat", komut)

    def test_gecersiz_izin_modu_reddedilir(self):
        nobetci.NOBETCI_ARAC = "dsh"
        for kotu in ("", "workspace-write", "danger-full-access", "auto",
                     "Workspace Write", "a;rm -rf /", "x" * 40):
            nobetci.DSH_PERMISSION_MODE = kotu
            with self.subTest(kotu=kotu):
                with self.assertRaises(ValueError):
                    nobetci.dsh_komutu(Path("/depo"), Path("/gorev.md"), 60)

    def test_dsh_calistir_gorevi_stdin_ve_cwd_ile_verir(self):
        from types import SimpleNamespace
        from unittest import mock

        nobetci.NOBETCI_ARAC = "dsh"
        nobetci.DSH_CHECKOUT = Path("/opt/dsh")
        nobetci.DSH_PERMISSION_MODE = "read-only"
        with mock.patch.dict(os.environ, {"SECRET_CANARY": "s3cr3t",
                                          "DEEPSEEK_API_KEY": "anahtar-canary",
                                          "NODE_OPTIONS": "--max-old-space-size=950"}), \
                mock.patch.object(nobetci.subprocess, "run") as calistir:
            calistir.return_value = SimpleNamespace(returncode=0, stdout="ok", stderr="")
            kod, cikti = nobetci.hermes_calistir(Path("/depo"), "görev metni", "i5", 60, False)
        self.assertEqual((kod, cikti), (0, "ok"))
        args, kwargs = calistir.call_args
        self.assertIn("headless", args[0])
        self.assertEqual(kwargs["input"], "görev metni")
        self.assertEqual(kwargs["cwd"], "/depo")
        self.assertEqual(kwargs["timeout"], 60)
        self.assertIn("DSH_HOME", kwargs["env"])
        self.assertIn("KARAR_DIR", kwargs["env"])
        self.assertIn("PATH", kwargs["env"])
        # i5 2026-11-11: tüm ortam sandbox'a geçmemeli; yalnız allowlist.
        self.assertNotIn("SECRET_CANARY", kwargs["env"])
        self.assertNotIn("DEEPSEEK_API_KEY", kwargs["env"])
        # Bellek tavanı sır değil; DSH'ye geçmeye devam etmeli.
        self.assertEqual(kwargs["env"].get("NODE_OPTIONS"), "--max-old-space-size=950")


class DshProfilTesti(unittest.TestCase):
    """Kurulu profil güvenli runner + kapalı native araçlar içermeli."""

    def _profil(self, eksik: str = "") -> Path:
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        yol = Path(d.name) / "cordis.patch.yml"
        parcalar = [
            "runnerCommand:",
            "  - " + str(Path.home() / ".agents" / "bin" / "dsh-bwrap-kiosk"),
            "runnerFailureSignatures:",
            '  - "dsh-bwrap-kiosk:"',
        ]
        for arac in ("tool-fs", "tool-fs-search", "tool-web", "tool-subagent",
                     "tool-subagent-fork", "tool-workflow", "tool-agent-team",
                     "tool-subagent-control"):
            if arac == eksik:
                continue
            parcalar += [f"- id: {arac}", "  disabled: true"]
        yol.write_text("\n".join(parcalar) + "\n", encoding="utf-8")
        return yol

    def test_gecerli_profil_kabul_edilir(self):
        ok, neden = nobetci.dsh_profil_denetle(self._profil())
        self.assertTrue(ok, neden)

    def test_native_arac_kapali_degilse_reddedilir(self):
        ok, neden = nobetci.dsh_profil_denetle(self._profil("tool-web"))
        self.assertFalse(ok)
        self.assertIn("tool-web", neden)

    def test_profil_depodan_atomik_yenilenir(self):
        with tempfile.TemporaryDirectory() as d:
            depo = Path(d) / "depo"
            (depo / "otomasyon").mkdir(parents=True)
            kaynak = self._profil()
            (depo / "otomasyon" / "dsh-headless.cordis.patch.yml").write_text(
                kaynak.read_text(), encoding="utf-8")
            hedef = Path(d) / "hedef.yml"
            with mock.patch.object(nobetci, "dsh_profil_yolu", return_value=hedef), \
                    mock.patch.object(nobetci, "dsh_runner_hazirla", return_value=True):
                self.assertTrue(nobetci.dsh_profil_hazirla(depo))
            self.assertTrue(hedef.is_file())
            self.assertTrue(nobetci.dsh_profil_denetle(hedef)[0])

    def test_runner_yanlissa_reddedilir(self):
        yol = self._profil()
        yol.write_text(yol.read_text().replace("dsh-bwrap-kiosk", "/bin/true"))
        ok, neden = nobetci.dsh_profil_denetle(yol)
        self.assertFalse(ok)
        self.assertIn("runnerCommand", neden)


class DshOturumTesti(unittest.TestCase):
    """DSH oturum deposu 7 gün/1 GB politikasıyla budanmalı (7 Kasım i5 bulgusu)."""

    def setUp(self):
        self.dizin = tempfile.TemporaryDirectory()
        self.addCleanup(self.dizin.cleanup)
        self.eski = nobetci.DURUM_KLASORU
        nobetci.DURUM_KLASORU = Path(self.dizin.name)

    def tearDown(self):
        nobetci.DURUM_KLASORU = self.eski

    def test_eski_oturum_silinir_yeni_kalir(self):
        kok = nobetci.dsh_home() / "sessions"
        eski = kok / "session-eski"
        yeni = kok / "session-yeni"
        eski.mkdir(parents=True)
        yeni.mkdir(parents=True)
        (eski / "log").write_text("x" * 10)
        (yeni / "log").write_text("y" * 10)
        sekiz_gun = time.time() - 8 * 86400
        os.utime(eski, (sekiz_gun, sekiz_gun))
        silinen, kalan, _ = nobetci.dsh_oturum_temizle(gun=7)
        self.assertGreaterEqual(silinen, 1)
        self.assertFalse(eski.exists())
        self.assertTrue(yeni.exists())
        self.assertEqual(kalan, 1)

    def test_eski_storage_dosyasi_silinir(self):
        kok = nobetci.dsh_home() / "storages" / "session_projcache"
        kok.mkdir(parents=True)
        eski = kok / "eski.json"
        yeni = kok / "yeni.json"
        eski.write_text("{}")
        yeni.write_text("{}")
        os.utime(eski, (time.time() - 8 * 86400,) * 2)
        silinen, kalan, _ = nobetci.dsh_oturum_temizle(gun=7)
        self.assertGreaterEqual(silinen, 1)
        self.assertFalse(eski.exists())
        self.assertTrue(yeni.exists())
        self.assertEqual(kalan, 1)

    def test_silinemeyen_oturum_sayilmaz(self):
        kok = nobetci.dsh_home() / "sessions"
        eski = kok / "session-eski"
        eski.mkdir(parents=True)
        (eski / "log").write_text("x")
        os.utime(eski, (time.time() - 8 * 86400,) * 2)
        with mock.patch.object(nobetci.shutil, "rmtree", side_effect=OSError("kilit")):
            silinen, kalan, _ = nobetci.dsh_oturum_temizle(gun=7)
        self.assertEqual(silinen, 0)
        self.assertEqual(kalan, 1)
        self.assertTrue(eski.exists())

    def test_bayt_siniri_asilinca_en_eski_silinir(self):
        kok = nobetci.dsh_home() / "sessions"
        for ad in ("a", "b", "c"):
            d = kok / f"session-{ad}"
            d.mkdir(parents=True)
            (d / "log").write_text("x" * 100)
        silinen, kalan, bayt = nobetci.dsh_oturum_temizle(gun=30, azami_bayt=150)
        self.assertGreaterEqual(silinen, 1)
        self.assertLessEqual(bayt, 150)
        self.assertLess(kalan, 3)


class KararYayinTesti(unittest.TestCase):
    """DSH kararı sandbox dışında yayınlanmalı; i3 kabulü çift onayla birleştirmeli."""

    def setUp(self):
        self.dizin = tempfile.TemporaryDirectory()
        self.addCleanup(self.dizin.cleanup)
        self.eski = nobetci.DURUM_KLASORU
        nobetci.DURUM_KLASORU = Path(self.dizin.name)
        self.depo = Path(self.dizin.name) / "depo"
        (self.depo / "otomasyon" / "betik").mkdir(parents=True)
        (self.depo / "otomasyon" / "betik" / "karar_dogrula.py").write_text("")
        (self.depo / "otomasyon" / "betik" / "yaz.py").write_text("")
        nobetci.karar_klasoru().mkdir(parents=True)
        self.sha = "a" * 40
        (nobetci.karar_klasoru() / "karar-97.json").write_text(
            json.dumps({"pr": 97, "sha": self.sha, "karar": "kabul"}), encoding="utf-8")

    def tearDown(self):
        nobetci.DURUM_KLASORU = self.eski

    def test_once_kapi_sonra_yaz_ve_i3_cift_onay(self):
        with mock.patch.object(nobetci.subprocess, "run") as calistir:
            calistir.return_value = SimpleNamespace(returncode=0, stdout="ok", stderr="")
            nobetci.kararlari_yayinla(self.depo, "i3", [{"pr": 97, "sha": self.sha}], None)
        self.assertEqual(calistir.call_count, 2)
        kapi = calistir.call_args_list[0].args[0]
        yaz = calistir.call_args_list[1].args[0]
        self.assertIn("karar_dogrula.py", kapi[1])
        self.assertIn("yaz.py", yaz[1])
        self.assertIn("--birlestir", yaz)
        self.assertIn("--cift-onay", yaz)

    def test_karar_yolu_dizin_ise_cokmez_ve_temizler(self):
        yol = nobetci.karar_klasoru() / "karar-97.json"
        yol.unlink()
        yol.mkdir()
        (yol / "ic").write_text("x")
        gunluk = Path(self.dizin.name) / "nobetci.log"
        nobetci.karar_dosyalarini_temizle([{"pr": 97}], gunluk)
        self.assertFalse(yol.exists())

    def test_karar_yoksa_yaz_calistirilmaz(self):
        (nobetci.karar_klasoru() / "karar-97.json").unlink()
        with mock.patch.object(nobetci.subprocess, "run") as calistir:
            nobetci.kararlari_yayinla(self.depo, "i5", [{"pr": 97, "sha": self.sha}], None)
        self.assertEqual(calistir.call_count, 0)

    def _karar_yaz(self, **degisiklik) -> Path:
        yol = nobetci.karar_klasoru() / "karar-97.json"
        veri = {"pr": 97, "sha": self.sha, "karar": "kabul"}
        veri.update(degisiklik)
        yol.write_text(json.dumps(veri), encoding="utf-8")
        return yol

    def test_baska_pr_numarasi_yayinlanmaz(self):
        """JSON 'pr' alanı listedeki PR'dan farklıysa karar başka PR'a yazılamaz."""
        self._karar_yaz(pr=98)
        gunluk = Path(self.dizin.name) / "nobetci.log"
        with mock.patch.object(nobetci.subprocess, "run") as calistir:
            nobetci.kararlari_yayinla(self.depo, "i5", [{"pr": 97, "sha": self.sha}], gunluk)
        self.assertEqual(calistir.call_count, 0)
        metin = gunluk.read_text(encoding="utf-8")
        self.assertIn("uyuşmuyor", metin)
        self.assertIn("json pr=98", metin)

    def test_bos_veya_yanlis_sha_yayinlanmaz(self):
        """JSON sha'sı head sha değilse ya da boşsa kapı/yaz hiç çalışmaz."""
        for sha in ("", "b" * 40):
            with self.subTest(sha=sha or "boş"):
                self._karar_yaz(sha=sha)
                gunluk = Path(self.dizin.name) / f"nobetci-{sha[:1] or 'bos'}.log"
                with mock.patch.object(nobetci.subprocess, "run") as calistir:
                    nobetci.kararlari_yayinla(
                        self.depo, "i5", [{"pr": 97, "sha": self.sha}], gunluk)
                self.assertEqual(calistir.call_count, 0)
                self.assertIn("uyuşmuyor", gunluk.read_text(encoding="utf-8"))

    def test_257kb_karar_reddedilir_ve_silinir(self):
        """Boyut sınırını aşan dosya kapıya verilmez, günlüğe yazılır ve silinir."""
        yol = nobetci.karar_klasoru() / "karar-97.json"
        yol.write_text("x" * (257 * 1024), encoding="utf-8")
        gunluk = Path(self.dizin.name) / "nobetci.log"
        with mock.patch.object(nobetci.subprocess, "run") as calistir:
            nobetci.kararlari_yayinla(self.depo, "i5", [{"pr": 97, "sha": self.sha}], gunluk)
        self.assertEqual(calistir.call_count, 0)
        self.assertFalse(yol.exists())
        self.assertIn("üst sınır", gunluk.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class ZamanAsimiTesti(unittest.TestCase):
    """27 Ekim: i5 oturumu 1860 sn'de öldürüldü (çıkış 124) ve günlükte yalnız "oturum bitti
    (çıkış 124)" vardı. Operatör ne yapacağını göremiyordu; sonraki tur aynı duvara çarpıyordu.
    Kilit: 124 + karar yazılmamışsa günlükte EYLEM söyleyen bir ZAMAN AŞIMI satırı olmalı.
    """

    class SahteGh:
        def __init__(self):
            self.denemeler = {}
            self.gunluk = {}
            self.kaydedilen = {}

        def kaydet(self, veri):
            self.kaydedilen = veri

    def test_124_gunlukte_eylem_satiri_yazar(self):
        dizin = tempfile.TemporaryDirectory()
        self.addCleanup(dizin.cleanup)
        gunluk_yolu = Path(dizin.name) / "nobetci.log"
        is_ = {"pr": 83, "sha": "a" * 40, "baslik": "x", "yas_dk": 10}
        eski_calistir, eski_isler = nobetci.hermes_calistir, nobetci.isler
        eski_arac = nobetci.NOBETCI_ARAC
        nobetci.hermes_calistir = lambda *a, **k: (124, "zaman aşımı (1860s)")
        nobetci.isler = lambda *a, **k: [is_]          # karar YAZILMADI (liste değişmedi)
        nobetci.NOBETCI_ARAC = "hermes"                 # DSH_* ortamından bağımsız test
        try:
            kod = nobetci.tek_tur(self.SahteGh(), Path(dizin.name), "i5", 1, False, 1860, gunluk_yolu)
        finally:
            nobetci.hermes_calistir, nobetci.isler = eski_calistir, eski_isler
            nobetci.NOBETCI_ARAC = eski_arac
        metin = gunluk_yolu.read_text(encoding="utf-8")
        self.assertEqual(kod, 124)
        self.assertIn("ZAMAN AŞIMI", metin, "124 için eylem satırı yok")
        self.assertIn("--zaman-asimi", metin, "çözüm yolu yazılmıyor")
        self.assertIn("#83", metin, "hangi PR olduğu yazılmıyor")
