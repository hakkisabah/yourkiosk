"""REGRESYON: `durum.json` yolu (tek istek) MQTT tetikleyicisini YEMEMELİ.

Gerçek hata: `durum.json` tek-istek yoluna geçildiğinde MQTT push'un yazdığı YEREL `tetikle.json`
hiç okunmadı → panelden "Bildir" anlık çalışmadı (30 dk yoklamaya kaldı).
Ayrıca `durum.json` tek hata noktası olmamalı: her 10 turda `lastupdate.json` ile çapraz kontrol.
"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import model  # noqa: E402


class ModelTekKaynakTesti(unittest.TestCase):
    def test_uretılen_model_guncel(self):
        """`model.generated.json` elle değiştirilmişse / model değişip üretilmemişse kırılır."""
        icerik = model.metin()
        for hedef in model.HEDEFLER:
            self.assertTrue(hedef.is_file(), f"model dosyası yok: {hedef} — çalıştır: python3 tools/model_disa_aktar.py")
            self.assertEqual(
                hedef.read_text(encoding="utf-8"), icerik,
                f"{hedef.name} güncel değil — çalıştır: cd kiosk && python3 tools/model_disa_aktar.py",
            )

    def test_kapsam_alanlari_modelde(self):
        adlar = {a["ad"] for a in model.YAYIN_ALANLARI}
        self.assertTrue({"ilceId", "bolgeId", "cihazId"} <= adlar)
        self.assertEqual(model.KAPSAM_KURALLARI["coklu_alan"], "VE")
        # alias'lar kiosk tarafındaki kabul listesiyle uyumlu olmalı
        cihaz = next(a for a in model.YAYIN_ALANLARI if a["ad"] == "cihazId")
        self.assertIn("clientID", cihaz["alias"])


class DurumYoluTetikTesti(unittest.TestCase):
    """`durum.secili_tetik`: durum.json'da tetik yoksa YEREL (MQTT) tetikle.json kullanılmalı."""

    def test_durum_tetigi_onde_gelir(self):
        from core import durum as durum_modulu

        belge = {"lastupdate": "D1", "tetik": {"zaman": "UZAK", "ilceId": ""}}
        secilen = durum_modulu.secili_tetik(belge, lambda: {"zaman": "YEREL"})
        self.assertEqual((secilen or {})["zaman"], "UZAK")

    def test_durum_tetigi_yoksa_yerel_kullanilir(self):
        from core import durum as durum_modulu

        secilen = durum_modulu.secili_tetik({"lastupdate": "D1"}, lambda: {"zaman": "YEREL"})
        self.assertIsNotNone(secilen, "MQTT push'un yazdığı yerel tetik yok sayılmamalı")
        self.assertEqual((secilen or {})["zaman"], "YEREL")

    def test_ikisi_de_yoksa_none(self):
        from core import durum as durum_modulu

        self.assertIsNone(durum_modulu.secili_tetik({"lastupdate": "D1"}, lambda: None))
        self.assertIsNone(durum_modulu.secili_tetik(None, lambda: {}))

    def test_yerel_okuma_hatasi_gostermeyi_durdurmaz(self):
        from core import durum as durum_modulu

        def patlat():
            raise OSError("disk")

        self.assertIsNone(durum_modulu.secili_tetik({"lastupdate": "D1"}, patlat))


class ModelDosyaBicimiTesti(unittest.TestCase):
    def test_uretilen_dosya_gecerli_json(self):
        for hedef in model.HEDEFLER:
            belge = json.loads(hedef.read_text(encoding="utf-8"))
            self.assertEqual(belge["surum"], model.SURUM)
            self.assertTrue(belge["_aciklama"].startswith("ÜRETİLMİŞ"))


if __name__ == "__main__":
    unittest.main()
