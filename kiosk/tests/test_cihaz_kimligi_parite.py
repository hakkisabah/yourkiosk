"""Cihaz kimliği normalizasyonu: yayıncı ile panel AYNI kuralı uygulamak zorunda.

NEDEN: kalp atışı konusunu yayıncı (`core/push.py: durum_kimligi`) üretir, panel de gelen konudan
kimliği çıkarıp match.json'daki cihazla eşleştirir. İki taraf farklı normalleştirirse veri gelir
ama eşleşme tutmaz: cihaz panelde sonsuza kadar "bilinmiyor" görünür (sessiz arıza, 28 Ekim i5
bulgusu — panel ham `İZMİR 01` ile arıyordu, yayıncı `ZM-R-01` yazıyordu).

KİLİT: örnek tablo TEK dosyada (`panel/src/domain/cihazKimligi.ornekler.json`). Aynı tabloyu
`panel/src/domain/cihazIzleme.test.ts` de okuyup `cihazKimligi()` için doğrular. Kuralı bir tarafta
değiştiren diğer tarafı da değiştirmek zorunda; aksi hâlde iki test birden kırmızı olur.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[2]
ORNEKLER = KOK / "panel" / "src" / "domain" / "cihazKimligi.ornekler.json"
PANEL_KAYNAK = KOK / "panel" / "src" / "domain" / "cihazIzleme.ts"


def _ornekler() -> list[dict[str, str]]:
    if not ORNEKLER.exists():  # yalnız kiosk ağacı kopyalanmış ortam
        pytest.skip(f"ortak örnek tablosu yok: {ORNEKLER}")
    return json.loads(ORNEKLER.read_text(encoding="utf-8"))["ornekler"]


def test_yayinci_ortak_tabloyla_ayni_sonucu_uretir() -> None:
    from core import push

    hatalar = []
    for ornek in _ornekler():
        ham, beklenen = ornek["ham"], ornek["beklenen"]
        elde = push.durum_kimligi(ham)
        # Yayıncı boş kimlikte "bilinmeyen"e düşer (konu boş kalmasın); panel boş bırakır
        # (eşleşmesin). Sözleşme: BOŞ OLMAYAN her girdide çıktı birebir aynı.
        if beklenen == "":
            assert elde == "bilinmeyen", f"{ham!r} → {elde!r} (beklenen 'bilinmeyen')"
            continue
        if elde != beklenen:
            hatalar.append(f"{ham!r}: yayıncı {elde!r} ≠ tablo {beklenen!r}")
    assert not hatalar, "normalizasyon sözleşmesi kaydı:\n" + "\n".join(hatalar)


def test_panel_kurali_kaynakta_duruyor() -> None:
    """Panel tarafı silinirse/tökezlenirse kilit sessizce boşa düşmesin."""
    if not PANEL_KAYNAK.exists():
        pytest.skip(f"panel ağacı yok: {PANEL_KAYNAK}")
    kaynak = PANEL_KAYNAK.read_text(encoding="utf-8")
    assert "export function cihazKimligi" in kaynak, "panel normalizasyon işlevi kaldırılmış"
    assert "[^A-Za-z0-9_-]" in kaynak, "panel karakter kuralı değişmiş (yayıncıyla ayrışır)"
    assert "AZAMI_DURUM_KIMLIK = 40" in kaynak, "panel uzunluk sınırı 40 değil"


def test_panel_ham_kimlikle_aramaz() -> None:
    """Asıl arıza buydu: görünüm ham kimlikle haritaya bakıyordu."""
    if not PANEL_KAYNAK.exists():
        pytest.skip(f"panel ağacı yok: {PANEL_KAYNAK}")
    izleme = PANEL_KAYNAK.read_text(encoding="utf-8")
    assert "durumlar.get(cihazKimligi(cihaz))" in izleme, "izlemeOzeti ham kimlikle arıyor"

    gorunum = KOK / "panel" / "src" / "views" / "CihazlarView.vue"
    if not gorunum.exists():
        pytest.skip(f"görünüm yok: {gorunum}")
    metin = gorunum.read_text(encoding="utf-8")
    assert "durumlar.value.get(cihazKimligi(cihaz))" in metin, "CihazlarView ham kimlikle arıyor"
    assert "durumlar.value.get(cihaz)" not in metin, "CihazlarView'de normalleştirilmemiş arama kaldı"
