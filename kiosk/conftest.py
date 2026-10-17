"""pytest kök yapılandırması (Qt offscreen + eksik sistem kütüphaneleri)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

# Uygulama düz içe aktarmalar kullanır (import config, from core... , from security...)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_CACHE_HOME", str(KOK / ".cache"))

# Bu makinede Qt sistem kütüphaneleri eksik: proje içi aşama kullanılır
_LIB = KOK / ".qt-libs" / "lib"
if _LIB.is_dir():
    mevcut = os.environ.get("LD_LIBRARY_PATH", "")
    os.environ["LD_LIBRARY_PATH"] = str(_LIB) + (f":{mevcut}" if mevcut else "")

from fontconfig_setup import yerel_yapilandirma  # noqa: E402  (Qt'den önce)

_conf = yerel_yapilandirma(KOK)
if _conf is not None:
    os.environ.setdefault("FONTCONFIG_FILE", str(_conf))
