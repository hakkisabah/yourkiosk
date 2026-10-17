"""SOL PANEL KAYDIRMA (slider) testleri — vurguyu TAKİP eden kaydırma.

KULLANICI GERİ BİLDİRİMİ (düzeltme)
----------------------------------
"Sol taraf sırayla aşağıya iniyor ancak ortadaki ana slider değişmeden 1-2 saniye önce
soldaki slider bir aşağı bir yukarı iniyor… Normalde sol taraf 5'ten fazla ise listenin
en aşağısına geldiğinde scroll hareket etmeli."

Yani kaydırma BAĞIMSIZ bir zamanlayıcıyla değil, **vurgulanan nöbetçiyi takip ederek** ve
nöbetçi değişimiyle (orta geçiş animasyonu) **aynı anda** yapılmalı.

Kurallar:
  * satır yüksekliği her zaman taban (MAKS_GORUNUR_SATIR) boyutunda,
  * kayıt sayısı tabanı aşınca panel kaydırılabilir olur,
  * aktif satır görünürse kaydırma YAPILMAZ; alttan taşarsa satır içine alınacak kadar
    aşağı kayılır (döngü başa dönünce yukarı),
  * otomatik takip kapatılabilir (elle kaydırma çubuğu kalır),
  * ayrı bir zamanlayıcı YOKTUR (eski hatalı davranışın kaynağı).
"""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QApplication

import config
from conftest import paneli_kur

TABAN = 5


def _cerceve(p, indeks: int):
    return p.pharmacy_widgets[indeks][2]


def _gorunur_mu(p, indeks: int, hedef: int) -> bool:
    """Aktif satır, `hedef` kaydırma konumunda tamamen görünür mü?"""
    alan = p._sol_kaydirma_alani
    y = _cerceve(p, indeks).y()
    yukseklik = _cerceve(p, indeks).height()
    return hedef <= y and y + yukseklik <= hedef + alan.viewport().height() + 1


# --------------------------------------------------- taban içinde: kaydırma YOK
@pytest.mark.parametrize("n", [1, 2, 3, 4, 5])
def test_tabana_kadar_kaydirma_alani_olmaz(pencere, n: int) -> None:
    p = pencere()
    yukseklikler = paneli_kur(p, n)
    assert len(yukseklikler) == n
    assert p._sol_kaydirma_alani is None
    assert p.sol_kaydirma_hedefi() == 0


def test_taban_ustunde_kaydirma_alani_acilir(pencere) -> None:
    p = pencere()
    yukseklikler = paneli_kur(p, 8)
    assert len(yukseklikler) == 8
    alan = p._sol_kaydirma_alani
    assert alan is not None, "8 kayıtta kaydırma alanı açılmalı"
    assert alan.verticalScrollBar().maximum() > 0, "kaydırma çubuğu (slider) etkin olmalı"
    assert alan.horizontalScrollBarPolicy().name == "ScrollBarAlwaysOff"


# ------------------------------------------- satır boyutu taban boyutuna SABİT
def test_satir_boyutu_taban_ile_ayni_kalir(pencere) -> None:
    """5 kayıt ile 8 kayıt aynı çerçeve yüksekliğini vermeli (küçülme YOK)."""
    p = pencere()
    bes = paneli_kur(p, TABAN)
    sekiz = paneli_kur(p, 8)
    assert len(set(sekiz)) == 1
    assert set(sekiz) == set(bes), f"kaydırmada satır boyutu değişmemeli: {sekiz} vs {bes}"


@pytest.mark.parametrize("n", [6, 7, 8, 9, 12, 20])
def test_cok_kayitta_da_boyut_sabit(pencere, n: int) -> None:
    p = pencere()
    yukseklikler = paneli_kur(p, n)
    assert len(yukseklikler) == n
    assert len(set(yukseklikler)) == 1
    assert p._sol_kaydirma_alani is not None


# ------------------------------------------ ASIL DÜZELTME: vurguyu takip eden kaydırma
def test_ilk_taban_kayitta_kaydirma_yok(pencere) -> None:
    """İlk 5 nöbetçi gösterilirken (satır alttan taşmadıkça) kaydırma olmaz."""
    p = pencere()
    paneli_kur(p, 8)
    for indeks in range(TABAN):
        assert p.sol_kaydirma_hedefi(indeks) == 0, f"indeks {indeks} için kaydırma gereksiz"


def test_vurgu_alttan_tasinca_kaydirir(pencere) -> None:
    """Vurgu görünür alanın altına inince panel o satırı içine alacak kadar kayar."""
    p = pencere()
    paneli_kur(p, 8)
    hedef_ilk = p.sol_kaydirma_hedefi(0)
    hedef_alti = p.sol_kaydirma_hedefi(5)
    assert hedef_ilk == 0
    assert hedef_alti > hedef_ilk, "6. nöbetçi için kaydırma başlamalı"
    assert _gorunur_mu(p, 5, hedef_alti)


def test_hedefler_asla_yukari_gitmez(pencere) -> None:
    """Liste ilerlerken kaydırma konumu hiç azalmaz (aşağı-yukarı zıplama yok)."""
    p = pencere()
    paneli_kur(p, 12)
    hedefler = [p.sol_kaydirma_hedefi(i) for i in range(12)]
    assert hedefler == sorted(hedefler), f"kaydırma tek yönde olmalı: {hedefler}"
    assert hedefler[0] == 0
    assert hedefler[-1] == p._sol_kaydirma_alani.verticalScrollBar().maximum()


@pytest.mark.parametrize("n", [6, 8, 12])
def test_aktif_satir_her_zaman_gorunur(pencere, n: int) -> None:
    p = pencere()
    paneli_kur(p, n)
    for indeks in range(n):
        hedef = p.sol_kaydirma_hedefi(indeks)
        assert _gorunur_mu(p, indeks, hedef), f"indeks {indeks} görünmüyor (hedef {hedef})"


def test_dongu_basa_donunce_yukari_doner(pencere) -> None:
    """Liste bitip başa dönüldüğünde kaydırma başa döner (doğru yer)."""
    p = pencere()
    paneli_kur(p, 8)
    assert p.sol_kaydirma_hedefi(7) > 0
    assert p.sol_kaydirma_hedefi(0) == 0, "başa dönünce en üstte"


# ------------------------------------------------------ orta geçişle AYNI ZAMANDA
def test_orta_gecisle_ayni_anda_baslar(pencere) -> None:
    """`update_display` hem orta geçişi hem kaydırmayı aynı çağrıda başlatmalı."""
    p = pencere()
    paneli_kur(p, 8)
    cagrilar: list[tuple] = []
    p.animation_handler.animate_transition = lambda *a: cagrilar.append(a)

    p.current_index = 5
    p.update_display()

    assert len(cagrilar) == 1, "orta geçiş animasyonu bir kez başlatılmalı"
    anim = p._sol_kaydirma_anim
    assert anim is not None, "kaydırma aynı çağrıda başlamalı"
    assert anim.endValue() == p.sol_kaydirma_hedefi(5)
    assert anim.duration() == config.SOL_PANEL_KAYDIRMA_SURE_MS
    assert anim.duration() == 1800, "orta geçişin süresiyle aynı (1800 ms) olmalı"


def test_bagimsiz_zamanlayici_yok(pencere, qtbot) -> None:
    """Kendi kendine hareket eden bir sayaç OLMAMALI (bildirilen hatanın kaynağı)."""
    p = pencere()
    paneli_kur(p, 8)
    assert not hasattr(p, "_sol_kaydirma_zamanlayici"), "bağımsız zamanlayıcı kaldırıldı"
    bar = p._sol_kaydirma_alani.verticalScrollBar()
    assert bar.value() == 0
    qtbot.wait(400)  # hiçbir çağrı yapılmadan beklersek
    QApplication.processEvents()
    assert bar.value() == 0, "kaydırma yalnızca vurgu değişiminde tetiklenmeli"


def test_aktif_satir_gorunurse_animasyon_baslamaz(pencere) -> None:
    """Kaydırma gerekmiyorsa animasyon BAŞLATILMAZ (nesne dursa da hareket yok)."""
    p = pencere()
    paneli_kur(p, 8)
    p.current_index = 2  # görünür alanda → kaydırma gerekmez
    p._sol_aktifi_gorunur_yap()
    anim = p._sol_kaydirma_anim
    assert anim is None or anim.state().name == "Stopped"
    assert p._sol_kaydirma_alani.verticalScrollBar().value() == 0


def test_kaydirma_gercekten_uygulanir(pencere, qtbot) -> None:
    """Vurgu değişince çubuk hedefe kadar gerçekten hareket etmeli."""
    p = pencere()
    paneli_kur(p, 8)
    p.current_index = 7
    hedef = p.sol_kaydirma_hedefi(7)
    p._sol_aktifi_gorunur_yap()
    bar = p._sol_kaydirma_alani.verticalScrollBar()
    qtbot.waitUntil(lambda: bar.value() >= hedef, timeout=config.SOL_PANEL_KAYDIRMA_SURE_MS + 2000)
    assert bar.value() == hedef


# ------------------------------------------------------------------ ayarlanabilir
def test_otomatik_takip_kapatilabilir(pencere, monkeypatch: pytest.MonkeyPatch) -> None:
    """`SOL_PANEL_OTOMATIK_KAYDIRMA=False` → çubuk kalır, otomatik kaydırma olmaz."""
    monkeypatch.setattr(config, "SOL_PANEL_OTOMATIK_KAYDIRMA", False)
    p = pencere()
    paneli_kur(p, 8)
    p.current_index = 7
    p._sol_aktifi_gorunur_yap()
    assert p._sol_kaydirma_alani.verticalScrollBar().value() == 0
    assert p._sol_kaydirma_anim is None
    assert p._sol_kaydirma_alani.verticalScrollBar().maximum() > 0  # elle kaydırma sürer


def test_kaydirma_suresi_ayardan(pencere, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "SOL_PANEL_KAYDIRMA_SURE_MS", 500)
    p = pencere()
    paneli_kur(p, 12)
    p.current_index = 11
    p._sol_aktifi_gorunur_yap()
    assert p._sol_kaydirma_anim.duration() == 500


def test_taban_kucukse_esik_de_kucuk(pencere, monkeypatch: pytest.MonkeyPatch) -> None:
    """Taban 3 iken 4 kayıt kaydırmaya geçer; ilk 3 kayıt kaydırma gerektirmez."""
    monkeypatch.setattr(config, "MAKS_GORUNUR_SATIR", 3)
    p = pencere()
    paneli_kur(p, 3)
    assert p._sol_kaydirma_alani is None
    paneli_kur(p, 4)
    assert p._sol_kaydirma_alani is not None
    assert p.sol_kaydirma_hedefi(2) == 0
    assert p.sol_kaydirma_hedefi(3) > 0


def test_cubuk_genisligi_ayardan(pencere, monkeypatch: pytest.MonkeyPatch) -> None:
    """Kaydırma çubuğu genişliği config'ten gelir (0 → gizli)."""
    monkeypatch.setattr(config, "SOL_PANEL_KAYDIRMA_CUBUGU_GENISLIK", 24)
    p = pencere()
    paneli_kur(p, 8)
    assert "width: 24px" in p._sol_kaydirma_alani.verticalScrollBar().styleSheet()

    monkeypatch.setattr(config, "SOL_PANEL_KAYDIRMA_CUBUGU_GENISLIK", 0)
    paneli_kur(p, 8)
    assert p._sol_kaydirma_alani.verticalScrollBarPolicy().name == "ScrollBarAlwaysOff"


def test_yeniden_kurulumda_animasyon_durur(pencere) -> None:
    """Panel yeniden kurulunca eski animasyon durdurulmalı (çifte hareket olmasın)."""
    p = pencere()
    paneli_kur(p, 12)
    p.current_index = 11
    p._sol_aktifi_gorunur_yap()
    eski = p._sol_kaydirma_anim
    assert eski is not None and eski.state().name == "Running"
    paneli_kur(p, 12)
    assert p._sol_kaydirma_alani is not None
    assert p._sol_kaydirma_anim is not eski, "yeni liste için yeni animasyon kurulmalı"
    assert eski.state().name != "Running", "eski animasyon durdurulmalı"


def test_animasyon_bitince_yeniden_kaydirma_hatasiz(pencere, qtbot) -> None:
    """Animasyon bitse de sonraki kaydırma hata vermemeli.

    Regresyon: animasyon `DeleteWhenStopped` ile oluşturulduğunda C++ nesnesi siliniyor,
    Python referansı ölü kalıyor ve bir sonraki `.stop()` "wrapped C/C++ object has been
    deleted" hatası atıyordu (Qt olay döngüsünde yükseldiği için kaydırma sessizce bozulur).
    """
    p = pencere()
    paneli_kur(p, 12)
    p.current_index = 6
    p._sol_aktifi_gorunur_yap()
    qtbot.waitUntil(lambda: p._sol_kaydirma_anim.state().name == "Stopped", timeout=4000)
    # aynı nesne yeniden kullanılmalı ve hata vermemeli
    anim = p._sol_kaydirma_anim
    p.current_index = 11
    p._sol_aktifi_gorunur_yap()
    assert p._sol_kaydirma_anim is anim, "animasyon nesnesi yeniden kullanılmalı"
    assert anim.endValue() == p.sol_kaydirma_hedefi(11)
    p.current_index = 0
    p._sol_aktifi_gorunur_yap()  # eski hedefe dönüş de hata vermemeli
    assert p._sol_kaydirma_anim is anim


def test_cerceve_ve_yazi_gorunumu_degismedi(pencere) -> None:
    """Kaydırma eklenirken çerçeve stil görseli ve puntolar aynı kalmalı (tasarım)."""
    p = pencere()
    paneli_kur(p, 8)
    ad, tel, cerceve = p.pharmacy_widgets[0]
    assert "border-image" in cerceve.styleSheet()
    assert "pharmacyFrame_0" in cerceve.styleSheet()
    assert ad.font().pointSize() == int(30 * p.scale)
    assert tel.font().pointSize() == int(35 * p.scale)
    assert cerceve.height() == paneli_kur(p, TABAN)[0]


def test_kaydirma_alaninda_tum_cerceveler_var(pencere) -> None:
    """8 çerçevenin hepsi kaydırılabilir içerikte olmalı (hiçbiri kaybolmasın)."""
    p = pencere()
    paneli_kur(p, 8)
    icerik = p._sol_kaydirma_alani.widget()
    assert icerik is not None
    assert icerik.layout().count() == 8
    assert len(p.pharmacy_widgets) == 8
    QApplication.processEvents()
    assert all(cerceve.parent() is not None for _a, _t, cerceve in p.pharmacy_widgets)
