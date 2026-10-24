"""Saat dilimi farkı: panel UTC (`...Z`) ile cihazın YEREL tetikleyicisi karşılaştırması.

GERÇEK SORUN (i5 bulgusu, PR #78): `durum.secili_tetik` iki tetikleyiciyi sözlüksel
karşılaştırıyordu ve "aynı biçim" varsayıyordu. Panel `new Date().toISOString()` ile UTC yazıyor
(`2026-10-24T22:25:00.000Z`), cihazın MQTT tetiği `datetime.now().isoformat()` ile yerel saat
(`2026-10-25T01:25:00`). UTC+3 cihazda yerel damga hep 3 saat ileri görünür → panelin DAHA YENİ
tetiği "eski" sayılır ve panel "Bildir" cihazda sessizce yutulur.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from core import durum as durum_modulu
from core import zaman


@pytest.fixture()
def yerel_saat_dilimi(monkeypatch):
    """Cihazı UTC+3 yap (Türkiye) — test makinesinin saat diliminden bağımsız."""
    monkeypatch.setenv("TZ", "Europe/Istanbul")
    if hasattr(time, "tzset"):
        time.tzset()
    yield
    monkeypatch.undo()
    if hasattr(time, "tzset"):
        time.tzset()


def test_coz_farkli_bicimleri_anlar() -> None:
    utc = zaman.coz("2026-10-24T22:25:00.000Z")
    assert utc is not None and utc.utcoffset() == timedelta(0)
    ofsetli = zaman.coz("2026-10-25T01:25:00+03:00")
    assert ofsetli is not None and ofsetli.utcoffset() == timedelta(hours=3)
    panel_bicimi = zaman.coz("2026-10-24 09:11:58")
    assert panel_bicimi is not None
    assert zaman.coz("dün") is None
    assert zaman.coz(None) is None
    assert zaman.coz("") is None


def test_karsilastir_ayni_an_farkli_bicim() -> None:
    # 22:25 UTC == 01:25 (+03) → EŞİT an
    assert zaman.karsilastir("2026-10-24T22:25:00.000Z", "2026-10-25T01:25:00+03:00") == 0
    # 22:30 UTC, 01:25 (+03)den daha yeni
    assert zaman.karsilastir("2026-10-24T22:30:00.000Z", "2026-10-25T01:25:00+03:00") == 1


def test_panel_tetigi_yerel_tetikten_yeniyse_secilir(yerel_saat_dilimi) -> None:
    """REGRESYON: yerel tetik `01:25` (yerel), panel tetiği `22:30Z` = `01:30` yerel → PANEL seçilmeli."""
    su_an = datetime.now()
    yerel_eski = (su_an - timedelta(minutes=5)).replace(microsecond=0).isoformat()  # uzantısız = yerel
    uzak_yeni = (su_an - timedelta(minutes=1)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    # sözlüksel karşılaştırma BURADA YANLIŞ: yerel metin (01:2x) > UTC metni (22:2x)
    assert yerel_eski > uzak_yeni, "testin savı anlamlı olsun: sözlüksel sıra ters"

    belge = {"tetik": {"zaman": uzak_yeni, "ilceId": ""}}
    yerel = {"zaman": yerel_eski, "ilceId": ""}
    secilen = durum_modulu.secili_tetik(belge, lambda: yerel)
    assert secilen is not None
    assert secilen["zaman"] == uzak_yeni, "panelin YENİ tetiği seçilmeli (TZ farkı yüzünden yutulmamalı)"


def test_yerel_tetik_daha_yeniyse_yerel_secilir(yerel_saat_dilimi) -> None:
    su_an = datetime.now()
    yerel_yeni = (su_an - timedelta(minutes=1)).replace(microsecond=0).isoformat()
    uzak_eski = (su_an - timedelta(minutes=30)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    belge = {"tetik": {"zaman": uzak_eski, "ilceId": ""}}
    yerel = {"zaman": yerel_yeni, "ilceId": ""}
    secilen = durum_modulu.secili_tetik(belge, lambda: yerel)
    assert secilen is not None and secilen["zaman"] == yerel_yeni


def test_cozulemeyen_damgada_sozluksele_duser() -> None:
    """Biçim çözülemezse eski davranış korunur (kırılma değil, geriye dönüş)."""
    belge = {"tetik": {"zaman": "zzz", "ilceId": ""}}
    yerel = {"zaman": "aaa", "ilceId": ""}
    secilen = durum_modulu.secili_tetik(belge, lambda: yerel)
    assert secilen is not None and secilen["zaman"] == "zzz"


def test_naif_damga_yerel_saat_sayilir(yerel_saat_dilimi) -> None:
    """Uzantısız damga cihazın yerel saatidir; +03 ofsetiyle aynı ana denk gelir."""
    an = datetime.now().replace(microsecond=0)
    assert zaman.karsilastir(an.isoformat(), an.isoformat() + "+03:00") == 0
