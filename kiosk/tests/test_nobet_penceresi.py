"""Nöbet penceresi (bitişine kadar gösterim) + sol panel satır boyutu testleri.

KULLANICI BİLDİRİMİ
-------------------
1. `14/10/2026 08:30 – 15/10/2026 08:30` nöbeti, **bitişine kadar** (15/10 08:30)
   ekranda kalmalı; 15/10 08:30'da başlayan nöbet ancak saat 08:30'dan sonra girmeli.
   (Önceki davranış: veri yalnızca 15'ini içeriyorsa 15'inin listesi gece 02:00'de
   gösteriliyordu — yanlış.)
2. Sol panelde nöbetçi sayısı azken çerçeveler BÜYÜMEMELİ; 5 kişilik referans
   boyutta kalmalı.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

import config
from core import sync
from pharmacy_app import PharmacyApp
from tools.fetch_nobet import EN_FAZLA_GUN, gecerli_baslangic

KOK = Path(__file__).resolve().parent.parent


# ------------------------------------------------------------------ yardımcılar
def veri_uret(gunler: dict[str, tuple[str, str]]) -> dict:
    """{'T...': ('başlangıç', 'bitiş')} → iç içe nöbet ağacı (tek kayıt)."""
    nobetler: dict[str, dict] = {}
    for anahtar, (bas, bit) in gunler.items():
        kayit = {
            "eczane": "TEST ECZANESİ",
            "tel": "0262 000 00 00",
            "adres": "TEST MAH.",
            "adres_tarifi": "",
            "bolge": "Test-1",
            "ilce": "TEST",
            "bolgeId": "2001",
            "ilceId": "1001",
            "start": bas,
            "end": bit,
        }
        nobetler[anahtar] = {"1001": [{"2001": [kayit]}]}
    return {"Nobetler": nobetler, "Yayinlar": {}}


IKI_GUN = veri_uret(
    {
        "T20261014": ("14/10/2026 08:30", "15/10/2026 08:30"),
        "T20261015": ("15/10/2026 08:30", "16/10/2026 08:30"),
    }
)


# ------------------------------------------- 1) pencereli seçim (asıl düzeltme)
@pytest.mark.parametrize(
    ("an", "beklenen", "aciklama"),
    [
        ("2026-10-14 09:00", "T20261014", "nöbet başladıktan sonra"),
        ("2026-10-15 02:00", "T20261014", "gece yarısı: dünün nöbeti SÜRÜYOR"),
        ("2026-10-15 07:59", "T20261014", "bitişten bir dakika önce hâlâ dünkü"),
        ("2026-10-15 08:29", "T20261014", "08:30'dan önce hâlâ dünkü"),
        ("2026-10-15 08:30", "T20261015", "08:30'da yeni nöbet başladı"),
        ("2026-10-15 23:59", "T20261015", "gün içi: bugünkü"),
    ],
)
def test_pencereye_gore_secim(an: str, beklenen: str, aciklama: str) -> None:
    anahtar, blok = sync.gun_sec(IKI_GUN["Nobetler"], datetime.fromisoformat(an))
    assert anahtar == beklenen, aciklama
    assert blok


def test_gosterilecek_kayitlar_pencereli() -> None:
    """Uçtan uca: gece 02:00'de dün başlayan kaydın eczanesi gösterilir."""
    from core.sync import CihazKonumu

    konum = CihazKonumu(ilce_id="1001", bolge_id="2001", bulundu=True)
    anahtar, kayitlar = sync.gosterilecek_kayitlar(
        IKI_GUN, konum, datetime.fromisoformat("2026-10-15 02:00")
    )
    assert anahtar == "T20261014"
    assert kayitlar and kayitlar[0]["start"] == "14/10/2026 08:30"


def test_gun_pencereleri_cozumlenir() -> None:
    pencereler = sync.gun_pencereleri(IKI_GUN["Nobetler"])
    assert [k for k, _b, _s in pencereler] == ["T20261014", "T20261015"]
    ilk = pencereler[0]
    assert ilk[1] == datetime(2026, 10, 14, 8, 30)
    assert ilk[2] == datetime(2026, 10, 15, 8, 30)


# ------------------------------------------------------------- geri düşme yolları
def test_veride_yalnizca_gelecek_varsa(caplog: pytest.LogCaptureFixture) -> None:
    """Veri tazelenmemişse (yalnızca yarının nöbeti varsa) yanlış güne atlamaz."""
    sadece_gelecek = veri_uret({"T20261015": ("15/10/2026 08:30", "16/10/2026 08:30")})
    with caplog.at_level("WARNING"):
        anahtar, _blok = sync.gun_sec(
            sadece_gelecek["Nobetler"], datetime.fromisoformat("2026-10-15 02:00")
        )
    assert anahtar == "T20261015"
    assert "henüz başlamamış" in caplog.text or "şu anki pencere yok" in caplog.text


def test_veride_yalnizca_gecmis_varsa_en_son_biteni_gosterir(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sadece_gecmis = veri_uret({"T20261014": ("14/10/2026 08:30", "15/10/2026 08:30")})
    with caplog.at_level("WARNING"):
        anahtar, _blok = sync.gun_sec(
            sadece_gecmis["Nobetler"], datetime.fromisoformat("2026-10-16 12:00")
        )
    assert anahtar == "T20261014"  # en son biten nöbet
    assert "en son biten nöbet" in caplog.text


def test_bos_veri() -> None:
    assert sync.gun_sec({}) == ("", {})


# --------------------------------------------------- çekim başlangıç tarihi kuralı
@pytest.mark.parametrize(
    ("an", "beklenen"),
    [
        ("2026-10-15 02:00", date(2026, 10, 14)),  # 08:30'dan önce → dün (devam eden nöbet)
        ("2026-10-15 08:29", date(2026, 10, 14)),
        ("2026-10-15 08:30", date(2026, 10, 15)),  # yeni nöbet başladı → bugün
        ("2026-10-15 23:00", date(2026, 10, 15)),
    ],
)
def test_gecerli_baslangic(an: str, beklenen: date) -> None:
    assert gecerli_baslangic(datetime.fromisoformat(an)) == beklenen


def test_gecerli_baslangic_gercek_veriyi_kapsar() -> None:
    """Otomatik başlangıç, şu anki nöbet penceresini MUTLAKA içermeli."""
    baslangic = gecerli_baslangic()
    an = datetime.now()
    beklenen = sync.nobet_anahtari(an)  # T<bugün|dün>
    assert "T" + baslangic.strftime("%Y%m%d") == beklenen
    assert (an.date() - baslangic).days in (0, 1)


def test_gun_sayisi_siniri_duruyor() -> None:
    with pytest.raises(ValueError):
        from tools.fetch_nobet import tarih_url

        tarih_url(date(2026, 10, 15), EN_FAZLA_GUN + 1)


# ------------------------------------------------------- 2) sol panel satır boyutu
def _kayit(i: int) -> dict:
    return {
        "eczane": f"ECZANE {i}",
        "tel": "0262 000 00 00",
        "adres": "TEST",
        "adres_tarifi": "",
        "bolge": f"B{i}",
        "ilce": "TEST",
        "baslangic": "",
        "bitis": "",
    }


def _satir_yukseklikleri(pencere: PharmacyApp, n: int) -> list[int]:
    from conftest import paneli_kur

    return paneli_kur(pencere, n)


def test_az_nobetci_cerceve_buyumez(pencere) -> None:
    """2 nöbetçi ile 5 nöbetçi aynı çerçeve yüksekliğini vermeli (bildirilen hata)."""
    p = pencere()
    bes = _satir_yukseklikleri(p, 5)
    iki = _satir_yukseklikleri(p, 2)
    assert len(iki) == 2
    assert set(iki) == set(bes), f"2 kişide çerçeve büyümüş: {iki} vs {bes}"


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5])
def test_tabana_kadar_boyut_sabit(pencere, n: int) -> None:
    p = pencere()
    bes = _satir_yukseklikleri(p, 5)
    assert set(_satir_yukseklikleri(p, n)) == set(bes)


def test_taban_ustunde_kaydirma_etkin(pencere) -> None:
    """5'ten fazla nöbetçide satırlar KÜÇÜLMEZ; panel kaydırılabilir olur."""
    p = pencere()
    bes = _satir_yukseklikleri(p, 5)[0]
    yedi = _satir_yukseklikleri(p, 7)
    assert len(yedi) == 7
    assert len(set(yedi)) == 1  # hepsi eşit boyutta
    assert set(yedi) == {bes}, "kaydırmada satır boyutu taban boyutunda kalmalı"
    assert p._sol_kaydirma_alani is not None, "kaydırma alanı (slider) açılmalı"
    assert p._sol_kaydirma_alani.verticalScrollBar().maximum() > 0


def test_taban_ayardan_degisir(pencere, monkeypatch: pytest.MonkeyPatch) -> None:
    """`gorunum.sol_panel_satir` (ayarlar.json) tabanı değiştirir."""
    p = pencere()
    monkeypatch.setattr(config, "MAKS_GORUNUR_SATIR", 3)
    uc = _satir_yukseklikleri(p, 3)
    ikili = _satir_yukseklikleri(p, 2)
    assert set(ikili) == set(uc)  # 2 kişi, 3 kişilik boyutta

    monkeypatch.setattr(config, "MAKS_GORUNUR_SATIR", 5)
    bes = _satir_yukseklikleri(p, 5)
    assert max(bes) < max(uc)  # taban büyüdükçe satır küçülür


def test_ayar_dosyasindan_taban(pencere, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """ayarlar.json → gorunum.sol_panel_satir gerçekten ekrana yansımalı."""
    import ayarlar

    for ad in ("MAKS_GORUNUR_SATIR",):
        monkeypatch.setattr(config, ad, getattr(config, ad))
    hedef = tmp_path / "ayarlar.json"
    hedef.write_text(json.dumps({"gorunum": {"sol_panel_satir": 2}}), encoding="utf-8")
    ozet = ayarlar.uygula(hedef, zorla=True)
    assert ozet["gecersiz"] == []
    assert config.MAKS_GORUNUR_SATIR == 2

    p = pencere()
    iki = _satir_yukseklikleri(p, 2)
    # taban 2 → 2 kayıt tam yerleşir (satırlar ekranı paylaşır)
    toplam = sum(iki) + p.nobet_widget.left_layout.spacing()
    assert 0 < toplam <= p.screen_h


# ------------------------------------------- 3) her kaydı KENDİ penceresiyle süzme
def veri_uret_coklu(gunler: dict[str, list[tuple[str, str, str, str]]]) -> dict:
    """{'T...': [(bölge adı, bölgeId, başlangıç, bitiş), ...]} → nöbet ağacı."""
    nobetler: dict[str, dict] = {}
    for anahtar, kayitlar in gunler.items():
        bolge_listesi = []
        for bolge_adi, bolge_id, bas, bit in kayitlar:
            bolge_listesi.append(
                {
                    bolge_id: [
                        {
                            "eczane": f"{bolge_adi} ECZANESİ",
                            "tel": "0262 000 00 00",
                            "adres": "TEST",
                            "adres_tarifi": "",
                            "bolge": bolge_adi,
                            "ilce": "ÇAYIROVA",
                            "bolgeId": bolge_id,
                            "ilceId": "1001",
                            "start": bas,
                            "end": bit,
                        }
                    ]
                }
            )
        nobetler[anahtar] = {"1001": bolge_listesi}
    return {"Nobetler": nobetler, "Yayinlar": {}}


#: Gerçek verideki Çayırova durumu: bir nöbet 08:30'da, diğeri 23:59'da bitiyor.
CAYIROVA = veri_uret_coklu(
    {
        "T20261014": [
            ("Çayırova 1.Bölge", "2001", "14/10/2026 08:30", "15/10/2026 08:30"),
            ("Çayırova 2.Bölge", "2002", "14/10/2026 08:30", "14/10/2026 23:59"),
        ]
    }
)


def _goster(an: str, kapsam: str = "ilce") -> list[str]:
    from core.sync import CihazKonumu

    konum = CihazKonumu(ilce_id="1001", bolge_id="2002", bulundu=True)
    _anahtar, kayitlar = sync.gosterilecek_kayitlar(
        CAYIROVA, konum, datetime.fromisoformat(an), kapsam=kapsam
    )
    return [k["bolge"] for k in kayitlar]


@pytest.mark.parametrize(
    ("an", "beklenen"),
    [
        ("2026-10-14 08:30", ["Çayırova 1.Bölge", "Çayırova 2.Bölge"]),
        ("2026-10-14 22:00", ["Çayırova 1.Bölge", "Çayırova 2.Bölge"]),
        ("2026-10-14 23:58", ["Çayırova 1.Bölge", "Çayırova 2.Bölge"]),
        ("2026-10-14 23:59", ["Çayırova 1.Bölge"]),  # 23:59'da biten nöbet düştü
        ("2026-10-15 00:30", ["Çayırova 1.Bölge"]),  # gece: yalnızca 08:30'a kadar süren
        ("2026-10-15 08:29", ["Çayırova 1.Bölge"]),
    ],
)
def test_biten_nobet_listeden_duser(an: str, beklenen: list[str]) -> None:
    """Kullanıcı bildirimi: 23:59'da biten nöbet o saatten sonra listede OLMAMALI."""
    assert _goster(an) == beklenen


def test_blok_penceresi_birlesim() -> None:
    """Kısa bir nöbet bloğun tamamını temsil etmemeli (birleşim penceresi)."""
    pencereler = sync.gun_pencereleri(CAYIROVA["Nobetler"])
    _anahtar, bas, bit = pencereler[0]
    assert bas == datetime(2026, 10, 14, 8, 30)
    assert bit == datetime(2026, 10, 15, 8, 30)  # en geç bitiş (kısa nöbet değil)


def test_ilk_kayit_kisa_olsa_da_blok_seciliir() -> None:
    """Bloğun ilk kaydı kısa (23:59) olsa da gün bloğu doğru seçilmeli."""
    ters = veri_uret_coklu(
        {
            "T20261014": [
                ("Kısa Bölge", "2001", "14/10/2026 08:30", "14/10/2026 23:59"),
                ("Uzun Bölge", "2002", "14/10/2026 08:30", "15/10/2026 08:30"),
            ]
        }
    )
    anahtar, blok = sync.gun_sec(ters["Nobetler"], datetime.fromisoformat("2026-10-15 02:00"))
    assert anahtar == "T20261014" and blok


def test_penceresiz_kayit_gizlenmez() -> None:
    """Başlangıç/bitiş okunamıyorsa kayıt gösterilir (veriyi yargılayamıyoruz)."""
    an = datetime.fromisoformat("2026-10-15 02:00")
    assert sync.kayit_aktif_mi({"eczane": "X"}, an) is True
    assert sync.kayit_aktif_mi({"eczane": "X", "start": "bozuk", "end": "bozuk"}, an) is True
    assert sync.kayit_aktif_mi("sözlük değil", an) is False


def test_aktif_kayit_yoksa_blok_gosterilir(caplog: pytest.LogCaptureFixture) -> None:
    """Süzme sonrası hiç kayıt kalmazsa ekran boş bırakılmaz (uyarı yazılır)."""
    kayitlar = [{"bolge": "B", "start": "01/01/2020 08:30", "end": "02/01/2020 08:30"}]
    with caplog.at_level("WARNING"):
        sonuc = sync.aktif_kayitlar(kayitlar, datetime.fromisoformat("2026-10-15 02:00"))
    assert sonuc == kayitlar
    assert "aktif kayıt yok" in caplog.text


# --------------------------------------------------- devir saati VERİDEN türetilir
def test_verideki_degisim_saati_veriden() -> None:
    from tools.fetch_nobet import verideki_degisim_saati

    assert verideki_degisim_saati(CAYIROVA) == (8, 30)  # veriden: 08:30
    dokuz = veri_uret_coklu({"T20261014": [("B", "2001", "14/10/2026 09:00", "15/10/2026 09:00")]})
    assert verideki_degisim_saati(dokuz) == (9, 0)  # saat değişirse araç uyum sağlar
    assert verideki_degisim_saati({"Nobetler": {}}) is None


def test_gecerli_baslangic_veriye_gore() -> None:
    """Devir saati veriden gelir; 'sabit 08:30 kuralı' kalmaz."""
    from tools.fetch_nobet import gecerli_baslangic

    dokuz = veri_uret_coklu({"T20261014": [("B", "2001", "14/10/2026 09:00", "15/10/2026 09:00")]})
    assert gecerli_baslangic(datetime.fromisoformat("2026-10-15 08:00"), dokuz) == date(2026, 10, 14)
    assert gecerli_baslangic(datetime.fromisoformat("2026-10-15 09:30"), dokuz) == date(2026, 10, 15)
    # gerçek veri (08:30) ile aynı kural
    assert gecerli_baslangic(datetime.fromisoformat("2026-10-15 02:00"), CAYIROVA) == date(2026, 10, 14)


def test_gecerli_baslangic_gercek_veriyi_kapsar() -> None:
    """Otomatik başlangıç, şu anki nöbet penceresini MUTLAKA içermeli (veri varsa)."""
    from tools.fetch_nobet import gecerli_baslangic, verideki_degisim_saati

    an = datetime.now()
    degisim = verideki_degisim_saati()
    beklenen = (8, 30) if degisim is None else degisim
    devir = an.replace(hour=beklenen[0], minute=beklenen[1], second=0, microsecond=0)
    beklenen_tarih = an.date() - timedelta(days=1) if an < devir else an.date()
    assert gecerli_baslangic(an) == beklenen_tarih
    assert (an.date() - gecerli_baslangic(an)).days in (0, 1)
