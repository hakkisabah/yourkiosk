"""`contentUrl` belge/kod tutarlılığı — i5 bulgusu 5 (ikinci yarısı).

ÖLÇÜLEN: panel `contentUrl` alanı SALT-OKUNUR (`panel/src/views/VeriView.vue` — yayın tablosunda
düz metin, düzenleme iletişim kutusu yalnız HEDEFLEME alanlarını bağlar) ama üç yerde operatöre
"adresi panelde `contentUrl` alanına yazın" deniyordu:

  · `deploy/gorseller-yukle.sh` başlığı + betiğin ÇIKTISI (operatör çıktıyı birebir izler),
  · `docs/GORSEL-MIMARISI.md` §5 ("bugün panel yalnız adres yazıyor" — yanlış),
  · `deploy/README.md` §2.5 (head'de düzeltildi; bu test geri gelmesini engeller).

Düzeltme #88 (panelde adres düzenleme) birleşene kadar geçerli kural: panelde giriş ÖNERİLMEZ,
adres veri dosyasına araçla yazılır. #88 birleşince VeriView'de `contentUrl`e bağlı bir girdi
(`v-model`) görünür → bu testlerin ilk bölümü kendiliğinden gevşer, belge tarafı da güncellenir.

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


def test_panelde_contenturl_girdisi_yok():
    """Ön koşul: VeriView `contentUrl`e YAZMIYOR (v-model/input yok) — belge kuralı buna dayanır."""
    metin = VERIVIEW.read_text(encoding="utf-8")
    assert "contentUrl" in metin, "VeriView contentUrl göstermiyor (test varsayımı geçersiz)"
    for satir in metin.splitlines():
        if "contentUrl" not in satir:
            continue
        assert "v-model" not in satir, f"contentUrl artık bağlanıyor gibi: {satir.strip()}"
        assert "<input" not in satir and "<v-text-field" not in satir, satir.strip()


# --- 2) belgeler/betikler panelde giriş önermemeli -------------------------------


@pytest.mark.parametrize("belge", BELGELER, ids=[b.name for b in BELGELER])
def test_belgeler_panelde_contenturl_girisi_onermez(belge: Path):
    """Yönlendirme satırının YANINDA (≤3 satır) salt-okunur uyarısı olmalı.

    Dosya düzeyinde arama yetmez: uyarı dosyanın başka yerinde dururken eski yanlış adım geri
    gelebiliyordu (mutasyon 5a/5b bunu yakaladı). Bu yüzden pencere satır bazında denetlenir.
    """
    satirlar = belge.read_text(encoding="utf-8").splitlines()
    hatalar: list[str] = []
    for i, satir in enumerate(satirlar):
        if "contentUrl" not in satir or SALT_OKUNUR.search(satir) or not YONLENDIRME.search(satir):
            continue
        pencere = "\n".join(satirlar[i:i + 3])
        if not SALT_OKUNUR.search(pencere):
            hatalar.append(f"{belge.name}:{i + 1}: {satir.strip()}")
    assert not hatalar, (
        "panelde contentUrl girisi oneriliyor, yaninda SALT-OKUNUR uyarisi yok:\n  "
        + "\n  ".join(hatalar)
    )
    if any("contentUrl" in s for s in satirlar):
        # Panel düzenlemesi #88'e ertelendiği her yerde atıf görünür olmalı.
        assert "#88" in "\n".join(satirlar) or not any(YONLENDIRME.search(s) for s in satirlar), (
            f"{belge.name}: contentUrl yonlendirmesi var ama #88 atfi yok"
        )


def test_gorseller_yukle_ciktisi_veri_dosyasi_yolunu_gosterir():
    """Betiğin ÇIKTISI (operatörün birebir izlediği metin) panelde alan doldurmayı söylememeli."""
    metin = (DEPO / "deploy" / "gorseller-yukle.sh").read_text(encoding="utf-8")
    assert "contentUrl alanı:" not in metin, "eski 'panelde contentUrl alanı:' yönlendirmesi geri gelmiş"
    assert "=== panelde yapılacak" not in metin, "eski 'panelde yapılacak' bloğu geri gelmiş"
    assert "gorsel_webp.py --veri" in metin, "çıktı, çalışan (veri dosyası) yolunu göstermiyor"
    assert SALT_OKUNUR.search(metin), "çıktı contentUrl'in salt-okunur olduğunu söylemiyor"


def test_gorsel_mimarisi_panelde_adres_yazildigini_iddia_etmez():
    metin = (DEPO / "docs" / "GORSEL-MIMARISI.md").read_text(encoding="utf-8")
    assert "panel yalnız **adres** yazıyor" not in metin, "panelde adres yazıldığı iddiası geri gelmiş"
    assert SALT_OKUNUR.search(metin), "görsel mimarisi belgesi salt-okunur gerçeğini yazmıyor"


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
