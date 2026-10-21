#!/usr/bin/env python3
"""BAĞLAM PAKETİ (i5/i3 makineleri) — son inceleme noktasından bu yana değişenler + taramalar.

Bu betik **karar vermez**: yalnızca o makinedeki Hermes ajanına inceleyeceği malzemeyi toplar
(diff + otomatik tarama bulguları + açık PR'lar). Kararı ajan verir, sonucu `yaz.py` yayınlar.

Tasarım ilkeleri (düşük donanım: i5/i3):
  * Ağ maliyeti: yalnız `git fetch` (tek sefer) + token varsa 1 API isteği (açık PR'lar).
  * Model maliyeti: değişiklik yoksa çıktı `degisiklik: false` → ajan modeli HİÇ çağırmaz.
  * Kırpma: diff en fazla `--sinir-bayt` (varsayılan 120 KB); kilit dosyaları ve ikili dosyalar atlanır.
  * Sır sızıntısı: bulunan sır örnekleri **maskelenir** (ilk 4 karakter + ***), günlüğe ham yazılmaz.

Kullanım:
    ./topla.py --depo ~/yourkiosk --durum ~/.local/state/yourkiosk-i5
    ./topla.py --ilk          # ilk çalıştırma: son nokta yok → son 50 commit'e bak
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------- tarama kuralları
SIR_KURALLARI = [
    ("github-token", re.compile(r"github_pat_[A-Za-z0-9_]{20,}|ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}")),
    ("aws-anahtar", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("ozel-anahtar", re.compile(r"-----BEGIN (?:RSA|OPENSSH|EC|PGP) PRIVATE KEY-----")),
    ("parola-atama", re.compile(r"(?i)\b(?:password|parola|passwd|secret|api[_-]?key)\s*[:=]\s*[\"'][^\"'\s]{6,}[\"']")),
    ("bearer", re.compile(r"(?i)bearer\s+[A-Za-z0-9\-_\.]{20,}")),
]

RISK_KURALLARI = [
    ("kabuk-enjeksiyonu", re.compile(r"shell\s*=\s*True")),
    ("os.system", re.compile(r"os\.system\s*\(")),
    ("eval/exec", re.compile(r"\b(?:eval|exec)\s*\(")),
    ("pickle", re.compile(r"pickle\.loads?\s*\(")),
    ("tls-dogrulama-kapali", re.compile(r"verify\s*=\s*False")),
    ("sifresiz-http", re.compile(r"http://(?!127\.0\.0\.1|localhost)")),
    ("izin-777", re.compile(r"chmod\s*\(?\s*0?777")),
    ("v-html/innerHTML", re.compile(r"v-html|innerHTML\s*=|dangerouslySetInnerHTML")),
    ("cors-yildiz", re.compile(r"allow_origins\s*=\s*\[?\s*[\"']\*")),
]

ATLANAN_DOSYALAR = re.compile(
    r"(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|node_modules/|dist/|\.venv/|__pycache__/|"
    r"\.git/|_arsiv/|\.cache/|\.tarayici-profil/)"
)
IKILI_UZANTILAR = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2", ".ttf", ".pdf", ".zip", ".mp4", ".mp3"}


# ---------------------------------------------------------------- yardımcılar
def git(depo: Path, *arg: str, kisa: bool = False, sessiz: bool = False) -> str:
    """git komutunu çalıştırır (hata → boş metin; betik durmaz).

    `sessiz=True` → hata mesajı stderr'e yazılmaz (monitor modunda gürültü olmasın).
    """
    try:
        sonuc = subprocess.run(
            ["git", "-C", str(depo), *arg], capture_output=True, text=True, timeout=180, check=False
        )
    except (OSError, subprocess.SubprocessError) as hata:
        if not sessiz:
            print(f"[topla] git hatası: {hata}", file=sys.stderr)
        return ""
    if sonuc.returncode != 0 and sonuc.stderr.strip() and not sessiz:
        print(f"[topla] git {' '.join(arg)}: {sonuc.stderr.strip()[:200]}", file=sys.stderr)
    return sonuc.stdout if not kisa else (sonuc.stdout or sonuc.stderr)


def depo_bul(verilen: str) -> Path:
    """Depo yolunu bul: --depo → KIOSK_YOLU → ~/calisma_konumun/yourkiosk → ~/yourkiosk → cwd.

    Yanlış yolda sessizce "0 commit / 0 dosya" demek yerine açık hata verir (KURULUM.md'de
    anlatılan "bulunamadı ama sonuçlar sıfır" durumunun nedeni buydu).
    """
    adaylar: list[Path] = []
    if verilen:
        aday = Path(verilen).expanduser()
        if not ((aday / ".git").exists() or (aday / ".git").is_file()):
            print(f"[topla] HATA: --depo verilen yol bir git deposu değil: {aday}", file=sys.stderr)
            print("[topla] ipucu: depo kökünü verin (içinde .git olan klasör) ya da KIOSK_YOLU ayarlayın", file=sys.stderr)
            raise SystemExit(2)
        adaylar.append(aday)
    if os.environ.get("KIOSK_YOLU"):
        adaylar.append(Path(os.environ["KIOSK_YOLU"]).expanduser())
    adaylar += [Path.home() / "calisma_konumun" / "yourkiosk", Path.home() / "projeler" / "yourkiosk", Path.home() / "yourkiosk", Path.cwd()]
    for aday in adaylar:
        if (aday / ".git").exists() or (aday / ".git").is_file():
            return aday
    print("[topla] HATA: git deposu bulunamadı. Denenen yollar:", file=sys.stderr)
    for aday in adaylar:
        print(f"         · {aday}", file=sys.stderr)
    print("[topla] çözüm: --depo /yol/yourkiosk  ya da  export KIOSK_YOLU=/yol/yourkiosk", file=sys.stderr)
    raise SystemExit(2)


def on_ek_kes(metin: str, on_ek: str) -> str:
    """`str.removeprefix` yerine (Python 3.8 uyumu: i5/i3 makineleri eski olabilir)."""
    return metin[len(on_ek):] if on_ek and metin.startswith(on_ek) else metin


def maskele(metin: str) -> str:
    """Sır örneğini maskeler: ilk 4 karakter + *** (ham sır hiçbir yere yazılmaz)."""
    metin = metin.strip()
    return (metin[:4] + "***") if len(metin) > 8 else "***"


def tara(diff: str) -> dict:
    """Eklenen satırlarda sır + riskli kod taraması (yalnız `+` satırları)."""
    sirlar: list[dict] = []
    riskler: list[dict] = []
    dosya, satir_no = "?", 0
    for satir in diff.splitlines():
        if satir.startswith("+++ "):
            dosya = on_ek_kes(satir[4:].strip(), "b/")
            satir_no = 0
            continue
        if satir.startswith("@@"):
            bulunan = re.search(r"\+(\d+)", satir)
            satir_no = int(bulunan.group(1)) - 1 if bulunan else 0
            continue
        if satir.startswith("+"):
            satir_no += 1
            icerik = satir[1:]
            for ad, kalip in SIR_KURALLARI:
                for eslesme in kalip.finditer(icerik):
                    sirlar.append({"dosya": dosya, "satir": satir_no, "tur": ad, "ornek": maskele(eslesme.group(0))})
            for ad, kalip in RISK_KURALLARI:
                if kalip.search(icerik):
                    riskler.append({"dosya": dosya, "satir": satir_no, "tur": ad, "ornek": icerik.strip()[:160]})
    return {"sirlar": sirlar[:50], "riskli_kod": riskler[:80]}


def api(yol: str, token: str | None, taban: str = "https://api.github.com") -> object | None:
    """GET isteği (token yoksa None). Ağ hatasında None döner — betik durmaz."""
    istek = urllib.request.Request(
        f"{taban}{yol}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "yourkiosk-otomasyon",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(istek, timeout=20) as yanit:
            return json.loads(yanit.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError) as hata:
        print(f"[topla] API hatası {yol}: {hata}", file=sys.stderr)
        return None


def token_oku(yol: str | None) -> str | None:
    if yol:
        try:
            return Path(yol).expanduser().read_text(encoding="utf-8").strip() or None
        except OSError:
            return None
    return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")


def cikti_ver(paket: dict, cikti: str) -> None:
    """Paketi (istenirse) dosyaya yazar, her durumda stdout'a basar."""
    metin = json.dumps(paket, ensure_ascii=False, indent=1)
    if cikti:
        Path(cikti).expanduser().write_text(metin, encoding="utf-8")
        print(f"[topla] paket yazıldı: {cikti}  (değişiklik: {paket.get('degisiklik')}, "
              f"{len(paket.get('commitler', []))} commit, {len(paket.get('degisen_dosyalar', []))} dosya)")
        bulgular = paket.get("taramalar", {})
        print(f"[topla] sır bulgusu: {len(bulgular.get('sirlar', []))} · riskli kod: {len(bulgular.get('riskli_kod', []))}")
        for uyari in paket.get("uyarilar", []):
            print(f"[topla] uyarı: {uyari}")
    else:
        print(metin)


def main() -> int:
    ap = argparse.ArgumentParser(description="i5/i3 için bağlam paketi")
    ap.add_argument("--depo", default="", help="git deposu (boşsa: KIOSK_YOLU → ~/calisma_konumun/yourkiosk → ~/yourkiosk)")
    ap.add_argument("--imza", action="store_true", help="yalnız uzak HEAD sha'sını yazdır (cron --monitor-script için)")
    ap.add_argument("--imza-sorun", action="store_true", help="guvenlik/sorun etiketli PR'ların 'no:sha' listesi (i3 monitor)")
    ap.add_argument("--durum", default=str(Path.home() / ".local/state/yourkiosk-otomasyon"))
    ap.add_argument("--token-dosya", default=str(Path.home() / ".config/hermes-secrets/github-yourkiosk.token"))
    ap.add_argument("--depo-adresi", default="hakkisabah/yourkiosk")
    ap.add_argument("--sinir-bayt", type=int, default=120_000)
    ap.add_argument("--ilk", action="store_true", help="ilk çalıştırma: son 50 commit'e bak")
    ap.add_argument("--cikti", default="", help="paketi bu dosyaya da yaz")
    a = ap.parse_args()

    depo = depo_bul(a.depo)
    durum = Path(a.durum).expanduser()

    # --- MONITOR MODLARI: deterministik çıktı (değişmediyse Hermes ajanı HİÇ çalışmaz)
    if a.imza or a.imza_sorun:
        git(depo, "fetch", "origin", "--prune", "--quiet", sessiz=True)
        dal = git(depo, "rev-parse", "--abbrev-ref", "origin/HEAD", kisa=True).strip().replace("origin/", "") or "main"
        if a.imza:
            print(git(depo, "rev-parse", f"origin/{dal}", kisa=True).strip())
            return 0
        token = token_oku(a.token_dosya)
        if not token:
            print("[topla] uyarı: token yok → uyarı listesi boş", file=sys.stderr)
            print("")
            return 0
        kayitlar = api(f"/repos/{a.depo_adresi}/issues?state=open&labels=guvenlik/sorun&per_page=20", token)
        satirlar = []
        if isinstance(kayitlar, list):
            for kayit in kayitlar:
                satirlar.append(f"{kayit.get('number')}:{(kayit.get('head') or {}).get('sha', '')[:12] or kayit.get('updated_at', '')}")
        guncel = api(f"/repos/{a.depo_adresi}/pulls?state=open&per_page=20", token)
        if isinstance(guncel, list):
            for pr in guncel:
                if "guvenlik/sorun" in [e.get("name") for e in pr.get("labels", [])]:
                    satirlar.append(f"{pr.get('number')}:{(pr.get('head') or {}).get('sha', '')[:12]}")
        print("\n".join(sorted(set(satirlar))))
        return 0

    durum.mkdir(parents=True, exist_ok=True)

    # 1) uzak değişiklikleri çek (uzağın adı 'origin' varsayılır)
    git(depo, "fetch", "origin", "--prune", "--quiet")
    dal = git(depo, "rev-parse", "--abbrev-ref", "origin/HEAD", kisa=True).strip().replace("origin/", "") or "main"
    bas = git(depo, "rev-parse", f"origin/{dal}", kisa=True).strip()

    son_dosya = durum / "son-sha"
    son = ""
    if son_dosya.is_file() and not a.ilk:
        son = son_dosya.read_text(encoding="utf-8").strip()

    paket: dict = {
        "zaman": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "depo": str(depo),
        "dal": dal,
        "bas_sha": bas,
        "son_sha": son,
        "degisiklik": True,
        "commitler": [],
        "degisen_dosyalar": [],
        "diff": "",
        "diff_kisaltildi": False,
        "taramalar": {"sirlar": [], "riskli_kod": []},
        "prlar": [],
        "uyarilar": [],
    }

    if not bas:
        paket.update({"degisiklik": False, "uyarilar": ["depo/dal okunamadı (git fetch başarısız?)"]})
        cikti_ver(paket, a.cikti)
        print("[topla] HATA: 'origin/<dal>' okunamadı. Kontrol: git -C "
              f"{depo} remote -v && git -C {depo} fetch origin", file=sys.stderr)
        return 2

    if son == bas:
        paket["degisiklik"] = False
        cikti_ver(paket, a.cikti)
        return 0

    # 2) commit listesi + diff
    # Karşılaştırma tabanı: kayıtlı son nokta → yoksa bir önceki commit (kök commit'te yok)
    ebeveyn = git(depo, "rev-parse", "--verify", "--quiet", f"{bas}~1", kisa=True).strip()
    taban = son or ebeveyn
    paket["taban_sha"] = taban
    if taban:
        aralik = f"{taban}..{bas}"
        diff_kaynak = ["diff", "--no-color", "-U3", f"{taban}..{bas}"]
    else:
        # tek (kök) commit: `git show` ile yamasını al
        aralik = bas
        diff_kaynak = ["show", "--no-color", "-U3", "--format=", bas]
    paket["aralik"] = aralik

    ham_commitler = git(depo, "log", aralik, "--format=%H%x09%an%x09%aI%x09%s", "--no-merges")
    for satir in ham_commitler.splitlines():
        parcalar = satir.split("\t")
        if len(parcalar) >= 4:
            paket["commitler"].append({"sha": parcalar[0][:12], "yazar": parcalar[1], "tarih": parcalar[2], "baslik": parcalar[3]})

    paket["degisen_dosyalar"] = [
        s for s in git(depo, "diff", "--name-status", aralik).splitlines() if s.strip()
    ][:200] if taban else paket["degisen_dosyalar"]

    tam_diff = git(depo, *diff_kaynak, "--", ".") if taban else git(depo, *diff_kaynak)
    # atlanan dosyaları diff'ten çıkar (kilit dosyası/ikili gürültüsü)
    parcalar, tutulan = re.split(r"(?m)^diff --git ", tam_diff), []
    for parca in parcalar[1:]:
        yol = on_ek_kes(parca.split(" ")[0], "a/")
        if ATLANAN_DOSYALAR.search(yol) or Path(yol).suffix.lower() in IKILI_UZANTILAR:
            continue
        tutulan.append("diff --git " + parca)
    temiz_diff = "".join(tutulan)

    if len(temiz_diff.encode("utf-8")) > a.sinir_bayt:
        paket["diff_kisaltildi"] = True
        paket["diff"] = temiz_diff.encode("utf-8")[: a.sinir_bayt].decode("utf-8", "ignore") + "\n\n… (diff kırpıldı)"
        paket["uyarilar"].append(f"diff {a.sinir_bayt} bayta kırpıldı; tamamı için dosya listesine bakın")
    else:
        paket["diff"] = temiz_diff

    paket["taramalar"] = tara(temiz_diff)

    # 3) açık PR'lar (token varsa; tek API isteği)
    token = token_oku(a.token_dosya)
    if token:
        prlar = api(f"/repos/{a.depo_adresi}/pulls?state=open&per_page=20", token)
        if isinstance(prlar, list):
            for pr in prlar:
                paket["prlar"].append(
                    {
                        "no": pr.get("number"),
                        "baslik": pr.get("title"),
                        "dallar": f"{pr.get('head', {}).get('ref')} → {pr.get('base', {}).get('ref')}",
                        "etiketler": [e.get("name") for e in pr.get("labels", [])],
                        "url": pr.get("html_url"),
                        "head_sha": (pr.get("head") or {}).get("sha", "")[:12],
                        "taslak": pr.get("draft", False),
                    }
                )
    else:
        paket["uyarilar"].append("token yok → açık PR listesi alınamadı (yalnız git verisi)")

    # 4) son noktayı güncelle (karar yazıldıktan sonra da güncellenebilir; kaybetmemek için burada)
    (durum / "son-sha").write_text(bas + "\n", encoding="utf-8")

    metin = json.dumps(paket, ensure_ascii=False, indent=1)
    cikti_ver(paket, a.cikti) if a.cikti else print(metin)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
