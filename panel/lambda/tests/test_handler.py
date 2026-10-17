"""Lambda modu testleri (Cognito'suz panel): şifre, oturum cookie'si ve imzalı S3 erişimi.

Çalıştırma:
    cd panel/lambda && python3 -m pytest tests -q
(boto3 gerekir; S3 çağrısı testte taklit edilir, AWS'ye çıkılmaz.)
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import handler  # noqa: E402

SIFRE = "dogru-sifre-123"
ORIGIN = "https://panel.example.com"


@pytest.fixture(autouse=True)
def ortam(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KOVA_ADI", "test-kova")
    monkeypatch.setenv("ON_EK", "kiosk")
    monkeypatch.setenv("OTURUM_ANAHTARI", "x" * 40)
    monkeypatch.setenv("PANEL_ORIGIN", ORIGIN)
    monkeypatch.setenv("PANEL_SIFRE_OZETI", handler.sifre_ozeti_uret(SIFRE, iterasyon=1000))
    handler._denemeler.clear()
    yield
    handler._denemeler.clear()


class SahteS3:
    """generate_presigned_url çağrılarını kaydeder (AWS'ye çıkılmaz)."""

    def __init__(self) -> None:
        self.cagrilar: list[tuple[str, dict]] = []

    def generate_presigned_url(self, islem: str, Params: dict, ExpiresIn: int) -> str:
        self.cagrilar.append((islem, {**Params, "ExpiresIn": ExpiresIn}))
        return f"https://s3.example/{islem}?imza=test"


@pytest.fixture()
def sahte_s3(monkeypatch: pytest.MonkeyPatch) -> SahteS3:
    s3 = SahteS3()
    monkeypatch.setattr(handler, "s3_istemcisi", lambda: s3)
    return s3


def olay(
    yol: str,
    veri: dict | None = None,
    *,
    cookie: str | None = None,
    origin: str | None = ORIGIN,
    yontem: str = "POST",
) -> dict:
    basliklar: dict[str, str] = {}
    if origin:
        basliklar["origin"] = origin
    if cookie:
        basliklar["cookie"] = f"{handler.COOKIE_ADI}={cookie}"
    return {
        "rawPath": yol,
        "requestMethod": yontem,
        "headers": basliklar,
        "body": json.dumps(veri) if veri is not None else "",
    }


def govde(yanit: dict) -> dict:
    return json.loads(yanit["body"])


def _giris_yap() -> str:
    """Geçerli bir oturum değeri üretir (gerçek giriş akışıyla)."""
    yanit = handler.lambda_handler(olay("/giris", {"sifre": SIFRE}))
    assert yanit["statusCode"] == 200
    cerez = yanit["headers"]["Set-Cookie"]
    return cerez.split(f"{handler.COOKIE_ADI}=", 1)[1].split(";", 1)[0]


# ------------------------------------------------------------------ şifre özeti
def test_sifre_ozeti_dogrular() -> None:
    ozet = handler.sifre_ozeti_uret(SIFRE, iterasyon=1000)
    assert handler.sifre_dogrula(SIFRE, ozet) is True
    assert handler.sifre_dogrula("yanlis", ozet) is False
    assert ozet.startswith("pbkdf2_sha256$1000$")
    assert SIFRE not in ozet, "şifre özete gömülmemeli"


def test_bozuk_ozet_reddedilir() -> None:
    for bozuk in ("", "duz-metin", "pbkdf2_sha256$abc$def$ghi", "md5$1$2$3"):
        assert handler.sifre_dogrula(SIFRE, bozuk) is False


# ------------------------------------------------------------------ giriş akışı
def test_giris_basarili_cookie_uretir() -> None:
    yanit = handler.lambda_handler(olay("/giris", {"sifre": SIFRE}))
    assert yanit["statusCode"] == 200
    assert govde(yanit)["giris"] is True
    cerez = yanit["headers"]["Set-Cookie"]
    assert "HttpOnly" in cerez and "Secure" in cerez and "SameSite=Lax" in cerez
    assert f"Max-Age={handler.oturum_suresi()}" in cerez


def test_yanlis_sifre_401() -> None:
    yanit = handler.lambda_handler(olay("/giris", {"sifre": "yanlis"}))
    assert yanit["statusCode"] == 401
    assert "Set-Cookie" not in yanit["headers"]


def test_hiz_siniri() -> None:
    for _ in range(handler._GIRIS_DENEME_SINIRI):
        assert handler.lambda_handler(olay("/giris", {"sifre": "yanlis"}))["statusCode"] == 401
    assert handler.lambda_handler(olay("/giris", {"sifre": "yanlis"}))["statusCode"] == 429
    # doğru şifre bile sınır aşıldıysa bekler
    assert handler.lambda_handler(olay("/giris", {"sifre": SIFRE}))["statusCode"] == 429


def test_basarili_giris_deneme_sayacini_sifirlar() -> None:
    for _ in range(3):
        handler.lambda_handler(olay("/giris", {"sifre": "yanlis"}))
    assert handler.lambda_handler(olay("/giris", {"sifre": SIFRE}))["statusCode"] == 200
    assert handler.lambda_handler(olay("/giris", {"sifre": "yanlis"}))["statusCode"] == 401  # 401, 429 değil


# ------------------------------------------------------------------ oturum cookie
def test_oturum_ureticisi_ve_dogrulayicisi() -> None:
    anahtar = "x" * 40
    deger = handler.oturum_uret(an=1_000, sure=60, anahtar=anahtar)
    assert handler.oturum_gecerli(deger, an=1_030, anahtar=anahtar) is True
    assert handler.oturum_gecerli(deger, an=1_100, anahtar=anahtar) is False, "süre dolmalı"


def test_oturum_kurcalanirsa_gecersiz() -> None:
    anahtar = "x" * 40
    deger = handler.oturum_uret(an=1_000, sure=3600, anahtar=anahtar)
    bitis, imza = deger.split(".")
    kurcalanmis = f"{int(bitis) + 99999}.{imza}"  # süreyi uzatmaya çalış
    assert handler.oturum_gecerli(kurcalanmis, an=1_030, anahtar=anahtar) is False
    assert handler.oturum_gecerli(f"{bitis}.{imza[:-2]}xy", an=1_030, anahtar=anahtar) is False
    assert handler.oturum_gecerli("imzasiz-deger", an=1_030, anahtar=anahtar) is False
    assert handler.oturum_gecerli(None, an=1_030, anahtar=anahtar) is False


def test_oturum_kontrol_ucu() -> None:
    assert govde(handler.lambda_handler(olay("/oturum", yontem="GET")))["giris"] is False
    gecerli = handler.lambda_handler(olay("/oturum", cookie=_giris_yap(), yontem="GET"))
    assert govde(gecerli)["giris"] is True


def test_cikis_cerezi_siler() -> None:
    yanit = handler.lambda_handler(olay("/cikis", cookie=_giris_yap()))
    assert yanit["statusCode"] == 200
    assert "Max-Age=0" in yanit["headers"]["Set-Cookie"]


def test_cerez_ayristirma() -> None:
    assert handler.cerezden_oturum("a=1; yk_oturum=abc.def; b=2") == "abc.def"
    assert handler.cerezden_oturum("a=1") is None
    assert handler.cerezden_oturum(None) is None


# ------------------------------------------------------------------ imzalı S3 erişimi
def test_imzala_oturumsuz_401(sahte_s3: SahteS3) -> None:
    yanit = handler.lambda_handler(olay("/imzala", {"dosya": "ayarlar.json", "islem": "oku"}))
    assert yanit["statusCode"] == 401
    assert sahte_s3.cagrilar == []


def test_imzala_okuma_url_dondurur(sahte_s3: SahteS3) -> None:
    yanit = handler.lambda_handler(
        olay("/imzala", {"dosya": "ayarlar.json", "islem": "oku"}, cookie=_giris_yap())
    )
    assert yanit["statusCode"] == 200
    assert govde(yanit)["url"].startswith("https://s3.example/get_object")
    islem, params = sahte_s3.cagrilar[-1]
    assert islem == "get_object"
    assert params["Key"] == "kiosk/ayarlar.json" and params["Bucket"] == "test-kova"
    assert params["ExpiresIn"] <= 600


def test_imzala_etag_ile_kosullu_okuma(sahte_s3: SahteS3) -> None:
    handler.lambda_handler(
        olay(
            "/imzala",
            {"dosya": "lastSystemData.json", "islem": "oku", "etag": '"abc123"'},
            cookie=_giris_yap(),
        )
    )
    _islem, params = sahte_s3.cagrilar[-1]
    assert params["IfMatch"] == '"abc123"'


def test_imzala_yazma_parametreleri(sahte_s3: SahteS3) -> None:
    yanit = handler.lambda_handler(
        olay(
            "/imzala",
            {"dosya": "kapsam-ayarlari.json", "islem": "yaz", "boyut": 1024},
            cookie=_giris_yap(),
        )
    )
    assert yanit["statusCode"] == 200
    islem, params = sahte_s3.cagrilar[-1]
    assert islem == "put_object"
    assert params["ContentType"].startswith("application/json")
    assert params["CacheControl"] == "no-store"


def test_imzala_beyaz_liste_ve_islem_denetimi(sahte_s3: SahteS3) -> None:
    cookie = _giris_yap()
    for istek, aciklama in [
        ({"dosya": "gizli.txt", "islem": "oku"}, "beyaz listede olmayan dosya"),
        ({"dosya": "../ayarlar.json", "islem": "oku"}, "yol kaçışı"),
        ({"dosya": "ayarlar.json", "islem": "sil"}, "izin verilmeyen işlem"),
        ({"dosya": "", "islem": "oku"}, "boş dosya adı"),
    ]:
        yanit = handler.lambda_handler(olay("/imzala", istek, cookie=cookie))
        assert yanit["statusCode"] == 400, aciklama
    assert sahte_s3.cagrilar == [], "geçersiz isteklerde imza üretilmemeli"


def test_imzala_boyut_siniri(sahte_s3: SahteS3) -> None:
    yanit = handler.lambda_handler(
        olay(
            "/imzala",
            {"dosya": "lastSystemData.json", "islem": "yaz", "boyut": handler.MAKS_YAZMA_BAYT + 1},
            cookie=_giris_yap(),
        )
    )
    assert yanit["statusCode"] == 400
    assert "çok büyük" in govde(yanit)["hata"]


def test_nesne_anahtari_onek_uygular() -> None:
    assert handler.nesne_anahtari("ayarlar.json") == "kiosk/ayarlar.json"
    assert handler.nesne_anahtari("/match.json") == "kiosk/match.json"
    with pytest.raises(ValueError):
        handler.nesne_anahtari("baska/bir.json")


# ------------------------------------------------------------------ CORS/CSRF
def test_yabanci_origin_403(sahte_s3: SahteS3) -> None:
    yanit = handler.lambda_handler(
        olay("/imzala", {"dosya": "ayarlar.json", "islem": "oku"}, origin="https://kötü.example")
    )
    assert yanit["statusCode"] == 403


def test_cors_on_kontrolu() -> None:
    yanit = handler.lambda_handler(olay("/giris", yontem="OPTIONS"))
    assert yanit["statusCode"] == 204
    assert yanit["headers"]["Access-Control-Allow-Origin"] == ORIGIN
    assert yanit["headers"]["Access-Control-Allow-Credentials"] == "true"


def test_bilinmeyen_uc_404() -> None:
    assert handler.lambda_handler(olay("/bilinmeyen", {}))["statusCode"] == 404


def test_yanitlarda_onbellek_kapatilir() -> None:
    yanit = handler.lambda_handler(olay("/oturum", yontem="GET"))
    assert yanit["headers"]["Cache-Control"] == "no-store"
    assert yanit["headers"]["X-Content-Type-Options"] == "nosniff"


def test_oturum_suresi_dolunca_imza_verilmez(sahte_s3: SahteS3, monkeypatch: pytest.MonkeyPatch) -> None:
    """Süresi geçmiş cookie ile imzalama denenirse 401 (gerçek zaman kullanılır)."""
    eski = handler.oturum_uret(an=time.time() - 10_000, sure=60)
    yanit = handler.lambda_handler(olay("/imzala", {"dosya": "ayarlar.json", "islem": "oku"}, cookie=eski))
    assert yanit["statusCode"] == 401
