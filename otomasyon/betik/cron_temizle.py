#!/usr/bin/env python3
"""Projeye ait eski `hermes cron` görevlerini bulur/siler (nöbetçiye geçiş temizliği).

NEDEN: `nobetci-kur.sh --cron-kaldir` yalnız "i5/i3 guvenlik" adını arıyordu; kullanıcının görevi
"i3 karar" adındaydı → silinmedi, üstüne servis kuruldu ve oturumlar iki kaynaktan açılmaya devam etti.

Bu betik **ada değil, iş dizinine** bakar: `Workdir` bu depoyu gösteren TÜM görevleri listeler.

    ./otomasyon/betik/cron_temizle.py            # yalnız listele (kuru)
    ./otomasyon/betik/cron_temizle.py --sil      # hepsini sil
    ./otomasyon/betik/cron_temizle.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]


def liste() -> list[dict]:
    try:
        cikti = subprocess.run(["hermes", "cron", "list"], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError) as hata:
        print(f"✗ hermes cron list çalıştırılamadı: {hata}", file=sys.stderr)
        return []
    gorevler: list[dict] = []
    simdiki: dict | None = None
    for satir in cikti.splitlines():
        kimlik = re.match(r"^\s{0,4}([0-9a-f]{12})\s", satir)
        if kimlik:
            if simdiki:
                gorevler.append(simdiki)
            simdiki = {"id": kimlik.group(1), "ad": "", "workdir": "", "script": "", "zamanlama": ""}
            continue
        if not simdiki:
            continue
        alan = re.match(r"^\s+(Name|Workdir|Script|Schedule):\s*(.+?)\s*$", satir)
        if alan:
            anahtar, deger = alan.group(1), alan.group(2)
            if anahtar == "Name":
                simdiki["ad"] = deger
            elif anahtar == "Workdir":
                simdiki["workdir"] = deger
            elif anahtar == "Script":
                simdiki["script"] = deger
            else:
                simdiki["zamanlama"] = deger
    if simdiki:
        gorevler.append(simdiki)
    return gorevler


def projeye_ait(gorev: dict) -> bool:
    yol = (gorev.get("workdir") or "").rstrip("/")
    if yol and Path(yol).resolve() == KOK.resolve():
        return True
    ad = (gorev.get("ad") or "").lower()
    betik = (gorev.get("script") or "").lower()
    return bool(re.search(r"\b(i5|i3)\b", ad)) and ("guvenlik" in ad or "karar" in ad) or "otomasyon-topla" in betik


def main() -> int:
    a = argparse.ArgumentParser(description="projeye ait cron görevlerini listele/sil")
    a.add_argument("--sil", action="store_true")
    a.add_argument("--json", action="store_true")
    secim = a.parse_args()

    hepsi = liste()
    hedef = [g for g in hepsi if projeye_ait(g)]

    if secim.json:
        print(json.dumps({"toplam": len(hepsi), "hedef": hedef}, ensure_ascii=False, indent=2))
        return 0

    print(f"cron görevleri: {len(hepsi)} · bu projeye ait: {len(hedef)}")
    for g in hedef:
        print(f"  {g['id']}  {g['ad'] or '(adsız)'}  [{g['zamanlama']}]  {g['workdir'] or g['script']}")

    if not hedef:
        print("✓ temiz — bu proje için cron görevi yok")
        return 0
    if not secim.sil:
        print("\nsilmek için: --sil")
        return 0

    kalan = 0
    for g in hedef:
        r = subprocess.run(["hermes", "cron", "remove", g["id"]], capture_output=True, text=True)
        if r.returncode == 0:
            print(f"✓ silindi: {g['id']} ({g['ad'] or 'adsız'})")
        else:
            kalan += 1
            print(f"✗ silinemedi: {g['id']} → {(r.stderr or r.stdout).strip()[:160]}")

    # DOĞRULAMA (kontrol noktası): silme sonrası tekrar listele
    sonra = [g for g in liste() if projeye_ait(g)]
    if sonra:
        print(f"✗ DOĞRULAMA BAŞARISIZ: {len(sonra)} görev hâlâ duruyor: {[g['id'] for g in sonra]}")
        return 1
    print("✓ doğrulama: projeye ait cron görevi kalmadı")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
