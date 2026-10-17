"""Yayın ekranındaki alt kuşak + kayan yazı testleri.

Beklenen davranış:
  * yayın görseli TAM EKRAN kalır; kırmızı kuşak onun **üstüne** biner
    (kuşağın altında boş/alakasız arka plan görünmez),
  * kuşak ekranın en altına yapışmaz: altında KUSAK_ALT_BOSLUK kadar boşluk var,
  * kuşak yüksekliği/punto config'ten: KUSAK_YUKSEKLIK, KUSAK_YAZI_PUNTO,
  * yazı BEYAZ ve kalın,
  * eczaneler TEKER TEKER: sağdan ortaya gelir, ortada bir süre durur, soldan
    çıkar; sıradaki aynı şekilde gelir. Biçim "ECZANE - telefon",
  * nöbet görünümünde kuşak hareket etmez.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import pytest
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication

import config
import utils
from core.ticker import KusakAnimasyonu
from pharmacy_app import PharmacyApp

pytestmark = pytest.mark.qt

from conftest import zamanlayicilari_durdur

KOK = Path(__file__).resolve().parent.parent


@pytest.fixture()
def pencere(qapp, monkeypatch):
    """Uygulamayı pencere modunda (offscreen) açar.

    Yayın modu testleri **saate bağlı kalmasın** diye aktif yayın seçimi sabitlenir:
    gerçek veri penceresi (ör. 08:30–23:59) dışında çalıştırıldığında da kod yolu test edilir.
    """
    from core.broadcast_manager import BroadcastManager

    monkeypatch.setattr(
        BroadcastManager,
        "get_active_yayinlar",
        lambda self, yayinlar, simdi=None: list(yayinlar or [])[:2],
    )
    uygulama = PharmacyApp(tam_ekran=False)
    uygulama.resize(1280, 720)
    uygulama.show()
    QApplication.processEvents()
    zamanlayicilari_durdur(uygulama)  # testler adımları elle sürer (30 ms'lik kuşak sayacı kapatılır)
    yield uygulama
    uygulama.close()


def yayin_moduna_gec(pencere: PharmacyApp) -> None:
    """Nöbet döngüsünü sonuna kadar döndürüp yayın moduna geçirir.

    Geçişten sonra kuşak yerleşimi ve etiket ölçüsü ZORLANIR: kayan yazının x konumu
    etiket genişliğinden hesaplandığı için, yerleşim henüz tamamlanmadan adım atmak
    (yük altında geciken yerleşim) piksel beklentilerini kaydırıyordu.
    """
    for _ in range(len(pencere.pharmacies) + 2):
        if pencere.is_broadcast_mode:
            break
        pencere.manage_loop()
    assert pencere.is_broadcast_mode, "yayın moduna geçilemedi (aktif yayın yok mu?)"
    yw = pencere.yayin_widget
    pencere.prepare_ticker_text()
    yw.kusagi_yerlestir()
    yw.ticker_label.adjustSize()
    QApplication.processEvents()


def kaydi_gecir(pencere: PharmacyApp) -> None:
    """Bir kaydın giriş + durma + çıkış adımlarını baştan sona oynatır."""
    for _ in range(pencere.kusak_animasyonu.toplam_adim):
        pencere.scroll_ticker()


# --------------------------------------------------------- kuşak (kırmızı şerit)
def test_yayin_gorseli_tam_ekran(pencere: PharmacyApp) -> None:
    yayin_moduna_gec(pencere)
    QApplication.processEvents()
    yw = pencere.yayin_widget
    assert pencere.stack.currentWidget() is yw
    assert yw.img_lbl.height() == yw.height(), "yayın görseli tam ekran olmalı"
    assert yw.img_lbl.width() == yw.width()


def test_kusak_gorselin_ustunde_biner(pencere: PharmacyApp) -> None:
    yayin_moduna_gec(pencere)
    yw = pencere.yayin_widget
    QApplication.processEvents()
    kusak = yw.ticker_strip
    assert kusak.isVisible(), "kırmızı kuşak görünmüyor"
    assert "#c8102e" in kusak.styleSheet()  # referans kırmızısı
    # kuşak yerleşimde değil, görselin üzerine bindirilmiş bir katman
    assert kusak.parent() is yw
    assert kusak.geometry().contains(0, 0) is False or kusak.y() > 0
    # o noktada en üstteki çocuk kuşak olmalı (görsel değil)
    ustte = yw.childAt(yw.width() // 2, kusak.y() + kusak.height() // 2)
    assert ustte in (kusak, yw.ticker_label), f"üstte {ustte} var, kuşak görselin altında kalmış"


def test_kusak_ekranin_dibine_yapismaz(pencere: PharmacyApp) -> None:
    yayin_moduna_gec(pencere)
    yw = pencere.yayin_widget
    kusak = yw.ticker_strip
    bosluk = yw.height() - (kusak.y() + kusak.height())
    assert bosluk == int(config.KUSAK_ALT_BOSLUK * pencere.scale), f"alt boşluk {bosluk} px"
    assert bosluk > 0
    assert kusak.width() == yw.width()  # tam genişlik


def test_kusak_boyutlari_configten(pencere: PharmacyApp) -> None:
    yayin_moduna_gec(pencere)
    kusak = pencere.yayin_widget.ticker_strip
    assert kusak.height() == int(config.KUSAK_YUKSEKLIK * pencere.scale)
    assert kusak.height() > int(60 * pencere.scale)  # eskisinden büyük (80 > 60)


def test_pencere_kuculunce_kusak_yeniden_konumlanir(pencere: PharmacyApp) -> None:
    """Cihazda pencere boyutu değişirse kuşak yine görselin üstünde kalmalı."""
    yayin_moduna_gec(pencere)
    pencere.resize(900, 600)
    QApplication.processEvents()
    yw = pencere.yayin_widget
    kusak = yw.ticker_strip
    assert kusak.y() + kusak.height() + yw.alt_bosluk == yw.height()
    assert yw.img_lbl.height() == yw.height()


# ------------------------------------------------------------- kayan yazı metni
def test_kayan_yazi_beyaz_ve_kalin(pencere: PharmacyApp) -> None:
    yayin_moduna_gec(pencere)
    etiket = pencere.yayin_widget.ticker_label
    assert etiket.parent() is pencere.yayin_widget.ticker_strip
    assert "white" in etiket.styleSheet()
    assert etiket.font().bold() is True
    assert etiket.font().pointSize() == int(config.KUSAK_YAZI_PUNTO * pencere.scale)


def test_kusak_metni_tek_eczane_biciminde(pencere: PharmacyApp) -> None:
    """Tekli modda yazı tek bir 'ECZANE - telefon' kaydıdır (ayırıcı yok)."""
    yayin_moduna_gec(pencere)
    metin = pencere.yayin_widget.ticker_label.text()
    assert metin.strip(), "kayan yazı metni boş"
    assert config.KUSAK_AYIRICI not in metin
    ilk = pencere.pharmacies[0]
    # telefon biçimlenmiş hâlde gösterilir: "DEVA - 0262 325 13 35"
    assert metin == f"{ilk['eczane'].upper()} - {utils.format_phone(ilk['tel'])}"
    assert re.fullmatch(r"[^-]+ - \d{4} \d{3} \d{2} \d{2}", metin.strip())


def test_kayan_yazi_telefon_yoksa_bolge_yazar(pencere: PharmacyApp) -> None:
    """Telefon alanı boş bir kayıt için kuşakta bölge adı görünür (bare '-' değil)."""
    yayin_moduna_gec(pencere)
    pencere.data_handler.pharmacies = [dict(p, tel="") for p in pencere.pharmacies]
    pencere.prepare_ticker_text()
    beklenen = pencere.pharmacies[0]["bolge"] if config.EKSIK_TELEFON_YERINE_BOLGE else "-"
    assert beklenen in pencere.yayin_widget.ticker_label.text()


# ------------------------------------------- sağdan ortaya gel → dur → çık
def test_yazi_sagdan_girer_ortada_durur(pencere: PharmacyApp) -> None:
    yayin_moduna_gec(pencere)
    etiket = pencere.yayin_widget.ticker_label
    anim = pencere.kusak_animasyonu
    serit = pencere.yayin_widget.ticker_strip.width()
    assert etiket.x() == serit, "yazı sağ kenardan başlamalı"

    # giriş boyunca hep sola (hiç geri gitmez)
    konumlar = [etiket.x()]
    for _ in range(anim.giris_adim):
        pencere.scroll_ticker()
        konumlar.append(etiket.x())
    assert all(y <= x for x, y in zip(konumlar, konumlar[1:])), "yazı sağdan sola gitmiyor"

    orta = KusakAnimasyonu.orta_konum(serit, etiket.width())
    assert abs(etiket.x() - orta) <= 1, f"yazı ortada durmadı (x={etiket.x()}, orta={orta})"


def test_yazi_ortada_bir_sure_bekler(pencere: PharmacyApp) -> None:
    yayin_moduna_gec(pencere)
    etiket = pencere.yayin_widget.ticker_label
    anim = pencere.kusak_animasyonu
    for _ in range(anim.giris_adim):
        pencere.scroll_ticker()
    orta = etiket.x()
    for _ in range(anim.durma_adim):
        pencere.scroll_ticker()
    assert etiket.x() == orta, "yazı ortada durmuyor"
    assert anim.durma_adim * config.KUSAK_ADIM_ARALIGI_MS == pytest.approx(
        config.KUSAK_DURMA_MS, abs=config.KUSAK_ADIM_ARALIGI_MS
    )


def test_yazi_soldan_cikar_ve_siradaki_gelir(pencere: PharmacyApp) -> None:
    yayin_moduna_gec(pencere)
    etiket = pencere.yayin_widget.ticker_label
    anim = pencere.kusak_animasyonu
    serit = pencere.yayin_widget.ticker_strip.width()

    for _ in range(anim.giris_adim + anim.durma_adim):
        pencere.scroll_ticker()
    orta = etiket.x()
    for _ in range(anim.cikis_adim - 1):  # son adım döngüyü tamamlar
        pencere.scroll_ticker()
    assert etiket.x() < orta  # ortadan sola çıktı
    assert etiket.x() < 0  # tamamen görünmez oldu

    # son adım: döngü bitti, sıradaki kayıt sağ kenardan başlar
    pencere.scroll_ticker()
    assert etiket.text() == pencere.ticker_items[1]
    assert etiket.x() == serit
    # bir adım sonra girmeye başlar
    pencere.scroll_ticker()
    assert serit - 200 < etiket.x() <= serit


def test_eczaneler_teker_teker_gelir(pencere: PharmacyApp) -> None:
    yayin_moduna_gec(pencere)
    etiket = pencere.yayin_widget.ticker_label
    adet = len(pencere.ticker_items)
    assert adet == len(pencere.pharmacies) and adet >= 1
    assert etiket.text() == pencere.ticker_items[0]

    kaydi_gecir(pencere)
    assert etiket.text() == pencere.ticker_items[1 % adet]
    kaydi_gecir(pencere)
    assert etiket.text() == pencere.ticker_items[2 % adet]


def test_son_kayittan_sonra_basa_doner(pencere: PharmacyApp) -> None:
    yayin_moduna_gec(pencere)
    etiket = pencere.yayin_widget.ticker_label
    for _ in range(len(pencere.ticker_items)):
        kaydi_gecir(pencere)
    assert etiket.text() == pencere.ticker_items[0]


def test_hareket_yumusatilmis(pencere: PharmacyApp) -> None:
    """Nöbet geçişiyle aynı his: yavaş başlar, ortada hızlanır, sonda yavaşlar."""
    yayin_moduna_gec(pencere)
    etiket = pencere.yayin_widget.ticker_label
    anim = pencere.kusak_animasyonu
    konumlar = [etiket.x()]
    for _ in range(anim.giris_adim):
        pencere.scroll_ticker()
        konumlar.append(etiket.x())
    farklar = [abs(konumlar[i] - konumlar[i - 1]) for i in range(1, len(konumlar))]
    assert farklar[0] < farklar[len(farklar) // 2]
    assert farklar[-1] < farklar[len(farklar) // 2]


def test_nobet_gorunumunde_kayan_yazi_hareket_etmez(pencere: PharmacyApp) -> None:
    yayin_moduna_gec(pencere)
    etiket = pencere.yayin_widget.ticker_label
    pencere.stop_broadcast_mode()
    QApplication.processEvents()
    assert pencere.is_broadcast_mode is False
    assert pencere.stack.currentWidget() is pencere.nobet_widget
    onceki = etiket.x()
    for _ in range(5):
        pencere.scroll_ticker()
    assert etiket.x() == onceki


def test_yayin_moduna_girince_metin_hazir(pencere: PharmacyApp) -> None:
    """Yayın moduna girildiği anda kuşak metni dolu olmalı (boş şerit görünmesin)."""
    yayin_moduna_gec(pencere)
    assert pencere.yayin_widget.ticker_label.text().strip() not in ("", "-")


# ------------------------------------------------------------------ zamanlayıcı
def test_kayan_yazi_zamanlayicisi_calisiyor(pencere: PharmacyApp) -> None:
    """Sayaç aralığı doğru ve (uygulama açılışında) etkin olmalı.

    Not: test fixture'ı sayaçları kapatır (testler adımları elle sürer); bu test
    sayaçların gerçekten kurulduğunu doğruladığı için açıkça yeniden başlatılır ve
    **sonunda tümü yine durdurulur**. Aksi hâlde pencere kapatıldıktan sonra tetiklenen
    sayaçlar Qt olay döngüsüne istisna atar ("Exceptions caught in Qt event loop") ve
    pytest-qt bu hatayı rastgele bir sonraki teste yazar (kırılgan testlerin asıl nedeni).
    """
    assert pencere.timer_manager.ticker_timer.interval() == config.KUSAK_ADIM_ARALIGI_MS
    pencere.timer_manager.start_all()
    assert pencere.timer_manager.ticker_timer.isActive()
    assert pencere.timer_manager.cycle_timer.isActive()
    assert pencere.timer_manager.clock_timer.isActive()
    zamanlayicilari_durdur(pencere)


def test_liste_modu_ayiriciyla_akar(pencere: PharmacyApp, monkeypatch: pytest.MonkeyPatch) -> None:
    """KUSAK_TEKLI = False ise referans davranış: tüm liste tek metin, kesintisiz akar."""
    monkeypatch.setattr(config, "KUSAK_TEKLI", False)
    yayin_moduna_gec(pencere)
    pencere.prepare_ticker_text()
    etiket = pencere.yayin_widget.ticker_label
    assert config.KUSAK_AYIRICI in etiket.text()
    assert all(item in etiket.text() for item in pencere.ticker_items)
    onceki = etiket.x()
    for _ in range(10):
        pencere.scroll_ticker()
    assert etiket.x() == onceki - 10 * config.KUSAK_HIZ  # sabit hızda kayar


def test_config_kusak_degerleri() -> None:
    assert config.KUSAK_YUKSEKLIK >= 60
    assert config.KUSAK_ALT_BOSLUK > 0
    assert config.KUSAK_YAZI_PUNTO >= 28
    assert config.KUSAK_HIZ > 0 and config.KUSAK_ADIM_ARALIGI_MS > 0
    assert config.KUSAK_TEKLI is True
    assert config.KUSAK_GIRIS_MS > 0 and config.KUSAK_DURMA_MS > 0 and config.KUSAK_CIKIS_MS > 0


def test_config_yayin_penceresi_veride_tutarli() -> None:
    """Veri tarafı: yayın kayıtları anlamlı bir gün penceresi taşımalı.

    Gerçek aktiflik **saate bağlıdır** (veri 08:30–23:59 penceresi kullanır); bu yüzden
    pencere dışında çalıştırıldığında "aktif yayın var" beklenmez — tutarlılık denetlenir.
    """
    veri = json.loads((KOK / "lastSystemData.json").read_text(encoding="utf-8"))
    yayinlar = veri["Yayinlar"]
    assert yayinlar, "veri dosyasında hiç yayın yok"

    an = datetime.now()
    aktif = [
        v
        for v in yayinlar.values()
        if datetime.fromisoformat(v["start"]) <= an <= datetime.fromisoformat(v["end"])
    ]
    ornek = next(iter(yayinlar.values()))
    bas = datetime.fromisoformat(ornek["start"])
    bit = datetime.fromisoformat(ornek["end"])
    assert bit > bas, "yayın bitişi başlangıçtan sonra olmalı"
    if bas.time() <= an.time() <= bit.time():
        assert aktif, "pencere içindeyiz ama aktif yayın bulunamadı"
