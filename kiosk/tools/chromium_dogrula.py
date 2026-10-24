#!/usr/bin/env python3
"""Chromium (tarayıcı) yeteneğini DOĞRULA — kurulum sonrası tek komut.

Ne yapar:
  1. `ldd` ile eksik paylaşımlı kütüphane var mı,
  2. `--headless` ile sürüm + boş sayfa çizimi (gerçek çalıştırma),
  3. kiosk arayüzünün GERÇEK sayfasını headless yükleyip ekran görüntüsü + konsol hataları,
  4. isteğe bağlı: bir URL'yi (ör. panel) yükleyip DOM metnini döker.

Kullanım:
    python3 tools/chromium_dogrula.py                       # sadece yetenek testi
    python3 tools/chromium_dogrula.py --url http://127.0.0.1:8090/index.html?clientID=X
    python3 tools/chromium_dogrula.py --url https://d308vfb9mn2991.cloudfront.net/ --metin
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ADAYLAR = (
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome-stable",
    str(Path.home() / ".hermes/tools/chromium-1208/chrome-linux64/chrome"),
)


def bul() -> str | None:
    for aday in ADAYLAR:
        if Path(aday).is_file():
            return aday
    # PATH'te ara
    for ad in ("chromium", "chromium-browser", "google-chrome-stable", "chrome"):
        yol = shutil.which(ad)
        if yol:
            return yol
    # hermes tools altında herhangi bir sürüm
    for yol in sorted(Path.home().glob(".hermes/tools/chromium-*/chrome-linux64/chrome")):
        return str(yol)
    return None


def eksik_kutuphaneler(ikili: str) -> list[str]:
    try:
        cikti = subprocess.run(["ldd", ikili], capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return sorted({s.split()[0] for s in cikti.splitlines() if "not found" in s})


#: Chrome 132+ ile `--headless=new` KALDIRILDI; `--headless=new` yazınca
#: "Multiple targets are not supported in headless mode" hatası veriyor. Düz `--headless` doğru.
GURULTU = ("dbus", "UPower", "Failed to call method", "libva", "GPU process", "sandbox")


def calistir(ikili: str, *arg: str, sure: int = 90) -> subprocess.CompletedProcess:
    """Chrome 145 headless çağrısı.

    DENENEN VE ÇALIŞMAYANLAR (ölçüldü, bu makinede):
      • `--headless=new` → "Multiple targets are not supported in headless mode"
      • `--user-data-dir=…` → aynı hata ya da asılı kalma (300 sn zaman aşımı)
      • `--disable-features=DbusServices` → gereksiz; DBus/UPower uyarıları zararsız
    ÇALIŞAN: düz `--headless` + `--no-sandbox` + `--disable-gpu` + `--screenshot=…`
    """
    return subprocess.run(
        [ikili, "--headless", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", *arg],
        capture_output=True, text=True, timeout=sure,
    )


def main() -> int:
    a = argparse.ArgumentParser(description="chromium yeteneğini doğrula")
    a.add_argument("--url", default="", help="yüklenecek adres (boşsa yalnız yetenek testi)")
    a.add_argument("--metin", action="store_true", help="sayfanın DOM metnini dök")
    a.add_argument("--ekran", default="", help="ekran görüntüsü yolu (.png)")
    secim = a.parse_args()

    ikili = bul()
    if not ikili:
        print("✗ chromium bulunamadı", file=sys.stderr)
        return 2
    print(f"ikili           : {ikili}")

    eksik = eksik_kutuphaneler(ikili)
    if eksik:
        print(f"✗ {len(eksik)} kütüphane eksik:", file=sys.stderr)
        for ad in eksik:
            print(f"   • {ad}", file=sys.stderr)
        print("\nKurulum (Arch): sudo pacman -S --needed " + " ".join(sorted({
            "alsa-lib", "at-spi2-core", "cairo", "libcups", "mesa", "nspr", "nss", "pango",
            "libx11", "libxcb", "libxcomposite", "libxdamage", "libxext", "libxfixes",
            "libxkbcommon", "libxrandr", "fontconfig", "ttf-liberation",
        })), file=sys.stderr)
        return 1
    print("kütüphaneler    : ✓ eksik yok")

    try:
        surum = calistir(ikili, "--version", sure=30)
        print(f"sürüm           : {(surum.stdout or surum.stderr).strip()}")
    except (OSError, subprocess.SubprocessError) as hata:
        print(f"✗ çalıştırılamadı: {hata}", file=sys.stderr)
        return 1

    # boş sayfa çizimi (gerçek render)
    with tempfile.TemporaryDirectory() as dizin:
        bos = Path(dizin) / "bos.png"
        deneme = calistir(ikili, f"--screenshot={bos}", "data:text/html,<h1>tamam</h1>", sure=60)
        if not bos.is_file() or bos.stat().st_size == 0:
            print("✗ headless render başarısız", file=sys.stderr)
            print((deneme.stderr or "")[-800:], file=sys.stderr)
            return 1
        print(f"headless render : ✓ ({bos.stat().st_size} bayt PNG)")

        if secim.url:
            print(f"\n--- {secim.url} ---")
            hedef = Path(dizin) / "sayfa.png"
            cikti = calistir(
                ikili, "--virtual-time-budget=8000", "--window-size=1920,1080",
                f"--screenshot={hedef}", secim.url, sure=120,
            )
            hatalar = [
                s for s in (cikti.stderr or "").splitlines()
                if re.search(r"ERROR|Uncaught|Failed to load|Not allowed", s)
                and not any(g in s for g in GURULTU)
            ]
            print(f"ekran görüntüsü : {hedef if hedef.is_file() else '(alınamadı)'}")
            if secim.ekran and hedef.is_file():
                Path(secim.ekran).write_bytes(hedef.read_bytes())
                print(f"kaydedildi      : {secim.ekran}")
            if hatalar:
                print("konsol hataları :")
                for s in hatalar[:15]:
                    print(f"   {s[:200]}")
            else:
                print("konsol hataları : (yok)")

            if secim.metin:
                dom = calistir(ikili, "--virtual-time-budget=8000", "--dump-dom", secim.url,
                               sure=120)
                metin = re.sub(r"<[^>]+>", " ", dom.stdout or "")
                metin = re.sub(r"\s+", " ", metin).strip()
                print(f"DOM metni       : {metin[:1200]}")
    print("\n✓ tarayıcı kullanılabilir")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
