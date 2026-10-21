#!/usr/bin/env python3
"""KARARI GITHUB'A YAZ — commit durumu + PR yorumu + etiketler (i5/i3 makineleri).

Ajan (o makinedeki Hermes) kararı verir, bu betik yayınlar. Yorumun içinde **makine-okunabilir**
bir JSON bloğu bulunur; diğer makine ve geliştirici (ben) onu ayrıştırır.

Karar dosyası (karar.json):
    {
      "makine": "i5",                  // "i5" güvenlik incelemesi | "i3" karar/ikinci görüş
      "sha": "<commit sha>",           // işaretlenecek commit (PR varsa head sha)
      "pr": 12,                        // PR numarası (yoksa null → yalnız commit durumu)
      "karar": "onay"|"sorun"|"red"|"duzeltme"|"kabul",
      "onem": "yuksek"|"orta"|"dusuk",
      "ozet": "tek paragraf, Türkçe",
      "bulgular": [{"dosya": "kiosk/core/x.py", "satir": 12, "onem": "yuksek", "aciklama": "..."}],
      "not": "geliştiriciye (bana) iletilecek not / sonraki adım"
    }

Kullanım:
    ./yaz.py karar.json                # yayınla
    ./yaz.py karar.json --kuru         # yalnız göster (hiçbir istek atmaz)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

TABAN = "https://api.github.com"
BASLIKLAR = {"Accept": "application/vnd.github+json", "User-Agent": "yourkiosk-otomasyon"}

#: makine → (commit durumu adı, onay etiketi, sorun etiketi)
MAKINE_AYARI = {
    "i5": ("guvenlik/inceleme", "guvenlik/onay", "guvenlik/sorun"),
    "i3": ("guvenlik/karar", "karar/verildi", "duzeltme/gerekli"),
}
GUNLUK_BASLIK = "i5/i3 güvenlik günlüğü (otomasyon)"
#: Otomatik birleştirmeyi durduran etiketler (kill-switch)
ENGELLEYEN_ETIKETLER = ("guvenlik/sorun", "duzeltme/gerekli", "birlestirme/durdur")
ONAY_KARARLARI = {"onay", "kabul"}
SORUN_KARARLARI = {"sorun", "red", "duzeltme"}


def token_oku(yol: str | None) -> str | None:
    if yol:
        try:
            return Path(yol).expanduser().read_text(encoding="utf-8").strip() or None
        except OSError:
            return None
    return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")


def istek(yol: str, token: str, yontem: str = "GET", govde: dict | None = None) -> tuple[int, object | None]:
    """API çağrısı → (http kodu, ayrıştırılmış gövde). Hata betiği durdurmaz."""
    veri = json.dumps(govde).encode("utf-8") if govde is not None else None
    istek_nesnesi = urllib.request.Request(
        f"{TABAN}{yol}",
        data=veri,
        method=yontem,
        headers={**BASLIKLAR, "Authorization": f"Bearer {token}", **({"Content-Type": "application/json"} if veri else {})},
    )
    try:
        with urllib.request.urlopen(istek_nesnesi, timeout=25) as yanit:
            ham = yanit.read().decode("utf-8")
            return yanit.status, (json.loads(ham) if ham.strip() else None)
    except urllib.error.HTTPError as hata:
        return hata.code, {"hata": hata.read().decode("utf-8", "ignore")[:300]}
    except (urllib.error.URLError, TimeoutError, ValueError) as hata:
        return 0, {"hata": str(hata)[:300]}


def durum_metni(karar: dict) -> tuple[str, str]:
    """(commit durumu, kısa açıklama) — GitHub açıklaması en fazla 140 karakter."""
    secim = str(karar.get("karar", "")).lower()
    durum = "success" if secim in ONAY_KARARLARI else ("failure" if secim in SORUN_KARARLARI else "error")
    onem = karar.get("onem") or "-"
    ozet = str(karar.get("ozet", "")).replace("\n", " ")[:110]
    return durum, f"{secim} ({onem}): {ozet}"[:140]


def yorum_govdesi(karar: dict, durum: str) -> str:
    makine = str(karar.get("makine", "i5")).lower()
    baslik = {
        "i5": "🔍 **i5 — güvenlik incelemesi**",
        "i3": "⚖️ **i3 — karar / ikinci görüş**",
    }.get(makine, f"🤖 **{makine}**")
    simge = {"success": "✅", "failure": "❌", "error": "⚠️"}.get(durum, "•")

    satirlar = [
        f"{baslik} — {simge} **{karar.get('karar')}** (önem: {karar.get('onem') or '-'})",
        "",
        str(karar.get("ozet", "")).strip(),
        "",
    ]
    bulgular = karar.get("bulgular") or []
    if bulgular:
        satirlar += ["| Dosya | Satır | Önem | Bulgu |", "|---|---|---|---|"]
        for b in bulgular[:25]:
            aciklama = str(b.get("aciklama", "")).replace("|", "\\|")[:200]
            satirlar.append(f"| `{b.get('dosya', '?')}` | {b.get('satir', '')} | {b.get('onem', '')} | {aciklama} |")
        if len(bulgular) > 25:
            satirlar.append(f"| … | | | (+{len(bulgular) - 25} bulgu daha) |")
        satirlar.append("")
    if karar.get("not"):
        satirlar += [f"**Geliştiriciye not:** {karar['not']}", ""]

    makine_blogu = {
        "makine": makine,
        "karar": karar.get("karar"),
        "onem": karar.get("onem"),
        "sha": karar.get("sha"),
        "pr": karar.get("pr"),
        "bulgu_sayisi": len(bulgular),
        "durum": durum,
        "zaman": karar.get("zaman", ""),
    }
    satirlar += [
        "<details><summary>makine-okunabilir karar</summary>",
        "",
        "```json",
        json.dumps(makine_blogu, ensure_ascii=False, indent=1),
        "```",
        "",
        "</details>",
        "",
        "_yourkiosk otomasyonu · elle düzenlemeyin (sonraki koşuda üzerine yazılır)_",
    ]
    return "\n".join(satirlar)


def gunluk_no(depo: str, token: str) -> int | None:
    """PR'sız commit kararları için TEK bir günlük konusu (issue) bulur/oluşturur.

    Neden: commit durumunun `description` alanı 140 karakterle sınırlı → gerekçe kayboluyordu.
    PR yoksa (main'e düşen commit) tam rapor bu konuya yorum olarak yazılır.
    """
    kod, liste = istek(f"/repos/{depo}/issues?state=all&per_page=100", token)
    if kod == 200 and isinstance(liste, list):
        for konu in liste:
            if str(konu.get("title", "")).startswith("i5/i3 güvenlik günlüğü"):
                return int(konu["number"])
    for etiket in ({"name": "otomasyon", "color": "5319e7"},):
        istek(f"/repos/{depo}/labels", token, "POST", {**etiket, "description": "otomasyon kayıtları"})
    kod, veri = istek(
        f"/repos/{depo}/issues",
        token,
        "POST",
        {
            "title": GUNLUK_BASLIK,
            "labels": ["otomasyon"],
            "body": "Otomasyonun **PR'sız commit** kararları burada toplanır (i5/i3). Elle düzenlemeyin.",
        },
    )
    if kod in (200, 201) and isinstance(veri, dict) and veri.get("number"):
        print(f"[yaz] günlük konusu açıldı: #{veri['number']}")
        return int(veri["number"])
    return None


def etiket_ekle(depo: str, token: str, no: int, eklenecek: list[str], cikarilacak: list[str], kuru: bool) -> None:
    for etiket in eklenecek:
        if kuru:
            print(f"[yaz][KURU] etiket ekle: {etiket}")
            continue
        kod, _ = istek(f"/repos/{depo}/issues/{no}/labels", token, "POST", {"labels": [etiket]})
        if kod == 404:  # etiket depoda yok → önce oluştur, sonra ekle
            istek(f"/repos/{depo}/labels", token, "POST",
                  {"name": etiket, "color": "0e8a16" if "onay" in etiket else "b60205"})
            istek(f"/repos/{depo}/issues/{no}/labels", token, "POST", {"labels": [etiket]})
    for etiket in cikarilacak:
        if kuru:
            print(f"[yaz][KURU] etiket çıkar: {etiket}")
            continue
        istek(f"/repos/{depo}/issues/{no}/labels/{urllib.parse.quote(etiket, safe='')}", token, "DELETE")


def birlestir(depo: str, token: str, pr_no: int, sha: str, kuru: bool) -> tuple[bool, str]:
    """PR'ı SQUASH ile birleştirir — yalnız güvenli koşullarda.

    Koruma katmanları (hepsi sağlanmazsa birleştirmez):
      · PR açık, taslak değil, `mergeable_state == clean`,
      · PR'ın head sha'sı kararın işaretlediği sha ile AYNI (incelenen kod birleşsin),
      · engelleyici etiket yok (`guvenlik/sorun`, `duzeltme/gerekli`, `birlestirme/durdur`),
      · head sha üzerindeki tüm durum kontrolleri başarılı (pending/failure varsa bekle).
    """
    kod, pr = istek(f"/repos/{depo}/pulls/{pr_no}", token)
    if kod != 200 or not isinstance(pr, dict):
        return False, f"PR okunamadı (HTTP {kod})"
    if pr.get("state") != "open":
        return False, "PR açık değil"
    if pr.get("draft"):
        return False, "PR taslak (draft)"
    if (pr.get("head") or {}).get("sha") != sha:
        return False, "PR'ın head sha'sı değişmiş (yeni commit var) — yeniden inceleme gerekir"
    etiketler = [e.get("name") for e in pr.get("labels", [])]
    engel = [e for e in etiketler if e in ENGELLEYEN_ETIKETLER]
    if engel:
        return False, f"engelleyici etiket: {', '.join(engel)}"
    if pr.get("mergeable_state") != "clean":
        return False, f"birleştirilemez durum: {pr.get('mergeable_state')} (çakışma/eksik kontrol olabilir)"

    kod, durum = istek(f"/repos/{depo}/commits/{sha}/status", token)
    if kod == 200 and isinstance(durum, dict):
        kotu = [s["context"] for s in durum.get("statuses", []) if s.get("state") in ("failure", "pending", "error")]
        if kotu:
            return False, f"başarısız/bekleyen kontroller: {', '.join(kotu)}"

    if kuru:
        return True, "KURU: koşullar uygun, birleştirilecek (squash)"

    kod, yanit = istek(
        f"/repos/{depo}/pulls/{pr_no}/merge",
        token,
        "PUT",
        {"merge_method": "squash", "sha": sha, "commit_title": f"{pr.get('title', '')} (#{pr_no})"},
    )
    if kod in (200, 201) and isinstance(yanit, dict) and yanit.get("merged"):
        return True, f"birleştirildi: {str(yanit.get('sha', ''))[:12]}"
    mesaj = (yanit or {}).get("message") if isinstance(yanit, dict) else ""
    return False, f"birleştirme başarısız (HTTP {kod}): {mesaj}"


def main() -> int:
    ap = argparse.ArgumentParser(description="i5/i3 kararını GitHub'a yaz")
    ap.add_argument("karar", nargs="?", default="", help="karar.json yolu")
    ap.add_argument("--ornek", action="store_true", help="geçerli bir örnek karar dosyası yaz (şablon)")
    ap.add_argument("--depo", default="", help="--ornek için: sha'nın alınacağı git deposu")
    ap.add_argument("--depo-adresi", default="hakkisabah/yourkiosk")
    ap.add_argument("--token-dosya", default=str(Path.home() / ".config/hermes-secrets/github-yourkiosk.token"))
    ap.add_argument("--kuru", action="store_true", help="hiçbir istek atmadan göster")
    ap.add_argument(
        "--birlestir", action="store_true",
        help="karar 'onay' ise PR'ı otomatik birleştir (koruma: etiketler/çakışma/kontrol durumu)",
    )
    a = ap.parse_args()

    # --- şablon üret (JSON elle yazmak hataya açık; bu komut her zaman geçerli dosya üretir)
    if a.ornek:
        depo = a.depo or str(Path(__file__).resolve().parents[2])
        sha = ""
        try:
            sha = subprocess.run(["git", "-C", depo, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=30).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            sha = ""
        ornek = {
            "makine": "i5", "sha": sha, "pr": None, "karar": "onay", "onem": "dusuk",
            "ozet": "Şablon: buraya 1-3 cümlelik değerlendirme yazın.",
            "bulgular": [{"dosya": "yol/dosya.py", "satir": 0, "onem": "dusuk", "aciklama": "örnek bulgu"}],
            "not": "Şablon: geliştiriciye iletilecek not (yoksa boş bırakın).",
            "zaman": datetime.now().isoformat(timespec="seconds"),
        }
        hedef = Path("karar-ornek.json") if not a.karar else Path(a.karar).expanduser()
        hedef.write_text(json.dumps(ornek, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"örnek karar dosyası yazıldı: {hedef}  (sha: {(sha or 'BULUNAMADI')[:12]})")
        print("düzenleyip: python3 otomasyon/betik/yaz.py " + str(hedef) + " --kuru")
        return 0

    if not a.karar:
        print("karar dosyası gerekli (ya da --ornek ile şablon üretin)", file=sys.stderr)
        return 2

    yol = Path(a.karar).expanduser()
    try:
        ham = yol.read_text(encoding="utf-8-sig").strip()
    except OSError as hata:
        print(f"karar dosyası okunamadı: {hata}", file=sys.stderr)
        return 2
    try:
        karar = json.loads(ham)
    except json.JSONDecodeError as hata:
        print(f"karar dosyası GEÇERSİZ JSON: {hata.msg} (satır {hata.lineno}, kolon {hata.colno})", file=sys.stderr)
        print("  ipucu: şablon üret → python3 otomasyon/betik/yaz.py --ornek", file=sys.stderr)
        return 2
    if not isinstance(karar, dict) or not karar.get("karar"):
        print("karar dosyasında 'karar' alanı yok", file=sys.stderr)
        return 2

    makine = str(karar.get("makine", "i5")).lower()
    baglam, onay_etiketi, sorun_etiketi = MAKINE_AYARI.get(makine, MAKINE_AYARI["i5"])
    durum, aciklama = durum_metni(karar)
    govde = yorum_govdesi(karar, durum)

    print(f"[yaz] makine={makine} karar={karar.get('karar')} → commit durumu: {baglam}={durum}")
    print(f"[yaz] açıklama: {aciklama}")

    if a.kuru:
        print("\n--- yayınlanacak yorum ---\n" + govde)
        print("\n--- istekler (KURU) ---")
        print(f"POST /repos/{a.depo_adresi}/statuses/{karar.get('sha')}  {{{durum}, {baglam}}}")
        if karar.get("pr"):
            print(f"POST /repos/{a.depo_adresi}/issues/{karar['pr']}/comments")
        print(f"etiketler: +{[onay_etiketi if durum == 'success' else sorun_etiketi]}")
        if a.birlestir and durum == "success" and karar.get("pr"):
            print(f"[KURU] otomatik birleştirme denenecek: PR #{karar['pr']} (squash)")
        return 0

    token = token_oku(a.token_dosya)
    if not token:
        print("token yok: ~/.config/hermes-secrets/github-yourkiosk.token (ya da GH_TOKEN)", file=sys.stderr)
        return 3

    sha = str(karar.get("sha") or "").strip()
    if not sha and karar.get("pr"):
        # PR numarası verilmişse head sha'yı API'den çöz (elle sha yazmak gerekmesin)
        kod, pr_veri = istek(f"/repos/{a.depo_adresi}/pulls/{karar['pr']}", token)
        if kod == 200 and isinstance(pr_veri, dict):
            sha = str((pr_veri.get("head") or {}).get("sha", ""))
            karar["sha"] = sha
            print(f"[yaz] PR #{karar['pr']} head sha: {sha[:12]}")
    if not sha:
        print("karar dosyasında 'sha' yok (ve pr yok) → commit durumu işaretlenemez", file=sys.stderr)
        return 2

    kod, yanit = istek(
        f"/repos/{a.depo_adresi}/statuses/{sha}",
        token,
        "POST",
        {"state": durum, "context": baglam, "description": aciklama, "target_url": karar.get("url") or ""},
    )
    print(f"[yaz] commit durumu: HTTP {kod}" + ("" if kod < 400 else f" → {yanit}"))
    if kod >= 400:
        return 4

    pr_no = karar.get("pr")
    if pr_no:
        kod, yanit = istek(f"/repos/{a.depo_adresi}/issues/{pr_no}/comments", token, "POST", {"body": govde})
        print(f"[yaz] PR #{pr_no} yorumu: HTTP {kod}" + ("" if kod < 400 else f" → {yanit}"))
        etiket_ekle(
            a.depo_adresi,
            token,
            int(pr_no),
            [onay_etiketi if durum == "success" else sorun_etiketi],
            [sorun_etiketi if durum == "success" else onay_etiketi],
            kuru=False,
        )
        print("[yaz] etiketler güncellendi")

        if a.birlestir and durum == "success":
            basarili, neden = birlestir(a.depo_adresi, token, int(pr_no), sha, kuru=False)
            print(f"[yaz] otomatik birleştirme: {'✓' if basarili else '✗'} {neden}")
            if not basarili:
                # nedeni PR'a yaz (görünür olsun, sessizce kalmasın)
                istek(
                    f"/repos/{a.depo_adresi}/issues/{pr_no}/comments",
                    token,
                    "POST",
                    {"body": f"⚙️ **Otomatik birleştirme yapılmadı:** {neden}\n\n"
                             "Düzeltme gerekmiyorsa PR'ı elle birleştirebilirsiniz; "
                             "yeniden denemek için `hermes cron run <job_id>`."},
                )
    else:
        # PR YOK (main'e düşen/rebase edilmiş commit): tam rapor günlük konusuna yazılır,
        # aksi hâlde yalnız 140 karakterlik durum açıklaması kalır ve gerekçe kaybolur.
        no = gunluk_no(a.depo_adresi, token)
        if no:
            baslik = f"#### `{sha[:12]}` · {karar.get('zaman') or ''} · {makine}\n\n"
            kod, yanit = istek(
                f"/repos/{a.depo_adresi}/issues/{no}/comments", token, "POST", {"body": baslik + govde}
            )
            print(f"[yaz] günlük #{no} yorumu: HTTP {kod}" + ("" if kod < 400 else f" → {yanit}"))
        else:
            print("[yaz] uyarı: günlük konusu bulunamadı/oluşturulamadı (PR'sız commit raporu kaydedilemedi)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
