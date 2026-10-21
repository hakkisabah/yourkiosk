#!/usr/bin/env python3
"""DURUM PANOSU — "i5/i3 konuştu mu?" sorusunun tek komutluk yanıtı.

Gösterir:
  · `main`in son commit'i ve üzerindeki `guvenlik/inceleme` / `guvenlik/karar` durumları,
  · açık PR'lar, etiketleri ve son i5/i3 kararı (yorumdaki makine-okunabilir JSON bloğu),
  · en son ne zaman bir makine karar yazmış (haberleşmenin başlayıp başlamadığı).

Kullanım:
    python3 otomasyon/betik/durum.py
    python3 otomasyon/betik/durum.py --son 5        # son 5 commit
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

TABAN = "https://api.github.com"


def token_oku(yol: Path) -> str | None:
    try:
        return yol.expanduser().read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def api(yol: str, token: str) -> tuple[int, object]:
    istek = urllib.request.Request(
        f"{TABAN}{yol}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "yourkiosk-durum",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(istek, timeout=20) as yanit:
            return yanit.status, json.loads(yanit.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as hata:
        return hata.code, {"hata": hata.read().decode("utf-8", "ignore")[:200]}
    except (urllib.error.URLError, TimeoutError, ValueError) as hata:
        return 0, {"hata": str(hata)[:200]}


def karar_bloklari(metin: str) -> list[dict]:
    """Yorumdaki ```json … ``` bloklarından `makine` alanı olanları çıkarır."""
    bloklar = []
    for ham in re.findall(r"```json\s*(\{.*?\})\s*```", metin or "", flags=re.S):
        try:
            veri = json.loads(ham)
        except ValueError:
            continue
        if isinstance(veri, dict) and veri.get("makine"):
            bloklar.append(veri)
    return bloklar


def main() -> int:
    ap = argparse.ArgumentParser(description="i5/i3 haberleşme durumu")
    ap.add_argument("--depo-adresi", default="hakkisabah/yourkiosk")
    ap.add_argument("--token-dosya", default=str(Path.home() / ".config/hermes-secrets/github-yourkiosk.token"))
    ap.add_argument("--son", type=int, default=10, help="son kaç commit incelensin (varsayılan 10)")
    a = ap.parse_args()

    token = token_oku(Path(a.token_dosya))
    if not token:
        print(f"token yok: {a.token_dosya} (ya da GH_TOKEN)")
        return 3

    kod, commits = api(f"/repos/{a.depo_adresi}/commits?per_page={a.son}", token)
    if kod != 200 or not isinstance(commits, list):
        print(f"commit listesi alınamadı: HTTP {kod} {commits}")
        return 4

    print(f"=== {a.depo_adresi} · haberleşme durumu ===")
    print()
    print("SON COMMIT'LER")
    durumlar: dict[str, list] = {}
    for c in commits:
        sha = c["sha"]
        baslik = (c["commit"]["message"] or "").splitlines()[0][:60]
        kod_d, durum = api(f"/repos/{a.depo_adresi}/commits/{sha}/status", token)
        kontroller = durum.get("statuses", []) if isinstance(durum, dict) else []
        durumlar[sha] = kontroller
        etiket = ", ".join(f"{k['context']}={k['state']}" for k in kontroller) or "— (i5 konuşmadı)"
        print(f"  {sha[:8]}  {c['commit']['author']['date'][:16]}  {baslik}")
        print(f"            durum: {etiket}")

    print()
    print("AÇIK PR'LAR")
    kod, prlar = api(f"/repos/{a.depo_adresi}/pulls?state=open&per_page=10", token)
    if kod == 200 and isinstance(prlar, list):
        if not prlar:
            print("  (yok)")
        for pr in prlar:
            etiketler = ", ".join(e["name"] for e in pr.get("labels", [])) or "—"
            print(f"  #{pr['number']}  {pr['title'][:55]}")
            print(f"        dal: {pr['head']['ref']} → {pr['base']['ref']} · etiket: {etiketler}")
            kod_y, yorumlar = api(f"/repos/{a.depo_adresi}/issues/{pr['number']}/comments?per_page=20", token)
            son_karar = None
            if kod_y == 200 and isinstance(yorumlar, list):
                for yorum in yorumlar:
                    for blok in karar_bloklari(yorum.get("body", "")):
                        son_karar = (blok, yorum.get("user", {}).get("login"), yorum.get("created_at"))
            if son_karar:
                blok, kim, zaman = son_karar
                print(f"        son karar: {blok.get('makine')} → {blok.get('karar')} ({blok.get('onem')}) · {zaman}")
            else:
                print("        son karar: — (henüz i5/i3 yorumu yok)")
    else:
        print(f"  alınamadı: HTTP {kod}")

    print()
    print("YORUM")
    # Not: `main`in ucundaki commit genellikle squash-merge commit'idir ve makineler onu İNCELEMEZ
    # (i5/i3 PR başlıklarını inceler). Bu yüzden "son commit'te durum yok" normaldir; doğru ölçüt
    # son N commit + AÇIK PR'lar.
    tum = [k for liste in durumlar.values() for k in liste]
    i5_say = sum(1 for k in tum if k.get("context") == "guvenlik/inceleme")
    i3_say = sum(1 for k in tum if k.get("context") == "guvenlik/karar")
    pr_i5 = pr_i3 = 0
    for pr in (prlar if kod == 200 and isinstance(prlar, list) else []):
        kh, ham_h = api(f"/repos/{a.depo_adresi}/commits/{(pr.get('head') or {}).get('sha', '')}/status", token)
        if kh != 200 or not isinstance(ham_h, dict):
            continue
        for k in ham_h.get("statuses", []):
            if k.get("context") == "guvenlik/inceleme":
                pr_i5 += 1
            elif k.get("context") == "guvenlik/karar":
                pr_i3 += 1

    print(f"  i5 (`guvenlik/inceleme`): son {a.son} commit'te {i5_say} · açık PR'larda {pr_i5}")
    print(f"  i3 (`guvenlik/karar`)   : son {a.son} commit'te {i3_say} · açık PR'larda {pr_i3}")
    if i5_say or i3_say or pr_i5 or pr_i3:
        print("  haberleşme ÇALIŞIYOR ✓ (makineler GitHub'a yazıyor)")
        if i3_say == 0 and pr_i3 == 0:
            print("  NOT: i3 henüz `guvenlik/karar` yazmamış → D modunda PR'lar birleşemez.")
            print("       i3 makinesi: bash otomasyon/kur.sh i3 --cron")
    else:
        print("  haberleşme HENÜZ BAŞLAMADI — hiçbir makine durum yazmamış.")
        print("  i5: bash otomasyon/kur.sh i5 --cron  ·  i3: bash otomasyon/kur.sh i3 --cron")
        print("  denetim: python3 otomasyon/betik/ortam-kontrol.py --rol i5 --yazma-dene")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
