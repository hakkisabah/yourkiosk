#!/usr/bin/env python3
"""Birleştirme öncesi KENDİ kontrol noktalarım (geliştirici makinesi).

Tekrarlanan hataları engellemek için: dal, commit sayısı, sır taraması, test izi.

    ./otomasyon/betik/orta_kontrol.py            # denetle
    ./otomasyon/betik/orta_kontrol.py --json

Neden: son turlarda (a) birleştirilmiş commit'lerin üstüne yeni dal açtım (PR kirlendi),
(b) sır içerebilecek değişiklikleri gözden kaçırdım. Bu betik ikisini de yakalar.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]

SIR_DESENLERI = [
    (r"AKIA[0-9A-Z]{16}", "AWS erişim anahtarı"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "özel anahtar"),
    (r"(?i)\b(password|parola|secret|token)\b\s*[:=]\s*['\"][^'\"\s]{8,}['\"]", "gömülü parola/token"),
    (r"https://[^/\s]+:[^/\s]+@", "URL içinde kimlik bilgisi"),
    (r"xox[baprs]-[0-9A-Za-z-]{10,}", "Slack token"),
]


def komut(*a: str) -> str:
    return subprocess.run(["git", *a], cwd=KOK, capture_output=True, text=True).stdout.strip()


def main() -> int:
    a = argparse.ArgumentParser(description="birleştirme öncesi kontrol noktaları")
    a.add_argument("--json", action="store_true")
    a.add_argument("--testler", action="store_true", help="kiosk + web testlerini de çalıştır (yavaş)")
    secim = a.parse_args()

    sonuc: dict[str, dict] = {}
    sorun = 0

    def madde(ad: str, durum: bool, ayrinti: str = "", onemli: bool = True) -> None:
        nonlocal sorun
        if not durum and onemli:
            sorun += 1
        sonuc[ad] = {"gecti": durum, "ayrinti": ayrinti}

    dal = komut("rev-parse", "--abbrev-ref", "HEAD")
    madde("dal adı", dal.startswith("ozellik/"), dal or "?")

    komut("fetch", "-q", "origin")
    main_sha = komut("rev-parse", "origin/main")
    ileri = komut("rev-list", "--count", "origin/main..HEAD")
    # Birleştirilmiş commit'lerin üstüne dal açmak PR'ı kirletir → tam 1 commit bekleniyor
    madde("origin/main'den fark", ileri == "1", f"{ileri} commit", onemli=False)

    geride = komut("rev-list", "--count", "HEAD..origin/main")
    madde("dal güncel (geride yok)", geride == "0", f"{geride} commit geride")

    kirli = komut("status", "--porcelain")
    madde("çalışma ağacı temiz", not kirli, kirli[:160])

    fark = komut("diff", "--unified=0", f"{main_sha}...HEAD")
    madde("değişiklik var", bool(fark.strip()), f"{len(fark)} bayt")

    bulunan = []
    for desen, ad in SIR_DESENLERI:
        for eslesme in re.finditer(desen, fark):
            satir_no = fark[: eslesme.start()].count("\n") + 1
            bulunan.append({"tur": ad, "satir": satir_no, "ornek": eslesme.group(0)[:40]})
    madde("sır taraması", not bulunan, json.dumps(bulunan, ensure_ascii=False) if bulunan else "temiz")

    degisen = [s.split()[-1] for s in komut("diff", "--name-only", f"{main_sha}...HEAD").splitlines() if s.strip()]
    testler = [d for d in degisen if "test" in d.lower()]
    kod = [d for d in degisen if d.endswith((".py", ".ts", ".vue", ".sh")) and "test" not in d.lower()]
    madde("test izi", bool(testler) or not kod, f"{len(testler)} test dosyası / {len(kod)} kod dosyası", onemli=False)

    if secim.testler:
        # KONTROL NOKTASI: geçen turda testler kırıkken birleştirdim → artık kapı.
        import subprocess as sp

        # DİKKAT: test.sh kiosk/ içinden çalışmalı; depo kökünden çağrılınca pytest koleksiyonu
        # patlıyor (çıkış 2) ve "testler kırık" sanılıyor. Geçen tur bu yüzden yanlış sonuç aldım.
        kiosk = sp.run(["tools/test.sh", "tests", "-q"], cwd=KOK / "kiosk", capture_output=True, text=True)
        madde("kiosk testleri", kiosk.returncode == 0, f"çıkış {kiosk.returncode}")
        web = sp.run(["npx", "vitest", "run"], cwd=KOK / "web", capture_output=True, text=True)
        madde("web testleri", web.returncode == 0, f"çıkış {web.returncode}")

    if secim.json:
        print(json.dumps(sonuc, ensure_ascii=False, indent=2))
        return 0 if sorun == 0 else 1

    print(f"=== BİRLEŞTİRME ÖNCESİ KONTROL ({dal}) ===")
    for ad, d in sonuc.items():
        print(f"{'✓' if d['gecti'] else '✗'} {ad:<22} {d['ayrinti']}")
    print(f"\n{'✓ geçti — birleştirme güvenli' if sorun == 0 else f'✗ {sorun} kontrol başarısız'}")
    print(f"değişen dosyalar: {len(degisen)}")
    return 0 if sorun == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
