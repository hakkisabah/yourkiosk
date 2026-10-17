"""NÖBET DEĞİŞİKLİĞİ TETİKLEYİCİSİ testleri — `core/tetik.py` (tek kural kaynağı).

Kapsam: dosya işlemleri (yaz/oku/sil/imza), ilçe-bölge kuralı ve cihazın hemen yenilenmesini
sağlayan yollar (hızlı damga okuma + zorla yükleme).
"""

from __future__ import annotations

import json

import pytest

import config
from core import data_handler, tetik, veri_kaynagi


@pytest.fixture()
def tetik_dosyasi(monkeypatch, tmp_path):
    """Gerçek `tetikle.json`'a dokunmadan geçici dosya kullan."""
    hedef = tmp_path / "tetikle-test.json"
    monkeypatch.setattr(config, "TETIK_DOSYASI", hedef.name)
    monkeypatch.setattr(tetik, "PROJE_KOK", tmp_path)
    return hedef


# ------------------------------------------------------------------ dosya işlemleri
def test_yaz_oku_sil(tetik_dosyasi) -> None:
    belge = tetik.yaz("I1", "B1", "test")
    assert tetik_dosyasi.is_file()
    okunan = tetik.oku()
    assert okunan == {"zaman": belge["zaman"], "ilceId": "I1", "bolgeId": "B1", "aciklama": "test"}
    assert tetik.sil() is True
    assert tetik.oku() is None
    assert tetik.sil() is False  # ikinci silme: dosya yok


def test_oku_bozuk_veya_eksik_zamanli_dosyayi_yok_sayar(tetik_dosyasi) -> None:
    assert tetik.oku() is None  # hiç dosya yok
    tetik_dosyasi.write_text("{bozuk", encoding="utf-8")
    assert tetik.oku() is None
    tetik_dosyasi.write_text(json.dumps({"ilceId": "I1"}), encoding="utf-8")
    assert tetik.oku() is None  # `zaman` yok → tetikleyici sayılmaz
    tetik_dosyasi.write_text(json.dumps({"zaman": "   "}), encoding="utf-8")
    assert tetik.oku() is None


def test_imza_yazimla_degisir(tetik_dosyasi) -> None:
    bos = tetik.imza()
    tetik.yaz("I1")
    dolu = tetik.imza()
    assert bos != dolu
    assert "tetik" not in bos  # dosya yokken de çalışır (imza '-' ile üretilir)


# ------------------------------------------------------------------ kural
def test_uygulanmali_kapsam_kurallari() -> None:
    t = {"zaman": "2026-10-17T09:00:00", "ilceId": "", "bolgeId": "", "aciklama": ""}
    assert tetik.uygulanmali(t, "I1", "B1") is True  # tüm cihazlar
    assert tetik.uygulanmali({**t, "ilceId": "*"}, "I1", "B1") is True
    assert tetik.uygulanmali({**t, "ilceId": "I1"}, "I1", "B1") is True  # kendi ilçesi
    assert tetik.uygulanmali({**t, "bolgeId": "B1"}, "I1", "B1") is True  # kendi bölgesi
    assert tetik.uygulanmali({**t, "ilceId": "I9"}, "I1", "B1") is False  # başka ilçe
    assert tetik.uygulanmali({**t, "ilceId": "I9", "bolgeId": "B9"}, "I1", "B1") is False


def test_uygulanmali_ayni_tetikleyici_tekrar_uygulanmaz() -> None:
    t = {"zaman": "2026-10-17T09:00:00", "ilceId": "", "bolgeId": "", "aciklama": ""}
    assert tetik.uygulanmali(t, "I1", "B1", son_uygulanan="2026-10-17T09:00:00") is False
    assert tetik.uygulanmali(t, "I1", "B1", son_uygulanan="2026-10-17T10:00:00") is False  # eski
    assert tetik.uygulanmali(t, "I1", "B1", son_uygulanan="2026-10-17T08:00:00") is True  # yeni
    assert tetik.uygulanmali(None, "I1", "B1") is False
    assert tetik.uygulanmali({"zaman": ""}, "I1", "B1") is False


# ------------------------------------------------------------------ cihaz yolları
def test_lastupdate_taze_onbellegi_atlar(monkeypatch, tmp_path) -> None:
    """Hızlı denetim, tur içi damga önbelleğine takılmadan TAZE değeri görmeli."""
    sira = {"deger": "D1"}
    monkeypatch.setattr(veri_kaynagi, "lastupdate_yukle", lambda: {"lastupdate": sira["deger"]})
    monkeypatch.setattr(veri_kaynagi, "_lastupdate_damgasi", None, raising=False)

    assert veri_kaynagi.lastupdate_taze() == "D1"  # tur içinde memo oluşur
    sira["deger"] = "D2"
    assert veri_kaynagi._guncel_lastupdate() == "D1"  # memo (eski davranış)
    assert veri_kaynagi.lastupdate_taze() == "D2"  # taze okuma: değişikliği görür


def test_uygulama_tetikleyiciyi_hemen_uygular(pencere, monkeypatch, tmp_path) -> None:
    """Qt uygulaması: kendi ilçesinin tetikleyicisini görünce BEKLEMEDEN veri yeniler."""
    import pharmacy_app

    hedef = tmp_path / "tetikle-test-app.json"
    monkeypatch.setattr(config, "TETIK_DOSYASI", hedef.name)
    monkeypatch.setattr(tetik, "PROJE_KOK", tmp_path)
    monkeypatch.setattr(pharmacy_app.veri_kaynagi, "lastupdate_taze", lambda: "D1")

    app = pencere()
    app.data_handler.lastupdate = "D1"  # damga değişmedi → yalnız tetikleyici yolu kalır
    app.data_handler.konum = type("K", (), {"ilce_id": "I1", "bolge_id": "B1"})()
    cagrilar: list[bool] = []
    monkeypatch.setattr(app, "load_data", lambda zorla=False: cagrilar.append(zorla))

    # başka ilçe: uygulanmaz
    tetik.yaz("I9", "", "başka ilçe")
    app.tetik_kontrol()
    assert cagrilar == []

    # kendi ilçesi: hemen uygulanır (zorla)
    tetik.yaz("I1", "", "kendi ilçemiz")
    app.tetik_kontrol()
    assert cagrilar == [True]
    assert app._son_tetik  # aynı tetikleyici tekrar uygulanmasın diye işaretlendi

    # aynı tetikleyici tekrar: uygulanmaz
    app.tetik_kontrol()
    assert cagrilar == [True]


def test_uygulama_damga_degisince_yeniler(pencere, monkeypatch, tmp_path) -> None:
    """Damga değiştiyse tetikleyici olmasa da veri yenilenir (hızlı denetim yolu)."""
    import pharmacy_app

    monkeypatch.setattr(config, "TETIK_DOSYASI", "tetikle-yok-test.json")
    monkeypatch.setattr(tetik, "PROJE_KOK", tmp_path)
    monkeypatch.setattr(pharmacy_app.veri_kaynagi, "lastupdate_taze", lambda: "D2")

    app = pencere()
    app.data_handler.lastupdate = "D1"
    cagrilar: list[bool] = []
    monkeypatch.setattr(app, "load_data", lambda zorla=False: cagrilar.append(zorla))

    app.tetik_kontrol()
    assert cagrilar == [False]  # damga yolu: zorla değil (normal yenileme)


def test_zorla_yukleme_damga_ayni_olsa_da_yeniler(monkeypatch) -> None:
    """Tetikleyici yolu: damga değişmese bile veri yeniden okunur (panel güncelledi)."""
    cagrilar = {"sistem": 0}
    monkeypatch.setattr(data_handler.veri_kaynagi, "lastupdate_yukle", lambda: {"lastupdate": "D1"})
    monkeypatch.setattr(
        data_handler.veri_kaynagi,
        "sistem_verisi_yukle",
        lambda: (cagrilar.__setitem__("sistem", cagrilar["sistem"] + 1), {"Nobetler": {}, "Yayinlar": {}})[1],
    )
    monkeypatch.setattr(data_handler.onbellek, "veri_temizle", lambda *_: 0)
    monkeypatch.setattr(data_handler.onbellek, "aktif", lambda: False)  # bakım adımı atlansın

    isleyici = data_handler.DataHandler()
    isleyici.load_data()
    ilk = cagrilar["sistem"]
    # veri elde var (liste boş değil) → damga aynıyken yeniden OKUNMAZ
    isleyici.pharmacies = [{"eczane": "X"}]
    isleyici.load_data()
    assert cagrilar["sistem"] == ilk
    # TETİKLEYİCİ yolu: damga aynı olsa da zorla okunur
    isleyici.load_data(zorla=True)
    assert cagrilar["sistem"] == ilk + 1
