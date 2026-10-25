"""KOMUT BİLDİRİMİ — `core/bildirim.py` (ekranda kısa "yeniden başlatılıyor" bilgisi)."""

from __future__ import annotations

from collections.abc import Iterator

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
