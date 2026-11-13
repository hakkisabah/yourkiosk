#!/usr/bin/env python3
"""Açık PR'ların inceleme/karar durumunu özetler (kapı tıkanıklığını teşhis için).

Kullanım:
    python3 pr_yorum_ozet.py 90 86 84           # her PR için SON karar yorumu + tazelik
    python3 pr_yorum_ozet.py --hepsi 90         # tüm karar turları (tarihçe)
    python3 pr_yorum_ozet.py --durum 90 86      # yalnız status context'leri + head sha
    DEPO=hakkisabah/yourkiosk TOKEN=~/.config/hermes-secrets/github-yourkiosk.token \\
        python3 pr_yorum_ozet.py 83

Neden: "PR neden birleşmiyor" sorusunun cevabı yorumlarda ve commit status'lerinde. Elle
tıklamak yerine tek komutta üç sınıfı ayır: incelenmemiş / karara bağlı / karar bekliyor.

İKİ TAZELİK ÖLÇÜTÜ basılır (ikisi de sessiz tuzağı kapatır):
  · kararın kendi `sha`'sı PR head'iyle aynı mı (değilse bulgu listesi BAYAT — yeniden çek),
  · status açıklamasındaki `[v<sürüm>]` damgası var mı (yoksa sürümden önceki karar, bayat sayılır).
Yorumlar varsayılan olarak SON turu basar; 40+ turluk PR'da tüm tarihçe bağlamı boğuyordu.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import urllib.request

KARAR_BLOGU = re.compile(r"```json\s*(\{.*?\})\s*```", re.S)
SURUM_DAMGASI = re.compile(r"^\s*\[v([0-9]+)\]")


def _alan(veri, *yol, varsayilan=""):
    for ad in yol:
        if not isinstance(veri, dict):
            return varsayilan
        veri = veri.get(ad)
    return varsayilan if veri is None else veri


def karar_blogu(govde: str) -> dict:
    """Yorumdaki `makine-okunabilir karar` JSON'unu çıkar (yoksa boş sözlük)."""
    eslesme = KARAR_BLOGU.search(govde or "")
    if not eslesme:
        return {}
    try:
        veri = json.loads(eslesme.group(1))
    except ValueError:
        return {}
    return veri if isinstance(veri, dict) else {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("prlar", nargs="+", type=int)
    ap.add_argument("--depo", default=os.environ.get("DEPO", "hakkisabah/yourkiosk"))
    ap.add_argument("--token-dosya",
                    default=os.environ.get("TOKEN", "~/.config/hermes-secrets/github-yourkiosk.token"))
    ap.add_argument("--durum", action="store_true", help="yorum yerine commit status'lerini yaz")
    ap.add_argument("--hepsi", action="store_true",
                    help="yalnız son karar turu değil, TÜM karar yorumları")
    ap.add_argument("--uzunluk", type=int, default=4000, help="yorum başına karakter")
    a = ap.parse_args()

    token = pathlib.Path(a.token_dosya).expanduser().read_text(encoding="utf-8").strip()
    if not token:
        raise SystemExit("token dosyası boş")

    def al(yol: str):
        istek = urllib.request.Request(
            f"https://api.github.com/repos/{a.depo}{yol}",
            headers={"Authorization": f"Bearer {token}",
                     "Accept": "application/vnd.github+json",
                     "User-Agent": "kapi-teshis"})
        with urllib.request.urlopen(istek, timeout=30) as y:
            return json.load(y)

    for no in a.prlar:
        pr = al(f"/pulls/{no}")
        head = _alan(pr, "head", "sha")
        durumlar = al(f"/commits/{head}/status").get("statuses", [])
        sozluk = {s.get("context"): s.get("state") for s in durumlar}
        print("=" * 78)
        print(f"PR #{no} · {str(_alan(pr, 'title'))[:60]}")
        # `mergeable` liste ucunda olmayabilir; tek PR ucunda da null gelebilir → mergeable_state oku.
        print(f"  head   : {head[:12]} · dal: {_alan(pr, 'head', 'ref')}")
        print(f"  durum  : {pr.get('mergeable_state')} · taslak: {pr.get('draft')}")
        for s in durumlar:
            damga = SURUM_DAMGASI.match(s.get("description") or "")
            surum = "v" + damga.group(1) if damga else "YOK (bayat sayılır)"
            zaman = s.get("updated_at") or s.get("created_at")
            print(f"  status : {s.get('context')} = {s.get('state')} · sürüm damgası: {surum} · {zaman}")
        for baglam in ("guvenlik/inceleme", "guvenlik/karar"):
            if baglam not in sozluk:
                print(f"  {baglam:18s}: YOK (incelenmemiş → kuyrukta olmalı)")
        if a.durum:
            continue
        kararlar = [c for c in al(f"/issues/{no}/comments?per_page=100")
                    if "makine" in (c.get("body") or "") or "inceleme" in (c.get("body") or "")[:400]]
        if not kararlar:
            print("  yorum : karar yorumu YOK (status taze + yorum yok = yazma yolu arızalı)")
            continue
        secili = kararlar if a.hepsi else kararlar[-1:]
        print(f"  yorum : {len(kararlar)} karar turu" + ("" if a.hepsi else " → yalnız SON tur"))
        for c in secili:
            govde = c.get("body") or ""
            blogu = karar_blogu(govde)
            karar_sha = str(blogu.get("sha") or "")
            taze = ("✓ karar head ile aynı" if karar_sha.startswith(head[:12]) else
                    f"✗ KARAR BAYAT — karar sha {karar_sha[:12] or 'YOK'}, head {head[:12]} → bu bulgu listesi ESKİ")
            print("-" * 70)
            print(c.get("created_at"), c.get("user", {}).get("login"),
                  "·", blogu.get("karar"), f"({blogu.get('onem')})",
                  "· bulgu:", blogu.get("bulgu_sayisi"))
            print("  " + taze)
            print(govde[: a.uzunluk])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
