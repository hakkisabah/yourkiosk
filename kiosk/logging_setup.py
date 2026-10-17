"""Günlükleme: hem stderr hem döner dosya.

Referans sürüm `print()` kullanıyordu; kiosk (autostart/systemd) senaryosunda hiç iz kalmıyordu.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

BICIM = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def gunluk_kur(dosya=None, seviye: int = logging.INFO) -> logging.Logger:
    kok = logging.getLogger()
    if getattr(kok, "_kiosk_kuruldu", False):
        return logging.getLogger("kiosk")

    dosya = Path(dosya) if dosya else None
    kok.setLevel(seviye)
    bicimlendirici = logging.Formatter(BICIM)

    akis = logging.StreamHandler(sys.stderr)
    akis.setFormatter(bicimlendirici)
    kok.addHandler(akis)

    if dosya is not None:
        try:
            dosya.parent.mkdir(parents=True, exist_ok=True)
            tutamac = logging.handlers.RotatingFileHandler(
                dosya, maxBytes=512 * 1024, backupCount=3, encoding="utf-8"
            )
            tutamac.setFormatter(bicimlendirici)
            kok.addHandler(tutamac)
        except OSError as hata:
            kok.warning("günlük dosyası açılamadı (%s): %s", dosya, hata)

    kok._kiosk_kuruldu = True  # type: ignore[attr-defined]
    return logging.getLogger("kiosk")
