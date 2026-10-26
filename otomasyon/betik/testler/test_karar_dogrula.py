"""karar_dogrula — karar kapısı regresyon testleri (ağ yok, `kanit=False`).

Kapının amacı: kararsızlığın `onay`a dönüşmesini ve kanıtsız/şablon kararların yayınlanmasını
ENGELLEMEK. Bu davranışlar testle kilitli; gevşetmek isteyen kişi testi de değiştirmek zorunda.
"""

from __future__ import annotations

import copy
import sys
import unittest
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
