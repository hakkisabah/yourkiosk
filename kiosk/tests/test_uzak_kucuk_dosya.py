"""`core.uzak.getir` — JSON içerikli küçük dosyalar kabul edilmeli, 403/404 gürültü yapmamalı.

GERÇEK HATA: `indir()` görsel içerik türü beyaz listesini uyguluyordu (png/jpeg/webp) ve
`tetikle.json` (`application/json`) reddediliyordu:
    WARNING kiosk.uzak: küçük dosya alınamadı (…/tetikle.json): içerik türü kabul edilmiyor: application/json
Sonuç: Qt modunda **anlık tetikleme hiç çalışmıyordu**. Ayrıca `komut.json` yokken (403) her 20 sn'de
uyarı basılıyordu.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import uzak  # noqa: E402
from security.network import AgHatasi  # noqa: E402

TABAN = "https://ornek.example"


class UzakKucukDosyaTesti(unittest.TestCase):
    def _getir(self, donus=None, hata: Exception | None = None):
        def sahte_indir(url, ayarlar, **kw):
            if hata is not None:
                raise hata
            return donus

        with mock.patch("security.network.indir", sahte_indir):
            return uzak.getir("tetikle.json", taban=TABAN)

    def test_json_kabul_edilir(self):
        govde = b'{"zaman":"2026-10-23T19:19:23.653Z"}'
        self.assertEqual(self._getir((govde, "application/json")), govde)

    def test_json_charset_eki_kabul_edilir(self):
        govde = b"{}"
        self.assertEqual(self._getir((govde, "application/json; charset=utf-8")), govde)

    def test_beklenmeyen_icerik_turu_reddedilir(self):
        self.assertIsNone(self._getir((b"<html>", "text/html")))

    def test_403_sessiz_none(self):
        self.assertIsNone(self._getir(hata=AgHatasi("HTTP 403")))

    def test_404_sessiz_none(self):
        self.assertIsNone(self._getir(hata=AgHatasi("HTTP 404")))

    def test_gercek_politika_hatasi_none(self):
        self.assertIsNone(self._getir(hata=AgHatasi("adres izin listesinde değil: kotu.example")))

    def test_taban_yoksa_none(self):
        with mock.patch.object(uzak, "taban_adres", return_value=""):
            self.assertIsNone(uzak.getir("tetikle.json"))


if __name__ == "__main__":
    unittest.main()
