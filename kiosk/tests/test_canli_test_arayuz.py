"""`tools/canli_test.py` — ARAYÜZ halkası (beyaz ekran kapısı) testleri.

NEDEN (6 Kasım i5 bulgusu, orta): sağlık kapısı yalnız süreç/uzak veri/disk/MQTT/tetik
halkalarına bakıyordu. `vite` `emptyOutDir: true` ile `web/dist`i baştan boşaltır; derleme
yarıda kalırsa cihaz BEYAZ EKRANLA açılır ve kapı bunu "sağlıklı" sayıp güncellemeyi
tamamlanmış ilan ederdi. Bu testler halkayı GERÇEK bir HTTP sunucusuna karşı ölçer.

Her test ÖLÇÜLEN kusuru yeniden üretir; halka zayıflarsa KIRMIZI olur.
"""

from __future__ import annotations

import http.server
import importlib.util
import threading
from pathlib import Path

import pytest

KIOSK = Path(__file__).resolve().parents[1]


def _modul():
    spec = importlib.util.spec_from_file_location("canli_test_arayuz", KIOSK / "tools" / "canli_test.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def canli():
    return _modul()


def _isleyici(dizin: Path):
    """Geçici dizini sunan sessiz istek işleyicisi (sınıf fabrikası)."""

    class Sessiz(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):  # noqa: ANN002, ANN003, D107
            super().__init__(*a, directory=str(dizin), **k)

        def log_message(self, format, *args):  # noqa: A002, ANN001
            pass

    return Sessiz


@pytest.fixture()
def sunucu(tmp_path: Path):
    """Geçici dizini sunan gerçek HTTP sunucusu: (port, dizin) döner."""
    s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _isleyici(tmp_path))
    t = threading.Thread(target=s.serve_forever, daemon=True)
    t.start()
    try:
        yield s.server_address[1], tmp_path
    finally:
        s.shutdown()
        s.server_close()


def _paket(dizin: Path, *, js: bytes = b"console.log('kiosk');" * 20, varlik: str = "/assets/app.js") -> None:
    (dizin / "assets").mkdir(parents=True, exist_ok=True)
    (dizin / "index.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>yourkiosk</title>"
        f"<div id='app'>yourkiosk kiosk</div><script type=\"module\" src=\"{varlik}\"></script>",
        encoding="utf-8",
    )
    hedef = dizin / varlik.lstrip("/")
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_bytes(js)


def test_saglam_paket_gecer(canli, sunucu) -> None:
    port, dizin = sunucu
    _paket(dizin)
    ok, metin = canli.arayuz_test(port=port)
    assert ok, metin
    assert "/assets/app.js" in metin


def test_index_yoksa_kirmizi(canli, sunucu) -> None:
    port, _ = sunucu
    ok, metin = canli.arayuz_test(port=port)
    assert not ok
    assert "index.html" in metin


def test_index_js_varligina_isaret_etmiyorsa_kirmizi(canli, sunucu) -> None:
    """Yarım derleme: index.html var ama hiçbir JS varlığına işaret etmiyor."""
    port, dizin = sunucu
    (dizin / "index.html").write_text(
        "<!doctype html><title>yourkiosk</title><div id='app'></div>", encoding="utf-8"
    )
    ok, metin = canli.arayuz_test(port=port)
    assert not ok
    assert "JS varlığına işaret etmiyor" in metin


def test_ana_js_varligi_yoksa_kirmizi(canli, sunucu) -> None:
    """vite hash'li dosyayı yazmadan düşerse: index.html durur, varlık 404 olur."""
    port, dizin = sunucu
    _paket(dizin)
    (dizin / "assets" / "app.js").unlink()
    ok, metin = canli.arayuz_test(port=port)
    assert not ok
    assert "ana JS varlığı" in metin and "404" in metin


def test_bos_js_varligi_kirmizi(canli, sunucu) -> None:
    port, dizin = sunucu
    _paket(dizin, js=b"")
    ok, metin = canli.arayuz_test(port=port)
    assert not ok
    assert "bayt" in metin


def _yanlis_tur_isle(dizin: Path):
    """Her dosyayı `text/html` olarak sunan işleyici (SPA fallback taklidi)."""

    class YanlisTur(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):  # noqa: ANN002, ANN003, D107
            super().__init__(*a, directory=str(dizin), **k)

        def guess_type(self, path):  # noqa: ANN001, D102
            return "text/html"

        def log_message(self, format, *args):  # noqa: A002, ANN001
            pass

    return YanlisTur


def test_js_yerine_html_gelirse_kirmizi(canli, tmp_path: Path) -> None:
    """Sunucu 200 dönse de içerik tipi JS değilse (SPA fallback) paket sağlam sayılmaz."""
    (tmp_path / "index.html").write_text(
        "<!doctype html><title>yourkiosk</title><script src=\"/app.js\"></script>", encoding="utf-8"
    )
    (tmp_path / "app.js").write_bytes(b"console.log('kiosk');" * 20)

    s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _yanlis_tur_isle(tmp_path))
    t = threading.Thread(target=s.serve_forever, daemon=True)
    t.start()
    try:
        ok, metin = canli.arayuz_test(port=s.server_address[1])
    finally:
        s.shutdown()
        s.server_close()
    assert not ok
    assert "içerik tipi" in metin


def test_sunucu_kapaliysa_kirmizi(canli) -> None:
    ok, metin = canli.arayuz_test(port=1)  # dinleyen yok
    assert not ok
    assert "ulaşılamadı" in metin


def test_kiosk_isi_yoksa_kirmizi(canli, sunucu) -> None:
    """Başka bir uygulamanın index.html'i kiosk paketi sayılmamalı."""
    port, dizin = sunucu
    _paket(dizin)
    (dizin / "index.html").write_text(
        "<!doctype html><title>baska</title><script src='/assets/app.js'></script>", encoding="utf-8"
    )
    ok, metin = canli.arayuz_test(port=port)
    assert not ok
    assert "kiosk işaretini taşımıyor" in metin
