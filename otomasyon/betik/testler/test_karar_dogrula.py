"""karar_dogrula — karar kapısı regresyon testleri (ağ yok, `kanit=False`).

Kapının amacı: kararsızlığın `onay`a dönüşmesini ve kanıtsız/şablon kararların yayınlanmasını
ENGELLEMEK. Bu davranışlar testle kilitli; gevşetmek isteyen kişi testi de değiştirmek zorunda.
"""

from __future__ import annotations

import copy
import sys
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import karar_dogrula as kd  # noqa: E402

ALANLAR = list(kd.DENETIM_ALANLARI)

DOGRU_I5 = {
    "makine": "i5", "pr": 83, "sha": "a" * 40, "karar": "sorun", "onem": "orta",
    "ozet": "MQTT ACL betikleri ve push katmanı incelendi; yeniden bağlanma döngüsü riskli.",
    "bulgular": [{"dosya": "kiosk/core/push.py", "satir": 42, "onem": "orta",
                  "aciklama": "Yeniden bağlanma gecikmesi sabit; broker düşerse tüm cihazlar aynı saniyede bağlanır.",
                  "kabul": "Gecikme rastgele dağıtılmalı (jitter) ve testte 600 cihazın dağılımı ölçülmeli."}],
    "denetlenen": ALANLAR,
}


def kopya(**degisiklik):
    k = copy.deepcopy(DOGRU_I5)
    k.update(degisiklik)
    return k


def dogrula(karar, makine=None):
    return kd.dogrula_karar(karar, makine, kanit=False)


class SemaTesti(unittest.TestCase):
    def test_gecerli_karar_gecer(self):
        s = dogrula(DOGRU_I5)
        self.assertTrue(s.gecti, s.rapor())

    def test_karar_sozcugu_zorunlu(self):
        self.assertFalse(dogrula(kopya(karar="olabilir")).gecti)

    def test_onem_sozcugu_zorunlu(self):
        self.assertFalse(dogrula(kopya(onem="cok")).gecti)

    def test_kisa_ozet_reddedilir(self):
        self.assertFalse(dogrula(kopya(ozet="iyi")).gecti)

    def test_sablon_metni_reddedilir(self):
        self.assertFalse(dogrula(kopya(ozet="Şablon: buraya 1-3 cümlelik değerlendirme yazın.")).gecti)

    def test_bulgu_dosya_bos_reddedilir(self):
        k = kopya()
        k["bulgular"][0]["dosya"] = ""
        self.assertFalse(dogrula(k).gecti)

    def test_kisa_aciklama_reddedilir(self):
        k = kopya()
        k["bulgular"][0]["aciklama"] = "riskli"
        self.assertFalse(dogrula(k).gecti)


class KapsamTesti(unittest.TestCase):
    def test_i5_eksik_alan_reddedilir(self):
        s = dogrula(kopya(denetlenen=ALANLAR[:4]))
        self.assertFalse(s.gecti)
        self.assertIn("TAMAMI", s.rapor())

    def test_kisa_adlar_kabul_edilir(self):
        # model "TLS", "IAM en az yetki" gibi adlar yazar; kanonik alana eşlenmeli
        k = kopya(denetlenen=["gömülü sır", "komut çalıştırma", "dosya/yol", "TLS", "IAM en az yetki",
                              "girdi doğrulama", "sır sızıntısı", "bağımlılık", "DoS/maliyet",
                              "kalıcılık/geri dönüş", "kapsayıcı/servis", "test kanıtı"])
        self.assertTrue(dogrula(k).gecti, dogrula(k).rapor())

    def test_i3_en_az_sekiz_alan_ister(self):
        k = kopya(makine="i3", karar="kabul", denetlenen=["gömülü sır", "kimlik/yetki", "test kanıtı"])
        self.assertFalse(dogrula(k, "i3").gecti)

    def test_i3_zorunlu_uc_alan(self):
        k = kopya(makine="i3", karar="duzeltme", denetlenen=ALANLAR[3:])
        self.assertFalse(dogrula(k, "i3").gecti)


class TutarlilikTesti(unittest.TestCase):
    def test_yuksek_bulgu_ile_onay_verilemez(self):
        k = copy.deepcopy(DOGRU_I5)
        k.update(karar="onay", bulgular=[{"dosya": "kiosk/core/push.py", "satir": 42, "onem": "yuksek",
                                         "aciklama": "Sır pakete gömülüyor; paneli açan herkes okuyabilir."}])
        s = dogrula(k)
        self.assertFalse(s.gecti)
        self.assertIn("yüksek", s.rapor())

    def test_sorun_bulgusuz_verilemez(self):
        self.assertFalse(dogrula(kopya(bulgular=[])).gecti)

    def test_onay_bulgusuz_gecer(self):
        s = dogrula(kopya(karar="onay", bulgular=[], onem="dusuk"))
        self.assertTrue(s.gecti, s.rapor())

    def test_kapanis_olcutu_zorunlu(self):
        # Düzeltme/sorun kararında her bulgu "neyi yapınca kapanır" yazmalı; yoksa iki tur sonra
        # aynı bulgu geri döner (25 Ekim: i3'ün reçetesi uygulandı, aynı sınıf hata açık kaldı).
        k = copy.deepcopy(DOGRU_I5)
        del k["bulgular"][0]["kabul"]
        s = dogrula(k)
        self.assertFalse(s.gecti)
        self.assertIn("kapanış ölçütü", s.rapor())

    def test_kapanis_olcutu_serbest_metin_olamaz(self):
        k = copy.deepcopy(DOGRU_I5)
        k["bulgular"][0]["kabul"] = "buraya yazılacak"
        self.assertIn("şablon", dogrula(k).rapor())

    def test_onayda_kapanis_olcutu_istenmez(self):
        k = copy.deepcopy(DOGRU_I5)
        del k["bulgular"][0]["kabul"]
        self.assertTrue(dogrula(kopya(karar="onay", bulgular=[])).gecti)


class FailClosedTesti(unittest.TestCase):
    def test_kararsizlik_onaya_donusemez(self):
        for ifade in ("tam emin değilim", "doğrulanmalı", "karar veremedim", "şüpheli"):
            s = dogrula(kopya(karar="onay", bulgular=[], ozet=f"Belge düzeltmesi; {ifade}."))
            self.assertFalse(s.gecti, ifade)
            self.assertIn("FAIL-CLOSED", s.rapor())

    def test_kararsizlik_sorun_kararinda_serbest(self):
        s = dogrula(kopya(karar="sorun", ozet="Belge düzeltmesi; bir noktadan tam emin değilim, doğrulanmalı."))
        self.assertTrue(s.gecti, s.rapor())


class YardimciTesti(unittest.TestCase):
    def test_dosya_normal(self):
        self.assertEqual(kd.dosya_normal("`kiosk/core/push.py`"), "kiosk/core/push.py")
        self.assertEqual(kd.dosya_normal("kiosk/core/push.py:37"), "kiosk/core/push.py")
        self.assertEqual(kd.dosya_normal("kiosk/core/push.py:37-40"), "kiosk/core/push.py")

    def test_satir_no(self):
        self.assertEqual(kd.satir_no(37), 37)
        self.assertEqual(kd.satir_no("37-40"), 37)
        self.assertEqual(kd.satir_no(None), 0)
        self.assertEqual(kd.satir_no(True), 0)

    def test_alan_normal(self):
        self.assertEqual(kd.alan_normal("TLS"), "ağ/tls")
        self.assertEqual(kd.alan_normal("IAM en az yetki"), "kimlik/yetki")
        self.assertEqual(kd.alan_normal("  Test  "), "test kanıtı")

    def test_ascii_alan_adlari_kanonik_ada_doner(self):
        """26 Ekim i5 bulgusu: ASCII yazan dürüst bir karar '12 alan eksik' diye reddediliyordu."""
        ciftler = {
            "ag/tls": "ağ/tls", "komut calistirma": "komut çalıştırma",
            "sir sizintisi": "sır sızıntısı", "bagimlilik": "bağımlılık",
            "kalicilik/geri donus": "kalıcılık/geri dönüş",
            "kapsayici/servis": "kapsayıcı/servis", "test kaniti": "test kanıtı",
            "girdi dogrulama": "girdi doğrulama", "gomulu sir": "gömülü sır",
        }
        for ascii_ad, kanonik in ciftler.items():
            self.assertEqual(kd.alan_normal(ascii_ad), kanonik, ascii_ad)

    def test_ascii_alan_listesi_kapsam_hatasi_vermez(self):
        """12 alanın hepsi ASCII yazılsa da kapsam denetimi geçer."""
        ascii_alanlar = ["gomulu sir", "komut calistirma", "dosya/yol", "ag/tls", "kimlik/yetki",
                         "girdi dogrulama", "sir sizintisi", "bagimlilik", "dos/maliyet",
                         "kalicilik/geri donus", "kapsayici/servis", "test kaniti"]
        self.assertEqual(sorted(kd.alan_normal(a) for a in ascii_alanlar),
                         sorted(kd.DENETIM_ALANLARI))


class KanitKatmaniTesti(unittest.TestCase):
    """`kanit_denetle` — 26 Ekim i5 bulgusu: bu katman hiç test edilmiyordu (hepsi kanit=False).

    Testler ağı taklit eder (`kd._api`), yani gerçek GitHub'a istek gitmez.
    """

    def _karar(self, **degisiklik):
        k = kopya()
        k.update(degisiklik)
        return k

    @staticmethod
    def _icerik(metin: str) -> dict:
        import base64
        return {"content": base64.b64encode(metin.encode()).decode(), "encoding": "base64"}

    def _api_taklit(self, dosyalar: dict[str, str], head: str, degisen=None):
        """`dosyalar`: yol → içerik. Dönüş: (kod, veri) üreten fonksiyon."""
        def api(yol, token, depo):
            if yol.startswith("/pulls/") and "/files" in yol:
                return 200, [{"filename": d} for d in (degisen if degisen is not None else dosyalar)]
            if yol.startswith("/pulls/"):
                return 200, {"head": {"sha": head}}
            if yol.startswith("/contents/"):
                import urllib.parse
                ad = urllib.parse.unquote(yol.split("/contents/")[1].split("?")[0])
                if ad in dosyalar:
                    return 200, self._icerik(dosyalar[ad])
                return 404, None
            return 404, None
        return api

    def test_satir_sayisi_son_yeni_satirda_bir_fazla_saymaz(self):
        # "a\nb\nc\n" = 3 satır. Eski kod 4 diyordu → olmayan 4. satır "kanıt" sayılıyordu.
        sha = "b" * 40
        karar = self._karar(sha=sha, bulgular=[{"dosya": "x.py", "satir": 4, "onem": "dusuk",
                                               "aciklama": "olmayan satır", "kabul": "x"}])
        sonuc = kd.Sonuc()
        with unittest.mock.patch.object(kd, "_api", self._api_taklit({"x.py": "a\nb\nc\n"}, sha)):
            kd.kanit_denetle(karar, sonuc, "t", "depo")
        self.assertFalse(sonuc.gecti)
        self.assertTrue(any("yalnız 3 satır" in h for h in sonuc.hatalar), sonuc.hatalar)

    def test_satir_sifir_ile_karar_gecmez(self):
        """26 Ekim i5 bulgusu: satır numarası olmayan bulgu yalnız UYARI alıyordu → kapı geçiyordu.

        Bulgu taşıyan 'sorun' kararında `dosya:satır` ZORUNLU; satir=0 karar geçmez.
        """
        sha = "f" * 40
        karar = self._karar(sha=sha, bulgular=[{"dosya": "x.py", "satir": 0, "onem": "orta",
                                               "aciklama": "satırsız bulgu", "kabul": "satır ver"}])
        sonuc = kd.Sonuc()
        with unittest.mock.patch.object(kd, "_api", self._api_taklit({"x.py": "a\nb\n"}, sha)):
            kd.kanit_denetle(karar, sonuc, "t", "depo")
        self.assertFalse(sonuc.gecti)
        self.assertTrue(any("satır numarası verilmemiş" in h for h in sonuc.hatalar), sonuc.hatalar)

    def test_onay_kararinda_satir_aranmaz(self):
        """Onayın kanıtı bulgu değil, denetlenen alan listesidir: satir=0 onayı bloklamaz."""
        sha = "a" * 40
        karar = self._karar(sha=sha, karar="onay", bulgular=[
            {"dosya": "x.py", "satir": 0, "onem": "dusuk", "aciklama": "bilgi notu", "kabul": "-"}])
        sonuc = kd.Sonuc()
        with unittest.mock.patch.object(kd, "_api", self._api_taklit({"x.py": "a\nb\n"}, sha)):
            kd.kanit_denetle(karar, sonuc, "t", "depo")
        self.assertTrue(sonuc.gecti, sonuc.hatalar)

    def test_bayat_sha_reddedilir(self):
        karar = self._karar(sha="a" * 40)
        sonuc = kd.Sonuc()
        with unittest.mock.patch.object(kd, "_api",
                                        self._api_taklit({"kiosk/core/push.py": "x\n" * 60}, "c" * 40)):
            kd.kanit_denetle(karar, sonuc, "t", "depo")
        self.assertFalse(sonuc.gecti)
        self.assertTrue(any("BAYAT" in h for h in sonuc.hatalar), sonuc.hatalar)

    def test_bulunamayan_dosya_hata(self):
        sha = "d" * 40
        karar = self._karar(sha=sha, bulgular=[{"dosya": "yok.py", "satir": 1, "onem": "orta",
                                               "aciklama": "yok", "kabul": "y"}])
        sonuc = kd.Sonuc()
        with unittest.mock.patch.object(kd, "_api", self._api_taklit({}, sha)):
            kd.kanit_denetle(karar, sonuc, "t", "depo")
        self.assertTrue(any("bulunamadı" in h for h in sonuc.hatalar), sonuc.hatalar)

    def test_degismeyen_dosya_uyari(self):
        sha = "e" * 40
        karar = self._karar(sha=sha, bulgular=[{"dosya": "baglam.py", "satir": 1, "onem": "dusuk",
                                               "aciklama": "bağlam", "kabul": "z"}])
        sonuc = kd.Sonuc()
        with unittest.mock.patch.object(kd, "_api",
                                        self._api_taklit({"baglam.py": "a\n"}, sha, degisen=["baska.py"])):
            kd.kanit_denetle(karar, sonuc, "t", "depo")
        self.assertTrue(sonuc.gecti, sonuc.hatalar)
        self.assertTrue(any("değişen dosyalar arasında değil" in u for u in sonuc.uyarilar), sonuc.uyarilar)

    def test_token_yoksa_kapi_fail_closed(self):
        # Kanıt katmanı çalışamıyorsa karar GEÇMEZ (eskiden yalnız uyarıyordu).
        sonuc = kd.dogrula_karar(kopya(), None, token=None, kanit=True)
        self.assertFalse(sonuc.gecti)
        self.assertTrue(any("fail-closed" in h for h in sonuc.hatalar), sonuc.hatalar)

    def test_head_okunamazsa_fail_closed(self):
        """26 Ekim i5 bulgusu: head 0/403/429 ile okunamazsa karar GEÇMEMELİ (eskiden yalnız uyarı).

        Kanıt dosyası karar dosyasındaki (bayat olabilecek) sha'da BULUNABİLİYOR: eski kod bu yüzden
        kararı geçiriyordu. Yeni kod head'i doğrulayamadığı için reddeder.
        """
        import base64
        karar = self._karar(sha="a" * 40)
        icerik = {"content": base64.b64encode(("x\n" * 60).encode()).decode(), "encoding": "base64"}
        cagrilar: list[str] = []

        def api(yol, token, depo):
            cagrilar.append(yol)
            if "/files" in yol:
                return 200, [{"filename": "kiosk/core/push.py"}]
            if yol.startswith("/pulls/"):
                return kod, None                      # head OKUNAMIYOR
            if yol.startswith("/contents/"):
                return 200, icerik                    # bayat sha'da kanıt "var"
            return 404, None

        for kod in (0, 403, 429):
            cagrilar.clear()
            sonuc = kd.Sonuc()
            with unittest.mock.patch.object(kd, "_api", api):
                kd.kanit_denetle(karar, sonuc, "t", "depo")
            self.assertFalse(sonuc.gecti, f"HTTP {kod}: bayat kanıtla karar geçti")
            self.assertTrue(any(f"head okunamadı (HTTP {kod})" in h for h in sonuc.hatalar), sonuc.hatalar)
            self.assertFalse(any("sha karşılaştırması yapılmadı" in u for u in sonuc.uyarilar), sonuc.uyarilar)
            self.assertFalse(any("/contents/" in y for y in cagrilar),
                             f"head okunamazken içerik denetlendi: {cagrilar}")

    def test_token_varken_kanit_katmani_calisir(self):
        sha = "f" * 40
        karar = self._karar(sha=sha)
        with unittest.mock.patch.object(kd, "_api",
                                        self._api_taklit({"kiosk/core/push.py": "x\n" * 60}, sha)):
            sonuc = kd.dogrula_karar(karar, None, token="t", kanit=True)
        self.assertTrue(sonuc.gecti, sonuc.hatalar)


if __name__ == "__main__":
    unittest.main(verbosity=2)
