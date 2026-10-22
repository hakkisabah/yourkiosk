"""Uzak (https) ayarlar: birleştirme kuralları ve çevrimdışı davranış.

Kullanıcı kararı: panelden yayınlanan `ayarlar.json` cihaza ULAŞMALI (tarayıcı + Qt).
Ama cihaza/ağa özgü anahtarlar yayınla EZİLMEMELİ — yanlış bir yayın cihazı kilitlememeli.
"""

from __future__ import annotations

import json

import config


def test_birlestir_uzak_kazanir() -> None:
    import ayarlar

    yerel = {"gelismis": {"max_gosterilen_kayit": 10}}
    uzak = {"gelismis": {"max_gosterilen_kayit": 60, "max_aktif_yayin": 3}, "ozellikler": {"yayinlar": False}}
    sonuc = ayarlar.birlestir(yerel, uzak)
    assert sonuc["gelismis"]["max_gosterilen_kayit"] == 60
    assert sonuc["gelismis"]["max_aktif_yayin"] == 3
    assert sonuc["ozellikler"]["yayinlar"] is False


def test_birlestir_cihaza_ozgu_anahtarlarda_yerel_kazanir() -> None:
    import ayarlar

    yerel = {
        "veri": {"kaynak": "https", "dosya_adresi": "https://cihaz/"},
        "ag": {"izinli_hostlar": ["cihaz.example"]},
    }
    uzak = {
        "veri": {"kaynak": "dosya", "dosya_adresi": "https://yanlis/"},  # yayın bunları değiştiremez
        "ag": {"izinli_hostlar": ["baska.example"]},
    }
    sonuc = ayarlar.birlestir(yerel, uzak)
    assert sonuc["veri"]["kaynak"] == "https"
    assert sonuc["veri"]["dosya_adresi"] == "https://cihaz/"
    assert sonuc["ag"]["izinli_hostlar"] == ["cihaz.example"]


def test_uzak_belge_kaynak_dosya_ise_istek_atmaz(monkeypatch) -> None:
    import ayarlar

    monkeypatch.setattr(config, "KAYNAK", "dosya", raising=False)
    monkeypatch.setattr(config, "DOSYA_ADRESI", "https://ornek/", raising=False)

    def patlat(*_a, **_k):  # ağ çağrısı YAPILMAMALI
        raise AssertionError("KAYNAK=dosya iken ağa çıkılmamalı")

    monkeypatch.setattr(ayarlar, "indir", patlat)
    assert ayarlar._uzak_belge() == {}


def test_uzak_belge_ag_hatasinda_bos_doner(monkeypatch) -> None:
    import ayarlar

    monkeypatch.setattr(config, "KAYNAK", "https", raising=False)
    monkeypatch.setattr(config, "DOSYA_ADRESI", "https://ornek/", raising=False)

    def hata(*_a, **_k):
        raise OSError("ağ yok")

    monkeypatch.setattr(ayarlar, "indir", hata)
    assert ayarlar._uzak_belge() == {}  # cihaz ayarsız kalmaz


def test_uygula_uzak_ayarlari_config_e_yazar(tmp_path, monkeypatch) -> None:
    import ayarlar

    yerel = tmp_path / "ayarlar.json"
    yerel.write_text(json.dumps({"gelismis": {"max_gosterilen_kayit": 10}}), encoding="utf-8")
    monkeypatch.setattr(ayarlar, "_uzak_belge", lambda: {"gelismis": {"max_gosterilen_kayit": 60}})
    eski = config.MAX_GOSTERILEN_ECZANE
    try:
        ayarlar.uygula(yerel, zorla=True)
        assert config.MAX_GOSTERILEN_ECZANE == 60
    finally:
        config.MAX_GOSTERILEN_ECZANE = eski
        ayarlar._uygulanan_yollar.clear()
