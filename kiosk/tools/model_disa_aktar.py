#!/usr/bin/env python3
"""Veri modelini panel/web'e aktarır (kaynak: `core/model.py`)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import model  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(model.main())
