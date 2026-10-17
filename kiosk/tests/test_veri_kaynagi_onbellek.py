"""Veri kaynağı önbelleği: `lastupdate` değişmediyse büyük veri dosyaları AĞDAN ÇEKİLMEZ.

Kullanıcı isteği: "kioskta tüm veriler cachelenmeli ancak bir şey değiştiğinde o
cache otomatikman silinmeli". Değişim ölçütü sunucudaki `lastupdate.json` değeridir;
damga aynıysa diskteki kopya kullanılır (yalnızca küçük damga dosyası indirilir).
"""

from __future__ import annotations

import json

import pytest

import config
from core import onbellek, veri_kaynagi

DAMGA1 = "2026-10-15T02:45:40"
DAMGA2 = "2026-10-15T09:00:00"
VERI = {"Nobetler": {"1": {"ilce": "TEST"}}, "Yayinlar": {"1": {"contentUrl": "https://ornek.example/a.png"}}}


@pytest.fixture(autouse=True)
def ortam(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(onbellek, "KOK", tmp_path)
    monkeypatch.setattr(config, "ONBELLEK_KLASORU", "onbellek")
    monkeypatch.setattr(config, "ONBELLEK_AKTIF", True)
    monkeypatch.setattr(config, "ONBELLEK_VERI_LASTUPDATE_KULLAN", True)
    monkeypatch.setattr(config, "KAYNAK", "https")
    monkeypatch.setattr(config, "DOSYA_ADRESI", "https://ornek.example/veri")
    monkeypatch.setattr(config, "ALLOWED_HOSTS", ["ornek.example"])
    monkeypatch.setattr(config, "AG_IZINLI_PORTLAR", [443])
    veri_kaynagi.onbellegi_temizle()
    yield
    veri_kaynagi.onbellegi_temizle()


def _sahte_ag(monkeypatch: pytest.MonkeyPatch, damga_kutusu: dict):
    """`indir` yerine geçen sahte ağ; hangi dosyaların çekildiğini kaydeder."""
    cekilenler: list[str] = []

    def sahte_indir(url, ayarlar, **kw):  # noqa: ANN001, ANN002
        cekilenler.append(url)
        if url.endswith("lastupdate.json"):
            return json.dumps({"lastUpdate": damga_kutusu["deger"]}).encode(), "application/json"
        return json.dumps(VERI).encode(), "application/json"

    monkeypatch.setattr(veri_kaynagi, "indir", sahte_indir)
    return cekilenler


def test_lastupdate_degismedikce_buyuk_veri_agdan_cekilmez(monkeypatch) -> None:
    kutu = {"deger": DAMGA1}
    cekilenler = _sahte_ag(monkeypatch, kutu)

    assert veri_kaynagi.sistem_verisi_yukle() == VERI
    assert sum("lastSystemData" in u for u in cekilenler) == 1, "ilk turda indirilmeli"

    veri_kaynagi.onbellegi_temizle()  # bellek önbelleği temiz; disk önbelleği duruyor
    assert veri_kaynagi.sistem_verisi_yukle() == VERI
    assert sum("lastSystemData" in u for u in cekilenler) == 1, "ikinci turda AĞDAN ÇEKİLMEMELİ"
    assert sum("lastupdate.json" in u for u in cekilenler) == 2, "damga dosyası her turda okunur"


def test_lastupdate_degisince_veri_yeniden_cekilir(monkeypatch) -> None:
    kutu = {"deger": DAMGA1}
    cekilenler = _sahte_ag(monkeypatch, kutu)
    assert veri_kaynagi.sistem_verisi_yukle() == VERI
    veri_kaynagi.onbellegi_temizle()

    kutu["deger"] = DAMGA2  # sunucuda içerik değişti
    assert veri_kaynagi.sistem_verisi_yukle() == VERI
    assert sum("lastSystemData" in u for u in cekilenler) == 2, "damga değişti → yeniden indirilmeli"
    assert onbellek.veri_lastupdate("lastSystemData.json") == DAMGA2, "yeni damga kaydedilmeli"


def test_veri_onbellegi_kapaliysa_her_kez_indirilir(monkeypatch) -> None:
    config.ONBELLEK_VERI_LASTUPDATE_KULLAN = False
    kutu = {"deger": DAMGA1}
    cekilenler = _sahte_ag(monkeypatch, kutu)
    veri_kaynagi.sistem_verisi_yukle()
    veri_kaynagi.onbellegi_temizle()
    veri_kaynagi.sistem_verisi_yukle()
    assert sum("lastSystemData" in u for u in cekilenler) == 2


def test_disk_onbellegi_bayatsa_yeniden_indirilir(monkeypatch) -> None:
    """Disk kaydı eski damgadaysa (uygulama kapalıyken veri değiştiyse) tazelenir."""
    kutu = {"deger": DAMGA1}
    _sahte_ag(monkeypatch, kutu)
    veri_kaynagi.sistem_verisi_yukle()
    veri_kaynagi.onbellegi_temizle()

    # disk kaydını eski damgaya çek (uygulama kapalıyken değişim senaryosu)
    dizin = onbellek._dizin_oku()
    dizin["veri"]["lastSystemData.json"]["lastupdate"] = "2020-01-01T00:00:00"
    onbellek._dizin_yaz(dizin)

    kutu["deger"] = DAMGA2
    cekilenler = _sahte_ag(monkeypatch, kutu)
    veri_kaynagi.sistem_verisi_yukle()
    assert sum("lastSystemData" in u for u in cekilenler) == 1
    assert onbellek.veri_lastupdate("lastSystemData.json") == DAMGA2
