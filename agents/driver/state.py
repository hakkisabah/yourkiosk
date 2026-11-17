"""Durum dosyası — atomik yazım + tek süreç kilidi."""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path


class Durum:
    def __init__(self, dizin: Path, ad: str) -> None:
        self.dizin = Path(dizin)
        self.dosya = self.dizin / f"{ad}.json"
        self.kilit = self.dizin / f"{ad}.lock"
        self._fh = None

    def __enter__(self):
        self.dizin.mkdir(parents=True, exist_ok=True)
        self._fh = self.kilit.open("w")
        fcntl.flock(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return self

    def __exit__(self, *exc):
        if self._fh is not None:
            fcntl.flock(self._fh, fcntl.LOCK_UN)
            self._fh.close()
        return False

    def oku(self) -> dict:
        try:
            veri = json.loads(self.dosya.read_text(encoding="utf-8"))
            return veri if isinstance(veri, dict) else {}
        except (OSError, ValueError):
            return {}

    def yaz(self, veri: dict) -> None:
        self.dizin.mkdir(parents=True, exist_ok=True)
        gecici = self.dosya.with_suffix(".tmp")
        gecici.write_text(json.dumps(veri, ensure_ascii=False, sort_keys=True) + "\n",
                          encoding="utf-8")
        os.chmod(gecici, 0o600)
        os.replace(gecici, self.dosya)
