"""`tetik.getir`/`komut.getir` KOŞULLU indirir — değişmeyen dosya için GÖVDE İNMEZ (304).

GERÇEK SORUN (i5 bulgusu, PR #78): `core/uzak.getir` önce tam gövdeyi indirip sonra bayt
karşılaştırması yapıyordu. `tetikle.json` için bu, Qt'de her 10 turda bir, tarayıcı uzun
yoklamasında ~3 saniyede bir TAM indirme demekti — dosya çoğu turda hiç değişmiyor.

ÇÖZÜM: ETag/Last-Modified hatırlanır (`security.network.kosullu_indir`) → sunucu 304 derse
gövde inmez, yerel dosyaya dokunulmaz (mtime değişmez → gereksiz arayüz tazelemesi olmaz).

Kanıt: gerçek HTTP sunucusu; sunucunun gönderdiği GÖVDE BAYTLARI sayılır.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import config
from core import komut, tetik, uzak
from security import network

GOVDE = json.dumps(
    {"zaman": "2026-10-24T07:10:00Z", "ilceId": "", "bolgeId": "", "aciklama": "test"}
).encode("utf-8")
ETAG = '"v1"'


class _Sunucu:
    """ETag destekli küçük HTTP sunucusu (If-None-Match eşleşirse 304, gövdesiz)."""

    def __init__(self) -> None:
        self.istekler: list[dict] = []
        self.govde_bayt = 0
        self.etag = ETAG
        self.icerik = GOVDE
        dis = self

        class Isleyici(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
                dis.istekler.append(
                    {
                        "yol": self.path,
                        "if-none-match": self.headers.get("If-None-Match") or "",
                        "if-modified-since": self.headers.get("If-Modified-Since") or "",
                    }
                )
                if dis.etag and self.headers.get("If-None-Match") == dis.etag:
                    self.send_response(304)
                    self.send_header("ETag", dis.etag)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(dis.icerik)))
                if dis.etag:
                    self.send_header("ETag", dis.etag)
                self.end_headers()
                self.wfile.write(dis.icerik)
                dis.govde_bayt += len(dis.icerik)

            def log_message(self, format, *args):  # noqa: A002 - sessiz günlük
                return

        self.httpd = HTTPServer(("127.0.0.1", 0), Isleyici)
        self.port = self.httpd.server_address[1]
        self.islec = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.islec.start()

    def kapat(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture()
def sunucu(monkeypatch):
    s = _Sunucu()
    monkeypatch.setattr(network, "IZINLI_SEMALAR", ("http", "https"))
    monkeypatch.setattr(config, "DOSYA_ADRESI", f"http://127.0.0.1:{s.port}", raising=False)
    monkeypatch.setattr(config, "ALLOWED_HOSTS", ("127.0.0.1",), raising=False)
    monkeypatch.setattr(config, "AG_IZINLI_PORTLAR", (s.port,), raising=False)
    monkeypatch.setattr(config, "TETIK_DOSYASI", "tetikle.json", raising=False)
    monkeypatch.setattr(config, "KOMUT_DOSYASI", "komut.json", raising=False)
    uzak._ETAG.clear()  # testler arası ETag sızmasın
    yield s
    s.kapat()
    uzak._ETAG.clear()


def test_ikinci_tur_304_alir_govde_inmez(sunucu, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(tetik, "PROJE_KOK", tmp_path)

    assert tetik.getir() is True, "ilk tur dosyayı indirmeli"
    dosya = tetik.dosya_yolu()
    assert dosya.is_file()
    ilk_mtime = dosya.stat().st_mtime_ns
    assert sunucu.govde_bayt == len(GOVDE)

    assert tetik.getir() is False, "değişmeyen dosya için 'değişti' denmemeli"
    assert sunucu.govde_bayt == len(GOVDE), "304'te gövde HİÇ inmemeli"
    assert sunucu.istekler[-1]["if-none-match"] == ETAG, "koşullu istek başlığı gönderilmeli"
    assert dosya.stat().st_mtime_ns == ilk_mtime, "yerel dosyaya dokunulmamalı"


def test_icerik_degisince_yeniden_indirilir(sunucu, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(tetik, "PROJE_KOK", tmp_path)
    assert tetik.getir() is True

    yeni = json.dumps({"zaman": "2026-10-24T09:30:00Z", "ilceId": "", "bolgeId": ""}).encode()
    sunucu.icerik = yeni
    sunucu.etag = '"v2"'
    assert tetik.getir() is True, "ETag değişti → yeni içerik inmeli"
    assert tetik.oku()["zaman"] == "2026-10-24T09:30:00Z"
    assert sunucu.govde_bayt == len(GOVDE) + len(yeni)


def test_etag_yoksa_eski_davranis_govde_her_turda_iner(sunucu, tmp_path, monkeypatch) -> None:
    """Sunucu ETag/Last-Modified vermiyorsa koşullu yol sessizce tam indirmeye döner."""
    monkeypatch.setattr(tetik, "PROJE_KOK", tmp_path)
    sunucu.etag = ""
    assert tetik.getir() is True
    assert tetik.getir() is False  # içerik aynı → yerel dosya değişmez
    assert sunucu.govde_bayt == 2 * len(GOVDE), "ETag yoksa gövde her turda iner (geriye dönük uyum)"


def test_komut_dosyasi_da_kosullu_indirilir(sunucu, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(komut, "PROJE_KOK", tmp_path)
    assert komut.getir() is True
    assert komut.getir() is False
    assert sunucu.govde_bayt == len(GOVDE), "komut.json değişmediyse gövde inmemeli"
