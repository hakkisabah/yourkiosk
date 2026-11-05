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
#:
#: İki tür kilit var (27 Ekim i5 bulgusu: `tools/gorsel_webp.py` `contentUrl` okuyordu ama
#: bekçiye kayıtlı değildi → testi düşürüyordu; "yeni tüketici" listesi gerçeği anlatmıyordu):
#:   "sira"          → Qt okuyucu; `y.get("contentUrl") or y.get("contentURL")` sırası zorunlu.
#:   "alan_listesi"  → toplu işleyici; `YAYIN_ALANLARI` demetinde `contentUrl` İLK olmalı
#:                     (ilk eşleşen alan yazılır, sıra bozulursa yedek alan ezilir).
TUKETICILER: dict[str, str] = {
    "core/data_handler.py": "sira",
    "core/tarayici.py": "sira",
    "pharmacy_app.py": "sira",
    "tools/gorsel_webp.py": "alan_listesi",
}


def _satirlar(ad: str) -> list[str]:
    return (KIOSK / ad).read_text(encoding="utf-8").splitlines()


def _sira_tuketicileri() -> list[str]:
    return [ad for ad, kilit in TUKETICILER.items() if kilit == "sira"]


def _alan_listesi_tuketicileri() -> list[str]:
    return [ad for ad, kilit in TUKETICILER.items() if kilit == "alan_listesi"]


def test_gorsel_adresi_ayni_sirada_okunur():
    """Her Qt tüketicisi `y.get("contentUrl") or y.get("contentURL")` biçimini kullanmalı."""
    dogru = 'y.get("contentUrl") or y.get("contentURL")'
    ters = 'y.get("contentURL") or y.get("contentUrl")'
    eksik: list[str] = []
    for ad in _sira_tuketicileri():
        metin = "\n".join(_satirlar(ad))
        if dogru not in metin:
            eksik.append(f"{ad}: doğru sıra ({dogru}) bulunamadı")
        if ters in metin:
            eksik.append(f"{ad}: TERS sıra ({ters}) — contentURL önce okunuyor")
    assert not eksik, "görsel okuma sırası tutarsız:\n" + "\n".join(eksik)


def test_toplu_isleyicide_contenturl_ilk_alan() -> None:
    """`tools/gorsel_webp.py` adresleri YENİDEN YAZAR: ilk eşleşen alan kazanır.

    `YAYIN_ALANLARI` demetinde `contentUrl` ilk olmazsa yedek alan (`contentURL`) önce
    bulunur ve panelin yazdığı asıl alan güncellenmeden kalır (27 Ekim i5 bulgusu: bu
    tüketici bekçiye kayıtlı değildi).
    """
    import ast

    for ad in _alan_listesi_tuketicileri():
        agac = ast.parse("\n".join(_satirlar(ad)))
        demet = None
        for dugum in agac.body:
            if isinstance(dugum, ast.Assign) and any(
                isinstance(h, ast.Name) and h.id == "YAYIN_ALANLARI" for h in dugum.targets
            ):
                demet = ast.literal_eval(dugum.value)
        assert demet is not None, f"{ad}: YAYIN_ALANLARI bulunamadı"
        assert demet[0] == "contentUrl", (
            f"{ad}: YAYIN_ALANLARI[0] 'contentUrl' olmalı, bulunan: {demet!r}"
        )
        assert demet.index("contentUrl") < demet.index("contentURL"), (
            f"{ad}: contentUrl, contentURL'den ÖNCE gelmeli — {demet!r}"
        )


def test_qt_url_okumaz_tarayici_okur_iddiasi_dogru() -> None:
    """26 Ekim i5 bulgusu: "cihaz `url` alanını HİÇ okumaz" iddiası YANLIŞTI.

    Qt tüketicileri `contentUrl → contentURL` okur (`url` okumaz). Tarayıcı modu ise ÜÇ alanı
    okur: `web/src/veri/yayin.ts` → `ADRES_ALANLARI = ['contentUrl', 'contentURL', 'url']`.
    Belge/kod yorumu bu gerçeği yazmak zorunda; `gorsel` alanı hiçbir tüketicide okunmaz.
    """
    for ad in _sira_tuketicileri():
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
