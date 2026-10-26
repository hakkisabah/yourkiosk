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


# --- tur tavanı (2026-10-25: oturumlar 60/60 turda bitip karar yazmıyordu) ----------

def test_tur_tavani_60tan_buyuk() -> None:
    """60 tur derin incelemeye yetmiyordu: oturum "Iteration budget reached (60/60)" ile bitiyor,
    PR'a yeni karar yazılmıyor, aynı head kuyrukta dönüyordu. Tavan en az 90 olmalı."""
    assert nobetci.OTURUM_TUR_TAVANI >= 90


def test_hermes_komutu_tur_tavanini_uygular(tmp_path) -> None:
    """Komut satırındaki `--max-turns`, sabitle AYNI olmalı (sessizce 60'a dönmesin)."""
    gorev = tmp_path / "gorev-i5.md"
    gorev.write_text("x", encoding="utf-8")
    komut = nobetci.hermes_komutu(tmp_path, gorev, nobetci.VARSAYILAN_ZAMAN_ASIMI)
    assert "--max-turns" in komut
    assert komut[komut.index("--max-turns") + 1] == str(nobetci.OTURUM_TUR_TAVANI)
    # duvar saati sınırı run-budget'tir; tur tavanı onu aşmamalı
    butce = int(komut[komut.index("--run-budget") + 1])
    assert butce <= nobetci.VARSAYILAN_ZAMAN_ASIMI


# --- tur tavanı ↔ duvar saati bütçesi tutarlılığı (25 Ekim i3 bulgusu) --------------
# i3: tavan 120'ye çıkarken bütçe 1140 sn kaldı → tur başına 9,5 sn; commit gerekçesindeki
# 1680 sn yalnız elle farklı bir --zaman-asimi verilirse doğruydu. Artık ikisi türetiliyor.

def test_varsayilan_zaman_asimi_tavandan_turetilir() -> None:
    beklenen = nobetci.OTURUM_TUR_TAVANI * nobetci.TUR_SURE_PAYI_S + nobetci.KAPANIS_PAYI_S
    assert nobetci.VARSAYILAN_ZAMAN_ASIMI == beklenen
    b = nobetci.butce_hesapla(beklenen)
    assert b["tur"] == nobetci.OTURUM_TUR_TAVANI          # tavan tam kullanılıyor
    assert b["tur_basi_sn"] >= nobetci.EN_AZ_TUR_SURESI_S  # tur başına yeterli süre
    assert b["yeterli"] is True


def test_dar_butcede_tavan_kisilir_duvar_saati_asilmaz() -> None:
    """1140 sn bütçeyle 120 tur istemek yerine tur sayısı kısılır (duvar saati aşılmaz)."""
    b = nobetci.butce_hesapla(1200)
    assert b["butce"] <= 1200
    assert b["tur"] < nobetci.OTURUM_TUR_TAVANI
    assert b["yeterli"] is False


def test_komut_dar_butcede_kisilmis_tur_yazar(tmp_path) -> None:
    gorev = tmp_path / "gorev-i5.md"
    gorev.write_text("x", encoding="utf-8")
    komut = nobetci.hermes_komutu(tmp_path, gorev, 1200)
    b = nobetci.butce_hesapla(1200)
    assert komut[komut.index("--max-turns") + 1] == str(b["tur"])
    assert int(komut[komut.index("--run-budget") + 1]) <= 1200
