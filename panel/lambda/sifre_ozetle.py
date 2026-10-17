#!/usr/bin/env python3
"""Yönetici şifresinden saklanabilir özet üretir (`PANEL_SIFRE_OZETI`).

Kullanım:
    python3 sifre_ozetle.py                 # şifreyi gizli sorar (önerilen)
    python3 sifre_ozetle.py --sifre 'gizli' # komut satırından (kabuk geçmişine yazılır!)

Çıktıyı Lambda ortam değişkeni olarak tanımlayın; şifrenin kendisini HİÇBİR YERE yazmayın.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from handler import sifre_ozeti_uret  # noqa: E402


def main() -> int:
    ayristirici = argparse.ArgumentParser(description="Panel şifre özeti üret")
    ayristirici.add_argument("--sifre", help="şifre (verilmezse gizli sorulur)")
    ayristirici.add_argument("--iterasyon", type=int, default=260_000)
    ayarlar = ayristirici.parse_args()

    sifre = ayarlar.sifre or getpass.getpass("Yönetici şifresi: ")
    if len(sifre) < 8:
        print("hata: şifre en az 8 karakter olmalı", file=sys.stderr)
        return 2
    if not 1000 <= ayarlar.iterasyon <= 2_000_000:
        print("hata: iterasyon aralık dışı", file=sys.stderr)
        return 2

    ozet = sifre_ozeti_uret(sifre, ayarlar.iterasyon)
    print(ozet)
    print("\nLambda ortam değişkeni olarak tanımlayın (şifreyi değil, SADECE bu özeti):", file=sys.stderr)
    print(f"  PANEL_SIFRE_OZETI={ozet}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
