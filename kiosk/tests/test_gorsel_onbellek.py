"""Yayın görsellerinin CİHAZDAN gösterilmesi (önbellek akışı) testleri.

Kullanıcı isteği: "Görselleri de artık yayın ekranında gösterilirken cihazdan
gösterilmeli ki her seferinde internet verisi oluşmasın." İlk gösterimde bir kez
indirilir, sonraki gösterimlerde ağa hiç çıkılmaz.
"""

from __future__ import annotations

import pytest
from conftest import png_uret

import config
import pharmacy_app
from core import onbellek
from security.network import AgHatasi

URL = "https://ornek.example/yayin/afis.png"


@pytest.fixture(autouse=True)
def onbellek_gecici(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Önbelleği geçici klasöre alır (gerçek klasöre ve ağa dokunulmaz)."""
    monkeypatch.setattr(onbellek, "KOK", tmp_path)
    monkeypatch.setattr(config, "ONBELLEK_KLASORU", "onbellek")
    monkeypatch.setattr(config, "ONBELLEK_AKTIF", True)
    monkeypatch.setattr(config, "ONBELLEK_GORSEL_LASTUPDATE_YENILER", True)
    monkeypatch.setattr(config, "ALLOWED_HOSTS", ["ornek.example"])
    monkeypatch.setattr(config, "AG_IZINLI_PORTLAR", [443])
    yield


def _indirici(monkeypatch: pytest.MonkeyPatch, govde: bytes, tur: str = "image/png"):
    """`pharmacy_app.indir` yerine geçen sahte indirici; çağrıları kaydeder."""
    cagrilar: list[str] = []

    def sahte(url, ayarlar, **kw):  # noqa: ANN001, ANN002
        cagrilar.append(url)
        return govde, tur

    monkeypatch.setattr(pharmacy_app, "indir", sahte)
    return cagrilar


def test_ilk_gosterim_indirir_sonrasi_onbellekten(pencere, monkeypatch) -> None:
    p = pencere()
    cagrilar = _indirici(monkeypatch, png_uret(48, 36))

    assert p._yayin_gorselini_yukle(URL) is True
    assert len(cagrilar) == 1, "ilk gösterimde bir kez indirilmeli"

    assert p._yayin_gorselini_yukle(URL) is True
    assert p._yayin_gorselini_yukle(URL) is True
    assert len(cagrilar) == 1, "sonraki gösterimlerde AĞA ÇIKILMAMALI"
    assert onbellek.istatistik()["gorsel_adet"] == 1


def test_son_gosterim_tarihi_kaydedilir(pencere, monkeypatch) -> None:
    """Cihaz, görselin son gösterim tarihini tutar (süre sonu temizliği bunu kullanır)."""
    p = pencere()
    _indirici(monkeypatch, png_uret(32, 32))
    p._yayin_gorselini_yukle(URL)
    p._yayin_gorselini_yukle(URL)
    kayit = onbellek._dizin_oku()["gorsel"][onbellek.gorsel_anahtari(URL)]
    assert kayit["gosterim"] == 2
    assert kayit["son_gosterim"] and kayit["url"] == URL


def test_ag_hatasinda_onbellekten_gosterilir(pencere, monkeypatch) -> None:
    """İnternet yoksa (ya da yayın sunucusu düşmüşse) son görsel cihazdan gösterilir."""
    p = pencere()  # önce pencere: açılışta önbellek bakımı çalışır
    onbellek.gorsel_yaz(URL, png_uret(40, 40), "image/png")

    def hata(url, ayarlar, **kw):  # noqa: ANN001, ANN002
        raise AgHatasi("ağ yok")

    monkeypatch.setattr(pharmacy_app, "indir", hata)
    assert p._yayin_gorselini_yukle(URL) is True, "önbellek varsa ağ hatası gösterimi engellemez"


def test_onbellek_yoksa_ag_hatasi_gosterilmez(pencere, monkeypatch) -> None:
    p = pencere()

    def hata(url, ayarlar, **kw):  # noqa: ANN001, ANN002
        raise AgHatasi("ağ yok")

    monkeypatch.setattr(pharmacy_app, "indir", hata)
    assert p._yayin_gorselini_yukle(URL) is False


def test_bozuk_onbellek_agdan_yeniden_alinir(pencere, monkeypatch) -> None:
    p = pencere()
    onbellek.gorsel_yaz(URL, png_uret(24, 24), "image/png")
    onbellek._gorsel_yolu(onbellek.gorsel_anahtari(URL)).write_bytes(b"bozuk bayt")
    cagrilar = _indirici(monkeypatch, png_uret(24, 24))

    assert p._yayin_gorselini_yukle(URL) is True
    assert len(cagrilar) == 1, "bozuk önbellek atılır ve yeniden indirilir"
    assert onbellek.gorsel_oku(URL) is not None, "önbellek onarılmış olmalı"


def test_bayat_gorsel_agdan_tazelenir(pencere, monkeypatch) -> None:
    """Veri (lastupdate) değiştiğinde görsel bir kez tazelenir."""
    p = pencere()
    cagrilar = _indirici(monkeypatch, png_uret(30, 30))
    assert p._yayin_gorselini_yukle(URL) is True
    assert len(cagrilar) == 1

    assert onbellek.gorselleri_bayat_isaretle({URL}) == 1
    assert p._yayin_gorselini_yukle(URL) is True
    assert len(cagrilar) == 2, "bayat işaretli görsel yeniden indirilmeli"
    # tazelendikten sonra yeniden önbellekten
    assert p._yayin_gorselini_yukle(URL) is True
    assert len(cagrilar) == 2


def test_gecersiz_gorsel_onbellege_yazilmaz(pencere, monkeypatch) -> None:
    """Doğrulamadan geçmeyen içerik (ör. HTML) ne gösterilir ne saklanır."""
    p = pencere()
    _indirici(monkeypatch, b"<html><body>olmaz</body></html>", "image/png")
    assert p._yayin_gorselini_yukle(URL) is False
    assert onbellek.istatistik()["gorsel_adet"] == 0, "reddedilen görsel önbelleğe yazılmamalı"


def test_onbellek_kapaliysa_her_gosterimde_indirilir(pencere, monkeypatch) -> None:
    config.ONBELLEK_AKTIF = False
    p = pencere()
    cagrilar = _indirici(monkeypatch, png_uret(20, 20))
    assert p._yayin_gorselini_yukle(URL) is True
    assert p._yayin_gorselini_yukle(URL) is True
    assert len(cagrilar) == 2, "önbellek kapalıyken eski davranış korunur"
    assert onbellek.istatistik()["gorsel_adet"] == 0
