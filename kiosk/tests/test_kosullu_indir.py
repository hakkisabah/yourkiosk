"""Görsel önbelleği: değişiklik YOKSA diskten okunmalı (304), varsa indirilmeli.

GERÇEK DURUM (kullanıcı sorusu): `gorsel_oku` "bayat" kayıtta None dönüyordu → veri damgası her
değiştiğinde TÜM görseller yeniden indiriliyordu (250 KB – 2,5 MB × 600 cihaz). Artık bayat kayıt
ETag/Last-Modified ile DOĞRULANIYOR; sunucu 304 derse gövde gelmez, diskteki kopya kullanılır.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from security.network import AgAyarlari, AgHatasi, kosullu_indir  # noqa: E402

URL = "https://ornek.example/a.png"


class _Yanit:
    def __init__(self, durum: int, govde: bytes = b"", basliklar: dict | None = None):
        self.status = durum
        self._govde = govde
        self.headers = basliklar or {}

    def read(self, n: int = -1) -> bytes:
        return self._govde

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class KosulluIndirTesti(unittest.TestCase):
    def _ayarlar(self) -> AgAyarlari:
        return AgAyarlari(izinli_hostlar=("ornek.example",), en_buyuk_bayt=1024 * 1024)

    def test_304_govde_indirilmez(self):
        yanit = _Yanit(304, b"", {"ETag": '"abc"'})
        with mock.patch("security.network._opener") as ac:
            ac.return_value.open.return_value = yanit
            bayt, tur, etag, tarih = kosullu_indir(URL, self._ayarlar(), etag='"abc"')
        self.assertIsNone(bayt)
        self.assertEqual(tur, "")
        self.assertEqual(etag, '"abc"')

    def test_200_govde_ve_etag_doner(self):
        yanit = _Yanit(200, b"\x89PNG" + b"0" * 100, {"Content-Type": "image/png", "ETag": '"yeni"',
                                                       "Last-Modified": "Mon, 27 Apr 2026 19:31:31 GMT"})
        with mock.patch("security.network._opener") as ac:
            ac.return_value.open.return_value = yanit
            bayt, tur, etag, tarih = kosullu_indir(URL, self._ayarlar())
        self.assertIsNotNone(bayt)
        self.assertEqual(tur, "image/png")
        self.assertEqual(etag, '"yeni"')
        self.assertIn("2026", tarih)

    def test_if_none_match_basligi_gonderilir(self):
        yanit = _Yanit(304, b"", {})
        with mock.patch("security.network._opener") as ac:
            ac.return_value.open.return_value = yanit
            kosullu_indir(URL, self._ayarlar(), etag='"abc"')
            istek = ac.return_value.open.call_args[0][0]
        self.assertEqual(istek.headers.get("If-none-match") or istek.headers.get("If-None-Match"), '"abc"')

    def test_politika_disi_host_reddedilir(self):
        with self.assertRaises(AgHatasi):
            kosullu_indir("https://kotu.example/a.png", self._ayarlar())

    def test_buyuk_govde_reddedilir(self):
        yanit = _Yanit(200, b"x" * 5000, {"Content-Type": "image/png"})
        ayarlar = AgAyarlari(izinli_hostlar=("ornek.example",), en_buyuk_bayt=1000)
        with mock.patch("security.network._opener") as ac:
            ac.return_value.open.return_value = yanit
            with self.assertRaises(AgHatasi):
                kosullu_indir(URL, ayarlar)


if __name__ == "__main__":
    unittest.main()
