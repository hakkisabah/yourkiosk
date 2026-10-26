"""Yayın görseli okuma SIRASI tek olmalı: `contentUrl` önce, `contentURL` yedek.

NEDEN: 25 Ekim i3 bulgusu — `pharmacy_app.py` gösterim yolu `contentURL`ü `contentUrl`den ÖNCE
okuyordu; `data_handler.py` ve `tarayici.py` ters sırada okuyordu. İki alan çeliştiğinde Qt ekranı
ile tarayıcı modu farklı görsel gösterir; panelin "kaydettim ama eskisi görünüyor" şikâyeti buradan
beslenir. Test, üç tüketicinin de aynı sırayı kullandığını kilitler.
"""

from __future__ import annotations

from pathlib import Path

KIOSK = Path(__file__).resolve().parents[1]

#: Görsel adresini okuyan tüketiciler (yeni bir tüketici eklersen buraya da ekle).
TUKETICILER = (
    "core/data_handler.py",
    "core/tarayici.py",
    "pharmacy_app.py",
)


def _satirlar(ad: str) -> list[str]:
    return (KIOSK / ad).read_text(encoding="utf-8").splitlines()


def test_gorsel_adresi_ayni_sirada_okunur():
    """Her tüketici `y.get("contentUrl") or y.get("contentURL")` biçimini kullanmalı."""
    dogru = 'y.get("contentUrl") or y.get("contentURL")'
    ters = 'y.get("contentURL") or y.get("contentUrl")'
    eksik: list[str] = []
    for ad in TUKETICILER:
        metin = "\n".join(_satirlar(ad))
        if dogru not in metin:
            eksik.append(f"{ad}: doğru sıra ({dogru}) bulunamadı")
        if ters in metin:
            eksik.append(f"{ad}: TERS sıra ({ters}) — contentURL önce okunuyor")
    assert not eksik, "görsel okuma sırası tutarsız:\n" + "\n".join(eksik)


def test_qt_url_okumaz_tarayici_okur_iddiasi_dogru() -> None:
    """26 Ekim i5 bulgusu: "cihaz `url` alanını HİÇ okumaz" iddiası YANLIŞTI.

    Qt tüketicileri `contentUrl → contentURL` okur (`url` okumaz). Tarayıcı modu ise ÜÇ alanı
    okur: `web/src/veri/yayin.ts` → `ADRES_ALANLARI = ['contentUrl', 'contentURL', 'url']`.
    Belge/kod yorumu bu gerçeği yazmak zorunda; `gorsel` alanı hiçbir tüketicide okunmaz.
    """
    for ad in TUKETICILER:
        for no, satir in enumerate(_satirlar(ad), 1):
            if 'get("url")' in satir or "get('url')" in satir:
                raise AssertionError(f"{ad}:{no}: Qt `url` alanını okumamalı — {satir.strip()[:120]}")

    web = (KIOSK.parent / "web" / "src" / "veri" / "yayin.ts").read_text(encoding="utf-8")
    assert "const ADRES_ALANLARI = ['contentUrl', 'contentURL', 'url'] as const" in web, (
        "tarayıcı modu adres alanları/sırası değişmiş — belge ve panel buna göre güncellenmeli"
    )

    belge = (KIOSK.parent / "docs" / "GORSEL-MIMARISI.md").read_text(encoding="utf-8")
    assert "url` ve `gorsel`\n  alanlarını HİÇ okumaz" not in belge, (
        "belge hâlâ 'cihaz url okumaz' diyor (yanlış: tarayıcı modu okur)"
    )
    assert "Tarayıcı modu" in belge and "contentURL → url" in belge, (
        "belge tarayıcı modunun üç alanı okuduğunu yazmıyor"
    )


def test_repoda_yeni_bir_gorsel_tuketicisi_sessizce_eklenemez() -> None:
    """Tüketici listesi elle tutuluyor; `contentUrl` okuyan YENİ bir dosya sessizce eklenemez.

    Tarama `url` sözcüğüne değil `contentUrl` alanına bakar: önbellek kodundaki `kayit["url"]`
    önbellek anahtarıdır, yayın görseli tüketicisi değildir (yanlış kırmızı üretmemeli).
    """
    izinli = set(TUKETICILER) | {
        "core/model.py",          # alias normalizasyonu (değer okumaz)
        "core/yayin_kapsam.py",   # kapsam/hedefleme, adres okumaz
        "tools/ornek_veri.py",    # örnek veri üretici
    }
    bulunan: list[str] = []
    for yol in KIOSK.rglob("*.py"):
        goreli = str(yol.relative_to(KIOSK))
        if "tests/" in goreli or goreli in izinli:
            continue
        if "contentUrl" in yol.read_text(encoding="utf-8"):
            bulunan.append(goreli)
    assert not bulunan, (
        "yeni görsel tüketicisi(leri): " + ", ".join(sorted(bulunan))
        + " — TUKETICILER listesine ekleyin ve `contentUrl ?? contentURL` sırasını uygulayın"
    )
