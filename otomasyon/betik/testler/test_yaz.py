"""yaz.py — PR yorum gövdesi testleri (ağ yok).

Neden: karar kapısı `kabul` (kapanış ölçütü) alanını ZORUNLU kılıyor; ama ölçüt PR yorumuna
basılmıyorsa geliştiriciye hiç ulaşmaz (26 Ekim i5 bulgusu). Aynı sınıf hata: kapı atlandığında
bunun yorumda görünmemesi.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yaz  # noqa: E402


def karar(**degisiklik) -> dict:
    k = {
        "makine": "i5", "pr": 90, "sha": "a" * 40, "karar": "sorun", "onem": "orta",
        "ozet": "İki bulgu var.", "denetlenen": ["gömülü sır"],
        "bulgular": [{"dosya": "otomasyon/betik/nobetci.py", "satir": 241, "onem": "orta",
                      "aciklama": "gunluk adı çakışıyor",
                      "kabul": "gunluk_yolu ayrı alan olmalı ve test bunu kilitlemeli"}],
    }
    k.update(degisiklik)
    return k


class YorumGovdesiTesti(unittest.TestCase):
    def test_kapanis_olcutu_yorumda_gorunur(self):
        govde = yaz.yorum_govdesi(karar(), "failure")
        self.assertIn("Kapanış ölçütü", govde)
        self.assertIn("gunluk_yolu ayrı alan olmalı", govde)

    def test_kabul_yoksa_tire_basilir(self):
        b = karar()["bulgular"][0]
        b.pop("kabul")
        govde = yaz.yorum_govdesi(karar(bulgular=[b]), "failure")
        self.assertIn("| — |", govde)

    def test_i3_eksiklerinde_de_kapanis_olcutu(self):
        govde = yaz.yorum_govdesi(karar(makine="i3", eksikler=[
            {"dosya": "web/src/kiosk.ts", "satir": 12, "onem": "orta",
             "aciklama": "önbellek atlanmıyor", "kabul": "bildirim gelince zorla yenileme testi"}]), "failure")
        self.assertIn("Kapanış ölçütü", govde)
        self.assertIn("bildirim gelince zorla yenileme testi", govde)

    def test_kapi_atlandi_yorumda_uyari(self):
        govde = yaz.yorum_govdesi(karar(kapi_atlandi="kanıt katmanı çevrimdışı, elle doğrulandı"), "failure")
        self.assertIn("KARAR KAPISI ATLANDI", govde)
        self.assertIn("çevrimdışı", govde)

    def test_baslik_ve_durum_simgesi(self):
        self.assertIn("i5 — güvenlik incelemesi", yaz.yorum_govdesi(karar(), "success"))
        self.assertIn("i3 — karar", yaz.yorum_govdesi(karar(makine="i3"), "failure"))


class DurumMetniTesti(unittest.TestCase):
    def test_aciklama_140_karakteri_asmaz(self):
        durum, aciklama = yaz.durum_metni(karar(ozet="çok uzun " * 60))
        self.assertEqual(durum, "failure")
        self.assertLessEqual(len(aciklama), 140)

    def test_onay_durumu_success(self):
        self.assertEqual(yaz.durum_metni(karar(karar="onay", onem="dusuk", bulgular=[]))[0], "success")


if __name__ == "__main__":
    unittest.main(verbosity=2)
