"""fontconfig köprüsü.

Bu geliştirme makinesinde `/etc/fonts/fonts.conf` yok; Qt yazı tipi altyapısı
bu dosya olmadan başlatılırken süreç çöküyor. Üretim kiosk cihazında fontconfig
paketi kurulu olacağı için bu modül orada hiçbir şey yapmaz.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger("kiosk.fontconfig")

SISTEM_CONF = Path("/etc/fonts/fonts.conf")
SABLON = """<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
  <dir>{font_dir}</dir>
  <cachedir>{cache_dir}</cachedir>
</fontconfig>
"""


def yerel_yapilandirma(kok: Path | None = None) -> Path | None:
    """Gerekiyorsa proje içi asgari fontconfig üretir; sistemde varsa None."""
    if SISTEM_CONF.exists():
        return None
    temel = Path(kok) if kok is not None else Path(__file__).resolve().parent
    hedef = temel / ".cache" / "fonts-local.conf"
    try:
        hedef.parent.mkdir(parents=True, exist_ok=True)
        hedef.write_text(
            SABLON.format(font_dir=temel / "font", cache_dir=temel / ".cache" / "fontconfig"),
            encoding="utf-8",
        )
    except OSError as hata:
        log.warning("fontconfig yapılandırması yazılamadı: %s", hata)
        return None
    return hedef


if __name__ == "__main__":
    yol = yerel_yapilandirma()
    print(yol if yol is not None else "")
