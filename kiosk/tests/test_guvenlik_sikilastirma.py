"""Güvenlik sertleştirmesi testleri.

Kapsanan başlıklar:
  * ağ kapısı: https + izin listesi + port + kullanıcı bilgisi + uzunluk/denetim karakteri,
  * yönlendirme denetimi (izin listesi atlatma) ve vekil sunucuların yok sayılması,
  * TLS alt sınırı ve sertifika doğrulaması,
  * JSON boyut/derinlik/düğüm sınırları, dosya okuma (symlink, kök dışı, boyut),
  * metin temizleme (denetim karakteri, çift yönlü yazı, uzunluk) ve sayı/liste sınırlama,
  * cihaz kimliğinin günlükte gizlenmesi, atomik yazma ve dosya izinleri,
  * veri katmanında uçtan uca süzme, yayın süresi sınırı, güvenlik denetimi raporu.
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

import pytest

import config
from core.broadcast_manager import BroadcastManager
from core.data_handler import kaydi_ekran_bicimine_cevir
from security import qt_sertlestirme, veri_dogrulama
from security.denetim import denetim_kodu, denetim_raporu, rapor_metni
from security.image_policy import dogrula
from security.network import (
    IZINLI_ICERIK_TURLERI,
    AgAyarlari,
    AgHatasi,
    _opener,
    _tls_baglami,
)
from security.veri_dogrulama import (
    VeriHatasi,
    atomik_yaz,
    dosya_oku_guvenli,
    json_yukle,
    kimlik_ozeti,
    liste_sinirla,
    sayi_sinirla,
    temiz_metin,
)

KOK = Path(__file__).resolve().parent.parent
AYARLAR = AgAyarlari(izinli_hostlar=("hakkisabah.com", "www.kocaelieo.org.tr"))


# ------------------------------------------------------------------ ağ kapısı
@pytest.mark.parametrize(
    "url",
    [
        "http://hakkisabah.com/x.png",  # https değil
        "file:///etc/passwd",
        "ftp://hakkisabah.com/x.png",
        "data:text/html,<b>x</b>",
        "https://kotu.example/x.png",  # izin listesinde değil
        "https://hakkisabah.com:8443/x.png",  # izinli olmayan port
        "https://user:parola@hakkisabah.com/x.png",  # kullanıcı bilgisi
        "https://hakkisabah.com/x.png\r\nHost: kotu.example",  # denetim karakteri
        "https://hakkisabah.com/x y.png",  # boşluk
        "https://" + "a" * 3000 + ".com/x.png",  # çok uzun
        "https://hakkisabah.com.evil.example/x.png",  # alan adı taklidi
        "",
    ],
)
def test_gecersiz_adresler_reddedilir(url: str) -> None:
    with pytest.raises(AgHatasi):
        AYARLAR.dogrula_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://hakkisabah.com/api/x.png",
        "https://HAKKISABAH.com/x.png",  # büyük harf normalleşir
        "https://hakkisabah.com./x.png",  # son nokta normalleşir
        "https://hakkisabah.com:443/x.png",  # açıkça 443
    ],
)
def test_gecerli_adresler_kabul(url: str) -> None:
    assert AYARLAR.dogrula_url(url) is not None
    assert AYARLAR.host_izinli(url) is True


def test_host_izinli_geriye_uyum() -> None:
    assert AYARLAR.host_izinli("https://hakkisabah.com/a.png")
    assert not AYARLAR.host_izinli("http://hakkisabah.com/a.png")
    assert not AYARLAR.host_izinli("file:///etc/passwd")


def test_tls_ayarlari_siki() -> None:
    import ssl

    baglam = _tls_baglami()
    assert baglam.verify_mode is ssl.CERT_REQUIRED
    assert baglam.check_hostname is True
    assert baglam.minimum_version >= ssl.TLSVersion.TLSv1_2
    assert baglam.options & ssl.OP_NO_COMPRESSION


def test_vekiller_yok_sayilir(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ortamda vekil sunucu olsa da uygulamanın opener'ı onu KULLANMAZ."""
    monkeypatch.setenv("https_proxy", "http://kotu-vekil:8080")
    assert urllib.request.getproxies().get("https"), "ortam değişkeni etkin değil (test anlamsız)"

    varsayilan = urllib.request.build_opener().handlers
    assert any(
        getattr(h, "proxies", None) for h in varsayilan
    ), "varsayılan opener vekili görmüyor: karşılaştırma anlamsız"

    bizim = _opener(AYARLAR).handlers
    assert not any(
        getattr(h, "proxies", None) for h in bizim
    ), "uygulamanın opener'ı ortam vekilini kullanıyor"


def test_ayni_hosta_yonlendirme_izlenir() -> None:
    tutamac = urllib.request.HTTPRedirectHandler()
    denetim = __import__("security.network", fromlist=["_YonlendirmeDenetimi"])._YonlendirmeDenetimi(AYARLAR)
    istek = urllib.request.Request("https://hakkisabah.com/a.png")
    yeni = denetim.redirect_request(istek, None, 302, "Found", {}, "https://hakkisabah.com/b.png")
    assert yeni is not None
    del tutamac


def test_farkli_hosta_yonlendirme_reddedilir() -> None:
    denetim = __import__("security.network", fromlist=["_YonlendirmeDenetimi"])._YonlendirmeDenetimi(AYARLAR)
    istek = urllib.request.Request("https://hakkisabah.com/a.png")
    with pytest.raises(AgHatasi, match="farklı ana makineye"):
        denetim.redirect_request(istek, None, 302, "Found", {}, "https://www.kocaelieo.org.tr/a.png")
    # izin listesi dışına yönlendirme hiç denenemez
    with pytest.raises(AgHatasi):
        denetim.redirect_request(istek, None, 302, "Found", {}, "https://kotu.example/a.png")


def test_icerik_turu_izin_listesi() -> None:
    assert "image/png" in IZINLI_ICERIK_TURLERI
    assert "text/html" not in IZINLI_ICERIK_TURLERI
    sonuc = dogrula(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40, icerik_turu="application/x-msdownload")
    assert not sonuc.kabul and "içerik türü" in sonuc.sebep


# -------------------------------------------------------------- JSON sınırları
def test_json_boyut_siniri() -> None:
    with pytest.raises(VeriHatasi, match="çok büyük"):
        json_yukle(b'{"a": 1}', en_buyuk_bayt=4)


def test_json_bos_govde() -> None:
    with pytest.raises(VeriHatasi, match="boş"):
        json_yukle(b"   ")


def test_json_derinlik_siniri() -> None:
    derin = "[" * 60 + "]" * 60
    with pytest.raises(VeriHatasi, match="derinli"):
        json_yukle(derin, en_buyuk_derinlik=8)


def test_json_ayristirici_tasmasi_veri_hatasina_cevrilir() -> None:
    """DERİN GÖVDE (i5 bulgusu): sınır denetimi ayrıştırmadan SONRA çalışır; 20.000 kat iç içe
    liste `json.loads` içinde RecursionError atar.

    KANIT SIKILIĞI (i5 notu): önceki test `match="derinli|ayrıştırıcı"` idi — hata DERİNLİK
    denetiminden gelse de geçerdi, yani ayrıştırıcı taşmasının çevrildiğini KANITLAMIYORDU.
    Burada derinlik/düğüm sınırları çok yüksek verilir → tek olası hata kaynağı ayrıştırıcıdır.
    """
    derin = ("[" * 100_000 + "]" * 100_000).encode()
    # Ölçüm (bu makine, Python 3.14): 20.000 ve 50.000 kat iç içe gövde C tarayıcıda SORUNSUZ
    # ayrıştırılıyor (sınır ~100.000); bu yüzden senaryo gerçek eşiğin üzerinde kurulur.
    # Gövde 200 KB — varsayılan 4 MB sınırının altında, yani hata BOYUTTAN gelmiyor.
    assert len(derin) < 4 * 1024 * 1024, "senaryo belge boyutu sınırının altında kalmalı"
    with pytest.raises(VeriHatasi, match="ayrıştırıcı"):
        json_yukle(derin, en_buyuk_derinlik=1_000, en_buyuk_dugum=1_000_000)


def test_recursionerror_dogrudan_veri_hatasina_cevrilir(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ayrıştırıcının kendi taşması ÇÖZÜLMEZSE çağıranın yoklama turu düşer.

    Doğrudan kanıt: `json.loads` RecursionError atacak şekilde değiştirilir; kapı bunu
    `VeriHatasi`ya çevirmeli (RecursionError dışarı SIZMAMALI).
    """

    def patlat(*_a: object, **_k: object) -> object:
        raise RecursionError("maximum recursion depth exceeded")

    monkeypatch.setattr(veri_dogrulama.json, "loads", patlat)
    with pytest.raises(VeriHatasi, match="ayrıştırıcı"):
        veri_dogrulama.json_yukle(b"{}")


def test_json_dugum_siniri() -> None:
    buyuk = json.dumps({f"k{i}": list(range(50)) for i in range(200)})
    with pytest.raises(VeriHatasi, match="düğüm"):
        json_yukle(buyuk, en_buyuk_dugum=500)


def test_json_bozuk_govde() -> None:
    with pytest.raises(VeriHatasi, match="çözülemedi"):
        json_yukle(b"{bozuk")
    with pytest.raises(VeriHatasi):
        json_yukle(b"\xff\xfe\x00\x01")  # geçersiz UTF-8


def test_json_gecerli_govde() -> None:
    assert json_yukle(b'{"a": [1, 2, {"b": "c"}]}') == {"a": [1, 2, {"b": "c"}]}
    assert json_yukle('{"c": "ü"}'.encode("utf-8")) == {"c": "ü"}


# ------------------------------------------------------------- dosya okuma kapısı
def test_symlink_reddedilir(tmp_path: Path) -> None:
    hedef = tmp_path / "gercek.json"
    hedef.write_text("{}", encoding="utf-8")
    bag = tmp_path / "bag.json"
    bag.symlink_to(hedef)
    with pytest.raises(VeriHatasi, match="sembolik bağ"):
        dosya_oku_guvenli(bag, kok=tmp_path)


def test_kok_disindaki_dosya_reddedilir(tmp_path: Path) -> None:
    disarisi = tmp_path / "disarisi"
    disarisi.mkdir()
    (disarisi / "x.json").write_text("{}", encoding="utf-8")
    icerisi = tmp_path / "icerisi"
    icerisi.mkdir()
    with pytest.raises(VeriHatasi, match="dışında"):
        dosya_oku_guvenli(disarisi / "x.json", kok=icerisi)


def test_buyuk_dosya_reddedilir(tmp_path: Path) -> None:
    dosya = tmp_path / "buyuk.json"
    dosya.write_text("x" * 5000, encoding="utf-8")
    with pytest.raises(VeriHatasi, match="çok büyük"):
        dosya_oku_guvenli(dosya, kok=tmp_path, en_buyuk_bayt=1024)


def test_normal_dosya_okunur(tmp_path: Path) -> None:
    dosya = tmp_path / "veri.json"
    dosya.write_text('{"a":1}', encoding="utf-8")
    assert dosya_oku_guvenli(dosya, kok=tmp_path) == b'{"a":1}'


def test_atomik_yazma_ve_izin(tmp_path: Path) -> None:
    hedef = tmp_path / "alt" / "durum.json"
    atomik_yaz(hedef, {"a": 1})
    assert json.loads(hedef.read_text(encoding="utf-8")) == {"a": 1}
    assert (os.stat(hedef).st_mode & 0o777) == 0o600  # yalnızca sahibi
    assert not list(tmp_path.rglob("*.tmp")), "geçici dosya kaldı"


# --------------------------------------------------------------- metin temizleme
def test_denetim_karakterleri_atilir() -> None:
    assert temiz_metin("DEVA\x00\x07 ECZANESİ\x1b") == "DEVA ECZANESİ"


def test_cift_yonlu_yazi_kontrolleri_atilir() -> None:
    sahte = "DEVA\u202e 02:10 - 0259\u202c"
    temiz = temiz_metin(sahte, tek_satir=True)
    assert "\u202e" not in temiz and "\u202c" not in temiz
    assert "DEVA" in temiz


def test_satir_sonu_ve_bosluk_sadelestirme() -> None:
    assert temiz_metin("A\n\n  B", tek_satir=True) == "A B"
    assert temiz_metin("A\nB", tek_satir=False) == "A\nB"
    assert temiz_metin("   kenar   ") == "kenar"


def test_uzunluk_sinirlanir() -> None:
    uzun = "x" * 500
    temiz = temiz_metin(uzun, en_buyuk=40)
    assert len(temiz) == 40 and temiz.endswith("…")


def test_sayi_olmayan_girdiler() -> None:
    assert temiz_metin(None) == ""
    assert temiz_metin(1234, tek_satir=True) == "1234"


# --------------------------------------------------- sayı / liste sınırlama
def test_sayi_sinirla() -> None:
    assert sayi_sinirla("10", alt=1, ust=60, varsayilan=10) == 10
    assert sayi_sinirla("10.0", alt=1, ust=60, varsayilan=10) == 10
    assert sayi_sinirla(99999999, alt=1, ust=60, varsayilan=10) == 60  # üst sınır
    assert sayi_sinirla(-5, alt=1, ust=60, varsayilan=10) == 1  # alt sınır
    assert sayi_sinirla("abc", alt=1, ust=60, varsayilan=10) == 10  # varsayılan
    assert sayi_sinirla(None, alt=1, ust=60, varsayilan=10) == 10


def test_liste_sinirla() -> None:
    assert liste_sinirla([1, 2, 3, 4], en_buyuk=2) == [1, 2]
    assert liste_sinirla("liste değil", en_buyuk=5) == []
    assert liste_sinirla([1, 2], en_buyuk=5) == [1, 2]


def test_kimlik_ozeti_ham_kimligi_sizdirmaz() -> None:
    kimlik = "98273648723468273"
    ozet = kimlik_ozeti(kimlik)
    assert kimlik not in ozet
    assert ozet.startswith("9827")
    assert "sha256:" in ozet
    assert kimlik_ozeti("") == "-"
    assert kimlik_ozeti("abc") != kimlik_ozeti("abd")  # özet ayırt edici


# ------------------------------------------------------- veri katmanı (uçtan uca)
def test_ekran_kaydinda_metin_suzulur() -> None:
    satir = kaydi_ekran_bicimine_cevir(
        {
            "eczane": "DEVA\u202e ECZANESİ\x00",
            "tel": "0262 325 13 35\r\nSahte: 0850",
            "adres": "A" * 500,
            "adres_tarifi": "karşısı\n\nikinci",
            "start": "14/10/2026 08:30",
            "bolge": "İzmit-2",
            "ilce": "İZMİT",
        }
    )
    assert "\u202e" not in satir["eczane"] and "\x00" not in satir["eczane"]
    assert "\r" not in satir["tel"] and "\n" not in satir["tel"]
    assert len(satir["adres"]) <= config.MAX_METIN_UZUNLUK
    assert satir["adres_tarifi"] == "karşısı\nikinci"
    assert satir["baslangic"] == "14/10/2026 08:30"


def test_yayin_listesi_siniri_uygulanir() -> None:
    mgr = BroadcastManager(app_instance=None)
    simdi = "2026-10-14T09:00:00"
    yayinlar = [
        {"start": "2026-10-14T08:00:00", "end": "2026-10-14T10:00:00", "duration": 5}
        for _ in range(getattr(config, "MAX_AKTIF_YAYIN", 20) + 15)
    ]
    aktif = mgr.get_active_yayinlar(yayinlar, simdi=__import__("datetime").datetime.fromisoformat(simdi))
    assert len(aktif) == config.MAX_AKTIF_YAYIN


# ----------------------------------------------------------- Qt eklenti sertleştirme
def test_qt_eklenti_durumu_raporlanir() -> None:
    bilgi = qt_sertlestirme.durum(KOK)
    assert {"eklenti_dizini", "riskli_eklenti", "riskli_modul", "riskli"} <= set(bilgi)
    assert isinstance(bilgi["riskli_eklenti"], list)
    assert isinstance(bilgi["riskli_modul"], list)


def test_modul_karantinasi_kullanilmayanlari_tasir(tmp_path: Path) -> None:
    pyqt = tmp_path / ".venv/lib/python3.14/site-packages/PyQt6"
    (pyqt / "Qt6/lib").mkdir(parents=True)
    (pyqt / "Qt6/qml/QtQuick").mkdir(parents=True)
    for ad in ("QtCore.abi3.so", "QtWidgets.abi3.so", "QtSql.abi3.so", "QtQml.abi3.so"):
        (pyqt / ad).write_bytes(b"sahte")
    for ad in ("libQt6Core.so.6", "libQt6Widgets.so.6", "libQt6Sql.so.6", "libQt6Qml.so.6"):
        (pyqt / "Qt6/lib" / ad).write_bytes(b"sahte")

    tasinan = qt_sertlestirme.modulleri_karantinaya_al(tmp_path)

    assert (pyqt / "QtCore.abi3.so").exists() and (pyqt / "QtWidgets.abi3.so").exists()
    assert not (pyqt / "QtSql.abi3.so").exists() and not (pyqt / "QtQml.abi3.so").exists()
    assert (pyqt / "Qt6/lib/libQt6Core.so.6").exists()
    assert not (pyqt / "Qt6/lib/libQt6Sql.so.6").exists()
    assert not (pyqt / "Qt6/qml").exists()
    assert any("QtSql.abi3.so" in t for t in tasinan)
    assert qt_sertlestirme.durum(tmp_path)["riskli_modul"] == []


def test_karantina_kapali_hicbir_sey_yapmaz() -> None:
    assert qt_sertlestirme.karantinaya_al(KOK, etkin=False) == []


def test_karantina_riskli_eklentileri_tasir(tmp_path: Path) -> None:
    kaynak = tmp_path / ".venv/lib/python3.14/site-packages/PyQt6/Qt6/plugins"
    (kaynak / "imageformats").mkdir(parents=True)
    (kaynak / "platforms").mkdir(parents=True)
    (kaynak / "imageformats/libqsvg.so").write_bytes(b"sahte")
    (kaynak / "imageformats/libqjpeg.so").write_bytes(b"sahte")
    (kaynak / "platforms/libqvnc.so").write_bytes(b"sahte")

    tasinan = qt_sertlestirme.karantinaya_al(tmp_path)
    assert any("imageformats/libqsvg.so" in t for t in tasinan)
    assert any("platforms/libqvnc.so" in t for t in tasinan)
    # izinli eklenti yerinde kalır
    assert (kaynak / "imageformats/libqjpeg.so").exists()
    assert not (kaynak / "imageformats/libqsvg.so").exists()
    assert (tmp_path / ".karantina/qt-eklentileri/imageformats/libqsvg.so").exists()
    assert qt_sertlestirme.durum(tmp_path)["riskli"] == []


def test_ortam_sertlestirme_mevcut_degeri_ezmez(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QT_PLUGIN_PATH", "/ozel/dizin")
    qt_sertlestirme.ortam_sertlestir()
    assert os.environ["QT_PLUGIN_PATH"] == "/ozel/dizin"


# --------------------------------------------------------------- güvenlik denetimi
def test_denetim_raporu_maddeleri() -> None:
    rapor = denetim_raporu()
    adlar = [ad for ad, _d, _s in rapor]
    assert any("Qt sürümü" in a for a in adlar)
    assert any("Ağ politikası" in a for a in adlar)
    assert any("Veri dosyaları" in a for a in adlar)
    assert all(d in ("tamam", "uyari", "hata") for _a, d, _s in rapor)
    assert all(s for _a, _d, s in rapor)  # her madde açıklama taşır


def test_denetim_metni_ve_cikis_kodu() -> None:
    metin = rapor_metni()
    assert "GÜVENLİK DENETİMİ" in metin and "[ OK ]" in metin
    assert denetim_kodu() in (0, 1)
    sahte = [("x", "tamam", "a"), ("y", "hata", "b")]
    assert denetim_kodu(sahte) == 1
    assert denetim_kodu([("x", "uyari", "a")]) == 0
