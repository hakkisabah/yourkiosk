"""ZAMAN DAMGASI KARŞILAŞTIRMA — tek kural kaynağı (saat dilimi farkını doğru ele alır).

GERÇEK SORUN (i5 bulgusu, PR #78): panel tetikleyicisini **UTC** yazıyor
(`new Date().toISOString()` → `2026-10-24T22:25:00.000Z`), cihazın yerel tetikleyicisi (MQTT push →
`core/tetik.yaz`) ise **yerel saat** (`datetime.now().isoformat()` → `2026-10-25T01:25:00`, uzantısız).
`durum.secili_tetik` bu iki metni sözlüksel karşılaştırıyordu: cihaz saati UTC+3 olduğu için yerel
damga HER ZAMAN 3 saat ileri görünüyor, panelin DAHA YENİ tetiği "eski" sayılıp seçilmiyordu →
panel "Bildir" cihazda sessizce yutulabiliyordu.

KURAL:
- `Z` / `+03:00` gibi saat dilimi taşıyan damgalar olduğu gibi çözülür,
- saat dilimi TAŞIMAYAN damgalar cihazın YEREL saati sayılır (yerel tetikleyici böyle yazılır),
- `2026-10-24 09:11:58` (panel `lastupdate` biçimi) de kabul edilir,
- ikisinden biri çözülemezse `None` döner → çağıran eski (sözlüksel) davranışa düşer.
"""

from __future__ import annotations

import logging
from datetime import datetime

log = logging.getLogger("kiosk.zaman")


def coz(deger: object) -> datetime | None:
    """Damgayı saat dilimi BİLİNEN `datetime`e çevirir (çözülemezse None)."""
    metin = str(deger or "").strip()
    if not metin:
        return None
    # `Z` soneki Python 3.11+ `fromisoformat` ile çözülür; eski sürümler için normalize et.
    if metin.endswith(("Z", "z")):
        metin = metin[:-1] + "+00:00"
    try:
        an = datetime.fromisoformat(metin)
    except ValueError:
        return None
    if an.tzinfo is None:
        # Yerel saat: cihazın kendi saat dilimi (yerel tetikleyici biçimi).
        an = an.astimezone()
    return an


def karsilastir(a: object, b: object) -> int | None:
    """`a` ile `b` anlarını karşılaştırır: a>b → 1, a<b → -1, eşit → 0.

    İkisinden biri çözülemezse `None` (çağıran sözlüksel karşılaştırmaya düşer).
    """
    an_a, an_b = coz(a), coz(b)
    if an_a is None or an_b is None:
        return None
    if an_a > an_b:
        return 1
    if an_a < an_b:
        return -1
    return 0


def yeni_mi(aday: object, mevcut: object) -> bool:
    """`aday` `mevcut`tan DAHA YENİ mi? (çözülemezse sözlüksel karşılaştırma)"""
    sira = karsilastir(aday, mevcut)
    if sira is None:
        return str(aday or "") > str(mevcut or "")
    return sira > 0
