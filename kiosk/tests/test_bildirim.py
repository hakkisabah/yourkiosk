"""KOMUT BİLDİRİMİ — `core/bildirim.py` (ekranda kısa "yeniden başlatılıyor" bilgisi)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from core import bildirim


@pytest.fixture(autouse=True)
def temiz() -> Iterator[None]:
    bildirim.sifirla()
    yield
    bildirim.sifirla()


def test_bilinmeyen_komut_genel_metin_alir() -> None:
    assert bildirim.metin_uret("") == bildirim.VARSAYILAN_METIN
    assert bildirim.metin_uret("rm -rf /") == bildirim.VARSAYILAN_METIN


def test_beyaz_listedeki_komutlarin_metni_sabit() -> None:
    assert "yeniden başlatılıyor" in bildirim.metin_uret("yeniden-baslat")
    assert "yeniden başlatılıyor" in bildirim.metin_uret("uygulamayi-yeniden-baslat")
    assert "yenileniyor" in bildirim.metin_uret("ekrani-yenile")


def test_goster_ve_aktif() -> None:
    assert bildirim.aktif(simdi=100.0) is None
    durum = bildirim.goster("ekrani-yenile", 4.0, simdi=100.0)
    assert durum["metin"] == bildirim.METINLER["ekrani-yenile"]
    gorunen = bildirim.aktif(simdi=101.0)
    assert gorunen is not None and gorunen["komut"] == "ekrani-yenile"


def test_sure_dolunca_kendiliginden_kalkar() -> None:
    """Süreli bildirim: süreç takılsa/çökse bile ekranda kalıcı yazı kalmaz."""
    bildirim.goster("yeniden-baslat", 8.0, simdi=10.0)
    assert bildirim.aktif(simdi=17.9) is not None
    assert bildirim.aktif(simdi=18.0) is None
    assert bildirim.aktif(simdi=19.0) is None, "süresi geçen kayıt temizlenmiş olmalı"


def test_temizle_hemen_kaldirir() -> None:
    bildirim.goster("uygulamayi-yeniden-baslat", 60.0, simdi=0.0)
    bildirim.temizle()
    assert bildirim.aktif(simdi=0.0) is None


def test_sifir_sure_bildirim_vermez() -> None:
    bildirim.goster("ekrani-yenile", 0.0, simdi=5.0)
    assert bildirim.aktif(simdi=5.0) is None


def test_donen_sozluk_kopya() -> None:
    """Çağıran, dönen sözlüğü değiştirse bile iç durum bozulmamalı."""
    durum = bildirim.goster("ekrani-yenile", 10.0, simdi=0.0)
    durum["metin"] = "sahte"
    aktif = bildirim.aktif(simdi=1.0)
    assert aktif is not None and aktif["metin"] == bildirim.METINLER["ekrani-yenile"]


# ------------------------------------------------ süre TEK KAYNAK (i5 bulgusu, PR #82)
def test_sure_uret_komuta_gore() -> None:
    """`ekrani-yenile` kısa, diğerleri varsayılan süre — tek kaynak `sure_uret`."""
    assert bildirim.sure_uret("ekrani-yenile") == bildirim.EKRANI_YENILE_SURE_S
    assert bildirim.sure_uret("Ekrani-Yenile") == bildirim.EKRANI_YENILE_SURE_S, "ad küçük harfe çevrilir"
    assert bildirim.sure_uret("yeniden-baslat") == bildirim.VARSAYILAN_SURE_S
    assert bildirim.sure_uret("bilinmeyen") == bildirim.VARSAYILAN_SURE_S


def test_goster_varsayilan_sureyi_sure_urettten_alir() -> None:
    """`goster(komut)` süre verilmezse `sure_uret` kullanır (Qt/tarayıcı ile aynı değer)."""
    durum = bildirim.goster("ekrani-yenile", simdi=100.0)
    assert durum["bitis"] - durum["baslangic"] == bildirim.EKRANI_YENILE_SURE_S
    durum2 = bildirim.goster("uygulamayi-yeniden-baslat", simdi=100.0)
    assert durum2["bitis"] - durum2["baslangic"] == bildirim.VARSAYILAN_SURE_S


def test_bekleme_suresi_yoklama_araligindan_turetilir() -> None:
    """Sabit `1.2` kopyalanmasın: bekleme, arayüz yoklama aralığından türetilir."""
    assert bildirim.ARAYUZ_YOKLAMA_S == 1.0, "web/src/App.vue yoklaması 1 sn — ikisi aynı olmalı"
    assert bildirim.YENILEME_ONCESI_BEKLEME_S == bildirim.ARAYUZ_YOKLAMA_S * 1.2


def test_tarayici_ve_qt_sabit_sure_kopyalamiyor() -> None:
    """Regresyon: `time.sleep(1.2)` ve `singleShot(8000)` sabitleri geri gelmemeli."""
    kok = Path(__file__).resolve().parents[1]
    tarayici = (kok / "core" / "tarayici.py").read_text(encoding="utf-8")
    assert "YENILEME_ONCESI_BEKLEME_S" in tarayici
    assert "time.sleep(1.2)" not in tarayici
    uygulama = (kok / "pharmacy_app.py").read_text(encoding="utf-8")
    assert "sure_uret" in uygulama, "Qt kaplaması süreyi tek kaynaktan almalı"
