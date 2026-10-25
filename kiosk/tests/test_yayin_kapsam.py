"""Yayın hedefleme (ilçe/bölge/cihaz) + `durum.json` (tek istek) davranışı."""

from __future__ import annotations

import json
import sys
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import durum as durum_modulu  # noqa: E402
from core.broadcast_manager import BroadcastManager  # noqa: E402
from core.yayin_kapsam import kapsam_ozeti, kapsam_uygun, yayin_kapsami  # noqa: E402

ILCE = "30607352906750376"
BOLGE = "73154087615041151"
CIHAZ = "98273648723468273"
BAS = "2026-10-24T08:30:00"
BIT = "2026-10-24T23:59:00"


def yayin(**ek) -> dict:
    return {"start": BAS, "end": BIT, "contentUrl": "https://ornek.example/a.webp", "duration": 30, **ek}


class KapsamTesti(unittest.TestCase):
    def test_kapsamsiz_yayin_tum_cihazlarda(self):
        self.assertTrue(kapsam_uygun(yayin()))
        self.assertTrue(kapsam_uygun(yayin(), "baska-ilce", "baska-bolge", "baska-cihaz"))

    def test_ilce_eslesmesi(self):
        y = yayin(ilceId=ILCE)
        self.assertTrue(kapsam_uygun(y, ILCE, BOLGE, CIHAZ))
        self.assertFalse(kapsam_uygun(y, "diger-ilce", BOLGE, CIHAZ))

    def test_bolge_eslesmesi(self):
        y = yayin(bolgeId=BOLGE)
        self.assertTrue(kapsam_uygun(y, ILCE, BOLGE, CIHAZ))
        self.assertFalse(kapsam_uygun(y, ILCE, "diger-bolge", CIHAZ))

    def test_cihaz_eslesmesi_en_dar(self):
        y = yayin(cihazId=CIHAZ)
        self.assertTrue(kapsam_uygun(y, ILCE, BOLGE, CIHAZ))
        self.assertFalse(kapsam_uygun(y, ILCE, BOLGE, "baska"))

    def test_alias_alanlar(self):
        self.assertEqual(yayin_kapsami({"ilce_id": "X"})["ilceId"], "X")
        self.assertEqual(yayin_kapsami({"clientID": "Y"})["cihazId"], "Y")

    def test_bos_alan_kisit_saymaz(self):
        y = yayin(ilceId="", bolgeId=None, cihazId="   ")
        self.assertTrue(kapsam_uygun(y, "herhangi", "herhangi", "herhangi"))

    def test_ozet(self):
        self.assertEqual(kapsam_ozeti(yayin()), "tüm cihazlar")
        self.assertIn("ilçe=", kapsam_ozeti(yayin(ilceId=ILCE)))


class AktifYayinKapsamTesti(unittest.TestCase):
    """Qt tarafı: kapsam dışı yayın AKTİF LİSTEYE hiç girmez (indirilmez)."""

    def setUp(self):
        self.mgr = BroadcastManager(None)
        self.yayinlar = [
            yayin(contentUrl="https://ornek.example/genel.webp"),
            yayin(contentUrl="https://ornek.example/ilce.webp", ilceId=ILCE),
            yayin(contentUrl="https://ornek.example/baska-ilce.webp", ilceId="999"),
            yayin(contentUrl="https://ornek.example/cihaz.webp", cihazId=CIHAZ),
        ]

    def _url(self, liste):
        return [y["contentUrl"] for y in liste]

    def test_kapsam_uygulanir(self):
        from datetime import datetime

        an = datetime.fromisoformat("2026-10-24T12:00:00")
        aktif = self.mgr.get_active_yayinlar(self.yayinlar, an, ILCE, BOLGE, CIHAZ)
        self.assertEqual(
            self._url(aktif),
            ["https://ornek.example/genel.webp", "https://ornek.example/ilce.webp",
             "https://ornek.example/cihaz.webp"],
        )

    def test_baska_ilce_cihazi_kendi_yayinini_gorur(self):
        from datetime import datetime

        an = datetime.fromisoformat("2026-10-24T12:00:00")
        aktif = self.mgr.get_active_yayinlar(self.yayinlar, an, "999", "baska", "cihaz-x")
        self.assertEqual(
            self._url(aktif),
            ["https://ornek.example/genel.webp", "https://ornek.example/baska-ilce.webp"],
        )


class DurumBelgesiTesti(unittest.TestCase):
    def test_damga_tetik_komut(self):
        belge = {
            "zaman": "2026-10-24T09:12:00Z",
            "lastupdate": "2026-10-24 09:11:58",
            "tetik": {"zaman": "2026-10-24T09:12:00Z", "ilceId": ILCE, "aciklama": "panel"},
            "komut": {"zaman": "2026-10-24T09:13:00Z", "id": "abc"},
        }
        self.assertEqual(durum_modulu.damga(belge), "2026-10-24 09:11:58")
        tetik = durum_modulu.tetik(belge) or {}
        self.assertEqual(tetik.get("ilceId"), ILCE)
        self.assertEqual(durum_modulu.komut_isareti(belge), "2026-10-24T09:13:00Z|abc")

    def test_eksik_alanlar_guvenli(self):
        self.assertEqual(durum_modulu.damga({}), "")
        self.assertIsNone(durum_modulu.tetik({}))
        self.assertEqual(durum_modulu.komut_isareti(None), "")
        self.assertEqual(durum_modulu.damga(None), "")

    def test_bozuk_json_none(self):
        with unittest.mock.patch.object(durum_modulu.uzak, "kosullu_getir", return_value=(b"{bozuk", False, ('"e"', ""))):
            self.assertIsNone(durum_modulu.getir())

    def test_yoksa_none(self):
        with unittest.mock.patch.object(durum_modulu.uzak, "kosullu_getir", return_value=(None, False, ("", ""))):
            self.assertIsNone(durum_modulu.getir())

    def test_gecerli_belge(self):
        govde = json.dumps({"lastupdate": "D1", "tetik": {"zaman": "Z"}, "komut": {}}).encode()
        with unittest.mock.patch.object(durum_modulu.uzak, "kosullu_getir",
                                        return_value=(govde, False, ('"e"', ""))):
            belge = durum_modulu.getir()
        self.assertEqual(durum_modulu.damga(belge), "D1")

    def test_304_bellek_kopyasini_dondurur(self):
        """Koşullu okuma: 304'te gövde yok → son başarılı belge döner (maliyet)."""
        govde = json.dumps({"lastupdate": "D2"}).encode()
        with unittest.mock.patch.object(durum_modulu.uzak, "kosullu_getir",
                                        return_value=(govde, False, ('"e"', ""))):
            ilk = durum_modulu.getir()
        with unittest.mock.patch.object(durum_modulu.uzak, "kosullu_getir",
                                        return_value=(None, True, ('"e"', ""))):
            ikinci = durum_modulu.getir()
        self.assertEqual(ikinci, ilk)
        self.assertEqual(durum_modulu.damga(ikinci), "D2")


if __name__ == "__main__":
    unittest.main()
