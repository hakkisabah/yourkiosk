"""Nöbetçi bekleme mantığı — oturum fırtınasını önleyen fren.

Neden: karar yazılamadığında (token/izin/geçici hata) nöbetçi her turda yeniden oturum açıyordu;
i5/i3 panolarında session sayısı sürekli artıyordu. Aynı PR+commit için üstel bekleme uygulanır.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_YOL = Path(__file__).resolve().parents[2] / "otomasyon" / "betik" / "nobetci.py"
_spec = importlib.util.spec_from_file_location("nobetci", _YOL)
assert _spec is not None and _spec.loader is not None
nobetci = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nobetci)


def test_deneme_yoksa_beklemez() -> None:
    assert nobetci.beklemeli_mi({}, 16, "abcdef123456", an=1000.0) == (False, 0)


def test_ilk_denemeden_sonra_taban_sure_bekler() -> None:
    denemeler = {"16:abcdef123456": {"sayi": 1, "son": 1000.0}}
    bekle, kalan = nobetci.beklemeli_mi(denemeler, 16, "abcdef123456", an=1000.0 + 60)
    assert bekle is True
    assert kalan == nobetci.BEKLEME_TABANI_S - 60


def test_sure_dolunca_yeniden_dener() -> None:
    denemeler = {"16:abcdef123456": {"sayi": 1, "son": 1000.0}}
    assert nobetci.beklemeli_mi(denemeler, 16, "abcdef123456",
                                an=1000.0 + nobetci.BEKLEME_TABANI_S + 1) == (False, 0)


def test_bekleme_ustel_artar_ve_tavani_asmaz() -> None:
    for sayi, beklenen in ((1, 600), (2, 1200), (3, 2400), (10, nobetci.BEKLEME_TAVAN_S)):
        denemeler = {"7:x": {"sayi": sayi, "son": 0.0}}
        bekle, kalan = nobetci.beklemeli_mi(denemeler, 7, "x", an=0.0)
        assert bekle is True
        assert kalan == beklenen


def test_farkli_commit_etkilenmez() -> None:
    denemeler = {"16:aaaaaaaaaaaa": {"sayi": 5, "son": 1000.0}}
    assert nobetci.beklemeli_mi(denemeler, 16, "bbbbbbbbbbbb", an=1001.0) == (False, 0)


def test_anahtar_sha_kisaltir() -> None:
    assert nobetci.anahtar(42, "1234567890abcdef") == "42:1234567890ab"
