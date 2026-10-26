"""YAYIN GÖRSELİ OPTİMİZASYONU — `tools/gorsel_webp.py` saf yardımcıları.

Dönüştürme Qt gerektirir; burada ADRES HARİTALAMA ve GERİ YAZMA kuralları kilitlenir
(yanlış yere yazmak, veri dosyasını bozmanın en kolay yoludur).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from tools import gorsel_webp as gw  # noqa: E402

BELGE = {
    "Yayinlar": {
        "1": {"contentUrl": "https://eski.example/afis.png", "start": "2026-10-25"},
        "2": {"contentURL": "https://eski.example/logo.jpg"},
        "3": {"url": "  https://eski.example/bosluklu.webp  "},
        "4": {"contentUrl": ""},          # boş adres → listeye girmez
        "5": {"start": "2026-10-26"},     # görseli yok → listeye girmez
        "6": "metin",                      # kayıt sözlük değil → atlanır
    }
}


def test_adresleri_bul_alan_adlarini_ve_yollari_dogru_verir() -> None:
    bulunan = gw.adresleri_bul(BELGE)
    yollar = [y for y, _ in bulunan]
    assert yollar == ["Yayinlar.1.contentUrl", "Yayinlar.2.contentURL", "Yayinlar.3.url"]
    assert bulunan[2][1] == "https://eski.example/bosluklu.webp", "boşluklar kırpılmalı"


def test_adresleri_bul_yayin_yoksa_bos() -> None:
    assert gw.adresleri_bul({}) == []
    assert gw.adresleri_bul({"Yayinlar": []}) == []
    assert gw.adresleri_bul(None) == []


def test_adresi_degistir_sadece_hedef_alanı_yazar() -> None:
    belge = json.loads(json.dumps(BELGE))
    assert gw.adresi_degistir(belge, "Yayinlar.2.contentURL", "https://yeni/abc.webp") is True
    assert belge["Yayinlar"]["2"]["contentURL"] == "https://yeni/abc.webp"
    assert belge["Yayinlar"]["1"]["contentUrl"] == "https://eski.example/afis.png"
    # olmayan yol → False, belge değişmez
    assert gw.adresi_degistir(belge, "Yayinlar.9.contentUrl", "x") is False
    assert gw.adresi_degistir(belge, "Yok.1.contentUrl", "x") is False


def test_yeni_adres_tabani_normalize_eder() -> None:
    assert gw.yeni_adres("https://cdn.example/yayin-gorselleri/", "a1b2") == "https://cdn.example/yayin-gorselleri/a1b2.webp"
    assert gw.yeni_adres("https://cdn.example/yayin-gorselleri", "a1b2") == "https://cdn.example/yayin-gorselleri/a1b2.webp"


def test_yerel_dosya_sorgu_dizesini_ve_kodlamayi_cozer(tmp_path: Path) -> None:
    (tmp_path / "afis 1.png").write_bytes(b"x")
    assert gw._yerel_dosya("https://e/afis%201.png?x=1", [tmp_path]) == tmp_path / "afis 1.png"
    assert gw._yerel_dosya("https://e/yok.png", [tmp_path]) is None
    assert gw._yerel_dosya("", [tmp_path]) is None


def test_veri_dosyasini_optimize_kuru_calismada_dosyaya_dokunmaz(tmp_path: Path, monkeypatch) -> None:
    """""--yaz" yoksa KURU: veri dosyası bayt bayt aynı kalmalı."""
    veri = tmp_path / "lastSystemData.json"
    veri.write_text(json.dumps(BELGE), encoding="utf-8")
    onceki = veri.read_bytes()
    (tmp_path / "afis.png").write_bytes(b"png")

    # dönüştürmeyi ve ağ kapısını taklit et (Qt/DNS gerekmesin)
    monkeypatch.setattr(gw, "donustur", lambda yol, *_a, **_k: (b"webp", {"bayt": 1000, "cikti_bayt": 100}))
    monkeypatch.setattr(gw, "adres_cihaz_kapisindan_gecer", lambda *_a, **_k: (True, ""))
    sonuc = gw.veri_dosyasini_optimize(veri, [tmp_path], "https://yeni/yayin-gorselleri")
    assert len(sonuc["degisen"]) == 1
    assert sonuc["yazildi"] is False
    assert veri.read_bytes() == onceki, "kuru çalışmada veri dosyası değişmemeli"


def test_veri_dosyasini_optimize_yazinca_yedek_alir(tmp_path: Path, monkeypatch) -> None:
    veri = tmp_path / "lastSystemData.json"
    veri.write_text(json.dumps(BELGE), encoding="utf-8")
    (tmp_path / "afis.png").write_bytes(b"png")
    monkeypatch.setattr(gw, "donustur", lambda yol, *_a, **_k: (b"webp", {"bayt": 1000, "cikti_bayt": 100}))
    monkeypatch.setattr(gw, "adres_cihaz_kapisindan_gecer", lambda *_a, **_k: (True, ""))

    sonuc = gw.veri_dosyasini_optimize(veri, [tmp_path], "https://yeni/yayin-gorselleri/", yaz=True)
    assert sonuc["yazildi"] is True
    assert Path(sonuc["yedek"]).is_file(), "yedek alınmalı"
    yeni = json.loads(veri.read_text(encoding="utf-8"))
    yeni_adres = yeni["Yayinlar"]["1"]["contentUrl"]
    assert yeni_adres.startswith("https://yeni/yayin-gorselleri/") and yeni_adres.endswith(".webp")
    # dokunulmayan alanlar korunur
    assert yeni["Yayinlar"]["1"]["start"] == "2026-10-25"
    assert yeni["Yayinlar"]["5"] == {"start": "2026-10-26"}


# --- i5 bulgusu 6: öngörülebilir /tmp yolu (sembolik bağ) -------------------------

def test_gecici_webp_dosyasi_tahmin_edilemez_ve_0600(tmp_path: Path) -> None:
    """Bulgu 6: `--s3` geçici dosyası `/tmp/<sha>.webp` sabit yoluna yazılıyordu.

    `/tmp`'ye sembolik bağ kurabilen yerel kullanıcı `aws s3 cp` girdisini başka bir dosyaya
    yönlendirebilirdi. Beklenen: mkstemp ile rastgele ad, 0600 izin, iş bitince silinir.
    """
    import stat as stat_mod

    yol1 = gw.gecici_webp_yaz(b"bir")
    yol2 = gw.gecici_webp_yaz(b"iki")
    try:
        assert yol1 != yol2, "geçici dosya adı tahmin edilebilir/sabit"
        assert yol1.parent != Path("/tmp") or "yourkiosk-gorsel-" in yol1.name
        assert stat_mod.S_IMODE(yol1.stat().st_mode) == 0o600, "geçici dosya 0600 değil"
        assert yol1.read_bytes() == b"bir"
    finally:
        yol1.unlink(missing_ok=True)
        yol2.unlink(missing_ok=True)

    kaynak = (KOK / "tools" / "gorsel_webp.py").read_text(encoding="utf-8")
    assert 'Path(f"/tmp/{anahtar}.webp")' not in kaynak, "sabit /tmp yolu geri gelmiş"
    assert "mkstemp" in kaynak, "mkstemp kullanılmıyor"


# --- i5 bulgusu 7: üretilen adres cihazın görsel kapısından geçmeli ---------------

def test_adres_kapisi_http_ve_ozel_hostu_reddeder() -> None:
    uygun, neden = gw.adres_cihaz_kapisindan_gecer("http://cdn.example/a.webp")
    assert uygun is False and "https" in neden.lower(), neden

    # 127.0.0.1 DNS'siz çözümlenir → ağ kapısı özel adresi reddeder (SSRF)
    uygun, neden = gw.adres_cihaz_kapisindan_gecer("https://127.0.0.1/a.webp")
    assert uygun is False, neden


def test_veri_yaz_modu_kapidan_gecmeyen_adresi_yazmaz(tmp_path: Path, monkeypatch) -> None:
    """Bulgu 7: `--veri --yaz` cihazın reddedeceği adresi veri dosyasına yazıyordu."""
    veri = tmp_path / "lastSystemData.json"
    veri.write_text(json.dumps(BELGE), encoding="utf-8")
    onceki = veri.read_bytes()
    (tmp_path / "afis.png").write_bytes(b"png")
    monkeypatch.setattr(gw, "donustur", lambda yol, *_a, **_k: (b"webp", {"bayt": 1000, "cikti_bayt": 100}))

    sonuc = gw.veri_dosyasini_optimize(veri, [tmp_path], "http://eski-sunucu/yayin-gorselleri", yaz=True)

    assert sonuc["degisen"] == [], "kapıdan geçmeyen adres 'değişti' sayılmamalı"
    assert len(sonuc["gecersiz"]) == 1
    assert sonuc["yazildi"] is False
    assert veri.read_bytes() == onceki, "kapıdan geçmeyen adres veri dosyasına yazılmış"


def test_cli_kapidan_gecmeyen_adreste_sifir_disi_kod_doner(tmp_path: Path, monkeypatch) -> None:
    """Bulgu 7 (uçtan uca): geçersiz adres → yazma yok, çıkış kodu != 0."""
    veri = tmp_path / "lastSystemData.json"
    veri.write_text(json.dumps(BELGE), encoding="utf-8")
    onceki = veri.read_bytes()
    (tmp_path / "afis.png").write_bytes(b"png")
    monkeypatch.setattr(gw, "donustur", lambda yol, *_a, **_k: (b"webp", {"bayt": 1000, "cikti_bayt": 100}))
    monkeypatch.setattr(
        sys, "argv",
        ["gorsel_webp.py", "--veri", str(veri), "--url-taban", "http://eski-sunucu/g",
         "--klasor", str(tmp_path), "--yaz"],
    )

    kod = gw.main()

    assert kod != 0, "geçersiz adreste araç başarı döndürdü"
    assert veri.read_bytes() == onceki, "geçersiz adres yazılmış"
