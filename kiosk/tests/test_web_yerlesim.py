"""TARAYICI ARAYÜZÜNÜN YERLEŞİM VERİSİ — güncellik ve Qt kaynağıyla uyum denetimi.

İki şeyi kilitler:
  1. `web/src/veri/yerlesim.json` güncel mi (config.py/ayarlar.py değişip aktarım
     yenilenmezse test kırmızı olur — `sema_disa_aktar.py` deseniyle aynı),
  2. `ELLE_YERLESIM`/`ELLE_RENKLER` içindeki satır içi değerler Qt kaynağında hâlâ
     VAR mı (ör. `int(125 * app_instance.scale)` silinirse test uyarır).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
ARAC_YOLU = KOK / "tools" / "web_disa_aktar.py"


def _arac():
    spec = importlib.util.spec_from_file_location("web_disa_aktar_test", ARAC_YOLU)
    assert spec and spec.loader
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def test_yerlesim_dosyasi_guncel() -> None:
    arac = _arac()
    assert arac.HEDEF.is_file(), f"yerleşim dosyası yok: {arac.HEDEF} (python3 tools/web_disa_aktar.py)"
    assert arac.guncel_mi(), (
        "web/src/veri/yerlesim.json BAYAT: `cd kiosk && python3 tools/web_disa_aktar.py` çalıştırın"
    )


def test_yerlesim_olculeri_qt_ile_ayni() -> None:
    belge = _arac().belge_uret()
    o = belge["yerlesim"]["olculer"]
    # 1080p, taban 5 → satır 208 px; sol panel 499; sağ panel 1418; saat kutusu 226
    assert o["satir_yuksekligi"] == 208
    assert o["sol_panel_genislik"] == 499
    assert o["sag_panel_genislik"] == 1418
    assert o["saat_kutusu_genislik"] == 226
    assert o["viewport_yukseklik"] == 955
    assert o["sol_gorunur_yukseklik"] == 1080


def test_elle_yerlesim_degerleri_qt_kaynaginda_var() -> None:
    """Satır içi ölçü/punto değerleri Qt dosyalarında gerçekten duruyor mu?"""
    arac = _arac()
    eksik: list[str] = []
    for ad, (_deger, dosya, ifade) in arac.ELLE_YERLESIM.items():
        yol = KOK / dosya
        if not yol.is_file() or ifade not in yol.read_text(encoding="utf-8"):
            eksik.append(f"{ad}: {dosya} içinde '{ifade}' bulunamadı")
    assert not eksik, "Qt kaynağı değişmiş görünüyor:\n" + "\n".join(eksik)


def test_elle_renkler_qt_kaynaginda_var() -> None:
    arac = _arac()
    for ad, (renk, dosya) in arac.ELLE_RENKLER.items():
        yol = KOK / dosya
        assert yol.is_file() and renk in yol.read_text(encoding="utf-8"), f"{ad} ({renk}) {dosya} içinde yok"


def test_tarayici_paylasilan_veri_dosyalari_cihaz_kimligini_icermez() -> None:
    """Sunulan veri listesinde makinebilgileri.json OLMAMALI (kimlik URL'de gelir)."""
    from core import tarayici

    assert "makinebilgileri.json" not in tarayici.SUNULAN_VERI_DOSYALARI
    assert "lastSystemData.json" in tarayici.SUNULAN_VERI_DOSYALARI


def test_yerlesimde_varsayilanlar_config_ile_uyumlu() -> None:
    belge = _arac().belge_uret()
    v = belge["varsayilanlar"]
    assert v["ozellikler"]["nobet_listesi"] is True
    assert v["kusak"]["yazi_punto"] == belge["sabitler"]["KUSAK_YAZI_PUNTO"]
    assert v["gorunum"]["sol_panel_satir"] == belge["sabitler"]["MAKS_GORUNUR_SATIR"]


def test_dosya_json_ve_ozet_tutarli() -> None:
    arac = _arac()
    belge = json.loads(arac.HEDEF.read_text(encoding="utf-8"))
    assert belge["surum"] == 1
    assert belge["surum_ozeti"] == arac.belge_uret()["surum_ozeti"]
    assert belge["yerlesim"]["ekran"]["genislik"] == 1920
