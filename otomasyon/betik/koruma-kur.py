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
            return yanit.status, yanit.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as hata:
        return hata.code, hata.read().decode("utf-8", "ignore")
    except (urllib.error.URLError, TimeoutError) as hata:
        return 0, str(hata)[:200]


def _json(metin: object) -> dict:
    """`istek()` metin döndürür; güvenli JSON çözümü."""
    if isinstance(metin, dict):
        return metin
    try:
        veri = json.loads(str(metin or ""))
    except ValueError:
        return {}
    return veri if isinstance(veri, dict) else {}


def son_commit_durumlari(a, token: str) -> dict:
    """Son commit'te `guvenlik/inceleme` durumu var mı? (fren ve --durum için)"""
    kod, ham = istek(f"/repos/{a.depo_adresi}/commits/{a.dal}", token)
    veri = _json(ham)
    sha = str(veri.get("sha", ""))
    if kod != 200 or not sha:
        return {"var": None, "sha": "", "durumlar": [], "hata": f"HTTP {kod}"}
    kod, ham2 = istek(f"/repos/{a.depo_adresi}/commits/{sha}/status", token)
    kontroller = _json(ham2).get("statuses", [])
    aranan = [k for k in kontroller if k.get("context") == "guvenlik/inceleme"]
    return {"var": bool(aranan), "sha": sha, "durumlar": kontroller, "kontrol": aranan}


def mevcut_durum(a, token: str) -> int:
    """`--durum`: hiçbir şeyi değiştirmeden mevcut koruma durumunu yazar (salt okuma)."""
    print()
    print("=== MEVCUT DURUM (salt okuma) ===")
    kod, ham = istek(f"/repos/{a.depo_adresi}/branches/{a.dal}/protection", token)
    veri = _json(ham)
    if kod == 200 and veri:
        pr = veri.get("required_pull_request_reviews") or {}
        kontroller = (veri.get("required_status_checks") or {}).get("contexts") or []
        print(f"  koruma          : AKTİF")
        print(f"  PR zorunlu      : {bool(pr)} (onay: {pr.get('required_approving_review_count', 0)})")
        print(f"  zorunlu kontrol : {kontroller or '(yok)'}")
        print(f"  force-push      : {veri.get('allow_force_pushes', {}).get('enabled')}")
        print(f"  silme           : {veri.get('allow_deletions', {}).get('enabled')}")
        print(f"  enforce_admins  : {veri.get('enforce_admins', {}).get('enabled')}")
    elif kod == 404:
        print("  koruma          : YOK (henüz kurulmamış)")
    else:
        print(f"  koruma okunamadı: HTTP {kod} — token'da 'Administration: Read' yok (i5/i3 normal)")
        print("  (aşağıdaki commit bilgisi yine de okunur; yalnız koruma alanları görünmez)")

    son = son_commit_durumlari(a, token)
    if son.get("var") is None:
        print(f"  son commit      : okunamadı ({son.get('hata')})")
        return 6
    print(f"  son commit      : {son['sha'][:12]}")
    if son["var"]:
        k = son["kontrol"][0]
        print(f"  i5 durumu       : {k.get('state')} · {k.get('updated_at', '')[:16]} ✓ (zorunlu kılınabilir)")
    else:
        print("  i5 durumu       : YOK → bu commit'te zorunlu kontrol eklerseniz PR'lar kilitlenir")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="yourkiosk için branch protection + güvenlik ayarları")
    ap.add_argument("--depo-adresi", default="hakkisabah/yourkiosk")
    ap.add_argument("--dal", default="main")
    ap.add_argument("--token-dosya", default=str(Path.home() / ".config/hermes-secrets/github-yourkiosk.token"))
    ap.add_argument("--onay", type=int, default=0, help="zorunlu onay sayısı (tek kişilik depoda 0)")
    ap.add_argument("--kontrol", default="guvenlik/inceleme",
                    help="zorunlu kontrol(ler); virgülle birden fazla: 'guvenlik/inceleme,guvenlik/karar' (boş: yok)")
    ap.add_argument("--durum", action="store_true", help="yalnız OKU: mevcut koruma ve zorunlu kontroller")
    ap.add_argument("--zorla", action="store_true",
                    help="zorunlu kontrolü, son commit'te o kontrol YOKKEN de ekle (PR'lar kilitlenebilir)")
    ap.add_argument("--kuru", action="store_true", help="yalnız göster")
    ap.add_argument("--uygula", action="store_true", help="gerçekten uygula")
    a = ap.parse_args()

    # virgülle birden fazla kontrol: --kontrol "guvenlik/inceleme,guvenlik/karar"
    kontrol_listesi = [k.strip() for k in a.kontrol.split(",") if k.strip()]
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
    if os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"):
        print("token   : ⚠ ORTAM DEĞİŞKENİ (GH_TOKEN/GITHUB_TOKEN) kullanılıyor — dosya değil!")
        print("          bu değişken başka bir token'a işaret ediyorsa 403 alırsınız; kaldırın: unset GH_TOKEN")
    else:
        print(f"token   : {a.token_dosya}")
    print(f"koruma  : PR zorunlu={koruma['required_pull_request_reviews'] is not None}, "
          f"onay={a.onay}, zorunlu kontrol={kontrol_listesi or 'yok'}, enforce_admins=True, "
          f"force-push=False, silme=False, doğrusal geçmiş=True")
    print(f"etiketler: {', '.join(e[0] for e in ETIKETLER)}")
    print("dependabot uyarıları: açılacak")

    token = token_oku(a.token_dosya)
    if not token:
        print("token yok: --token-dosya ya da GH_TOKEN", file=sys.stderr)
        return 3

    if a.durum:
        return mevcut_durum(a, token)

    if a.kuru or not a.uygula:
        print("\n(KURU — uygulamak için --uygula)")
        return 0

    # FREN: son commit'te kontrol yoksa zorunlu kılmak TÜM PR'ları kilitler
    if kontrol_listesi and not a.zorla:
        son = son_commit_durumlari(a, token)
        if not son.get("var"):
            print("DURDURULDU: bu commit'te `%s` durumu YOK." % kontrol_listesi[0])
            print("  Zorunlu kontrol eklerseniz, i5 o kontrolü yazana kadar HİÇBİR PR birleştirilemez.")
            print("  Sıra: önce i5 makinesinde cron çalışsın (bir commit'i incelesin), sonra bu komut.")
            print("  Kontrol: python3 otomasyon/betik/durum.py")
            print("  Bilerek yapıyorsanız: --zorla")
            return 7

    kod, govde = istek(f"/repos/{a.depo_adresi}", token)
    if kod != 200:
        print(f"depo doğrulanamadı: HTTP {kod} {govde[:300]}", file=sys.stderr)
        return 4
    print("[1/4] depo erişimi OK")

    kod, govde = istek(f"/repos/{a.depo_adresi}/branches/{a.dal}/protection", token, "PUT", koruma)
    if kod not in (200, 201):
        print(f"[2/4] branch protection HATA: HTTP {kod} {govde[:300]}", file=sys.stderr)
        if kod == 403:
            print("", file=sys.stderr)
            print("  NEDEN 403? Bu işlem YÖNETİCİ yetkisi ister. Kontrol listesi:", file=sys.stderr)
            print("   1) Token'da 'Administration: Read and write' var mı?", file=sys.stderr)
            print("      github.com/settings/personal-access-tokens → token → Edit → Repository permissions", file=sys.stderr)
            print("   2) Komut YÖNETİCİ makinesinde mi çalışıyor? i5/i3 token'larında Administration", file=sys.stderr)
            print("      BİLİNÇLİ olarak yoktur → bu komut yalnız geliştirici makinesinde çalışır.", file=sys.stderr)
            print("   3) Depo PRIVATE ise ücretsiz hesapta branch protection kapalıdır", file=sys.stderr)
            print("      ('Upgrade to GitHub Pro' der) → depo public olmalı ya da Pro gerekir.", file=sys.stderr)
            print("   4) GH_TOKEN/GITHUB_TOKEN ortam değişkeni başka (zayıf) bir token'a işaret ediyor olabilir.", file=sys.stderr)
            print("   Arayüzden yapmak isterseniz: Settings → Branches → 'main' →", file=sys.stderr)
            print("     Require status checks → guvenlik/inceleme (i5 bir kez yazdıktan sonra)", file=sys.stderr)
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
