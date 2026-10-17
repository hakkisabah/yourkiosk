#!/usr/bin/env python3
"""Tarayıcı (Chromium kiosk) gösterim modunu başlatır.

Ayarlar `ayarlar.json` (grup: `calistirma`) ve `kiosk/config.py`'den okunur.

    python3 tools/tarayici_kiosk.py --kuru          # yalnızca adres + komutu yazdır
    python3 tools/tarayici_kiosk.py                 # sunucuyu aç, Chromium kiosk başlat
    python3 tools/tarayici_kiosk.py --port 8091 --veri-modu https

Not: `main.py` de aynı yolu kullanır — `calistirma.mod = "tarayici"` yapıldığında
uygulama Qt yerine bu modda açılır (bkz. README §8).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

import ayarlar  # noqa: E402
from logging_setup import gunluk_kur  # noqa: E402
import config  # noqa: E402
from core import tarayici  # noqa: E402


def main(argv=None) -> int:
    import argparse

    ayristirici = argparse.ArgumentParser(description="yourkiosk tarayıcı gösterim modu")
    ayristirici.add_argument("--client-id", default="", help="cihaz kimliği (boşsa makinebilgileri.json'dan)")
    ayristirici.add_argument("--port", type=int, default=None, help="yerel sunucu portu")
    ayristirici.add_argument("--tarayici", default=None, help="tarayıcı çalıştırılabilir dosyası")
    ayristirici.add_argument("--veri-modu", choices=["yerel", "https"], default=None)
    ayristirici.add_argument("--kuru", action="store_true", help="başlatma; yalnızca adres ve komutu yazdır")
    ayristirici.add_argument(
        "--tani", action="store_true", help="ön kontrol raporu + tarayıcı konsolunu terminale dök"
    )
    ayristirici.add_argument("--yeniden-baslat-s", type=int, default=None)
    ayristirici.add_argument("--log-seviyesi", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    secenek = ayristirici.parse_args(argv)

    ayarlar.uygula()  # ayarlar.json içindeki calistirma.* değerleri config'e işlenir
    gunluk_kur(config.LOG_DOSYASI, getattr(logging, secenek.log_seviyesi))

    return tarayici.main(
        [
            *(["--client-id", secenek.client_id] if secenek.client_id else []),
            *(["--port", str(secenek.port)] if secenek.port else []),
            *(["--tarayici", secenek.tarayici] if secenek.tarayici else []),
            *(["--veri-modu", secenek.veri_modu] if secenek.veri_modu else []),
            *(["--yeniden-baslat-s", str(secenek.yeniden_baslat_s)] if secenek.yeniden_baslat_s is not None else []),
            *(["--kuru"] if secenek.kuru else []),
            *(["--tani"] if secenek.tani else []),
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
