"""Çalışma zamanı ayarları (`ayarlar.json`) ve özellik aç/kapa testleri.

Kapsam:
  * ayar dosyası okuma/uygulama, tip ve aralık denetimi, bilinmeyen anahtar uyarısı,
  * tutarlılık kuralları (ikisi birden kapalı olamaz, alt>üst sınır),
  * gelişmiş JSON sınırlarının panelden yükseltilebilmesi (gerçek veri yolundan geçiyor),
  * özellik anahtarlarının ekrandaki etkisi (nöbet listesi / yayınlar / kayan yazı / saat),
  * depoda duran `ayarlar.ornek.json` dosyasının hatasız uygulanması.
"""

from __future__ import annotations

import json
from pathlib import Path

import config
import pytest
from PyQt6.QtWidgets import QApplication

import ayarlar
from pharmacy_app import PharmacyApp
from security.veri_dogrulama import VeriHatasi, json_yukle

KOK = Path(__file__).resolve().parent.parent

pytestmark = []


# --------------------------------------------------------------------- fixture
@pytest.fixture()
def config_yedek(monkeypatch):
    """KURALLAR'da geçen config değerlerini test sonunda geri koyar."""
    adlar = {cfg_ad for cfg_ad, *_ in ayarlar.KURALLAR.values()}
    adlar |= {"OZELLIK_NOBET_LISTESI", "OZELLIK_YAYINLAR", "OZELLIK_KAYAN_YAZI", "OZELLIK_SAAT_TARIH"}
    for ad in sorted(adlar):
        if hasattr(config, ad):
            monkeypatch.setattr(config, ad, getattr(config, ad))
    yield
    ayarlar._uygulanan_yollar.clear()


def ayar_dosyasi(tmp_path: Path, belge: dict, ad: str = "ayarlar.json") -> Path:
    hedef = tmp_path / ad
    hedef.write_text(json.dumps(belge, ensure_ascii=False), encoding="utf-8")
    return hedef


# ------------------------------------------------------------------- saf testler
def test_dosya_yoksa_varsayilanlar_korunur(tmp_path: Path, config_yedek) -> None:
    onceki = config.MAX_JSON_BAYT
    ozet = ayarlar.uygula("yok-boyle-dosya.json", kok=tmp_path, zorla=True)
    assert ozet["uygulanan"] == []
    assert config.MAX_JSON_BAYT == onceki  # değişmedi


def test_ayarlar_config_e_yazilir(tmp_path: Path, config_yedek) -> None:
    yol = ayar_dosyasi(
        tmp_path,
        {
            "gelismis": {"max_json_bayt": 33_554_432, "max_json_derinlik": 64},
            "ozellikler": {"kayan_yazi": False},
            "kusak": {"yukseklik": 140},
        },
    )
    ozet = ayarlar.uygula(yol, zorla=True)
    assert config.MAX_JSON_BAYT == 33_554_432
    assert config.MAX_JSON_DERINLIK == 64
    assert config.OZELLIK_KAYAN_YAZI is False
    assert config.KUSAK_YUKSEKLIK == 140
    assert any("max_json_bayt" in s for s in ozet["uygulanan"])
    assert ozet["gecersiz"] == []


def test_tip_ve_aralik_denetimi(tmp_path: Path, config_yedek) -> None:
    onceki = config.MAX_JSON_BAYT
    yol = ayar_dosyasi(
        tmp_path,
        {
            "gelismis": {"max_json_bayt": "abc", "max_json_derinlik": 10_000, "max_metin_uzunluk": 5},
            "kusak": {"yukseklik": True},
        },
    )
    ozet = ayarlar.uygula(yol, zorla=True)
    assert config.MAX_JSON_BAYT == onceki  # geçersiz: varsayılan kaldı
    assert len(ozet["gecersiz"]) == 4
    assert any("sayıya çevrilemedi" in s for s in ozet["gecersiz"])
    assert any("üst sınırın üstünde" in s for s in ozet["gecersiz"])
    assert any("alt sınırın altında" in s for s in ozet["gecersiz"])


def test_bilinmeyen_anahtar_uyari_verir(tmp_path: Path, config_yedek) -> None:
    yol = ayar_dosyasi(tmp_path, {"ozellikler": {"olmayan_ozellik": True}, "yok": {"x": 1}})
    ozet = ayarlar.uygula(yol, zorla=True)
    assert any("bilinmeyen anahtar" in s for s in ozet["gecersiz"])
    assert any("bilinmeyen ayar grubu" in s for s in ozet["gecersiz"])


def test_liste_degerleri_demete_cevrilir(tmp_path: Path, config_yedek) -> None:
    yol = ayar_dosyasi(
        tmp_path,
        {"ag": {"izinli_hostlar": ["ornek.com", "www.ornek.com"], "izinli_portlar": [443, 8443]}},
    )
    ayarlar.uygula(yol, zorla=True)
    assert config.ALLOWED_HOSTS == ("ornek.com", "www.ornek.com")
    assert config.AG_IZINLI_PORTLAR == (443, 8443)


def test_ikisi_birden_kapali_olamaz(tmp_path: Path, config_yedek) -> None:
    yol = ayar_dosyasi(tmp_path, {"ozellikler": {"nobet_listesi": False, "yayinlar": False}})
    ozet = ayarlar.uygula(yol, zorla=True)
    assert config.OZELLIK_NOBET_LISTESI is True  # tutarlılık kuralı geri açtı
    assert any("ikisi de kapalı olamaz" in s for s in ozet["tutarlilik"])


def test_yayin_suresi_sinir_tutarliligi(tmp_path: Path, config_yedek) -> None:
    yol = ayar_dosyasi(tmp_path, {"gelismis": {"yayin_sure_en_az_s": 30, "yayin_sure_en_cok_s": 10}})
    ozet = ayarlar.uygula(yol, zorla=True)
    assert config.YAYIN_SURE_EN_COK_S == 30
    assert any("üst sınır = alt sınır" in s for s in ozet["tutarlilik"])


def test_json_sinirlari_veri_yoluna_uygulanir(tmp_path: Path, config_yedek) -> None:
    """Panelden yükseltilen sınır gerçekten JSON kapısını gevşetmeli (20-30 MB senaryosu)."""
    yol = ayar_dosyasi(tmp_path, {"gelismis": {"max_json_bayt": 32 * 1024 * 1024}})
    ayarlar.uygula(yol, zorla=True)

    kucuk = json.dumps({"a": 1}).encode()
    assert json_yukle(kucuk, en_buyuk_bayt=config.MAX_JSON_BAYT) == {"a": 1}

    buyuk = json.dumps({"k": "x" * 5_000_000}).encode()  # ~5 MB
    assert len(buyuk) > 4 * 1024 * 1024
    # varsayılan sınırla reddedilirdi:
    with pytest.raises(VeriHatasi):
        json_yukle(buyuk, en_buyuk_bayt=4 * 1024 * 1024)
    # yükseltilmiş sınırla kabul edilir:
    assert json_yukle(buyuk, en_buyuk_bayt=config.MAX_JSON_BAYT)["k"]


def test_yaz_ve_yeniden_oku(tmp_path: Path, config_yedek) -> None:
    hedef = ayarlar.yaz(dosya="yeni.json", kok=tmp_path)
    assert hedef.is_file()
    belge = json.loads(hedef.read_text(encoding="utf-8"))
    assert set(belge) >= {"ozellikler", "kusak", "veri", "ag", "gelismis"}
    assert belge["ozellikler"]["nobet_listesi"] is True
    # yazılan belge tekrar uygulanabilir ve hata üretmez
    ozet = ayarlar.uygula(hedef, zorla=True)
    assert ozet["gecersiz"] == []


def test_ornek_ayar_dosyasi_gecerli(config_yedek) -> None:
    """Depodaki ayarlar.ornek.json gerçekten uygulanabilmeli (kullanıcıya bozuk dosya gitmesin)."""
    ozet = ayarlar.uygula(KOK / "ayarlar.ornek.json", zorla=True)
    gecersiz = [s for s in ozet["gecersiz"] if "_aciklama" not in s]
    assert gecersiz == [], f"örnek dosyada geçersiz ayar: {gecersiz}"
    assert ozet["uygulanan"], "örnek dosyadan hiç ayar uygulanmadı"
    assert config.OZELLIK_NOBET_LISTESI is True
    assert config.KUSAK_YUKSEKLIK == 110


def test_ozet_ve_ozellik_okuma(config_yedek) -> None:
    ozet = ayarlar.ozet()
    assert set(ozet["ozellikler"]) == {"nobet_listesi", "yayinlar", "kayan_yazi", "saat_tarih"}
    assert ayarlar.ozellik("nobet_listesi") is True
    config.OZELLIK_KAYAN_YAZI = False
    assert ayarlar.ozellik("kayan_yazi") is False
    assert ayarlar.ozellik("tanimsiz_ozellik", varsayilan=False) is False


# ------------------------------------------------------------- ekran (Qt) testleri
@pytest.fixture()
def pencere_fabrikasi(qapp, monkeypatch):
    """PharmacyApp üretir; yayın seçimini sabitler (saatten bağımsız).

    `qapp` şart: QApplication olmadan QMainWindow oluşturmak Qt'yi düşürür.
    """
    from core.broadcast_manager import BroadcastManager

    monkeypatch.setattr(
        BroadcastManager, "get_active_yayinlar", lambda self, yayinlar, simdi=None: list(yayinlar or [])[:1]
    )
    pencereler: list[PharmacyApp] = []

    def uret() -> PharmacyApp:
        pencere = PharmacyApp(tam_ekran=False)
        pencere.resize(1280, 720)
        pencere.show()
        QApplication.processEvents()
        # Sayaçlar durdurulur: pencere kapatıldıktan sonra tetiklenirlerse Qt olay
        # döngüsüne istisna atıp pytest-qt'nin rastgele bir sonraki testi düşürmesine
        # yol açıyorlardı (testler adımları zaten elle sürer).
        from conftest import zamanlayicilari_durdur

        zamanlayicilari_durdur(pencere)
        pencereler.append(pencere)
        return pencere

    yield uret
    for pencere in pencereler:
        pencere.close()


def test_nobet_listesi_kapali_yayin_gorunumunde_kalir(config_yedek, pencere_fabrikasi) -> None:
    config.OZELLIK_NOBET_LISTESI = False
    pencere = pencere_fabrikasi()
    for _ in range(3):
        pencere.manage_loop()
    assert pencere.stack.currentWidget() is pencere.yayin_widget
    # nöbet ekranı hiç gösterilmemeli
    pencere.stop_broadcast_mode()
    assert pencere.stack.currentWidget() is pencere.yayin_widget
    assert pencere.is_broadcast_mode is False


def test_kayan_yazi_kapali_kusak_gizlenir(config_yedek, pencere_fabrikasi) -> None:
    config.OZELLIK_KAYAN_YAZI = False
    pencere = pencere_fabrikasi()
    for _ in range(len(pencere.pharmacies) + 2):
        if pencere.is_broadcast_mode:
            break
        pencere.manage_loop()
    assert pencere.is_broadcast_mode is True
    assert pencere.yayin_widget.ticker_strip.isVisible() is False
    # hareket de olmamalı
    etiket = pencere.yayin_widget.ticker_label
    onceki = etiket.x()
    for _ in range(5):
        pencere.scroll_ticker()
    assert etiket.x() == onceki


def test_kayan_yazi_acikken_kusak_gorunur(config_yedek, pencere_fabrikasi) -> None:
    config.OZELLIK_KAYAN_YAZI = True
    pencere = pencere_fabrikasi()
    for _ in range(len(pencere.pharmacies) + 2):
        if pencere.is_broadcast_mode:
            break
        pencere.manage_loop()
    assert pencere.yayin_widget.ticker_strip.isVisible() is True


def test_yayinlar_kapali_yayin_moduna_girilmez(config_yedek, pencere_fabrikasi) -> None:
    config.OZELLIK_YAYINLAR = False
    pencere = pencere_fabrikasi()
    for _ in range(len(pencere.pharmacies) + 5):
        pencere.manage_loop()
    assert pencere.is_broadcast_mode is False
    assert pencere.stack.currentWidget() is pencere.nobet_widget
    # döngü nöbet listesinde dönmeye devam etmeli
    assert 0 <= pencere.current_index < len(pencere.pharmacies)


def test_saat_tarih_kapali_metin_bosaltilir(config_yedek, pencere_fabrikasi) -> None:
    config.OZELLIK_SAAT_TARIH = False
    pencere = pencere_fabrikasi()
    pencere.update_clock()
    blok = pencere.nobet_widget.ui_blocks[0]
    assert blok["time_lbl"].text() == ""
    assert blok["date_lbl"].text() == ""
    assert blok["day_lbl"].text() == ""

    config.OZELLIK_SAAT_TARIH = True
    pencere.update_clock()
    assert blok["time_lbl"].text() != ""
    assert blok["date_lbl"].text() != ""


def test_sadece_gorsel_modu(config_yedek, pencere_fabrikasi) -> None:
    """Yalnızca görsel yayını: nöbet listesi kapalı, kuşak kapalı."""
    config.OZELLIK_NOBET_LISTESI = False
    config.OZELLIK_KAYAN_YAZI = False
    pencere = pencere_fabrikasi()
    for _ in range(3):
        pencere.manage_loop()
    assert pencere.stack.currentWidget() is pencere.yayin_widget
    assert pencere.yayin_widget.ticker_strip.isVisible() is False
    assert pencere.nobet_widget.isVisible() is False
