"""UZAKTAN KOMUT testleri — `core/komut.py` (+ `core/uzak.py` senkronu).

Güvenlik iddiaları burada kilitlenir: beyaz liste, HMAC imza (fail-closed), hedef cihaz,
tek seferlik uygulama, kuru çalıştırma ve sabit argv (kabuk yok).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

import config
from core import komut, uzak

ANAHTAR = b"test-anahtari-0123456789"


@pytest.fixture()
def ortam(monkeypatch, tmp_path):
    """Cihaz dosyalarını geçici klasöre taşır (gerçek komut.anahtar/duruma dokunmaz)."""
    monkeypatch.setattr(komut, "PROJE_KOK", tmp_path)
    anahtar_dosyasi = tmp_path / "komut.anahtar"
    anahtar_dosyasi.write_bytes(ANAHTAR + b"\n")
    monkeypatch.setattr(komut, "anahtar_yolu", lambda: anahtar_dosyasi)
    monkeypatch.setattr(config, "KOMUT_IMZA_ZORUNLU", True)
    monkeypatch.setattr(config, "KOMUT_KURU_CALISTIRMA", False)
    monkeypatch.setattr(config, "KOMUT_YENIDEN_BASLAT", "systemctl reboot")
    monkeypatch.setattr(config, "KOMUT_UYGULAMA_YENIDEN_BASLAT", "systemctl restart kiosk.service")
    monkeypatch.setattr(config, "KOMUT_EKRANI_YENILE", "")
    return tmp_path


def _belge(komut_adi: str = "uygulamayi-yeniden-baslat", *, cihaz: str = "", kimlik: str = "cmd-1", imzali: bool = True) -> dict:
    belge = {
        "id": kimlik,
        "komut": komut_adi,
        "cihazId": cihaz,
        "zaman": datetime(2026, 10, 17, 18, 0, 0).isoformat(),
        "olusturan": "test",
        "aciklama": "",
    }
    if imzali:
        belge["imza"] = komut.imzala(belge, ANAHTAR)
    return belge


def _yaz(ortam: Path, belge: dict) -> None:
    (ortam / "komut.json").write_text(json.dumps(belge, ensure_ascii=False), encoding="utf-8")


class SahteCalistirici:
    """`subprocess.run` yerine geçer; çağrıları kaydeder."""

    def __init__(self, cikis: int = 0, cikti: str = "tamam", patlat: Exception | None = None):
        self.cagrilar: list[list[str]] = []
        self.cikis = cikis
        self.cikti = cikti
        self.patlat = patlat

    def __call__(self, argv, **_kw):
        self.cagrilar.append(list(argv))
        if self.patlat:
            raise self.patlat

        class T:
            returncode = self.cikis
            stdout = self.cikti
            stderr = ""

        return T()


# ------------------------------------------------------------------ imza
def test_imza_gecerli_ve_tamper_reddedilir() -> None:
    belge = _belge()
    assert komut.imza_dogrula(belge, ANAHTAR).kabul is True
    # farklı anahtar
    assert komut.imza_dogrula(belge, b"baska-anahtar").kabul is False
    # içerik değiştirilmiş (imza tutmaz)
    bozuk = dict(belge, komut="yeniden-baslat")
    assert komut.imza_dogrula(bozuk, ANAHTAR).kabul is False
    # imzasız + zorunlu → red
    assert komut.imza_dogrula(_belge(imzali=False), ANAHTAR, True).kabul is False
    # imzasız + zorunlu değil → kabul (varsayılan zorunlu)
    assert komut.imza_dogrula(_belge(imzali=False), ANAHTAR, False).kabul is True


def test_imza_var_ama_cihazda_anahtar_yoksa_reddedilir() -> None:
    karar = komut.imza_dogrula(_belge(), None)
    assert karar.kabul is False and "anahtar yok" in karar.sebep


# ------------------------------------------------------------------ doğrulama kuralları
def test_beyaz_liste_disi_komut_reddedilir(ortam) -> None:
    karar = komut.dogrula({"id": "x", "komut": "rm -rf /", "imza": "abc"}, anahtar=ANAHTAR)
    assert karar.kabul is False and "izin listesinde olmayan" in karar.sebep


def test_kimliksiz_komut_reddedilir(ortam) -> None:
    karar = komut.dogrula(_belge(kimlik=""), anahtar=ANAHTAR)
    assert karar.kabul is False and "kimliği" in karar.sebep


def test_baska_cihazin_komutu_reddedilir(ortam) -> None:
    belge = _belge(cihaz="BASKASI")
    assert komut.dogrula(belge, cihaz_id="BENIM", anahtar=ANAHTAR).kabul is False
    # boş/"*" → tüm cihazlar
    assert komut.dogrula(_belge(), cihaz_id="BENIM", anahtar=ANAHTAR).kabul is True
    assert komut.dogrula(_belge(cihaz="*"), cihaz_id="BENIM", anahtar=ANAHTAR).kabul is True
    assert komut.dogrula(_belge(cihaz="BENIM"), cihaz_id="BENIM", anahtar=ANAHTAR).kabul is True


def test_argv_tanimli_degilse_reddedilir(ortam, monkeypatch) -> None:
    monkeypatch.setattr(config, "KOMUT_UYGULAMA_YENIDEN_BASLAT", "")
    karar = komut.dogrula(_belge(), anahtar=ANAHTAR)
    assert karar.kabul is False and "tanımlı değil" in karar.sebep
    # ekrani-yenile için argv boş OLABİLİR (uygulama içi)
    assert komut.dogrula(_belge("ekrani-yenile"), anahtar=ANAHTAR).kabul is True


def test_argv_config_ten_okunur(ortam) -> None:
    assert komut.argv("uygulamayi-yeniden-baslat") == ["systemctl", "restart", "kiosk.service"]
    assert komut.argv("yeniden-baslat") == ["systemctl", "reboot"]
    assert komut.argv("ekrani-yenile") == []


# ------------------------------------------------------------------ uygulama
def test_kuru_calistirmada_hicbir_sey_calistirilmaz(ortam) -> None:
    calistirici = SahteCalistirici()
    sonuc = komut.uygula(_belge(), kuru=True, calistir=calistirici)
    assert calistirici.cagrilar == []
    assert sonuc.kuru is True and "KURU" in sonuc.ozet()
    # durum yine yazılır (aynı komut tekrar denenmesin)
    assert komut.durum_oku()["son_id"] == "cmd-1"


def test_komut_sabit_argv_ile_calistirilir(ortam) -> None:
    calistirici = SahteCalistirici(cikis=0, cikti="ok")
    sonuc = komut.uygula(_belge(), calistir=calistirici)
    assert calistirici.cagrilar == [["systemctl", "restart", "kiosk.service"]]
    assert sonuc.cikis_kodu == 0 and sonuc.cikti == "ok"


def test_komut_hatasi_uygulamayi_dusurmez(ortam) -> None:
    calistirici = SahteCalistirici(patlat=TimeoutError("zaman aşımı"))
    sonuc = komut.uygula(_belge(), calistir=calistirici)
    assert "zaman aşımı" in sonuc.hata
    assert komut.durum_oku()["son_id"] == "cmd-1"  # sonsuz döngüye girmesin


def test_ekrani_yenile_uygulama_ici_isleme(ortam) -> None:
    calistirici = SahteCalistirici()
    sonuc = komut.uygula(_belge("ekrani-yenile"), calistir=calistirici)
    assert sonuc.uygulama_ici is True and calistirici.cagrilar == []
    assert "uygulama içi" in sonuc.ozet()


# ------------------------------------------------------------------ ekran bildirimi
def test_bildirim_komuttan_once_gosterilir_ve_sonra_kalkar(ortam) -> None:
    """Kullanıcı isteği: komut uygulanırken ekranda kısa "yeniden başlatılıyor" bilgisi.

    SIRA ÖNEMLİ: bildirim `subprocess` çağrısından ÖNCE kurulmalı (Qt ancak o an boyayabilir).
    """
    from core import bildirim

    bildirim.sifirla()
    gorulen: dict = {}

    def geri_cagri(komut_adi: str) -> None:
        aktif = bildirim.aktif()
        gorulen["komut"] = komut_adi
        gorulen["bildirim_var"] = aktif is not None
        gorulen["metin"] = (aktif or {}).get("metin", "")

    def sahte_calistir(argv, **_kw):
        gorulen["calisti"] = True
        gorulen["bildirim_calisme_aninda"] = bildirim.aktif() is not None
        return SahteCalistirici()(argv)

    sonuc = komut.uygula(_belge(), calistir=sahte_calistir, bildirim_geri_cagri=geri_cagri)

    assert sonuc is not None and sonuc.cikis_kodu == 0
    assert gorulen["komut"] == "uygulamayi-yeniden-baslat"
    assert gorulen["bildirim_var"] is True
    assert "yeniden başlatılıyor" in gorulen["metin"]
    assert gorulen["calisti"] is True
    assert gorulen["bildirim_calisme_aninda"] is True, "bildirim çalıştırmadan önce kurulmalı"
    assert bildirim.aktif() is None, "komut bitince bildirim kalkmalı"


def test_kuru_calistirmada_bildirim_gosterilmez(ortam) -> None:
    from core import bildirim

    bildirim.sifirla()
    cagrildi: list[str] = []
    komut.uygula(_belge(), kuru=True, calistir=SahteCalistirici(), bildirim_geri_cagri=cagrildi.append)
    assert cagrildi == []
    assert bildirim.aktif() is None


def test_ekrani_yenile_bildirimi_kisa_sureli(ortam) -> None:
    """`uygulama içi` komut (ekranı yenile) 4 sn'lik bildirim bırakır: tarayıcı sayfası bunu
    okuyup yazıyı gösterebilsin diye `temizle()` çağrılmaz, süre dolunca kendiliğinden kalkar."""
    from core import bildirim

    bildirim.sifirla()
    komut.uygula(_belge("ekrani-yenile"), calistir=SahteCalistirici())
    aktif = bildirim.aktif()
    assert aktif is not None and aktif["komut"] == "ekrani-yenile"
    assert 0 < (aktif["bitis"] - aktif["baslangic"]) <= bildirim.VARSAYILAN_SURE_S


# ------------------------------------------------------------------ uçtan uca kontrol
def test_kontrol_komut_yoksa_bos_doner(ortam) -> None:
    karar, sonuc = komut.kontrol(cihaz_id="BENIM")
    assert karar.kabul is False and sonuc is None


def test_kontrol_gecerli_komutu_uygular_ve_tekrar_engeli(ortam) -> None:
    _yaz(ortam, _belge(cihaz="BENIM"))
    calistirici = SahteCalistirici()
    karar, sonuc = komut.kontrol(cihaz_id="BENIM", calistir=calistirici)
    assert karar.kabul is True and sonuc is not None
    assert calistirici.cagrilar == [["systemctl", "restart", "kiosk.service"]]

    # AYNI komut ikinci kez: uygulanmaz (S3'te dosya unutulsa bile yeniden başlatmaz)
    karar2, sonuc2 = komut.kontrol(cihaz_id="BENIM", calistir=calistirici)
    assert karar2.kabul is False and "zaten uygulandı" in karar2.sebep
    assert sonuc2 is None
    assert len(calistirici.cagrilar) == 1


def test_kontrol_imzasiz_komutu_reddeder(ortam) -> None:
    _yaz(ortam, _belge(imzali=False))
    calistirici = SahteCalistirici()
    karar, sonuc = komut.kontrol(cihaz_id="BENIM", calistir=calistirici)
    assert karar.kabul is False and "imza" in karar.sebep
    assert calistirici.cagrilar == [] and sonuc is None


def test_durum_dosyasi_son_yirmi_kaydi_tutar(ortam) -> None:
    calistirici = SahteCalistirici()
    for i in range(25):
        komut.uygula(_belge(kimlik=f"cmd-{i}"), kuru=True, calistir=calistirici)
    durum = komut.durum_oku()
    assert durum["son_id"] == "cmd-24"
    assert len(durum["gecmis"]) == 20


# ------------------------------------------------------------------ uzak senkron
def test_senkron_taban_adres_yoksa_calismaz(ortam, monkeypatch) -> None:
    monkeypatch.setattr(config, "DOSYA_ADRESI", "")
    assert uzak.taban_adres() == ""
    assert uzak.senkron({"komut.json": ortam / "komut.json"}) == []


def test_senkron_icerik_degisince_yazar_ayniysa_dokunmaz(ortam, monkeypatch) -> None:
    monkeypatch.setattr(config, "DOSYA_ADRESI", "https://ornek.example/kiosk")
    hedef = ortam / "komut.json"
    govdeler = {"/komut.json": b'{"komut":"ekrani-yenile","id":"1","zaman":"2026-01-01T00:00:00","imza":"x"}'}
    monkeypatch.setattr(uzak, "getir", lambda ad, **_k: govdeler.get("/" + ad))

    assert uzak.senkron({"komut.json": hedef}) == ["komut.json"]
    assert hedef.is_file()
    ilk_zaman = hedef.stat().st_mtime_ns
    # içerik AYNI → mtime değişmemeli (gereksiz arayüz bildirimi olmasın)
    assert uzak.senkron({"komut.json": hedef}) == []
    assert hedef.stat().st_mtime_ns == ilk_zaman
    # içerik değişti → yazılır
    govdeler["/komut.json"] = b'{"komut":"ekrani-yenile","id":"2","zaman":"2026-01-01T00:01:00","imza":"y"}'
    assert uzak.senkron({"komut.json": hedef}) == ["komut.json"]
    assert json.loads(hedef.read_text(encoding="utf-8"))["id"] == "2"


def test_komut_getir_yerel_kopyayi_gunceller(ortam, monkeypatch) -> None:
    monkeypatch.setattr(config, "DOSYA_ADRESI", "https://ornek.example/kiosk")
    belge = _belge(kimlik="uzaktan-1")
    monkeypatch.setattr(uzak, "kosullu_getir",
                        lambda ad, **_k: (json.dumps(belge).encode(), False, ('"e"', "")) if ad == "komut.json" else (None, False, ("", "")))
    assert komut.getir() is True
    okunan = komut.oku()
    assert okunan and okunan["id"] == "uzaktan-1"
    # indirme tek başına çalıştırmaz
    assert komut.durum_oku()["son_id"] == ""


# ------------------------------------------------------------------ uygulama entegrasyonu (Qt)
def test_uzaktan_komut_tetik_kontrol_ile_uygulanir(pencere, monkeypatch, tmp_path) -> None:
    """`tetik_kontrol` her turda uzaktan komutu denetler ve uygular (kuru modda çalıştırmadan)."""
    import pharmacy_app

    monkeypatch.setattr(komut, "PROJE_KOK", tmp_path)
    monkeypatch.setattr(config, "TETIK_DOSYASI", "tetikle-yok-test.json")
    monkeypatch.setattr(config, "KOMUT_KURU_CALISTIRMA", True)  # hiçbir süreç çalışmasın
    monkeypatch.setattr(pharmacy_app.veri_kaynagi, "client_id", lambda: "BENIM")
    monkeypatch.setattr(pharmacy_app.veri_kaynagi, "lastupdate_taze", lambda: "D1")

    anahtar_dosyasi = tmp_path / "komut.anahtar"
    anahtar_dosyasi.write_bytes(b"test-anahtari")
    monkeypatch.setattr(komut, "anahtar_yolu", lambda: anahtar_dosyasi)
    belge = {
        "id": "cmd-app-1",
        "komut": "uygulamayi-yeniden-baslat",
        "cihazId": "BENIM",
        "zaman": "2026-10-17T18:00:00",
    }
    belge["imza"] = komut.imzala(belge, b"test-anahtari")
    (tmp_path / "komut.json").write_text(json.dumps(belge), encoding="utf-8")

    app = pencere()
    app.data_handler.lastupdate = "D1"
    app.tetik_kontrol()

    durum = komut.durum_oku()
    assert durum["son_id"] == "cmd-app-1"
    assert "KURU" in durum["gecmis"][-1]["sonuc"]

    # ikinci tur: aynı komut tekrar uygulanmaz (tek seferlik)
    app.tetik_kontrol()
    assert len([k for k in komut.durum_oku()["gecmis"] if k["id"] == "cmd-app-1"]) == 1


def test_qt_komut_kaplamasi_kisa_bilgi_gosterir(pencere) -> None:
    """Qt: komut uygulanmadan önce kaplama görünür, metni sabittir, 8 sn sonra kalkar."""
    from core import bildirim

    bildirim.sifirla()
    app = pencere()
    assert app.komut_kaplama.isHidden()

    app._komut_bildirimi("yeniden-baslat")

    assert not app.komut_kaplama.isHidden()
    assert "yeniden başlatılıyor" in app.komut_kaplama.text()
    # kaplama sahnenin tamamını kaplar (küçük bir köşe yazısı değil)
    assert app.komut_kaplama.geometry().width() == app.stack.rect().width()

    app.komut_kaplama.hide()
    assert app.komut_kaplama.isHidden()


def test_uzaktan_imzasiz_komut_uygulanmaz(pencere, monkeypatch, tmp_path) -> None:
    """İmzasız komut cihazda ASLA uygulanmaz (fail-closed)."""
    import pharmacy_app

    monkeypatch.setattr(komut, "PROJE_KOK", tmp_path)
    monkeypatch.setattr(config, "TETIK_DOSYASI", "tetikle-yok-test.json")
    monkeypatch.setattr(pharmacy_app.veri_kaynagi, "client_id", lambda: "BENIM")
    monkeypatch.setattr(pharmacy_app.veri_kaynagi, "lastupdate_taze", lambda: "D1")
    monkeypatch.setattr(komut, "anahtar_yolu", lambda: tmp_path / "yok.anahtar")
    (tmp_path / "komut.json").write_text(
        json.dumps({"id": "cmd-x", "komut": "yeniden-baslat", "cihazId": "BENIM", "zaman": "2026-10-17T18:00:00"}),
        encoding="utf-8",
    )

    app = pencere()
    app.data_handler.lastupdate = "D1"
    app.tetik_kontrol()
    assert komut.durum_oku()["son_id"] == ""
