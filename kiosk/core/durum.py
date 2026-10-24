"""`durum.json` — cihazın TEK istekle tüm küçük kontrol bilgilerini alması.

NEDEN: her yoklama turunda 3 ayrı dosya çekiliyordu (`lastupdate.json`, `tetikle.json`,
`komut.json`). 600 cihaz × 300 sn'lik turda bu **~15,5 M istek/ay** (~$18). Tek dosya:
- 1 istek/tur (3× azalma),
- aynı yanıt hem damgayı hem tetikleyiciyi hem komut işaretini taşır.

PANEL YAZAR (`durum.json`):
    {
      "zaman": "2026-10-24T09:12:00Z",          # bu belgenin üretim anı
      "lastupdate": "2026-10-24 09:11:58",       # veri damgası
      "tetik": {"zaman": "...", "ilceId": "", "bolgeId": "", "aciklama": "panel: sistem"},
      "komut": {"zaman": "...", "id": "..."}     # yalnız işaret; gövde ayrı dosyada (nadir)
    }

GERİYE UYUM: `durum.json` yoksa (404) eski üç dosyalı yol aynen çalışır.
"""

from __future__ import annotations

import json
import logging

from core import uzak

log = logging.getLogger("kiosk.durum")

AD = "durum.json"


def getir() -> dict | None:
    """`durum.json` içeriği (yoksa/bozuksa None → çağıran eski yola düşer)."""
    govde = uzak.getir(AD)
    if not govde:
        return None
    try:
        belge = json.loads(govde)
    except ValueError:
        log.warning("durum.json bozuk JSON — yok sayıldı")
        return None
    if not isinstance(belge, dict):
        return None
    return belge


def damga(belge: dict | None) -> str:
    return str((belge or {}).get("lastupdate") or "").strip()


def tetik(belge: dict | None) -> dict | None:
    deger = (belge or {}).get("tetik")
    return deger if isinstance(deger, dict) and deger else None


def secili_tetik(belge: dict | None, yerel_oku) -> dict | None:
    """Tetikleyici seçimi: UZAK (panel → `durum.json`) önce, yoksa YEREL (MQTT → `tetikle.json`).

    NEDEN: MQTT push yerel dosyaya yazar. `durum.json` yoluna geçildiğinde bu dosya okunmazsa
    "Bildir" anlık çalışmaz (yaşandı). `yerel_oku` enjekte edilir → test edilebilir.
    """
    uzak_tetik = tetik(belge)
    if uzak_tetik:
        return uzak_tetik
    try:
        yerel = yerel_oku()
    except Exception:  # noqa: BLE001 - yerel okuma hatası gösterimi durdurmamalı
        return None
    return yerel if isinstance(yerel, dict) and yerel else None


def komut_isareti(belge: dict | None) -> str:
    """Komut dosyası için kısa işaret (zaman + id). Değişmediyse komut dosyası çekilmez."""
    deger = (belge or {}).get("komut")
    if not isinstance(deger, dict):
        return ""
    return f"{deger.get('zaman', '')}|{deger.get('id', '')}".strip("|")
