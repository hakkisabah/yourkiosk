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


def test_gorsel_aliaslari_cihazda_okunmuyor_iddiasi_dogru():
    """Belge/kod yorumu 'cihaz url alanını okur' derse yanlış olur: cihaz `url`/`gorsel` okumaz.

    i3 bulgusu: `docs/GORSEL-MIMARISI.md` ve panel yorumu `contentUrl ?? contentURL ?? url`
    diyordu; cihazda `url` hiç okunmuyor (model.py:46'daki alias listesi yalnız normalleştirme).
    """
    for ad in TUKETICILER:
        for no, satir in enumerate(_satirlar(ad), 1):
            if 'get("url")' in satir or "get('url')" in satir:
                raise AssertionError(f"{ad}:{no}: cihaz `url` alanını okumamalı — {satir.strip()[:120]}")
