"""hermes_komutu / butce_hesapla — nöbetçi oturumunun komut satırı sözleşmesi.

İki hata sınıfını makineyle kilitler:
1. **Tur tavanı ↔ duvar saati tutarsızlığı** (25 Ekim): 120 tur yazıp 9,5 sn/tur bütçe vermek
   incelemeyi yarıda kesiyordu. Bütçe darsa tavan KISILIR ve bu görünür olur.
2. **Ayrı profil** (26 Ekim i5 mimarisi): nöbetçi Open WebUI ile aynı gateway'i paylaşırsa aynı
   CPU/kota/oturum tavanını yer. `NOBETCI_PROFIL` verilince komut `hermes -p <ad> chat …` olmalı.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
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
        nobetci.hermes_calistir = lambda *a, **k: (124, "zaman aşımı (1860s)")
        nobetci.isler = lambda *a, **k: [is_]          # karar YAZILMADI (liste değişmedi)
        try:
            kod = nobetci.tek_tur(self.SahteGh(), Path(dizin.name), "i5", 1, False, 1860, gunluk_yolu)
        finally:
            nobetci.hermes_calistir, nobetci.isler = eski_calistir, eski_isler
        metin = gunluk_yolu.read_text(encoding="utf-8")
        self.assertEqual(kod, 124)
        self.assertIn("ZAMAN AŞIMI", metin, "124 için eylem satırı yok")
        self.assertIn("--zaman-asimi", metin, "çözüm yolu yazılmıyor")
        self.assertIn("#83", metin, "hangi PR olduğu yazılmıyor")
