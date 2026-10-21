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
    ap.add_argument("--son", type=int, default=3, help="son kaç commit gösterilsin")
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
    son_sha = commits[0]["sha"]
    son_kontroller = durumlar.get(son_sha, [])
    son_i5 = next((k for k in son_kontroller if k.get("context") == "guvenlik/inceleme"), None)
    if son_i5:
        print(f"  i5 SON commit'i incelemiş ✓  ({son_i5.get('state')} · {son_i5.get('updated_at', '')[:16]})")
        print("  haberleşme ÇALIŞIYOR: i5 makinesi GitHub'a yazıyor.")
    else:
        eskiler = [k for sha, liste in durumlar.items() if sha != son_sha for k in liste
                   if k.get("context") == "guvenlik/inceleme"]
        print("  i5 SON commit'i İNCELEMEMİŞ — haberleşme henüz başlamadı.")
        if eskiler:
            print(f"  (daha eski commit'lerde {len(eskiler)} durum var; bunlar geçmiş/elle koşular olabilir)")
        print("  i5 makinesinde: hermes cron list   → görev var mı?")
        print("  kurulum: bash otomasyon/kur.sh i5 --cron")
        print("  denetim: python3 otomasyon/betik/ortam-kontrol.py --rol i5")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
