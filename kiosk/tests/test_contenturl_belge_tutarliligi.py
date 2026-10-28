"""`contentUrl` belge/kod tutarlılığı — i5 bulgusu 5 (ikinci yarısı).

ÖLÇÜLEN: panel `contentUrl` alanı SALT-OKUNUR (`panel/src/views/VeriView.vue` — yayın tablosunda
düz metin, düzenleme iletişim kutusu yalnız HEDEFLEME alanlarını bağlar) ama üç yerde operatöre
"adresi panelde `contentUrl` alanına yazın" deniyordu:

  · `deploy/gorseller-yukle.sh` başlığı + betiğin ÇIKTISI (operatör çıktıyı birebir izler),
  · `docs/GORSEL-MIMARISI.md` §5 ("bugün panel yalnız adres yazıyor" — yanlış),
  · `deploy/README.md` §2.5 (head'de düzeltildi; bu test geri gelmesini engeller).

Düzeltme: #88 BİRLEŞTİ → panel `contentUrl`i düzenleyebiliyor (`VeriView` → "Görsel adresi
(contentUrl)", `v-model="gorselUrl"`). Bu yüzden belgelerdeki "panelden giremezsiniz / SALT-OKUNUR"
metinleri yanlıştı ve kaldırıldı; testler artık TERSİNİ kilitler: panel alanı var olmalı ve her
belge onun ADINI vermeli. Toplu geçiş yolu (`gorsel_webp.py --veri --yaz`) alternatif olarak kalır.

İkinci yarı: `gorsel_webp.py --veri --yaz` üretilen WebP baytlarını bir klasöre YAZMAZSA veri
dosyasındaki yeni adresler S3'te var olmayan nesnelere işaret eder (cihaz 404 → boş ekran).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

DEPO = Path(__file__).resolve().parents[2]
KIOSK = DEPO / "kiosk"
VERIVIEW = DEPO / "panel" / "src" / "views" / "VeriView.vue"

BELGELER = (
    DEPO / "deploy" / "README.md",
    DEPO / "deploy" / "gorseller-yukle.sh",
    DEPO / "deploy" / "CANLIYA-GECIS.md",
    DEPO / "docs" / "GORSEL-MIMARISI.md",
)

#: "şu alana yaz" anlamına gelen kalıplar (alan adı contentUrl olan satırlarda aranır).
YONLENDIRME = re.compile(
    r"(alan[ıi]na\s+yaz|alan[ıi]\s*:|panelde[^\n]{0,60}yaz|→\s*Kaydet)",
    re.IGNORECASE,
)
SALT_OKUNUR = re.compile(r"SALT-OKUNUR|salt-okunur", re.IGNORECASE)

sys.path.insert(0, str(KIOSK))
from tools import gorsel_webp as gw  # noqa: E402

BELGE = {
    "Yayinlar": {
        "1": {"contentUrl": "https://eski.example/afis.png", "start": "2026-10-25"},
        "2": {"contentURL": "https://eski.example/logo.jpg"},
    }
}


# --- 1) panel gerçekten salt-okunur mu? -----------------------------------------


def test_panelde_contenturl_girdisi_var():
    """#88 birleşti: panel `contentUrl`i DÜZENLEYEBİLİR (görsel adresi alanı bağlı).

    Belge kuralı buna dayanır: "adresi panelden giremezsiniz" cümlesi artık yanlıştır ve
    geri gelirse bu test kırmızı olur.
    """
    metin = VERIVIEW.read_text(encoding="utf-8")
    assert "contentUrl" in metin, "VeriView contentUrl göstermiyor (test varsayımı geçersiz)"
    assert "v-model=\"gorselUrl\"" in metin, "contentUrl girişi (v-model) kaldırılmış (işlev geriledi)"
    assert "Görsel adresi (contentUrl)" in metin, "alan etiketi kaldırılmış"


# --- 2) belgeler/betikler panel alanını göstermeli --------------------------------


@pytest.mark.parametrize("belge", BELGELER, ids=[b.name for b in BELGELER])
def test_belgeler_yanlis_salt_okunur_iddiasini_yazmaz(belge: Path):
    """Panel artık düzenlenebilir: "SALT-OKUNUR / panelden giremezsiniz" YANLIŞ bilgidir."""
    kacak = [f"{belge.name}:{i}" for i, satir in enumerate(
        belge.read_text(encoding="utf-8").splitlines(), 1)
        if "contentUrl" in satir and SALT_OKUNUR.search(satir)]
    assert not kacak, (
        "contentUrl hâlâ SALT-OKUNUR diye anlatılıyor (#88 birleşti): " + ", ".join(kacak))


@pytest.mark.parametrize("belge", BELGELER, ids=[b.name for b in BELGELER])
def test_belgeler_panel_alanini_gosterir(belge: Path):
    """contentUrl'den söz eden her belge paneldeki alanın ADINI vermeli (uygulanabilir adım)."""
    metin = belge.read_text(encoding="utf-8")
    if "contentUrl" not in metin:
        pytest.skip(f"{belge.name}: contentUrl geçmiyor")
    assert "Görsel adresi (contentUrl)" in metin or "Nöbet ve Yayınlar" in metin, (
        f"{belge.name}: panelde hangi alana yazılacağı yazmıyor")


def test_gorseller_yukle_ciktisi_iki_yolu_da_gosterir():
    """Betiğin ÇIKTISI (operatörün birebir izlediği metin) panel alanını ve toplu yolu göstermeli."""
    metin = (DEPO / "deploy" / "gorseller-yukle.sh").read_text(encoding="utf-8")
    assert "Görsel adresi (contentUrl)" in metin, "çıktı paneldeki alanı göstermiyor"
    assert "gorsel_webp.py --veri" in metin, "çıktı, toplu (veri dosyası) yolu göstermiyor"
    assert "contentUrl alanı:" not in metin


def test_gorsel_mimarisi_panelde_adres_yazildigini_iddia_etmez():
    metin = (DEPO / "docs" / "GORSEL-MIMARISI.md").read_text(encoding="utf-8")
    assert "panel yalnız **adres** yazıyor" not in metin, "panelde adres yazıldığı iddiası geri gelmiş"
    assert "Görsel adresi (contentUrl)" in metin, "görsel mimarisi belgesi panel alanını yazmıyor"


# --- 3) --veri --yaz üretilen WebP'leri gerçekten yazmalı ------------------------


def _govde(yol, *_a, **_k):
    """İçerik adlı çıktı: her kaynak dosya farklı bayt üretir (sha çakışmasın)."""
    return b"webp-" + Path(yol).name.encode(), {"bayt": 1000, "cikti_bayt": 100}


def test_veri_yaz_modu_webp_dosyalarini_varsayilan_klasore_yazar(tmp_path: Path, monkeypatch):
    veri = tmp_path / "lastSystemData.json"
    veri.write_text(json.dumps(BELGE), encoding="utf-8")
    (tmp_path / "afis.png").write_bytes(b"png")
    (tmp_path / "logo.jpg").write_bytes(b"jpg")
    monkeypatch.setattr(gw, "donustur", _govde)
    monkeypatch.setattr(gw, "adres_cihaz_kapisindan_gecer", lambda *_a, **_k: (True, ""))

    sonuc = gw.veri_dosyasini_optimize(veri, [tmp_path], "https://yeni/yayin-gorselleri", yaz=True)

    klasor = Path(sonuc["cikti_klasoru"])
    assert klasor.is_dir(), "--yaz WebP'leri hiçbir klasöre yazmadı (adresler S3'te 404 olur)"
    yazilan = {p.name for p in klasor.glob("*.webp")}
    assert len(yazilan) == 2, f"beklenen 2 WebP, bulunan {sorted(yazilan)}"
    belge = json.loads(veri.read_text(encoding="utf-8"))
    for kayit in belge["Yayinlar"].values():
        adres = kayit.get("contentUrl") or kayit.get("contentURL")
        assert adres.rsplit("/", 1)[1] in yazilan, f"adres yazılmayan dosyaya işaret ediyor: {adres}"


def test_kuru_calismada_webp_klasoru_olusturulmaz(tmp_path: Path, monkeypatch):
    """Kuru çalışma dosya sistemine HİÇ yazmamalı (v0.1 sözleşmesi korunur)."""
    veri = tmp_path / "lastSystemData.json"
    veri.write_text(json.dumps(BELGE), encoding="utf-8")
    (tmp_path / "afis.png").write_bytes(b"png")
    monkeypatch.setattr(gw, "donustur", _govde)
    monkeypatch.setattr(gw, "adres_cihaz_kapisindan_gecer", lambda *_a, **_k: (True, ""))

    sonuc = gw.veri_dosyasini_optimize(veri, [tmp_path], "https://yeni/yayin-gorselleri", yaz=False)

    assert sonuc["cikti_klasoru"] is None
    assert not (tmp_path / "yayin-gorselleri").exists(), "kuru çalışma klasör oluşturdu"
