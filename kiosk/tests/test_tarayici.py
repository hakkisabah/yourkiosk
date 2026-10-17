"""TARAYICI (Chromium kiosk) MODU testleri — URL, komut, yerel sunucu ve süpervizör.

Bu testler tarayıcı GEREKTİRMEZ; arayüzün kendisi `web/` altındaki vitest paketiyle
(npm run test) doğrulanır. Burada doğrulananlar: adres/komut üretimi, güvenlik kapıları
(beyaz liste, dizin listesi yok, cihaz kimliği sunulmaz), yeniden başlatma koruması.
"""

from __future__ import annotations

import urllib.error
import urllib.request

import pytest

import config
from core import tarayici


# ------------------------------------------------------------------ URL / komut
def test_url_cihaz_kimligini_tasir() -> None:
    adres = tarayici.url_olustur("CIHAZ-1")
    assert adres.startswith("http://127.0.0.1:")
    assert "clientID=CIHAZ-1" in adres
    assert "veri=yerel" in adres
    assert "/index.html?" in adres


def test_url_veri_modu_ve_port() -> None:
    adres = tarayici.url_olustur("C1", "https", port=1234)
    assert "veri=https" in adres
    assert ":1234/" in adres


def test_url_kimlik_kacisli_yazilir() -> None:
    adres = tarayici.url_olustur("a b&c")
    assert "clientID=a+b%26c" in adres


def test_komut_kiosk_bayraklari() -> None:
    adres = "http://127.0.0.1:8090/index.html?clientID=C1"
    komut = tarayici.komut_olustur(adres, "chromium")
    assert komut[0] == "chromium"
    assert "--kiosk" in komut
    # `--app=` KULLANILMAZ (bazı sürümlerde kiosk ile birlikte boş pencere) → adres konumsal
    assert not any(p.startswith("--app=") for p in komut)
    assert komut[-1] == adres
    assert any(p.startswith("--user-data-dir=") for p in komut)
    assert any(p.startswith("--window-size=") for p in komut)
    # siyah ekrana karşı kararlılık bayrakları (kiosk cihazında GPU'suz çizim)
    assert "--disable-gpu" in komut
    assert "--disable-gpu-compositing" in komut
    assert "--disable-dev-shm-usage" in komut
    assert "--disable-background-networking" in komut
    # ZAMANLAMA: arka planda/örtülü pencerede zamanlayıcı kısıtlaması + rAF duraklaması kapalı
    # (yoksa nöbet adımı gecikir, yayın atlanır, geçişler yarı yolda takılır)
    assert "--disable-background-timer-throttling" in komut
    assert "--disable-renderer-backgrounding" in komut
    assert "--disable-backgrounding-occluded-windows" in komut


def test_tani_bayraklari_konsolu_terminale_doker() -> None:
    komut = tarayici.komut_olustur("http://127.0.0.1:8090/index.html", "chromium", tani=True)
    assert "--enable-logging=stderr" in komut
    assert "--v=1" in komut
    assert "--enable-logging=stderr" not in tarayici.komut_olustur("http://x/", "chromium")


def test_tani_raporu_eksikleri_soyler() -> None:
    """`tani_raporu` arayüz/veri/kimlik durumunu tek tek bildirir (tarayıcı açmadan)."""
    satirlar = tarayici.tani_raporu("CIHAZ-YOK", 0)
    metin = "\n".join(satirlar)
    assert "arayüz kökü" in metin
    assert "derlenmiş mi" in metin
    assert "/index.html" in metin and "/lastSystemData.json" in metin
    assert "match.json eşleşme" in metin
    assert "YOK" in metin  # olmayan kimlik bildirilir (hata değil, uyarı)
    assert "veri içeriği" in metin


def test_ek_bayraklar_komuta_eklenir() -> None:
    eski = config.TARAYICI_EK_BAYRAKLAR
    try:
        config.TARAYICI_EK_BAYRAKLAR = "--disable-gpu --start-fullscreen"
        komut = tarayici.komut_olustur("http://x/index.html")
        assert "--disable-gpu" in komut and "--start-fullscreen" in komut
    finally:
        config.TARAYICI_EK_BAYRAKLAR = eski


def test_tarayici_bul() -> None:
    assert tarayici.tarayici_bul("/bin/true") == "/bin/true"
    assert tarayici.tarayici_bul("/yok/boyle/birsey") is None


def test_kuru_calisma_bir_sey_baslatmaz(capsys) -> None:
    kod = tarayici.main(["--client-id", "C1", "--kuru", "--port", "9999"])
    cikti = capsys.readouterr().out
    assert kod == 0
    assert "adres : http://127.0.0.1:9999/index.html" in cikti
    assert "clientID=C1" in cikti
    assert "komut :" in cikti and "--kiosk" in cikti


# ------------------------------------------------------------------ yerel sunucu
@pytest.fixture()
def sunucu():
    """Geçici portta yerel web sunucusu (test sonunda kapatılır)."""
    if not (tarayici.web_kok() / "index.html").is_file():
        pytest.skip("web/index.html yok")
    tarayici._IstekIsleyici.gunluk.clear()
    s, port, _ = tarayici.sunucu_baslat("127.0.0.1", 0)
    yield port
    s.shutdown()
    s.server_close()


def _indir(port: int, yol: str) -> tuple[int, bytes, dict]:
    istek = urllib.request.Request(f"http://127.0.0.1:{port}{yol}")
    try:
        with urllib.request.urlopen(istek, timeout=5) as yanit:
            return yanit.status, yanit.read(), dict(yanit.headers)
    except urllib.error.HTTPError as hata:
        return hata.code, hata.read(), dict(hata.headers)


def test_arayuz_sunulur(sunucu: int) -> None:
    kod, govde, basliklar = _indir(sunucu, "/index.html")
    assert kod == 200
    assert b"yourkiosk" in govde.lower()  # kiosk sunucusu bu işareti arar
    assert "no-store" in basliklar.get("Cache-Control", "")


def test_veri_dosyalari_sunulur_ve_taze_tutulur(sunucu: int) -> None:
    kod, govde, basliklar = _indir(sunucu, "/lastSystemData.json")
    assert kod == 200 and len(govde) > 10
    assert "no-store" in basliklar.get("Cache-Control", "")  # lastupdate her zaman taze okunsun
    for ad in ("lastupdate.json", "match.json", "sablon.json"):
        assert _indir(sunucu, f"/{ad}")[0] == 200
    # ayarlar.json cihazda varsa sunulur (yoksa 404 — dosya henüz yazılmamıştır)
    from pathlib import Path

    if (Path(__file__).resolve().parent.parent / "ayarlar.json").is_file():
        assert _indir(sunucu, "/ayarlar.json")[0] == 200


def test_tasarim_gorselleri_qt_dosyalarindan_sunulur(sunucu: int) -> None:
    kod, govde, basliklar = _indir(sunucu, "/bg_layout/box.png")
    assert kod == 200
    assert basliklar.get("Content-Type", "").startswith("image/png")
    assert govde[:4] == b"\x89PNG"


def test_cihaz_kimligi_sunulmaz(sunucu: int) -> None:
    """`makinebilgileri.json` (clientID) arayüze HİÇ verilmez: kimlik URL'de gelir."""
    assert _indir(sunucu, "/makinebilgileri.json")[0] == 403


def test_kok_disina_cikma_engellenir(sunucu: int) -> None:
    for yol in ("/../kiosk.log", "/..%2fconfig.py", "/%2e%2e/security/network.py", "/..\\config.py"):
        kod, _govde, _b = _indir(sunucu, yol)
        assert kod in (403, 404), f"{yol} → {kod}"


def test_beyaz_liste_disi_dosyalar_verilmez(sunucu: int) -> None:
    # uzantı beyaz listede değil: GEÇİCİ dosya oluşturup denetle (gerçek dosya → 403)
    gecici = tarayici.web_kok() / "gecici.dat"
    gecici.write_bytes(b"gizli")
    try:
        assert _indir(sunucu, "/gecici.dat")[0] == 403
    finally:
        gecici.unlink(missing_ok=True)
    # olmayan dosya: 404 (var olan ama izinsiz dosya 403 ile ayrılır)
    assert _indir(sunucu, "/olmayan.dat")[0] == 404
    # proje kökündeki izinli olmayan dosya (örn. günlük) sunulmaz: 403
    # (dosya temizlikte silinmiş olabilir → test için geçici olarak oluşturup denetliyoruz)
    gunluk = tarayici.KOK / "kiosk.log"
    olusturuldu = not gunluk.exists()
    if olusturuldu:
        gunluk.write_text("test\n", encoding="utf-8")
    try:
        assert _indir(sunucu, "/kiosk.log")[0] == 403
    finally:
        if olusturuldu:
            gunluk.unlink(missing_ok=True)
    # web klasöründe olmayan yol (dosya yok → 404; yine de HİÇ sunulmaz)
    assert _indir(sunucu, "/security/network.py")[0] == 404


def test_olmayan_dosya_404(sunucu: int) -> None:
    assert _indir(sunucu, "/yok.html")[0] == 404


def test_ayni_portta_bizim_sunucu_algilanir(sunucu: int) -> None:
    assert tarayici._bizim_sunucu_mu("127.0.0.1", sunucu) is True
    assert tarayici._bizim_sunucu_mu("127.0.0.1", 1) is False


# ------------------------------------------------------------------ görsel köprüsü
def _png(genislik: int = 8, yukseklik: int = 8) -> bytes:
    """Küçük, geçerli bir PNG üretir — tarayıcı modu testleri Qt'den bağımsız kalsın diye."""
    import struct
    import zlib

    def parca(tur: bytes, icerik: bytes) -> bytes:
        return struct.pack(">I", len(icerik)) + tur + icerik + struct.pack(">I", zlib.crc32(tur + icerik) & 0xFFFFFFFF)

    satir = b"".join(b"\x00" + b"\x40\x80\xc0" * genislik for _ in range(yukseklik))
    return b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            parca(b"IHDR", struct.pack(">IIBBBBB", genislik, yukseklik, 8, 2, 0, 0, 0)),
            parca(b"IDAT", zlib.compress(satir)),
            parca(b"IEND", b""),
        ]
    )


def _gorsel_yolu(url: str) -> str:
    import urllib.parse

    return "/gorsel?u=" + urllib.parse.quote(url, safe="")


def test_gorsel_koprusu_onbellekten_ag_siz_sunulur(sunucu: int, monkeypatch) -> None:
    """CORS NEDENİYLE görseller sunucudan sunulur: önbellekteki görsel AĞA ÇIKILMADAN verilir.

    Tarayıcı farklı alan adındaki görseli `fetch` edemez ("Failed to fetch"). Bu uç,
    Qt moduyla AYNI cihaz önbelleğini (`onbellek/`) kullanır.
    """
    from core import onbellek

    url = f"https://{config.ALLOWED_HOSTS[0]}/api/nobet-gorsel.png"
    png = _png()
    onbellek.gorsel_yaz(url, png, "image/png")

    def yasak(*_a, **_k):
        raise AssertionError("önbellekteki görsel için ağa çıkılmamalı")

    monkeypatch.setattr("security.network.indir", yasak)
    kod, govde, basliklar = _indir(sunucu, _gorsel_yolu(url))
    assert kod == 200
    assert govde == png
    assert basliklar.get("Content-Type") == "image/png"
    # gösterim sayacı ilerledi mi (süre sonu temizliği buna bakar)
    kayit = onbellek._dizin_oku().get("gorsel", {}).get(onbellek.gorsel_anahtari(url), {})
    assert kayit.get("gosterim", 0) >= 1
    assert kayit.get("url") == url


def test_gorsel_koprusu_politika_disi_hostu_reddeder(sunucu: int) -> None:
    """İzin listesinde olmayan alan adı 403: sunucu 'açık proxy' hâline gelmemeli."""
    assert _indir(sunucu, _gorsel_yolu("https://kotu.example/gorsel.png"))[0] == 403
    assert _indir(sunucu, _gorsel_yolu("http://127.0.0.1:9000/gizli.png"))[0] == 403


def test_gorsel_koprusu_parametresiz_400(sunucu: int) -> None:
    assert _indir(sunucu, "/gorsel")[0] == 400
    assert _indir(sunucu, "/gorsel?u=")[0] == 400


def test_gorsel_koprusu_ag_hatasinda_502(sunucu: int, monkeypatch) -> None:
    from security.network import AgHatasi

    def patlat(*_a, **_k):
        raise AgHatasi("bağlantı kurulamadı")

    monkeypatch.setattr("security.network.indir", patlat)
    url = f"https://{config.ALLOWED_HOSTS[0]}/yok.png"
    kod, govde, _ = _indir(sunucu, _gorsel_yolu(url))
    assert kod == 502
    assert "bağlantı kurulamadı" in govde.decode("utf-8")


def test_gorsel_koprusu_bozuk_govdeyi_reddeder(sunucu: int, monkeypatch) -> None:
    """Ağdan gelen bozuk/metin gövde önbelleğe YAZILMAZ (güvenlik denetimi köprüde de geçerli)."""
    from core import onbellek

    def metin_don(url, _ayarlar, **_k):
        return b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/png"

    monkeypatch.setattr("security.network.indir", metin_don)
    url = f"https://{config.ALLOWED_HOSTS[0]}/kotu.png"
    kod, _, _ = _indir(sunucu, _gorsel_yolu(url))
    assert kod == 403
    assert onbellek.gorsel_oku(url) is None, "reddedilen görsel önbelleğe yazıldı"


def test_imza_veri_dosyasi_degisince_de_degisir(sunucu: int, monkeypatch) -> None:
    """Panel/araç `lastSystemData.json`'u değiştirdiğinde DAMGA AYNI KALSA BİLE imza değişmeli.

    Eski kurgu yalnız `lastupdate.json` + `tetikle.json` üst verisine bakıyordu; damga
    tazelenmemişse arayüz damgaya bağlı önbellekten eski gövdeyi servis ediyordu.
    """
    import json

    ad = "lastSystemData-test-imza.json"
    monkeypatch.setattr(config, "SISTEM_VERISI_DOSYASI", ad)
    yol = tarayici.KOK / ad
    try:
        ilk = tarayici.degisiklik_imzasi()
        assert ad in ilk and f"{ad}:-" not in ilk.replace("lastSystemData-test-imza.json:-", "YOK")
        yol.write_text('{"Nobetler": {}, "Yayinlar": {}}', encoding="utf-8")
        sonra = tarayici.degisiklik_imzasi()
        assert sonra != ilk, "veri dosyası değişince imza değişmeli"

        kod, govde, _ = _indir(sunucu, f"/degisiklik?imza={urllib.parse.quote(ilk, safe='')}&sure=1")
        belge = json.loads(govde.decode("utf-8"))
        assert kod == 200 and belge["degisti"] is True
    finally:
        yol.unlink(missing_ok=True)


def test_uzak_kontrol_bir_tur_komut_yoksa_bos_doner(monkeypatch) -> None:
    """Uzaktan komut yoksa hiçbir şey yapılmaz (boş metin)."""
    monkeypatch.setattr(tarayici, "uzak_kontrol_bir_tur", tarayici.uzak_kontrol_bir_tur)  # dokunma
    from core import komut as komut_modulu

    monkeypatch.setattr(komut_modulu, "kontrol", lambda **_k: (komut_modulu.Karar(False, "komut yok"), None))
    assert tarayici.uzak_kontrol_bir_tur("CIHAZ", {"surec": None}) == ""


def test_uzak_kontrol_bir_tur_ekrani_yenile_tarayiciyi_yeniden_baslatir(monkeypatch) -> None:
    """`ekrani-yenile` → tarayıcı süreci kapatılır, süpervizör onu yeniden başlatır."""
    from core import komut as komut_modulu

    sonuc = komut_modulu.Sonuc(id="c1", komut="ekrani-yenile", uygulama_ici=True, zaman="2026-10-17T18:00:00")
    monkeypatch.setattr(komut_modulu, "kontrol", lambda **_k: (komut_modulu.Karar(True, "imza geçerli"), sonuc))

    class SahteSurec:
        def __init__(self) -> None:
            self.durduruldu = False

        def poll(self):
            return None

        def terminate(self) -> None:
            self.durduruldu = True

    surec = SahteSurec()
    satir = tarayici.uzak_kontrol_bir_tur("CIHAZ", {"surec": surec})
    assert satir and "ekrani-yenile" in satir
    assert surec.durduruldu is True


def test_uzak_kontrol_bir_tur_kapali_surece_dokunmaz(monkeypatch) -> None:
    """Tarayıcı süreci çalışmıyorsa (poll != None) terminate çağrılmaz."""
    from core import komut as komut_modulu

    sonuc = komut_modulu.Sonuc(id="c1", komut="ekrani-yenile", uygulama_ici=True, zaman="2026-10-17T18:00:00")
    monkeypatch.setattr(komut_modulu, "kontrol", lambda **_k: (komut_modulu.Karar(True, "ok"), sonuc))

    class OluSurec:
        def poll(self):
            return 0

        def terminate(self) -> None:  # pragma: no cover - çağrılmamalı
            raise AssertionError("kapalı sürece dokunulmamalı")

    assert tarayici.uzak_kontrol_bir_tur("CIHAZ", {"surec": OluSurec()})


def test_eksik_ayar_dosyalari_varsayilanla_doner(sunucu: int, monkeypatch) -> None:
    """`ayarlar.json`/`kapsam-ayarlari.json` cihazda yoksa 404 yerine VARSAYILAN içerik.

    Bu dosyalar isteğe bağlıdır (Qt tarafı da yoksa varsayılanları kullanır); 404 dönerse
    tarayıcı konsolu gereksiz hata satırlarıyla dolar.
    """
    import json

    # gerçek dosyalar varsa da yoksa da 200 + geçerli JSON dönmeli
    kod, govde, basliklar = _indir(sunucu, "/ayarlar.json")
    assert kod == 200
    assert "application/json" in basliklar.get("Content-Type", "")
    belge = json.loads(govde.decode("utf-8"))
    assert isinstance(belge, dict) and belge, "ayarlar.json boş döndü"

    kod, govde, _ = _indir(sunucu, "/kapsam-ayarlari.json")
    assert kod == 200
    assert isinstance(json.loads(govde.decode("utf-8")), dict)


def test_ayar_varsayilani_gruplari_kapsar() -> None:
    """Varsayılan belge ayar gruplarını içerir ve `_açıklama` anahtarları SÜZÜLÜR."""
    import json

    belge = json.loads(tarayici.ayar_varsayilani("ayarlar.json").decode("utf-8"))
    for grup in ("ozellikler", "kusak", "gorunum"):
        assert grup in belge, f"{grup} grubu varsayılanda yok"
    assert not any(k.startswith("_") for d in belge.values() for k in d), "_açıklama anahtarları süzülmedi"
    assert tarayici.ayar_varsayilani("baska-bir-dosya.json") is None


# ------------------------------------------------------------------ değişiklik bildirimi
def _bekle_ile_degistir(port: int, imza: str, gecikme_s: float, yaz: callable) -> tuple[int, dict, float]:
    """`/degisiklik` isteğini açar, `gecikme_s` sonra `yaz()` çağırır; (kod, gövde, süre) döner."""
    import json
    import threading
    import time

    kutu: dict = {}

    def istek() -> None:
        bas = time.monotonic()
        kod, govde, _ = _indir(port, f"/degisiklik?imza={urllib.parse.quote(imza, safe='')}&sure=8")
        kutu["kod"] = kod
        kutu["govde"] = json.loads(govde.decode("utf-8"))
        kutu["sure"] = time.monotonic() - bas

    ip = threading.Thread(target=istek, daemon=True)
    ip.start()
    time.sleep(gecikme_s)
    yaz()
    ip.join(timeout=10)
    return kutu.get("kod", 0), kutu.get("govde", {}), kutu.get("sure", 0.0)


def test_degisiklik_ucu_bilinmeyen_imzada_hemen_doner(sunucu: int, monkeypatch, tmp_path) -> None:
    """Arayüz ilk açılışta imzayı öğrenir: bilinmeyen imza → ANINDA yanıt (beklemez)."""
    monkeypatch.setattr(config, "TETIK_DOSYASI", "tetikle-test-yok.json")
    import time

    bas = time.monotonic()
    kod, govde, _ = _indir(sunucu, "/degisiklik?imza=&sure=5")
    gecen = time.monotonic() - bas
    belge = __import__("json").loads(govde.decode("utf-8"))
    assert kod == 200
    assert belge["degisti"] is True
    assert belge["imza"]
    assert gecen < 1.0, "bilinmeyen imzada beklenmemeli"
    assert "damga" in belge


def test_degisiklik_ucu_degisiklik_yoksa_nabiz_doner(sunucu: int, monkeypatch) -> None:
    """İmza aynıysa istek `sure` boyunca açık kalır ve `degisti: false` (nabız) döner."""
    import json
    import time

    monkeypatch.setattr(config, "TETIK_DOSYASI", "tetikle-test-yok.json")
    _, govde, _ = _indir(sunucu, "/degisiklik?imza=&sure=0")
    imza = json.loads(govde.decode("utf-8"))["imza"]

    bas = time.monotonic()
    kod, govde2, _ = _indir(sunucu, f"/degisiklik?imza={urllib.parse.quote(imza, safe='')}&sure=1")
    gecen = time.monotonic() - bas
    assert kod == 200
    assert json.loads(govde2.decode("utf-8"))["degisti"] is False
    assert 0.8 <= gecen < 4.0, f"yoklama süresi beklenmedik: {gecen:.2f}s"


def test_degisiklik_ucu_lastupdate_degisince_aninda_doner(sunucu: int, monkeypatch) -> None:
    """NÖBET DEĞİŞİKLİĞİ: `lastupdate.json` yazıldığı AN uzun yoklama döner (20 sn beklenmez)."""
    import json

    monkeypatch.setattr(config, "TETIK_DOSYASI", "tetikle-test-yok.json")
    lastupdate = tarayici.KOK / str(config.LASTUPDATE_DOSYASI)
    onceki = lastupdate.read_bytes() if lastupdate.is_file() else None
    try:
        _, govde, _ = _indir(sunucu, "/degisiklik?imza=&sure=0")
        imza = json.loads(govde.decode("utf-8"))["imza"]

        def yaz() -> None:
            lastupdate.write_bytes(json.dumps({"lastupdate": "2026-10-17 09:12:00"}).encode())

        kod, belge, gecen = _bekle_ile_degistir(sunucu, imza, 0.6, yaz)
        assert kod == 200
        assert belge["degisti"] is True
        assert belge["damga"] == "2026-10-17 09:12:00"
        assert belge["imza"] != imza
        assert gecen < 3.0, f"değişiklik geç bildirildi: {gecen:.2f}s"
    finally:
        if onceki is None:
            lastupdate.unlink(missing_ok=True)
        else:
            lastupdate.write_bytes(onceki)


def test_tetikleyici_yazilinca_imza_ve_yanit_degisir(sunucu: int, monkeypatch) -> None:
    """Panel tetikleyiciyi yazınca imza değişir ve `/degisiklik` tetikleyiciyi döner."""
    import json

    ad = "tetikle-test.json"
    monkeypatch.setattr(config, "TETIK_DOSYASI", ad)
    yol = tarayici.KOK / ad
    try:
        _, govde, _ = _indir(sunucu, "/degisiklik?imza=&sure=0")
        imza = json.loads(govde.decode("utf-8"))["imza"]

        def yaz() -> None:
            yol.write_text(
                json.dumps({"zaman": "2026-10-17T09:12:00", "ilceId": "30607352906750376", "bolgeId": ""}),
                encoding="utf-8",
            )

        kod, belge, gecen = _bekle_ile_degistir(sunucu, imza, 0.5, yaz)
        assert kod == 200 and belge["degisti"] is True
        assert belge["tetik"]["zaman"] == "2026-10-17T09:12:00"
        assert belge["tetik"]["ilceId"] == "30607352906750376"
        assert gecen < 3.0
    finally:
        yol.unlink(missing_ok=True)


def test_tetikleyici_yoksa_varsayilan_doner() -> None:
    """`tetikle.json` cihazda yoksa 404 değil 'tetikleyici yok' belgesi döner (varsayılan)."""
    import json

    belge = json.loads(tarayici.ayar_varsayilani("tetikle.json").decode("utf-8"))
    assert belge["zaman"] == "" and belge["ilceId"] == ""
    # tanımsız imza + tetikleyici yok → `tetik_oku` None, uç yine de çalışır
    assert tarayici.tetik_oku() in (None, {}) or tarayici.tetik_oku().get("zaman")


def test_tetik_oku_bozuk_dosyayi_yok_sayar(monkeypatch) -> None:
    ad = "tetikle-test-bozuk.json"
    monkeypatch.setattr(config, "TETIK_DOSYASI", ad)
    yol = tarayici.KOK / ad
    try:
        yol.write_text("{bozuk", encoding="utf-8")
        assert tarayici.tetik_oku() is None
        # `zaman` alanı olmayan tetikleyici de geçersiz sayılır (imza değişmez)
        yol.write_text('{"ilceId": "X"}', encoding="utf-8")
        assert tarayici.tetik_oku() is None
    finally:
        yol.unlink(missing_ok=True)


# ------------------------------------------------------------------ derlenmiş arayüz
def test_derlenmis_arayuz_sunulur() -> None:
    """Tarayıcıya KAYNAK değil DERLENMİŞ arayüz sunulur (kaynakta `.ts` → beyaz ekran)."""
    assert tarayici.derlenmis_mi(), "web/dist yok: cd web && npm run build"
    assert tarayici.web_kok() == tarayici.derlenmis_kok()
    assert tarayici.web_kok() != tarayici.web_kaynak_kok()


def test_derlenmis_html_tarayicida_calisir(sunucu: int) -> None:
    """Sunulan index.html YALNIZCA derlenmiş varlıklara başvurur (`.ts` istemez)."""
    kod, govde, _ = _indir(sunucu, "/index.html")
    assert kod == 200
    metin = govde.decode("utf-8")
    assert "yourkiosk" in metin.lower()  # port algılama işareti
    assert "/src/main.ts" not in metin, "kaynak arayüz sunuluyor → tarayıcı beyaz ekran verir"
    assert "./assets/" in metin or "/assets/" in metin
    # derlenmiş JS/CSS gerçekten sunulmalı
    for yol in [p for p in metin.split('"') if "assets/" in p and p.endswith((".js", ".css"))][:2]:
        tam = yol.split("?")[0]
        tam = tam if tam.startswith("/") else f"/{tam.lstrip('./')}"
        kod_v, govde_v, basliklar = _indir(sunucu, tam)
        assert kod_v == 200 and len(govde_v) > 100, f"{tam} sunulmadı"
        assert "javascript" in basliklar.get("Content-Type", "") or "css" in basliklar.get("Content-Type", "")


def test_derlenmis_arayuzde_hata_guvenlik_agi_var(sunucu: int) -> None:
    """Boş ekran yerine hata kartı çizen bağımsız güvenlik ağı derlemede bulunmalı."""
    kod, govde, _ = _indir(sunucu, "/index.html")
    assert kod == 200
    metin = govde.decode("utf-8")
    assert "__kioskKart" in metin, "hata güvenlik ağı derlemede yok"
    assert "arayüz başlatılamadı" in metin
    assert "addEventListener" in metin


def test_arayuz_derlenmemisse_net_hata(tmp_path, monkeypatch, capsys) -> None:
    """Derlenmemiş arayüzle tarayıcı açılmaz: beyaz ekran yerine açıklayıcı hata."""
    kaynak = tmp_path / "web"
    kaynak.mkdir()
    (kaynak / "index.html").write_text('<script type="module" src="/src/main.ts"></script>', encoding="utf-8")
    monkeypatch.setattr(tarayici, "web_kaynak_kok", lambda: kaynak)
    monkeypatch.setattr(tarayici, "derlenmis_kok", lambda: kaynak / "dist")

    assert tarayici.derlenmis_mi() is False
    kod = tarayici.baslat("C1", tarayici="/bin/true", port=0)
    cikti = capsys.readouterr().out
    assert kod == 4, "derlenmemiş arayüzde başlatma reddedilmeli"
    assert "npm run build" in cikti and "derlenmemiş" in cikti


def test_sunucu_derlenmemis_kokte_hata_verir(tmp_path, monkeypatch) -> None:
    """Doğrudan `sunucu_baslat` çağrısı da kaynak klasörle açılmaz."""
    kaynak = tmp_path / "web"
    kaynak.mkdir()
    (kaynak / "index.html").write_text("kaynak", encoding="utf-8")
    monkeypatch.setattr(tarayici, "web_kaynak_kok", lambda: kaynak)
    monkeypatch.setattr(tarayici, "derlenmis_kok", lambda: kaynak / "dist")
    with pytest.raises(FileNotFoundError, match="DERLENMEMİŞ"):
        tarayici.sunucu_baslat("127.0.0.1", 0)


# ------------------------------------------------------------------ süpervizör
def test_tarayici_kapaninca_yeniden_baslatma_ve_sinir(monkeypatch, capsys) -> None:
    """`/bin/true` hemen kapanır: yeniden başlatma sınırı aşılırsa vazgeçilir (sonsuz döngü yok)."""
    monkeypatch.setattr(config, "TARAYICI_PROFIL_KLASORU", ".tarayici-profil-test")
    try:
        kod = tarayici.baslat("C1", tarayici="/bin/true", port=0, yeniden_baslat_s=0)
        assert kod == 0  # tek çalıştırma, yeniden başlatma kapalı
        # yeniden başlatma açık + deneme sınırı 0 → ilk kapanışta durur
        kod = tarayici.baslat("C1", tarayici="/bin/true", port=0, yeniden_baslat_s=0, deneme_siniri=0)
        assert kod == 0
    finally:
        import shutil
        from pathlib import Path

        yol = Path(__file__).resolve().parent.parent / ".tarayici-profil-test"
        shutil.rmtree(yol, ignore_errors=True)


def test_tarayici_yoksa_hata_kodu(capsys) -> None:
    kod = tarayici.baslat("C1", tarayici="/yok/boyle/bir/tarayici", port=0)
    assert kod == 2
