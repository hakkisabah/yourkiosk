"""YOKLAMA ARALIĞI — "kapatıp açmadan düzelmiyor" sınıfına karşı kilit.

Gerçek hata: `pharmacy_app.yoklama_araligi()` içinde `push_modulu` **tanımsızdı** (import yok).
`NameError` geniş `except` tarafından yutuluyor, `bagli` her zaman False oluyordu → aralık
hesabı sessizce yanlış. Bu test, import'un varlığını ve aralık kararını birlikte doğrular.

Ayrıca: `push.durum()["bagli"]` paho'nun GERÇEK `is_connected()` değerini yansıtmalı; sözlükteki
bayrak kısa kopmalarda bayat kalıyordu (log: "MQTT bağlandı" → 2 sn sonra "KOPUK").
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def uygulama():
    from PyQt6.QtWidgets import QApplication

    import pharmacy_app

    qapp = QApplication.instance() or QApplication([])
    yield qapp, pharmacy_app


def test_push_modulu_tanimli(uygulama) -> None:
    """`push` modülü pharmacy_app içinde ÇÖZÜLMELİ (NameError sınıfı)."""
    _qapp, pharmacy_app = uygulama
    assert hasattr(pharmacy_app, "push_modulu"), (
        "pharmacy_app'te `push_modulu` tanımsız — yoklama aralığı sessizce 'kopuk' sayılır"
    )
    assert callable(getattr(pharmacy_app.push_modulu, "durum"))


def test_bagli_iken_120_sn(uygulama, monkeypatch) -> None:
    _qapp, pharmacy_app = uygulama
    monkeypatch.setattr(pharmacy_app.push_modulu, "durum", lambda: {"bagli": True})
    uygulama_nesnesi = pharmacy_app.PharmacyApp.__new__(pharmacy_app.PharmacyApp)
    assert uygulama_nesnesi.yoklama_araligi() == 120_000


def test_kopuk_iken_30_sn(uygulama, monkeypatch) -> None:
    _qapp, pharmacy_app = uygulama
    monkeypatch.setattr(pharmacy_app.push_modulu, "durum", lambda: {"bagli": False})
    uygulama_nesnesi = pharmacy_app.PharmacyApp.__new__(pharmacy_app.PharmacyApp)
    assert uygulama_nesnesi.yoklama_araligi() == 30_000


def test_durum_hatasi_aralik_hesabini_kirmaz(uygulama, monkeypatch) -> None:
    """Push durumu okunamazsa istisna YUTULMAZ ama yoklama da durmaz: sıkı moda düşer."""
    _qapp, pharmacy_app = uygulama

    def patlat() -> dict:
        raise RuntimeError("paho yok")

    monkeypatch.setattr(pharmacy_app.push_modulu, "durum", patlat)
    uygulama_nesnesi = pharmacy_app.PharmacyApp.__new__(pharmacy_app.PharmacyApp)
    assert uygulama_nesnesi.yoklama_araligi() == 30_000


def test_push_durum_gercek_baglantiyi_okur(monkeypatch) -> None:
    """`durum()` sözlük bayrağına değil `is_connected()`e güvenir."""
    from core import push

    class SahteIstemci:
        def __init__(self, bagli: bool) -> None:
            self.bagli = bagli

        def is_connected(self) -> bool:
            return self.bagli

    monkeypatch.setattr(push, "_istemci_ref", [SahteIstemci(True)])
    assert push.durum()["bagli"] is True
    monkeypatch.setattr(push, "_istemci_ref", [SahteIstemci(False)])
    assert push.durum()["bagli"] is False
