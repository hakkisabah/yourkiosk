"""CİHAZ ÖNBELLEĞİ testleri (Qt'siz).

Amaç (kullanıcı isteği): tüm veri cachelenmeli, bir şey değiştiğinde cache
otomatik silinmeli/geçersizleşmeli; yayın görselleri cihazdan gösterilmeli ve
son gösterim tarihi geçenler hem cihazda hem sunucuda silinmeli.

Bu dosya önbellek katmanının kendisini doğrular (ağ yok, sahte klasör).
Uygulama akışı: `tests/test_gorsel_onbellek.py`.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from conftest import png_uret

import config
from core import onbellek


@pytest.fixture(autouse=True)
def onbellek_klasoru(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Önbelleği geçici klasöre yönlendirir (gerçek klasöre dokunulmaz).

    `KOK` de geçici dizine çevrilir: dosya güvenlik denetimleri kök dışına çıkmayı
    yasakladığı için önbellek kökü ile denetim kökü tutarlı olmalı.
    """
    monkeypatch.setattr(onbellek, "KOK", tmp_path)
    monkeypatch.setattr(config, "ONBELLEK_KLASORU", "onbellek")
    monkeypatch.setattr(config, "ONBELLEK_AKTIF", True)
    monkeypatch.setattr(config, "ONBELLEK_MAKS_BAYT", 512 * 1024 * 1024)
    monkeypatch.setattr(config, "ONBELLEK_GORSEL_SAKLAMA_GUN", 2)
    yield


URL = "https://ornek.example/yayin/afis.png"


# ------------------------------------------------------------------ VERİ (JSON)
def test_veri_yaz_oku() -> None:
    govde = b'{"Nobetler": {}}'
    onbellek.veri_yaz("lastSystemData.json", govde, lastupdate="2026-10-15T02:45:40")
    assert onbellek.veri_oku("lastSystemData.json", "2026-10-15T02:45:40") == govde
    assert onbellek.veri_lastupdate("lastSystemData.json") == "2026-10-15T02:45:40"


def test_lastupdate_degisince_onbellek_gecersiz() -> None:
    """Kullanıcı isteği: 'bir şey değiştiğinde cache otomatikman silinsin'."""
    onbellek.veri_yaz("lastSystemData.json", b'{"a":1}', lastupdate="2026-10-15T02:45:40")
    assert onbellek.veri_oku("lastSystemData.json", "2026-10-15T02:45:40") is not None
    assert onbellek.veri_oku("lastSystemData.json", "2026-10-15T09:00:00") is None


def test_bozuk_veri_onbellegi_kullanilmaz() -> None:
    onbellek.veri_yaz("sablon.json", b'{"a":1}', lastupdate="X")
    # dosyayı boz (sha256 tutmayacak)
    yol = onbellek._veri_yolu("sablon.json")
    yol.write_bytes(b'{"a":999}')
    assert onbellek.veri_oku("sablon.json", "X") is None
    assert onbellek.istatistik()["veri_adet"] == 0, "bozuk kayıt dizinden düşürülmeli"


def test_veri_temizle() -> None:
    onbellek.veri_yaz("a.json", b"{}", lastupdate="1")
    onbellek.veri_yaz("b.json", b"{}", lastupdate="1")
    assert onbellek.veri_temizle("a.json") == 1
    assert onbellek.veri_oku("a.json", "1") is None
    assert onbellek.veri_oku("b.json", "1") is not None
    assert onbellek.veri_temizle() == 1
    assert onbellek.istatistik()["veri_adet"] == 0


def test_kapali_onbellek_hicbir_sey_yazmaz() -> None:
    config.ONBELLEK_AKTIF = False
    onbellek.veri_yaz("a.json", b"{}", lastupdate="1")
    onbellek.gorsel_yaz(URL, png_uret(), "image/png")
    assert onbellek.veri_oku("a.json", "1") is None
    assert onbellek.gorsel_oku(URL) is None
    assert onbellek.istatistik()["veri_adet"] == 0


# ------------------------------------------------------------------ GÖRSEL
def test_gorsel_anahtari_kararli_ve_uzantili() -> None:
    a1 = onbellek.gorsel_anahtari(URL)
    assert a1 == onbellek.gorsel_anahtari(URL), "aynı adres → aynı anahtar"
    assert a1.endswith(".png")
    assert onbellek.gorsel_anahtari(URL + "?v=2") != a1, "adres değişti → farklı anahtar"
    assert onbellek.gorsel_anahtari("https://x/y/afiş").endswith(".bin")


def test_gorsel_yaz_oku_ve_son_gosterim() -> None:
    png = png_uret(16, 16)
    onbellek.gorsel_yaz(URL, png, "image/png")
    assert onbellek.gorsel_oku(URL) == png

    dizin = onbellek._dizin_oku()
    anahtar = onbellek.gorsel_anahtari(URL)
    assert dizin["gorsel"][anahtar]["gosterim"] == 0
    onbellek.gorsel_gosterildi(URL)
    onbellek.gorsel_gosterildi(URL)
    dizin = onbellek._dizin_oku()
    assert dizin["gorsel"][anahtar]["gosterim"] == 2
    assert datetime.fromisoformat(dizin["gorsel"][anahtar]["son_gosterim"]) is not None


def test_bozuk_gorsel_diskten_okunmaz() -> None:
    onbellek.gorsel_yaz(URL, png_uret(), "image/png")
    onbellek._gorsel_yolu(onbellek.gorsel_anahtari(URL)).write_bytes(b"bozuk")
    assert onbellek.gorsel_oku(URL) is None
    assert onbellek.istatistik()["gorsel_adet"] == 0


def test_bayat_isaretlenen_gorsel_okunmaz() -> None:
    onbellek.gorsel_yaz(URL, png_uret(), "image/png")
    assert onbellek.gorsel_oku(URL) is not None
    assert onbellek.gorselleri_bayat_isaretle({URL}) == 1
    assert onbellek.gorsel_oku(URL) is None, "bayat görsel yeniden indirilmeli"
    # tekrar yazıldığında (indirme sonrası) bayat işareti kalkar
    onbellek.gorsel_yaz(URL, png_uret(), "image/png")
    assert onbellek.gorsel_oku(URL) is not None


def test_gorsel_temizle_dosyayi_da_siler() -> None:
    onbellek.gorsel_yaz(URL, png_uret(), "image/png")
    yol = onbellek._gorsel_yolu(onbellek.gorsel_anahtari(URL))
    assert yol.is_file()
    onbellek.gorsel_temizle(URL)
    assert not yol.is_file()
    assert onbellek.istatistik()["gorsel_adet"] == 0


# ------------------------------------------------------------------ BAKIM
def _eskit(url: str, gun: int) -> None:
    """Kaydın son gösterimini geçmişe çeker (süre sonu testi için)."""
    dizin = onbellek._dizin_oku()
    anahtar = onbellek.gorsel_anahtari(url)
    dizin["gorsel"][anahtar]["son_gosterim"] = (datetime.now() - timedelta(days=gun)).isoformat(timespec="seconds")
    onbellek._dizin_yaz(dizin)


def test_son_gosterimi_gecen_gorsel_silinir() -> None:
    """Yayının son gösterim tarihi geçtikten sonra görsel cihazdan silinir."""
    onbellek.gorsel_yaz(URL, png_uret(), "image/png")
    _eskit(URL, gun=5)  # saklama süresi 2 gün
    ozet = onbellek.bakim()
    assert ozet["silinen"] == 1
    assert onbellek.istatistik()["gorsel_adet"] == 0
    assert not onbellek._gorsel_yolu(onbellek.gorsel_anahtari(URL)).is_file()


def test_taze_gorsel_silinmez() -> None:
    onbellek.gorsel_yaz(URL, png_uret(), "image/png")
    _eskit(URL, gun=1)
    assert onbellek.bakim()["silinen"] == 0


def test_veride_gecmeyen_gorsel_artik_silinir() -> None:
    diger = "https://ornek.example/yayin/eski.png"
    onbellek.gorsel_yaz(URL, png_uret(), "image/png")
    onbellek.gorsel_yaz(diger, png_uret(), "image/png")
    ozet = onbellek.bakim(gecerli_url_kumesi={URL})
    assert ozet["silinen"] == 1
    assert onbellek.gorsel_oku(URL) is not None
    assert onbellek.gorsel_oku(diger) is None


def test_kota_asilinca_en_eski_silinir() -> None:
    png = png_uret(64, 64)
    config.ONBELLEK_MAKS_BAYT = len(png) * 3 + 64  # 6 görsel sığmaz, ~3'ü sığar
    adresler = [f"https://ornek.example/yayin/{i}.png" for i in range(6)]
    for i, adres in enumerate(adresler):
        onbellek.gorsel_yaz(adres, png, "image/png")
        dizin = onbellek._dizin_oku()
        dizin["gorsel"][onbellek.gorsel_anahtari(adres)]["son_gosterim"] = (
            datetime.now() - timedelta(minutes=10 - i)
        ).isoformat(timespec="seconds")
        onbellek._dizin_yaz(dizin)
    ozet = onbellek.bakim()
    assert ozet["kalan_bayt"] <= config.ONBELLEK_MAKS_BAYT
    assert ozet["silinen"] >= 1
    # en yeni (son eklenen) hayatta kalmalı
    assert onbellek.gorsel_oku(adresler[-1]) is not None


def test_oksuz_dosya_ve_dosyasiz_kayit_temizlenir() -> None:
    onbellek.gorsel_yaz(URL, png_uret(), "image/png")
    # dizinde kaydı olmayan dosya
    oksuz = onbellek.gorsel_klasoru() / "oksuz.png"
    oksuz.write_bytes(b"x")
    # dosyası olmayan kayıt
    dizin = onbellek._dizin_oku()
    dizin["gorsel"]["kayitsiz"] = {"url": "https://yok", "bayt": 1, "alindi": datetime.now().isoformat()}
    onbellek._dizin_yaz(dizin)

    ozet = onbellek.bakim()
    assert ozet["oksuz_dosya"] == 1
    assert not oksuz.is_file()
    assert "kayitsiz" not in onbellek._dizin_oku()["gorsel"]


def test_onbellegi_bosalt() -> None:
    onbellek.veri_yaz("a.json", b"{}", lastupdate="1")
    onbellek.gorsel_yaz(URL, png_uret(), "image/png")
    sonuc = onbellek.onbellegi_bosalt()
    assert sonuc["silinen_dosya"] == 2
    assert onbellek.istatistik()["veri_adet"] == 0
    assert onbellek.istatistik()["gorsel_adet"] == 0


# ------------------------------------------------------------------ DAMGA
def test_damga_degisimi_bir_kez_bildirilir() -> None:
    assert onbellek.damgayi_kaydet("2026-10-15T02:45:40") is False  # ilk kayıt: değişim yok
    assert onbellek.damgayi_kaydet("2026-10-15T02:45:40") is False  # aynı damga
    assert onbellek.damgayi_kaydet("2026-10-15T09:00:00") is True  # değişti
    assert onbellek.kayitli_damga() == "2026-10-15T09:00:00"


def test_dizin_bozuksa_sifirdan_kurulur() -> None:
    onbellek.gorsel_yaz(URL, png_uret(), "image/png")
    onbellek._dizin_yolu().write_text("{bozuk json", encoding="utf-8")
    assert onbellek.gorsel_oku(URL) is None  # çökmek yerine boş kabul edilir
    assert onbellek.istatistik()["gorsel_adet"] == 0


def test_arac_insan_okur_cikti_uretir(capsys) -> None:
    """`tools/onbellek_durumu.py` gerçekten çalışır (bozuk araç sessizce fark edilmez)."""
    import importlib.util
    from pathlib import Path

    yol = Path(__file__).resolve().parent.parent / "tools" / "onbellek_durumu.py"
    spec = importlib.util.spec_from_file_location("onbellek_durumu", yol)
    assert spec and spec.loader
    arac = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(arac)

    onbellek.veri_yaz("a.json", b"{}", lastupdate="2026-10-15 02:45:40")
    onbellek.gorsel_yaz(URL, png_uret(), "image/png")
    arac.durum()
    cikti = capsys.readouterr().out
    assert "görsel kaydı  : 1 dosya" in cikti
    assert "veri kaydı    : 1 dosya" in cikti

    arac.liste()
    dokum = capsys.readouterr().out
    assert "gösterim=" in dokum and URL in dokum


def test_istatistik_alanlari() -> None:
    onbellek.veri_yaz("a.json", b"{}", lastupdate="1")
    onbellek.gorsel_yaz(URL, png_uret(), "image/png")
    bilgi = onbellek.istatistik()
    assert bilgi["aktif"] is True
    assert bilgi["veri_adet"] == 1 and bilgi["gorsel_adet"] == 1
    assert bilgi["gorsel_bayt"] > 0 and bilgi["veri_bayt"] > 0
    assert bilgi["maks_bayt"] == config.ONBELLEK_MAKS_BAYT
