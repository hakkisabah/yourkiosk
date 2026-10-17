"""Kapsam (ilçe/bölge/cihaz) ayarları — çok kullanıcılı/çok cihazlı özellik yönetimi.

Çözümleme sırası: varsayilan → ilce → bolge → cihaz (en özel kazanır).
Aynı test verisi (`tests/veri/kapsam_ornek.json`) yönetim panelinde de
(`panel/src/domain/kapsam.test.ts`) doğrulanır; iki taraf aynı sonucu vermeli.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import ayarlar
import config

ORNEK = Path(__file__).parent / "veri" / "kapsam_ornek.json"


@pytest.fixture(autouse=True)
def config_koruma():
    """`kapsam_uygula` config'i değiştirir; her testten sonra eski değerlere dönülür.

    (Aksi hâlde diğer testler/şema dışa aktarımı kirlenmiş varsayılanları görür.)
    """
    adlar = [kural[0] for kural in ayarlar.KURALLAR.values()]
    eski = {ad: getattr(config, ad) for ad in adlar}
    yield
    for ad, deger in eski.items():
        setattr(config, ad, deger)


@pytest.fixture()
def kapsam_yolu(tmp_path: Path) -> Path:
    hedef = tmp_path / "kapsam-ayarlari.json"
    hedef.write_text(ORNEK.read_text(encoding="utf-8"), encoding="utf-8")
    return hedef


def test_varsayilan_kapsam_uygulanir(kapsam_yolu: Path) -> None:
    ozet = ayarlar.kapsam_uygula(dosya=kapsam_yolu)
    assert "kayan_yazi=True" in " ".join(ozet["uygulanan"])
    assert config.OZELLIK_KAYAN_YAZI is True
    assert config.KUSAK_YAZI_PUNTO == 36


def test_ilce_kapsami_bolgeye_devreder(kapsam_yolu: Path) -> None:
    """İlçe `kayan_yazi=false` der, bölge `true` ile geçersiz kılar → bölge kazanır."""
    ozet = ayarlar.kapsam_uygula(dosya=kapsam_yolu, ilce_id="1001", bolge_id="2002")
    assert config.OZELLIK_KAYAN_YAZI is True
    assert ozet["kapsam"]["ozellikler.kayan_yazi"] == "bolge:2002"


def test_cihaz_kapsami_en_ozel(kapsam_yolu: Path) -> None:
    """Cihaz kapsamı punto 28 ile hem varsayılanı hem bölgeyi geçersiz kılar."""
    ozet = ayarlar.kapsam_uygula(
        dosya=kapsam_yolu, ilce_id="1001", bolge_id="2002", client_id="ORNEK-CIHAZ-0001"
    )
    assert config.KUSAK_YAZI_PUNTO == 28
    assert ozet["kapsam"]["kusak.yazi_punto"] == "cihaz:ORNEK-CIHAZ-0001"
    assert ozet["kapsam"]["ozellikler.saat_tarih"] == "varsayilan"  # varsayılan kapsamdan geldi


def test_ilce_kapsami_cihaz_yoksa_gecerli(kapsam_yolu: Path) -> None:
    """Cihaz kaydı yoksa ilçe değeri geçerli; başka bölgeye girilirse varsayılan."""
    ayarlar.kapsam_uygula(dosya=kapsam_yolu, ilce_id="1001", bolge_id="2999", client_id="YOK-0001")
    assert config.OZELLIK_KAYAN_YAZI is False  # ilçe kazandı
    assert config.KUSAK_YAZI_PUNTO == 36  # varsayılan


def test_bilinmeyen_grup_ve_anahtar_yok_sayilir(kapsam_yolu: Path, tmp_path: Path) -> None:
    bozuk = tmp_path / "kapsam2.json"
    bozuk.write_text(
        json.dumps(
            {
                "varsayilan": {"bilinmeyen_grup": {"x": 1}, "kusak": {"olmayan_anahtar": 5}},
                "ilceler": {"1001": {"ozellikler": {"__yorum": "yok sayılmalı"}}},
            }
        ),
        encoding="utf-8",
    )
    ozet = ayarlar.kapsam_uygula(dosya=bozuk, ilce_id="1001")
    assert ozet["uygulanan"] == []
    assert ozet["gecersiz"] == []


def test_gecersiz_deger_kabul_edilmez(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Aralık dışı değer sessizce kabul edilmez; varsayılan korunur."""
    bozuk = tmp_path / "kapsam3.json"
    bozuk.write_text(
        json.dumps({"varsayilan": {"kusak": {"yazi_punto": 9999, "yukseklik": "abc"}}}),
        encoding="utf-8",
    )
    eski = config.KUSAK_YAZI_PUNTO
    with caplog.at_level("WARNING"):
        ozet = ayarlar.kapsam_uygula(dosya=bozuk)
    assert config.KUSAK_YAZI_PUNTO == eski
    assert len(ozet["gecersiz"]) == 2
    assert "üst sınırın üstünde" in caplog.text and "sayıya çevrilemedi" in caplog.text


def test_dosya_yoksa_davranis_ayni() -> None:
    """Kapsam dosyası yoksa hiçbir şey değişmez (config varsayılanları)."""
    eski = (config.OZELLIK_KAYAN_YAZI, config.KUSAK_YAZI_PUNTO, config.MAKS_GORUNUR_SATIR)
    ozet = ayarlar.kapsam_uygula(dosya="/yok/boyle/dosya.json", ilce_id="1001", bolge_id="2002")
    assert ozet["atlandi"] is True and ozet["uygulanan"] == []
    assert (config.OZELLIK_KAYAN_YAZI, config.KUSAK_YAZI_PUNTO, config.MAKS_GORUNUR_SATIR) == eski


def test_kapsam_ozeti_etkin_degerleri_verir(kapsam_yolu: Path) -> None:
    ayarlar.kapsam_uygula(dosya=kapsam_yolu, ilce_id="1001", bolge_id="2002", client_id="ORNEK-CIHAZ-0001")
    ozet = ayarlar.kapsam_ozeti(dosya=kapsam_yolu, ilce_id="1001", bolge_id="2002", client_id="ORNEK-CIHAZ-0001")
    assert ozet["kusak.yazi_punto"]["etkin"] == 28
    assert ozet["kusak.yazi_punto"]["kapsam"] == "cihaz:ORNEK-CIHAZ-0001"
    assert ozet["ozellikler.nobet_listesi"]["kapsam"] == "config (varsayılan)"  # hiç geçersiz kılınmadı


def test_ornek_kapsam_dosyasi_gecerli() -> None:
    """Depodaki `kapsam-ayarlari.ornek.json` doğrulanabilir olmalı (yorum anahtarları hariç)."""
    from security.veri_dogrulama import json_yukle

    ornek = Path(__file__).parent.parent / "kapsam-ayarlari.ornek.json"
    belge = json_yukle(ornek.read_bytes(), etiket="kapsam-ayarlari.ornek.json")
    assert belge["_aciklama"] is not None
    # gerçek kapsam grupları geçerli anahtarlardan oluşmalı
    gecerli = {a for (g, a) in ayarlar.KURALLAR if g in ayarlar.KAPSAM_GRUPLARI}
    for grup, icerik in belge.items():
        if grup in ayarlar.KAPSAM_GRUPLARI:
            assert set(icerik) <= gecerli, f"{grup}: bilinmeyen anahtar"
