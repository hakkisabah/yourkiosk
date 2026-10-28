"""Belgedeki sayılar koddaki sayılarla aynı mı? (27 Ekim i5 bulgusu #4)

NEDEN: `deploy/mosquitto/KURULUM.md` `max_queued_messages 5` diyordu, `kur.sh` ise `50`
yazıyordu; `max_connections` tavanları belgede hiç yoktu. Operatör belgeye güvenip
"kuyruk 5" diye plan yapıyor, gerçek kurulum ise 50 ile çalışıyordu. Belge ile kod
ayrıştığında hatayı kimse görmez (ikisi de "doğru" görünür) — bu yüzden makine denetler.

KAPSAM: kur.sh'ın yazdığı mosquitto anahtarları. Belge bir anahtardan söz ediyorsa
değeri kur.sh'taki değerlerden biri olmak zorunda; hiç söz etmiyorsa bu test susar
(eksik belge ayrı bir iştir, yanlış belge bu testin konusudur).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
KUR_SH = KOK.parent / "deploy" / "mosquitto" / "kur.sh"
BELGE = KOK.parent / "deploy" / "mosquitto" / "KURULUM.md"

#: kur.sh içinde `anahtar değer` olarak yazılan mosquitto ayarları
ANAHTARLAR = (
    "message_size_limit",
    "max_queued_messages",
    "max_inflight_messages",
    "max_connections",
    "persistence",
)


@pytest.mark.skipif(not KUR_SH.exists() or not BELGE.exists(), reason="deploy/mosquitto yok")
def test_belgedeki_mosquitto_degerleri_kur_sh_ile_ayni() -> None:
    kod = KUR_SH.read_text(encoding="utf-8")
    belge = BELGE.read_text(encoding="utf-8")

    kodda: dict[str, set[str]] = {}
    for anahtar in ANAHTARLAR:
        kodda[anahtar] = {
            m.group(1)
            for m in re.finditer(rf"^\s*{anahtar}\s+(\S+)\s*$", kod, re.MULTILINE)
        }

    uyusmazlik: list[str] = []
    for anahtar in ANAHTARLAR:
        belgede = re.findall(rf"`{anahtar}\s+([^`\s]+)", belge)
        if not belgede or not kodda[anahtar]:
            continue
        for deger in belgede:
            if deger not in kodda[anahtar]:
                uyusmazlik.append(
                    f"{anahtar}: belge {deger!r} diyor, kur.sh {sorted(kodda[anahtar])} yazıyor"
                )

    assert not uyusmazlik, "KURULUM.md ile kur.sh ayrıştı:\n  " + "\n  ".join(uyusmazlik)


@pytest.mark.skipif(not KUR_SH.exists() or not BELGE.exists(), reason="deploy/mosquitto yok")
def test_belge_tavanları_anlatıyor() -> None:
    """Kuyruk/bağlantı tavanları belgede HİÇ yoksa operatör ayarı göremez (i5 bulgusu)."""
    belge = BELGE.read_text(encoding="utf-8")
    eksik = [a for a in ("max_queued_messages", "max_connections") if a not in belge]
    assert not eksik, f"KURULUM.md bu tavanlardan söz etmiyor: {eksik}"
