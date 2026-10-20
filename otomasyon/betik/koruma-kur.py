#!/usr/bin/env python3
"""BRANCH PROTECTION + DEPO GÜVENLİK AYARLARI (tek komut).

Neden onay sayısı 0? GitHub **kendi PR'ını onaylamana izin vermez**; depo tek kişilikse
"1 onay zorunlu" kuralı bütün PR'ları kilitlemez ama **hiçbir zaman** birleştirilemez hâle getirir.
Bu yüzden güvenlik kapısı **zorunlu durum kontrolü** ile kurulur: i5 `guvenlik/inceleme = success`
yazmadan birleştirme yapılamaz. (İkinci bir GitHub hesabı ortak yapılırsa `--onay 1` kullanılabilir.)

Kullanım:
    ./koruma-kur.py --kuru          # yalnız ne yapılacağını göster (hiçbir istek atmaz)
    ./koruma-kur.py --uygula        # kuralları uygula
    ./koruma-kur.py --uygula --onay 1 --kontrol guvenlik/inceleme
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

TABAN = "https://api.github.com"
ETIKETLER = [
    ("guvenlik/onay", "0e8a16", "i5 incelemesi temiz"),
    ("guvenlik/sorun", "b60205", "i5 güvenlik sorunu buldu"),
    ("karar/verildi", "1d76db", "i3 karar verdi (kabul)"),
    ("duzeltme/gerekli", "d93f0b", "i3 düzeltme istedi"),
]


def token_oku(yol: str) -> str:
    try:
        return Path(yol).expanduser().read_text(encoding="utf-8").strip()
    except OSError:
        return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""


def istek(yol: str, token: str, yontem: str = "GET", govde: dict | None = None) -> tuple[int, str]:
    veri = json.dumps(govde).encode("utf-8") if govde is not None else None
    istek_nesnesi = urllib.request.Request(
        f"{TABAN}{yol}",
        data=veri,
        method=yontem,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "yourkiosk-koruma",
            "Authorization": f"Bearer {token}",
            **({"Content-Type": "application/json"} if veri else {}),
        },
    )
    try:
        with urllib.request.urlopen(istek_nesnesi, timeout=25) as yanit:
            return yanit.status, yanit.read().decode("utf-8", "ignore")[:400]
    except urllib.error.HTTPError as hata:
        return hata.code, hata.read().decode("utf-8", "ignore")[:400]
    except (urllib.error.URLError, TimeoutError) as hata:
        return 0, str(hata)[:200]


def main() -> int:
    ap = argparse.ArgumentParser(description="yourkiosk için branch protection + güvenlik ayarları")
    ap.add_argument("--depo-adresi", default="hakkisabah/yourkiosk")
    ap.add_argument("--dal", default="main")
    ap.add_argument("--token-dosya", default=str(Path.home() / ".config/hermes-secrets/github-yourkiosk.token"))
    ap.add_argument("--onay", type=int, default=0, help="zorunlu onay sayısı (tek kişilik depoda 0)")
    ap.add_argument("--kontrol", default="guvenlik/inceleme", help="zorunlu durum kontrolü adı (boş: yok)")
    ap.add_argument("--kuru", action="store_true", help="yalnız göster")
    ap.add_argument("--uygula", action="store_true", help="gerçekten uygula")
    a = ap.parse_args()

    kontrol_listesi = [a.kontrol] if a.kontrol else []
    koruma = {
        "required_status_checks": {"strict": True, "contexts": kontrol_listesi} if kontrol_listesi else None,
        "enforce_admins": True,
        "required_pull_request_reviews": {
            "required_approving_review_count": a.onay,
            "dismiss_stale_reviews": True,
            "require_last_push_approval": False,
        }
        if a.onay > 0
        else {"required_approving_review_count": 0, "dismiss_stale_reviews": True},
        "restrictions": None,
        "required_linear_history": True,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "required_conversation_resolution": True,
    }

    print(f"depo    : {a.depo_adresi}  dal: {a.dal}")
    print(f"koruma  : PR zorunlu={koruma['required_pull_request_reviews'] is not None}, "
          f"onay={a.onay}, zorunlu kontrol={kontrol_listesi or 'yok'}, enforce_admins=True, "
          f"force-push=False, silme=False, doğrusal geçmiş=True")
    print(f"etiketler: {', '.join(e[0] for e in ETIKETLER)}")
    print("dependabot uyarıları: açılacak")

    if a.kuru or not a.uygula:
        print("\n(KURU — uygulamak için --uygula)")
        return 0

    token = token_oku(a.token_dosya)
    if not token:
        print("token yok: --token-dosya ya da GH_TOKEN", file=sys.stderr)
        return 3

    kod, govde = istek(f"/repos/{a.depo_adresi}", token)
    if kod != 200:
        print(f"depo doğrulanamadı: HTTP {kod} {govde}", file=sys.stderr)
        return 4
    print("[1/4] depo erişimi OK")

    kod, govde = istek(f"/repos/{a.depo_adresi}/branches/{a.dal}/protection", token, "PUT", koruma)
    if kod not in (200, 201):
        print(f"[2/4] branch protection HATA: HTTP {kod} {govde}", file=sys.stderr)
        return 5
    print("[2/4] branch protection uygulandı")

    for ad, renk, aciklama in ETIKETLER:
        kod, govde = istek(f"/repos/{a.depo_adresi}/labels", token, "POST",
                           {"name": ad, "color": renk, "description": aciklama})
        print(f"      etiket {ad}: HTTP {kod}" + ("" if kod in (201, 422) else f" → {govde}"))

    kod, govde = istek(f"/repos/{a.depo_adresi}/vulnerability-alerts", token, "PUT")
    print(f"[3/4] dependabot uyarıları: HTTP {kod}" + ("" if kod in (204, 200) else f" → {govde}"))

    kod, metin = istek(f"/repos/{a.depo_adresi}/branches/{a.dal}/protection", token)
    if kod == 200:
        print("[4/4] doğrulama: koruma etkin")
        try:
            veri = json.loads(metin)
            print(f"      enforce_admins={veri.get('enforce_admins', {}).get('enabled')}, "
                  f"force_push={veri.get('allow_force_pushes', {}).get('enabled')}")
        except ValueError:
            pass
    else:
        print(f"[4/4] doğrulama okunamadı: HTTP {kod}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
