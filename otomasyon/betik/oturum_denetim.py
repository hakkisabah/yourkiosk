#!/usr/bin/env python3
"""Oturum denetimi — "neden sürekli yeni session açılıyor?" sorusunu KANITLA yanıtlar.

i5/i3 makinelerinde çalıştırılır. Hiçbir şeyi değiştirmez (salt okuma).

    ./otomasyon/betik/oturum_denetim.py                # son 24 saat
    ./otomasyon/betik/oturum_denetim.py --gun 3       # son 3 gün
    ./otomasyon/betik/oturum_denetim.py --json        # makine okunur

Baktığı yerler:
  1. `~/.hermes/state.db` → oturumların KAYNAĞI (source: nobetci/cron/tui/gateway…) + saat dağılımı
  2. nöbetçi durum dosyaları → bugünkü oturum sayısı, bekleyen PR'lar
  3. `hermes cron list` → hâlâ çalışan eski cron görevleri
  4. systemd --user → nöbetçi servisi (aktif mi, kaç kez yeniden başlamış)
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERMES = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
DB = HERMES / "state.db"
DURUM = Path.home() / ".local" / "state" / "yourkiosk-otomasyon"


def _db() -> sqlite3.Connection | None:
    if not DB.is_file():
        return None
    try:
        return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    except sqlite3.Error:
        return None


def oturumlar(gun: int) -> list[dict]:
    c = _db()
    if c is None:
        return []
    # `started_at` UNIX epoch (float) — ISO değil
    esik = (datetime.now(timezone.utc) - timedelta(days=gun)).timestamp()
    try:
        satirlar = c.execute(
            "select id, coalesce(created_source, source, '?'), started_at, cwd, title "
            "from sessions where started_at >= ? order by started_at desc",
            (esik,),
        ).fetchall()
    except sqlite3.Error:
        return []
    sonuc = []
    for r in satirlar:
        try:
            an = datetime.fromtimestamp(float(r[2])).strftime("%Y-%m-%d %H:%M")
        except (TypeError, ValueError, OSError):
            an = str(r[2])
        sonuc.append({"id": r[0], "kaynak": r[1], "baslangic": an, "cwd": r[3] or "", "baslik": r[4] or ""})
    return sonuc


def saat_dagilimi(liste: list[dict]) -> dict[str, int]:
    sayac: Counter[str] = Counter()
    for o in liste:
        sayac[str(o["baslangic"])[:13] + ":00"] += 1
    return dict(sorted(sayac.items()))


def nobetci_durumu() -> list[dict]:
    sonuc = []
    for p in sorted(DURUM.glob("nobetci-*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        sonuc.append({
            "rol": d.get("rol", p.stem.replace("nobetci-", "")),
            "bugun_oturum": d.get("bugun_oturum", 0),
            "is": d.get("is", 0),
            "son_karar": d.get("son_karar", ""),
            "guncelleme": d.get("guncelleme", ""),
            "bekleyen": list((d.get("denemeler") or {}).keys())[:8],
        })
    return sonuc


def cron_gorevleri() -> list[str]:
    try:
        cikti = subprocess.run(["hermes", "cron", "list"], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return ["(hermes cron list çalıştırılamadı)"]
    satirlar = [s.strip() for s in cikti.splitlines()]
    adlar = [s for s in satirlar if s.startswith("Name:") or "Name:" in s]
    return adlar or ["(cron görevi yok)"]


def servis() -> list[str]:
    try:
        cikti = subprocess.run(
            ["systemctl", "--user", "show", "yourkiosk-nobetci.service",
             "-p", "ActiveState", "-p", "NRestarts", "-p", "ExecMainStartTimestamp"],
            capture_output=True, text=True, timeout=15,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ["(systemctl okunamadı)"]
    return [s for s in cikti.splitlines() if s]


def main() -> int:
    a = argparse.ArgumentParser(description="oturum kaynağı denetimi (salt okuma)")
    a.add_argument("--gun", type=int, default=1)
    a.add_argument("--json", action="store_true")
    secim = a.parse_args()

    oturum = oturumlar(secim.gun)
    kaynak_sayaci = Counter(o["kaynak"] for o in oturum)
    proje_sayaci = Counter(o["cwd"].rstrip("/").split("/")[-1] for o in oturum if o["cwd"])
    veri = {
        "pencere_gun": secim.gun,
        "toplam_oturum": len(oturum),
        "kaynak_dagilimi": dict(kaynak_sayaci),
        "proje_dagilimi": dict(proje_sayaci.most_common(5)),
        "saat_dagilimi": saat_dagilimi(oturum),
        "nobetci": nobetci_durumu(),
        "cron": cron_gorevleri(),
        "servis": servis(),
        "son_oturumlar": oturum[:12],
    }
    if secim.json:
        print(json.dumps(veri, ensure_ascii=False, indent=2))
        return 0

    print(f"=== OTURUM DENETİMİ (son {secim.gun} gün) ===")
    print(f"toplam oturum : {len(oturum)}")
    print("kaynak        : " + (", ".join(f"{k}={v}" for k, v in kaynak_sayaci.most_common()) or "-"))
    print("proje (cwd)   : " + (", ".join(f"{k}={v}" for k, v in proje_sayaci.most_common(5)) or "-"))

    dagilim = saat_dagilimi(oturum)
    if dagilim:
        print("\nsaatlik dağılım (en yoğun 8 saat):")
        for saat, adet in sorted(dagilim.items(), key=lambda x: -x[1])[:8]:
            print(f"  {saat}  {'█' * min(adet, 40)} {adet}")

    print("\nnöbetçi durumu:")
    for n in veri["nobetci"]:
        print(f"  {n['rol']}: bugün {n['bugun_oturum']} oturum · iş={n['is']} · son={n['son_karar'] or '-'}")
        if n["bekleyen"]:
            print(f"     beklemede: {', '.join(n['bekleyen'])}")

    print("\ncron görevleri:")
    for s in veri["cron"]:
        print(f"  {s}")
    print("\nnöbetçi servisi:")
    for s in veri["servis"]:
        print(f"  {s}")

    if veri["son_oturumlar"]:
        print("\nson oturumlar:")
        for o in veri["son_oturumlar"]:
            print(f"  {o['baslangic']}  {o['kaynak']:<10} {o['cwd'][-38:]:<38} {o['baslik'][:40]}")

    # yorum
    print("\n--- değerlendirme ---")
    if kaynak_sayaci.get("nobetci", 0) > 20:
        print("• nobetci kaynaklı oturum fazla: cooldown devrede mi? `systemctl --user restart yourkiosk-nobetci`")
        print("  ve `git pull` (cooldown düzeltmesi #39) uygulanmış olmalı.")
    if any("guvenlik" in s.lower() or "i5" in s.lower() or "i3" in s.lower() for s in veri["cron"]):
        print("• HÂLÂ eski cron görevi var → `./otomasyon/nobetci-kur.sh <rol> --cron-kaldir`")
    if not veri["nobetci"]:
        print("• nöbetçi durum dosyası yok → servis hiç çalışmamış olabilir (--durum ile bak)")
    if kaynak_sayaci.get("tui", 0) or kaynak_sayaci.get("cli", 0):
        print("• tui/cli oturumları SENİN elle açtıkların (dashboard/terminal). Bunlar otomasyon değil.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
