#!/usr/bin/env python3
"""`.env.local` denetimi — panel YAYINA ÇIKMADAN önce yer tutucu değerleri yakalar.

NEDEN: bir kez `.env.ornek`'ten kopyalanmış **yer tutucu** değerlerle derlenip yayınlandı ve panel
"Kurulum" ekranına düştü (`VITE_USER_POOL_ID` = eu-central-1_XXXX...). Derleme başarılı olduğu için
hata sessizce canlıya gitti. Bu betik derlemeden ÖNCE durur.

    ./panel/infra/env_denetle.py                 # denetle (0 = temiz, 1 = yer tutucu var)
    ./panel/infra/env_denetle.py --ayrinti       # değerleri maskeli göster
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DIZIN = Path(__file__).resolve().parent
ENV = DIZIN.parent / ".env.local"
ORNEK = DIZIN.parent / ".env.ornek"

ZORUNLU = ("VITE_BUCKET", "VITE_AWS_REGION", "VITE_USER_POOL_ID", "VITE_USER_POOL_CLIENT_ID", "VITE_IDENTITY_POOL_ID")
YER_TUTUCU = (
    re.compile(r"X{4,}", re.I),
    re.compile(r"ORNEK|EXAMPLE|DEGISTIR|CHANGEME|TODO", re.I),
    re.compile(r"^eu-central-1:1{8}-2{4}-3{4}-4{4}-5{12}$"),
    re.compile(r"^<.*>$"),
)


def oku(yol: Path) -> dict[str, str]:
    veri: dict[str, str] = {}
    if not yol.is_file():
        return veri
    for satir in yol.read_text(encoding="utf-8").splitlines():
        satir = satir.strip()
        if not satir or satir.startswith("#") or "=" not in satir:
            continue
        anahtar, _, deger = satir.partition("=")
        veri[anahtar.strip()] = deger.strip().strip('"').strip("'")
    return veri


def main() -> int:
    ayar = argparse.ArgumentParser(description=".env.local yer tutucu denetimi")
    ayar.add_argument("--ayrinti", action="store_true")
    secim = ayar.parse_args()

    if not ENV.is_file():
        print(f"✗ {ENV} yok — `cp panel/.env.ornek panel/.env.local` + gerçek değerler", file=sys.stderr)
        return 1

    deger = oku(ENV)
    sorunlar: list[str] = []
    for anahtar in ZORUNLU:
        ham = deger.get(anahtar, "")
        if not ham:
            sorunlar.append(f"{anahtar}: boş")
            continue
        for desen in YER_TUTUCU:
            if desen.search(ham):
                sorunlar.append(f"{anahtar}: YER TUTUCU ({ham[:18]}…)")
                break

    mod = (deger.get("VITE_AUTH_MODU") or "cognito").strip().lower()
    if mod not in ("cognito", "lambda"):
        sorunlar.append(f"VITE_AUTH_MODU: geçersiz ({mod}) — 'cognito' veya 'lambda' olmalı")

    if secim.ayrinti:
        for anahtar in ZORUNLU:
            ham = deger.get(anahtar, "")
            gizli = ham[:10] + "…" if len(ham) > 12 else ham
            print(f"  {anahtar:<28}= {gizli or '(yok)'}")

    if sorunlar:
        print("✗ .env.local yayına uygun değil (panel Kurulum ekranına düşer):", file=sys.stderr)
        for s in sorunlar:
            print(f"    • {s}", file=sys.stderr)
        print(f"  düzelt: {ENV} — gerçek Cognito değerlerini gir (docs/AWS-KURULUM.md §Cognito)", file=sys.stderr)
        return 1

    print(f"✓ .env.local tamam ({len(ZORUNLU)} zorunlu değer gerçek görünüyor)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
