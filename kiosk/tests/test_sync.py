"""Senkronizasyon akışı testleri.

Kapsanan spec adımları:
  1. lastupdate.json değişim kontrolü (saatte 1)
  2. değişiklik varsa lastSystemData.json + match.json okunması
  3. match.json'dan cihazın ilçe/bölge kimliğinin bulunması
  4. lastSystemData içinde o ilçe/bölgenin verilerinin gösterilmesi
  5. 08:30 nöbet günü kuralı ve ekran alanları (eczane, tel, adres, adres_tarifi)
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

import config
from core import sync, veri_kaynagi
from core.data_handler import DataHandler, kaydi_ekran_bicimine_cevir
from core.sync import CihazKonumu
from tools.fetch_nobet import (
    EN_FAZLA_GUN,
    id_uret,
    sablona_cevir,
    tarih_url,
    yayinlari_cogalt,
)

KOK = Path(__file__).resolve().parent.parent


def gun_anahtarlari(sistem_verisi: dict) -> list[str]:
    """Verideki gün anahtarları (artan sırada) — testler tarihe bağımlı olmasın."""
    return sorted(k for k in sistem_verisi["Nobetler"] if k.startswith("T"))


def gun_ani(anahtar: str, saat: int = 12) -> datetime:
    """'T20261015' → o günün öğle vakti (nöbet penceresinin içi)."""
    return datetime.strptime(anahtar[1:], "%Y%m%d").replace(hour=saat, minute=0)


def ilcedeki_bolge_idleri(sistem_verisi: dict, ilce_id: str, anahtar: str) -> set[str]:
    """Bir gün bloğunda o ilçenin bölge id'leri (beklentiyi veriden türetmek için)."""
    blok = sistem_verisi["Nobetler"][anahtar].get(ilce_id, [])
    return {b for kutu in blok if isinstance(kutu, dict) for b in kutu}


def kayitli_cihaz_konumu(sistem_verisi: dict, match: dict, client_id: str) -> sync.CihazKonumu:
    """Cihazın match.json'daki yeri + kayıtlardan bulunan ilçe/bölge adları."""
    return sync.konum_adlarini_bul(sistem_verisi, sync.cihaz_konumunu_bul(match, client_id))


@pytest.fixture()
def sistem_verisi() -> dict:
    return json.loads((KOK / "lastSystemData.json").read_text(encoding="utf-8"))


@pytest.fixture()
def match() -> dict:
    return json.loads((KOK / "match.json").read_text(encoding="utf-8"))


@pytest.fixture()
def client_id() -> str:
    return json.loads((KOK / "makinebilgileri.json").read_text(encoding="utf-8"))["clientID"]


# --------------------------------------------------------- 1) lastupdate
def test_lastupdate_okuma_ve_degisim() -> None:
    assert sync.lastupdate_oku({"lastupdate": "2026-10-14 17:08:34"}) == "2026-10-14 17:08:34"
    assert sync.lastupdate_oku({"lastUpdate": "x"}) == "x"
    assert sync.lastupdate_oku({}) == ""
    assert sync.lastupdate_oku(None) == ""

    assert sync.degisti_mi("yeni", "eski") is True
    assert sync.degisti_mi("aynı", "aynı") is False
    assert sync.degisti_mi("a", "") is True
    assert sync.degisti_mi("", "") is False  # iki boş değer değişiklik sayılmaz


def test_lastupdate_dosyasi_gercek(capsys: pytest.CaptureFixture[str]) -> None:
    govde = json.loads((KOK / "lastupdate.json").read_text(encoding="utf-8"))
    assert sync.lastupdate_oku(govde)
    del capsys


# ------------------------------------------------- 2-3) match ile yer bulma
def test_cihaz_konumu_bulunur(match: dict, client_id: str) -> None:
    konum = sync.cihaz_konumunu_bul(match, client_id)
    assert konum.bulundu is True
    assert konum.ilce_id and konum.bolge_id
    assert konum.bolge_id in json.dumps(match)


def test_bilinmeyen_cihaz_bulunamaz(match: dict) -> None:
    konum = sync.cihaz_konumunu_bul(match, "00000000000000000")
    assert konum.bulundu is False
    assert konum.ilce_id == ""


def test_lastupdate_anahtari_ilce_sayilmaz(match: dict, client_id: str) -> None:
    """match.json içindeki 'lastUpdate' alanı ilçe gibi işlenmemeli."""
    konum = sync.cihaz_konumunu_bul(match, client_id)
    assert konum.ilce_id != "lastUpdate"


def test_konum_adlari_kayittan_bulunur(sistem_verisi: dict, match: dict, client_id: str) -> None:
    """Cihazın ilçe/bölge ADLARI kayıtlardan bulunmalı (konum nereye ayarlanmışsa)."""
    konum = kayitli_cihaz_konumu(sistem_verisi, match, client_id)
    assert konum.bulundu
    assert konum.ilce and konum.bolge, "ilçe/bölge adı bulunamadı"

    beklenen = {
        (k["ilce"], k["bolge"])
        for k in sync.tum_kayitlar(sistem_verisi)
        if str(k.get("bolgeId")) == konum.bolge_id
    }
    assert beklenen, "bölge id'si kayıtlarda yok"
    assert (konum.ilce, konum.bolge) in beklenen


def test_tum_kayitlar_gunleri_gezer(sistem_verisi: dict) -> None:
    """Ağaçtaki tüm kayıtlar gezer; sayı **veriden türetilir** (veri hacmi değişince kırılmaz)."""
    kayitlar = sync.tum_kayitlar(sistem_verisi)
    beklenen = 0
    for blok in sistem_verisi["Nobetler"].values():
        for ilce_listesi in blok.values():
            for kutu in ilce_listesi:
                for liste in kutu.values():
                    beklenen += len(liste)
    assert beklenen > 0
    assert len(kayitlar) == beklenen
    assert all("eczane" in k and "bolgeId" in k for k in kayitlar)
    assert all(k.get("start") and k.get("end") for k in kayitlar), "her kaydın penceresi olmalı"


# ------------------------------------------------------- 4) nöbet günü kuralı
@pytest.mark.parametrize(
    ("an", "beklenen"),
    [
        ("2026-10-14 08:29", "T20261013"),  # 08:30'dan önce: dünün nöbeti
        ("2026-10-14 08:30", "T20261014"),
        ("2026-10-14 23:59", "T20261014"),
        ("2026-10-15 00:00", "T20261014"),  # gece yarısı nöbet değişmez
        ("2026-10-15 08:29", "T20261014"),
        ("2026-10-15 08:30", "T20261015"),
    ],
)
def test_nobet_gunu_kurali(an: str, beklenen: str) -> None:
    assert sync.nobet_anahtari(datetime.fromisoformat(an)) == beklenen


def test_gun_secimi_istenen_anahtar(sistem_verisi: dict) -> None:
    gunler = gun_anahtarlari(sistem_verisi)
    hedef = gunler[len(gunler) // 2]
    anahtar, blok = sync.gun_sec(sistem_verisi["Nobetler"], gun_ani(hedef))
    assert anahtar == hedef
    assert blok


def test_gun_secimi_veri_disinda_son_gune_duser(sistem_verisi: dict) -> None:
    anahtar, blok = sync.gun_sec(sistem_verisi["Nobetler"], datetime(2027, 1, 1, 12, 0))
    assert anahtar == gun_anahtarlari(sistem_verisi)[-1]  # verinin son günü
    assert blok


def test_gun_secimi_bos_veri() -> None:
    assert sync.gun_sec({}) == ("", {})


# --------------------------------------------------- ilçe / bölge filtreleme
def test_ilce_kapsami_tum_bolgeleri_getirir(sistem_verisi: dict, match: dict, client_id: str) -> None:
    """'ilce' kapsamı: cihazın ilçesindeki TÜM bölgeler gelir (beklenti veriden türetilir)."""
    konum = kayitli_cihaz_konumu(sistem_verisi, match, client_id)
    ilk_gun = gun_anahtarlari(sistem_verisi)[0]
    anahtar, kayitlar = sync.gosterilecek_kayitlar(sistem_verisi, konum, gun_ani(ilk_gun), kapsam="ilce")
    assert anahtar == ilk_gun
    beklenen_bolgeler = ilcedeki_bolge_idleri(sistem_verisi, konum.ilce_id, ilk_gun)
    assert kayitlar, "hiç kayıt gelmedi"
    assert {k["bolgeId"] for k in kayitlar} == beklenen_bolgeler
    assert all(k["ilceId"] == konum.ilce_id for k in kayitlar)
    assert all(k["ilce"] == konum.ilce for k in kayitlar)


def test_bolge_kapsami_yalnizca_kendi_bolgesi(sistem_verisi: dict, match: dict, client_id: str) -> None:
    konum = kayitli_cihaz_konumu(sistem_verisi, match, client_id)
    ilk_gun = gun_anahtarlari(sistem_verisi)[0]
    _anahtar, kayitlar = sync.gosterilecek_kayitlar(
        sistem_verisi, konum, gun_ani(ilk_gun), kapsam="bolge"
    )
    assert len(kayitlar) == 1
    assert kayitlar[0]["bolgeId"] == konum.bolge_id


def test_baska_ilcenin_verisi_gelmez(sistem_verisi: dict) -> None:
    """Başka bir ilçeye ait kayıtlar cihazın listesine girmez."""
    konum = CihazKonumu(ilce_id="47394149001009938", bolge_id="51375548141235632", bulundu=True)  # BAŞİSKELE
    ilk_gun = gun_anahtarlari(sistem_verisi)[0]
    _anahtar, kayitlar = sync.gosterilecek_kayitlar(sistem_verisi, konum, gun_ani(ilk_gun))
    assert {k["ilce"] for k in kayitlar} == {"BAŞİSKELE"}


def test_gun_ilerledikce_farkli_eczaneler(sistem_verisi: dict, match: dict, client_id: str) -> None:
    konum = sync.konum_adlarini_bul(sistem_verisi, sync.cihaz_konumunu_bul(match, client_id))
    gunler = gun_anahtarlari(sistem_verisi)
    bugun = sync.gosterilecek_kayitlar(sistem_verisi, konum, gun_ani(gunler[0]))[1]
    yarin = sync.gosterilecek_kayitlar(sistem_verisi, konum, gun_ani(gunler[1]))[1]
    assert [k["eczane"] for k in bugun] != [k["eczane"] for k in yarin]


# ------------------------------------------------------------------- yayınlar
def test_aktif_yayinlar_isoya_gore(sistem_verisi: dict) -> None:
    ilk = sistem_verisi["Yayinlar"]["1"]
    an = datetime.fromisoformat(ilk["start"]) + timedelta(minutes=1)
    aktif = sync.aktif_yayinlar(sistem_verisi, an)
    assert len(aktif) == 2  # iki yayın aynı pencerede
    bos = sync.aktif_yayinlar(sistem_verisi, datetime(2026, 11, 20, 12, 0))
    assert bos == []


def test_yayinlar_30_gune_cogaltilir() -> None:
    sablon = json.loads((KOK / "sablon.json").read_text(encoding="utf-8"))
    cogaltilmis = yayinlari_cogalt(sablon["Yayinlar"], 30, date(2026, 10, 14))
    assert len(cogaltilmis) == 60  # 2 şablon x 30 gün
    # aynı saat/süre, sadece gün değişir; milisaniye biçimi korunur
    ilk, ikinci = cogaltilmis["1"], cogaltilmis["3"]
    assert ilk["start"].endswith(".468") and ilk["start"][:10] == "2026-10-14"
    assert ikinci["start"][:10] == "2026-10-15"
    assert datetime.fromisoformat(ikinci["end"]) - datetime.fromisoformat(ikinci["start"]) == timedelta(minutes=17)


# ------------------------------------------------------- veri işleyici (uçtan)
def test_data_handler_uctan_uca(monkeypatch: pytest.MonkeyPatch) -> None:
    """Uçtan uca: cihaz hangi bölgeye ayarlanmışsa oranın verisi gelir."""
    veri_kaynagi.onbellegi_temizle()
    handler = DataHandler()
    assert handler.load_data() is True
    assert handler.nobet_gunu.startswith("T")
    assert handler.konum.bulundu and handler.konum.ilce and handler.konum.bolge
    assert handler.lastupdate
    # Tüm kayıtlar cihazın ilçesinden olmalı
    assert handler.pharmacies
    assert {k["ilceId"] for k in handler.pharmacies} == {handler.konum.ilce_id}
    # Sol liste: eczane + tel ; orta kısım: + adres + adres_tarifi
    kayit = handler.pharmacies[0]
    assert kayit["eczane"] and kayit["tel"]
    assert kayit["bolge"] and kayit["adres"] is not None
    assert handler.yayinlar


def test_data_handler_gosterilen_kayit_penceresi(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gösterilen kayıtların penceresi şu anı KAPSAMALI (nöbet bitişine kadar)."""
    veri_kaynagi.onbellegi_temizle()
    handler = DataHandler()
    assert handler.load_data() is True
    bas = sync._tarih(handler.pharmacies[0]["baslangic"])
    bit = sync._tarih(handler.pharmacies[0]["bitis"])
    assert bas and bit
    assert bas <= datetime.now() < bit, "gösterilen nöbet şu anı kapsamıyor"


def test_lastupdate_degismediyse_yeniden_yuklemez(monkeypatch: pytest.MonkeyPatch) -> None:
    veri_kaynagi.onbellegi_temizle()
    handler = DataHandler()
    assert handler.load_data() is True
    ilk_kayitlar = list(handler.pharmacies)

    cagrildi = {"sayi": 0}
    gercek = veri_kaynagi.sistem_verisi_yukle

    def sayac():
        cagrildi["sayi"] += 1
        return gercek()

    monkeypatch.setattr(veri_kaynagi, "sistem_verisi_yukle", sayac)
    assert handler.load_data() is True  # lastupdate aynı -> veri yenilenmemeli
    assert cagrildi["sayi"] == 0
    assert handler.pharmacies == ilk_kayitlar


def test_lastupdate_degisirse_yeniden_yukler(monkeypatch: pytest.MonkeyPatch) -> None:
    veri_kaynagi.onbellegi_temizle()
    handler = DataHandler()
    handler.load_data()
    monkeypatch.setattr(veri_kaynagi, "lastupdate_yukle", lambda: {"lastupdate": "2099-01-01 00:00:00"})
    cagrildi = {"sayi": 0}
    gercek = veri_kaynagi.sistem_verisi_yukle

    def sayac():
        cagrildi["sayi"] += 1
        return gercek()

    monkeypatch.setattr(veri_kaynagi, "sistem_verisi_yukle", sayac)
    assert handler.load_data() is True
    assert cagrildi["sayi"] == 1
    assert handler.lastupdate == "2099-01-01 00:00:00"


def test_cihaz_matchte_yoksa_veri_yuklenmez(monkeypatch: pytest.MonkeyPatch) -> None:
    veri_kaynagi.onbellegi_temizle()
    monkeypatch.setattr(veri_kaynagi, "client_id", lambda: "00000000000000000")
    handler = DataHandler()
    assert handler.load_data() is False
    assert handler.pharmacies == []


def test_ekran_bicimine_cevirme() -> None:
    satir = kaydi_ekran_bicimine_cevir(
        {
            "eczane": " ASLI ",
            "tel": "02623230142",
            "adres": "CEDİT MAH.",
            "adres_tarifi": "Hastane karşısı",
            "start": "14/10/2026 08:30",
            "end": "15/10/2026 08:30",
            "bolge": "İzmit-2",
            "ilce": "İZMİT",
        }
    )
    assert satir["eczane"] == "ASLI"
    assert satir["baslangic"] == "14/10/2026 08:30"
    assert satir["adres_tarifi"] == "Hastane karşısı"


# --------------------------------------------------------- fetch_nobet aracı
def test_url_tarih_kurallari() -> None:
    assert tarih_url(date(2026, 10, 14), 16) == ("2026-10-14", "2026-10-29")
    assert tarih_url(date(2026, 10, 15), 1) == ("2026-10-15", "2026-10-15")
    with pytest.raises(ValueError, match="en fazla"):
        tarih_url(date(2026, 10, 14), EN_FAZLA_GUN + 1)
    with pytest.raises(ValueError):
        tarih_url(date(2026, 10, 14), 0)


def test_id_uretimi_kararli_ve_17_hane() -> None:
    ilk = id_uret("İZMİT", "ilce")
    assert ilk == id_uret("İZMİT", "ilce")  # kararlı
    assert ilk != id_uret("GEBZE", "ilce")
    assert len(ilk) == 17 and ilk.isdigit()


def test_sablona_cevirme_islevi() -> None:
    ham = {
        "": {
            "ilce": "İZMİT",
            "bolge": "İzmit-2",
            "eczane": "ASLI",
            "tel": "02623230142",
            "adres": "CEDİT MAH.",
            "adres_tarifi": "",
            "enlem": "40.7",
            "boylam": "29.9",
            "baslangic": "2026-10-14 08:30:00",
            "bitis": "2026-10-15 08:30:00",
        }
    }
    agac = sablona_cevir(ham)
    assert list(agac) == ["T20261014"]
    ilce_id = next(iter(agac["T20261014"]))
    bolge_id = next(iter(agac["T20261014"][ilce_id][0]))
    kayit = agac["T20261014"][ilce_id][0][bolge_id][0]
    assert kayit["start"] == "14/10/2026 08:30"  # şablon biçimi
    assert kayit["end"] == "15/10/2026 08:30"
    assert kayit["ilceId"] == ilce_id and kayit["bolgeId"] == bolge_id


def test_sablon_dosyasi_ile_uyum(sistem_verisi: dict, match: dict) -> None:
    """Üretilen dosyalar şablonun anahtar yapısına uyar."""
    sablon = json.loads((KOK / "sablon.json").read_text(encoding="utf-8"))
    # Nobetler -> T gün -> {ilceId: [ {bolgeId: [kayıt]} ]}
    assert set(sistem_verisi) >= {"Nobetler", "Yayinlar", "lastUpdate"}
    gun = next(iter(sistem_verisi["Nobetler"]))
    assert gun.startswith("T")
    ilce_id = next(iter(sistem_verisi["Nobetler"][gun]))
    assert isinstance(sistem_verisi["Nobetler"][gun][ilce_id], list)
    assert set(sablon["Nobetler"]["T20261014"]) == {"ilceId"}
    # match.json -> {ilceId: [ {bolgeId: [makine id'leri]} ]}
    ilce_listesi = match[next(iter([k for k in match if k != "lastUpdate"]))]
    assert isinstance(ilce_listesi, list) and isinstance(ilce_listesi[0], dict)


def test_config_kaynak_ayarlari() -> None:
    assert config.LASTUPDATE_KONTROL_MS == 60 * 60 * 1000
    assert config.REFRESH_INTERVAL_MS == 60 * 60 * 1000
    assert "www.kocaelieo.org.tr" in config.ALLOWED_HOSTS
    assert config.KAPSAM in ("ilce", "bolge")
