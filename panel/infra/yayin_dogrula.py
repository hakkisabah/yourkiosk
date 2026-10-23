#!/usr/bin/env python3
"""Canlı panel doğrulaması — yayınlanan paket GERÇEKTEN doğru mu?

NEDEN: yer tutucu `.env.local` ile derlenen panel canlıya gitti ve kimse fark etmedi; kullanıcı
"panel açılmıyor / Kurulum ekranı" diyene kadar sürdü. Bu betik yayından SONRA canlıyı kontrol eder:

  • sunulan index.html hangi pakete bakıyor?
  • pakette YER TUTUCU (XXXX, ORNEK, eu-central-1:1111…) var mı?
  • `panel/.env.local` içindeki GERÇEK Cognito kimliği pakette geçiyor mu?

    ./panel/infra/yayin_dogrula.py                       # varsayılan adres
    ./panel/infra/yayin_dogrula.py --adres https://…
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from pathlib import Path

DIZIN = Path(__file__).resolve().parent
ENV = DIZIN.parent / ".env.local"
VARSAYILAN_ADRES = "https://d308vfb9mn2991.cloudfront.net/"
# NOT: "ORNEK"/"EXAMPLE" kelimesi pakette MEŞRU olabilir (arayüz metni, kod örneği) → aranmaz.
YER_TUTUCU = (
    re.compile(r"eu-central-1_[Xx]{6,}"),        # VITE_USER_POOL_ID yer tutucusu
    re.compile(r"eu-central-1:1{8}-2{4}-3{4}"),  # VITE_IDENTITY_POOL_ID yer tutucusu
    re.compile(r"[X]{20,}"),                     # istemci kimliği yer tutucusu
)


def _getir(url: str) -> tuple[bytes, dict[str, str]]:
    istek = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "User-Agent": "yourkiosk-dogrula/1.0"})
    with urllib.request.urlopen(istek, timeout=20) as yanit:
        return yanit.read(), dict(yanit.headers)


def env_oku() -> dict[str, str]:
    veri: dict[str, str] = {}
    if ENV.is_file():
        for satir in ENV.read_text(encoding="utf-8").splitlines():
            if "=" in satir and not satir.strip().startswith("#"):
                k, _, v = satir.partition("=")
                veri[k.strip()] = v.strip().strip('"').strip("'")
    return veri


def main() -> int:
    a = argparse.ArgumentParser(description="canlı panel doğrulaması")
    a.add_argument("--adres", default=VARSAYILAN_ADRES)
    secim = a.parse_args()
    adres = secim.adres.rstrip("/") + "/"

    try:
        html, basliklar = _getir(adres)
    except Exception as hata:  # noqa: BLE001
        print(f"✗ panel açılmıyor: {adres} ({hata})", file=sys.stderr)
        return 1

    metin = html.decode("utf-8", "replace")
    paketler = sorted(set(re.findall(r"assets/index-[A-Za-z0-9._-]+\.js", metin)))
    print(f"adres           : {adres}")
    print(f"index.html      : {len(html)} bayt · last-modified={basliklar.get('Last-Modified', '-')}")
    print(f"paket           : {', '.join(paketler) or '(bulunamadı)'}")
    if not paketler:
        print("✗ index.html ana paketi göstermiyor", file=sys.stderr)
        return 1

    icerikler: list[str] = []
    for paket in paketler:
        try:
            govde, _ = _getir(adres + paket)
            icerikler.append(govde.decode("utf-8", "replace"))
        except Exception as hata:  # noqa: BLE001
            print(f"✗ paket indirilemedi: {paket} ({hata})", file=sys.stderr)
            return 1
    birlesik = "\n".join(icerikler)

    env = env_oku()
    havuz = env.get("VITE_USER_POOL_ID", "")
    istemci = env.get("VITE_USER_POOL_CLIENT_ID", "")

    sorun = 0
    for desen in YER_TUTUCU:
        if desen.search(birlesik):
            print(f"✗ pakette YER TUTUCU değer var ({desen.pattern}) — panel Kurulum ekranına düşer")
            sorun += 1
            break

    if havuz:
        if havuz in birlesik:
            print(f"✓ gerçek havuz kimliği pakette: {havuz}")
        else:
            print(f"✗ havuz kimliği pakette YOK ({havuz}) — env derlemeye girmemiş")
            sorun += 1
    if istemci:
        if istemci in birlesik:
            print(f"✓ istemci kimliği pakette: {istemci[:8]}…")
        else:
            print("✗ istemci kimliği pakette yok")
            sorun += 1

    print(f"\n{'✓ canlı panel doğru derlenmiş' if sorun == 0 else f'✗ {sorun} sorun — yeniden yayınlayın'}")
    return 0 if sorun == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
