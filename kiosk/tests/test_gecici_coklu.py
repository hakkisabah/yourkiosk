"""GEÇİCİ ÇOKLU TEST aracı testleri (`tools/gecici_coklu_test.py`).

NEDEN: araç bir kez "ilk üç günü dolduruyordu, uygulama ise 'şimdi'yi içeren bloğu gösteriyordu"
hatasıyla sessizce işe yaramadı (ekranda cihazın kendi kayıtları göründü). Bu testler aracın
**gösterilecek bloğu** doldurduğunu, damgayı tazelediğini ve geri almanın birebir olduğunu kilitler.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from core import sync
from tools import gecici_coklu_test as arac


def _kayit(eczane: str, ilce_id: str, bolge_id: str, start: str = "", end: str = "") -> dict:
    return {
        "eczane": eczane,
        "tel": "02620000000",
        "adres": "ADRES",
        "adres_tarifi": "",
        "bolge": "Test Bölge",
        "ilce": "ÇAYIROVA",
        "bolgeId": bolge_id,
        "ilceId": ilce_id,
        # gerçek veride kayıtlar pencere taşır (08:30 → ertesi gün 08:30): blok seçimi buna bakar
        "start": start,
        "end": end,
    }


def _sistem(an: datetime, ilce_id: str = "I1", bolge_id: str = "B1", gun_sayisi: int = 5) -> dict:
    """`an` çevresinde `gun_sayisi` bloklu, hedef ilçede 1 kayıtlı veri üretir (pencereleriyle)."""
    nobetler: dict[str, dict] = {}
    for i in range(gun_sayisi):
        # blok anahtarı 08:30 devrine göre üretilir (uygulamanın kuralı: 08:30'dan önce önceki gün)
        gun = (an + timedelta(days=i - 2)).replace(hour=8, minute=30, second=0, microsecond=0)
        anahtar = sync.nobet_anahtari(gun)
        bas = f"{gun.day:02d}/{gun.month:02d}/{gun.year} 08:30"
        ertesi = gun + timedelta(days=1)
        bit = f"{ertesi.day:02d}/{ertesi.month:02d}/{ertesi.year} 08:30"
        nobetler[anahtar] = {
            ilce_id: [{bolge_id: [_kayit("GERÇEK", ilce_id, bolge_id, bas, bit)]}],
            "I9": [{"B9": [_kayit("BAŞKA İLÇE", "I9", "B9", bas, bit)]}],
        }
    return {"Nobetler": nobetler, "Yayinlar": {}}


def _kur(monkeypatch, tmp_path, sistem: dict, lastupdate: str = "ESKİ-DAMGA") -> dict:
    """Araç dosya yollarını geçici klasöre yönlendirir (gerçek cihaz dosyalarına DOKUNMAZ)."""
    (tmp_path / "_arsiv").mkdir(parents=True, exist_ok=True)
    sistem_yolu = tmp_path / "lastSystemData.json"
    lastupdate_yolu = tmp_path / "lastupdate.json"
    sistem_yolu.write_text(json.dumps(sistem, ensure_ascii=False), encoding="utf-8")
    lastupdate_yolu.write_text(json.dumps({"lastupdate": lastupdate}), encoding="utf-8")
    monkeypatch.setattr(arac, "KOK", tmp_path)
    monkeypatch.setattr(arac, "SISTEM", sistem_yolu)
    monkeypatch.setattr(arac, "LASTUPDATE", lastupdate_yolu)
    monkeypatch.setattr(arac, "ARSIV", tmp_path / "_arsiv")
    monkeypatch.setattr(arac, "SISTEM_YEDEK", tmp_path / "_arsiv" / "lastSystemData.gercek.json")
    monkeypatch.setattr(arac, "LASTUPDATE_YEDEK", tmp_path / "_arsiv" / "lastupdate.gercek.json")
    monkeypatch.setattr(arac, "ISARET", tmp_path / "_arsiv" / "GECICI-COKLU-TEST.md")
    monkeypatch.setattr(arac, "cihaz_konumu", lambda: ("I1", "B1"))  # cihazın ilçesi
    return {"sistem": sistem_yolu, "lastupdate": lastupdate_yolu, "kok": tmp_path}


# ------------------------------------------------------------------ blok seçimi (kök neden)
def test_hedef_bloklar_gosterilen_blogu_secer() -> None:
    """Eski hata: `gunler[:3]` (ilk üç gün). Doğrusu: `sync.gun_sec` ile GÖSTERİLEN blok + komşusu."""
    an = datetime(2026, 10, 17, 12, 0)
    sistem = _sistem(an, gun_sayisi=5)
    nobetler = sistem["Nobetler"]
    secilen, _ = sync.gun_sec(nobetler, an)
    bloklar = arac.hedef_bloklar(nobetler, an, komsu=1)
    assert bloklar[0] == secilen, "gösterilecek blok ilk sırada olmalı"
    assert len(bloklar) == 2, "varsayılan: gösterilen blok + 1 komşu"
    assert sorted(nobetler)[0] not in bloklar  # ilk gün (eski hatalı davranış) seçilmemeli
    assert arac.hedef_bloklar(nobetler, an, hepsi=True) == sorted(nobetler)


def test_hedef_bloklar_komususuz() -> None:
    an = datetime(2026, 10, 17, 12, 0)
    nobetler = _sistem(an)["Nobetler"]
    assert len(arac.hedef_bloklar(nobetler, an, komsu=0)) == 1


# ------------------------------------------------------------------ doldurma
def test_cogalt_yalniz_hedef_ilceyi_doldurur() -> None:
    an = datetime(2026, 10, 17, 12, 0)
    sistem = _sistem(an, gun_sayisi=5)
    bloklar = arac.hedef_bloklar(sistem["Nobetler"], an, komsu=0)
    arac.cogalt(sistem, 8, "I1", bloklar)

    assert arac.blok_sayisi(sistem, bloklar[0], "I1") == 8
    assert sistem.get("_gecici_test") is True
    # diğer ilçe dokunulmamış
    assert arac.blok_sayisi(sistem, bloklar[0], "I9") == 1
    # komşu bloklar doldurulmadı
    digerleri = [g for g in sorted(sistem["Nobetler"]) if g not in bloklar]
    assert all(arac.blok_sayisi(sistem, g, "I1") == 1 for g in digerleri)


def test_cogalt_hedefi_asla_azaltmaz() -> None:
    an = datetime(2026, 10, 17, 12, 0)
    sistem = _sistem(an, gun_sayisi=3)
    blok = sync.nobet_anahtari(an)
    ilce_listesi = sistem["Nobetler"][blok]["I1"]
    for i in range(10):  # hedefin (8) ÜSTÜNDE kayıt var → hiç eklenmemeli
        ilce_listesi.append({f"9{i:016d}": [_kayit(f"FAZLA {i}", "I1", f"9{i:016d}")]})
    onceki = arac.blok_sayisi(sistem, blok, "I1")
    assert onceki == 11
    arac.cogalt(sistem, 8, "I1", [blok])
    assert arac.blok_sayisi(sistem, blok, "I1") == onceki, "hedefin üstündeki kayıt azaltılmamalı"


def test_cogalt_hedefe_tamamlar() -> None:
    an = datetime(2026, 10, 17, 12, 0)
    sistem = _sistem(an, gun_sayisi=3)
    blok = sync.nobet_anahtari(an)
    assert arac.blok_sayisi(sistem, blok, "I1") == 1
    arac.cogalt(sistem, 8, "I1", [blok])
    assert arac.blok_sayisi(sistem, blok, "I1") == 8


# ------------------------------------------------------------------ uçtan uca (dosya)
def test_main_gosterilen_blogu_doldurur_ve_damgayi_tazeler(monkeypatch, tmp_path, capsys) -> None:
    an = datetime.now()
    sistem = _sistem(an, gun_sayisi=5)
    yollar = _kur(monkeypatch, tmp_path, sistem)
    monkeypatch.setattr("sys.argv", ["gecici_coklu_test.py", "--adet", "8"])

    assert arac.main() == 0
    cikti = capsys.readouterr().out
    yeni = json.loads(yollar["sistem"].read_text(encoding="utf-8"))
    secilen = sync.gun_sec(yeni["Nobetler"], an)[0]

    assert arac.blok_sayisi(yeni, secilen, "I1") == 8, "gösterilecek blok doldurulmalı"
    assert "gösterilecek" in cikti and secilen in cikti
    # DAMGA TAZELENDİ (eski hata: tazelenmiyordu)
    yeni_damga = json.loads(yollar["lastupdate"].read_text(encoding="utf-8"))["lastupdate"]
    assert yeni_damga and yeni_damga != "ESKİ-DAMGA"
    # yedekler alındı
    assert arac.SISTEM_YEDEK.is_file() and arac.LASTUPDATE_YEDEK.is_file()


def test_kuru_modu_hicbir_sey_yazmaz(monkeypatch, tmp_path) -> None:
    an = datetime.now()
    sistem = _sistem(an)
    yollar = _kur(monkeypatch, tmp_path, sistem)
    onceki = yollar["sistem"].read_text(encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["gecici_coklu_test.py", "--kuru"])

    assert arac.main() == 0
    assert yollar["sistem"].read_text(encoding="utf-8") == onceki
    assert not arac.SISTEM_YEDEK.is_file()


def test_geri_al_birebir_yukler(monkeypatch, tmp_path) -> None:
    an = datetime.now()
    sistem = _sistem(an)
    yollar = _kur(monkeypatch, tmp_path, sistem)
    onceki_ozet = arac.ozet(yollar["sistem"])

    monkeypatch.setattr("sys.argv", ["gecici_coklu_test.py", "--adet", "8"])
    assert arac.main() == 0
    assert arac.ozet(yollar["sistem"]) != onceki_ozet

    monkeypatch.setattr("sys.argv", ["gecici_coklu_test.py", "--geri-al"])
    assert arac.main() == 0
    assert arac.ozet(yollar["sistem"]) == onceki_ozet, "geri alma birebir olmalı"
    assert json.loads(yollar["lastupdate"].read_text(encoding="utf-8"))["lastupdate"] == "ESKİ-DAMGA"


def test_ikinci_kez_calistirma_uyarir(monkeypatch, tmp_path, capsys) -> None:
    an = datetime.now()
    _kur(monkeypatch, tmp_path, _sistem(an))
    monkeypatch.setattr("sys.argv", ["gecici_coklu_test.py"])
    assert arac.main() == 0
    assert arac.main() == 1
    assert "geri-al" in capsys.readouterr().out
