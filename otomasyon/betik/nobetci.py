#!/usr/bin/env python3
"""nobetci — olay güdümlü i5/i3 nöbetçisi (cron yerine).

NEDEN: `hermes cron` her turda bir oturum açar; 30 dakikalık aralıkta iş olmasa da oturum sayısı
büyür ve PR'lar en kötü 30 dakika bekler. Nöbetçi tek bir uzun ömürlü süreçtir:

  * GitHub'ı **koşullu istek** (ETag / If-None-Match) ile yoklar → değişiklik yoksa 304 döner,
    yanıt gövdesi indirilmez ve 304'ler oran sınırına sayılmaz (GitHub belgelenmiş davranışı),
  * **yapılacak iş listesi** çıkarır (rol başına: i5 → incelenecek PR'lar, i3 → karar/merge),
  * liste boşsa **hiç oturum açmaz** (0 token),
  * liste doluysa **tek** `hermes chat -q` oturumu açar ve o turda listedeki TÜM PR'ları işler,
  * iş bitince uyur; yeni commit/PR geldiğinde en geç `--aralik` saniye içinde yeniden uyanır.

Böylece: boşta 0 oturum, olay başına ~1 oturum, gecikme saniyeler (cron: dakikalar).

Kullanım:
    ./otomasyon/betik/nobetci.py --rol i5 --durum          # durum (tek sefer, oturum açmaz)
    ./otomasyon/betik/nobetci.py --rol i5 --bir-kez --kuru # ne yapacağını göster, çalıştırma
    ./otomasyon/betik/nobetci.py --rol i5 --bir-kez        # tek tur (test)
    ./otomasyon/betik/nobetci.py --rol i5                  # 7/24 döngü (systemd servisi bunu çalıştırır)

Servis kurulumu: ./otomasyon/nobetci-kur.sh i5
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEPO_VARSAYILAN = Path(__file__).resolve().parents[2]
DURUM_KLASORU = Path.home() / ".local" / "state" / "yourkiosk-otomasyon"
TOKEN_VARSAYILAN = Path.home() / ".config" / "hermes-secrets" / "github-yourkiosk.token"

ZORUNLU = ("guvenlik/inceleme", "guvenlik/karar")
ONAY_ETIKETI = "guvenlik/onay"
SORUN_ETIKETI = "guvenlik/sorun"


def simdi() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def gunluk(yol: Path | None, mesaj: str) -> None:
    satir = f"[{simdi()}] {mesaj}"
    print(satir, flush=True)
    if yol:
        yol.parent.mkdir(parents=True, exist_ok=True)
        with yol.open("a", encoding="utf-8") as f:
            f.write(satir + "\n")


class Github:
    """ETag önbellekli, oran sınırına duyarlı küçük GitHub istemcisi."""

    def __init__(self, token: str, depo: str, durum_yolu: Path, gunluk_yolu: Path | None = None):
        self.token = token
        self.depo = depo
        self.durum_yolu = durum_yolu
        self.gunluk = gunluk_yolu
        self.onbellek: dict[str, dict] = {}
        if durum_yolu.exists():
            try:
                self.onbellek = json.loads(durum_yolu.read_text(encoding="utf-8")).get("etag", {})
            except ValueError:
                self.onbellek = {}

    def kaydet(self, ek: dict) -> None:
        self.durum_yolu.parent.mkdir(parents=True, exist_ok=True)
        veri = {"etag": self.onbellek, **ek, "guncelleme": simdi()}
        gecici = self.durum_yolu.with_suffix(".tmp")
        gecici.write_text(json.dumps(veri, indent=2), encoding="utf-8")
        gecici.replace(self.durum_yolu)

    def al(self, yol: str) -> tuple[int, object | None]:
        url = f"https://api.github.com{yol}"
        basliklar = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "yourkiosk-nobetci",
        }
        eski = self.onbellek.get(url)
        if eski and "etag" in eski:
            basliklar["If-None-Match"] = eski["etag"]
        istek = urllib.request.Request(url, headers=basliklar)
        try:
            with urllib.request.urlopen(istek, timeout=30) as r:
                govde = json.loads(r.read().decode())
                etag = r.headers.get("ETag")
                if etag:
                    self.onbellek[url] = {"etag": etag, "veri": govde}
                return r.status, govde
        except urllib.error.HTTPError as hata:
            if hata.code == 304:
                return 304, eski.get("veri") if eski else None
            if hata.code in (403, 429):
                kalan = hata.headers.get("X-RateLimit-Remaining")
                gunluk(self.gunluk, f"UYARI: GitHub {hata.code} (kalan {kalan}) — bekleniyor")
            else:
                gunluk(self.gunluk, f"UYARI: {yol} → HTTP {hata.code} {hata.read()[:160]!r}")
            return hata.code, None
        except (urllib.error.URLError, TimeoutError) as hata:
            gunluk(self.gunluk, f"UYARI: ağ hatası ({hata}) — bekleniyor")
            return 0, None


def birlesik_durumlar(gh: Github, sha: str) -> dict[str, str]:
    """commit'e yazılmış durum kontrolleri → {bağlam: durum}"""
    kod, govde = gh.al(f"/repos/{gh.depo}/commits/{sha}/status")
    if kod in (0, 304) and not govde:
        return {}
    if not isinstance(govde, dict):
        return {}
    return {s.get("context", "?"): s.get("state", "?") for s in govde.get("statuses", [])}


def isler(gh: Github, rol: str, limit: int) -> list[dict]:
    """Rol için yapılacak işler. i5: incelenecek PR'lar · i3: karar/merge edilecek PR'lar."""
    kod, govde = gh.al(f"/repos/{gh.depo}/pulls?state=open&per_page={max(limit, 1)}")
    if kod == 304 and govde is None:
        return []
    if not isinstance(govde, list):
        return []

    cikti: list[dict] = []
    for pr in govde[:limit]:
        if pr.get("draft"):
            continue
        no = pr["number"]
        sha = pr["head"]["sha"]
        etiketler = {e["name"] for e in pr.get("labels", [])}
        durumlar = birlesik_durumlar(gh, sha)
        inceleme = durumlar.get(ZORUNLU[0])
        karar = durumlar.get(ZORUNLU[1])

        if rol == "i5":
            # incelenmemiş (ya da sorun bulunup etiketlenmiş) PR'lar
            if inceleme != "success" or SORUN_ETIKETI in etiketler:
                cikti.append({"pr": no, "sha": sha, "baslik": pr["title"], "etiketler": sorted(etiketler),
                              "inceleme": inceleme, "karar": karar})
        else:  # i3 — yalnız i5 onay verdikten sonra çalışır
            if inceleme == "success" and (karar != "success" or ONAY_ETIKETI not in etiketler):
                cikti.append({"pr": no, "sha": sha, "baslik": pr["title"], "etiketler": sorted(etiketler),
                              "inceleme": inceleme, "karar": karar})
    return cikti


def gorev_metni(rol: str, depo: Path, is_listesi: list[dict]) -> str:
    satirlar = [
        f"Sen {rol} makinesindeki nöbetçi ajansın. Aşağıdaki PR'lar için sırayla iş yap.",
        f"Proje kökü: {depo}",
        "",
        "UYGULANACAK AKIŞ: " + ("otomasyon/prompt/i5-guvenlik.md" if rol == "i5" else "otomasyon/prompt/i3-karar.md"),
        "Bu dosyayı oku ve TAM olarak onu uygula (komutlar, karar JSON şeması, sınırlar).",
        "",
        "YAPILACAKLAR:",
    ]
    for is_ in is_listesi:
        not_ = []
        if is_.get("inceleme"):
            not_.append(f"inceleme={is_['inceleme']}")
        if is_.get("karar"):
            not_.append(f"karar={is_['karar']}")
        ek = f" ({', '.join(not_)})" if not_ else ""
        satirlar.append(f"- PR #{is_['pr']} · head {is_['sha'][:12]} · {is_['baslik']}{ek}")
    if rol == "i3":
        satirlar += ["", "i5 onayı olan ve birleştirilebilir PR'ları `--birlestir --cift-onay` ile BİRLEŞTİR.",
                     "Bir PR birleşince diğerleri 'behind' kalabilir; o PR'a 'dal güncellenmeli' yorumu bırak."]
    satirlar += ["", "Bitince kısa bir özet yaz: hangi PR'a ne yazdın, ne birleşti."]
    return "\n".join(satirlar) + "\n"


def hermes_calistir(depo: Path, metin: str, rol: str, zaman_asimi: int, kuru: bool) -> tuple[int, str]:
    if kuru:
        print("\n--- ÇALIŞTIRILACAK GÖREV ---")
        print(metin)
        return 0, "kuru"
    gorev = DURUM_KLASORU / f"gorev-{rol}.md"
    gorev.parent.mkdir(parents=True, exist_ok=True)
    gorev.write_text(metin, encoding="utf-8")
    komut = ["hermes", "chat", "--query-file", str(gorev), "--oneshot",
             "--max-turns", "60", "--run-budget", str(max(120, zaman_asimi - 60)),
             "--in", str(depo), "--source", "nobetci"]
    try:
        sonuc = subprocess.run(komut, capture_output=True, text=True, timeout=zaman_asimi)
        return sonuc.returncode, (sonuc.stdout or "") + (sonuc.stderr or "")
    except FileNotFoundError:
        return 127, "hermes bulunamadı (PATH)"
    except subprocess.TimeoutExpired:
        return 124, f"zaman aşımı ({zaman_asimi}s)"


def tek_tur(gh: Github, depo: Path, rol: str, limit: int, kuru: bool, zaman_asimi: int,
            gunluk_yolu: Path | None) -> int:
    is_listesi = isler(gh, rol, limit)
    if not is_listesi:
        gunluk(gunluk_yolu, f"{rol}: iş yok (0 oturum)")
        gh.kaydet({"rol": rol, "is": 0, "son_karar": "bos"})
        return 0
    gunluk(gunluk_yolu, f"{rol}: {len(is_listesi)} iş → oturum açılıyor: "
                        + ", ".join(f"#{i['pr']}" for i in is_listesi))
    kod, cikti = hermes_calistir(depo, gorev_metni(rol, depo, is_listesi), rol, zaman_asimi, kuru)
    gunluk(gunluk_yolu, f"{rol}: oturum bitti (çıkış {kod})")
    gh.kaydet({"rol": rol, "is": len(is_listesi), "son_karar": "calisti", "cikis": kod,
               "prlar": [i["pr"] for i in is_listesi]})
    if kod != 0 and cikti:
        gunluk(gunluk_yolu, "çıktı (son 600 karakter): " + cikti[-600:].replace("\n", " ⏎ "))
    return kod


def main() -> int:
    ayar = argparse.ArgumentParser(description="yourkiosk nöbetçi (olay güdümlü i5/i3)")
    ayar.add_argument("--rol", choices=["i5", "i3"], required=True)
    ayar.add_argument("--aralik", type=int, default=15, help="yoklama aralığı sn (varsayılan 15)")
    ayar.add_argument("--limit", type=int, default=8, help="tur başına en çok PR")
    ayar.add_argument("--bir-kez", action="store_true", help="tek tur çalış ve çık (test)")
    ayar.add_argument("--kuru", action="store_true", help="oturum açma, görevi yazdır")
    ayar.add_argument("--durum", action="store_true", help="durum dosyasını yazdır ve çık")
    ayar.add_argument("--zaman-asimi", type=int, default=1200, help="oturum zaman aşımı sn")
    ayar.add_argument("--depo", type=Path, default=DEPO_VARSAYILAN)
    ayar.add_argument("--token", type=Path, default=TOKEN_VARSAYILAN)
    ayar.add_argument("--log", type=Path, default=None)

    secim = ayar.parse_args()
    durum_yolu = DURUM_KLASORU / f"nobetci-{secim.rol}.json"
    gunluk_yolu = secim.log or (DURUM_KLASORU / f"nobetci-{secim.rol}.log")

    if secim.durum:
        if not durum_yolu.exists():
            print(f"durum yok: {durum_yolu} (nöbetçi hiç çalışmamış)")
            return 1
        veri = json.loads(durum_yolu.read_text(encoding="utf-8"))
        print(f"nöbetçi durumu · {secim.rol} · {durum_yolu}")
        for anahtar, deger in veri.items():
            if anahtar == "etag":
                print(f"  etag önbelleği : {len(deger)} adres")
            else:
                print(f"  {anahtar:15s}: {deger}")
        return 0

    if not secim.token.exists():
        print(f"✗ token yok: {secim.token}", file=sys.stderr)
        return 2
    token = secim.token.read_text(encoding="utf-8").strip()
    depo_adi = os.environ.get("GITHUB_DEPO", "hakkisabah/yourkiosk")

    # tek örnek: iki nöbetçi aynı anda çalışırsa aynı PR'a iki oturum açar
    DURUM_KLASORU.mkdir(parents=True, exist_ok=True)
    kilit = DURUM_KLASORU / f"nobetci-{secim.rol}.lock"
    kilit_dosya = kilit.open("w")
    try:
        fcntl.flock(kilit_dosya, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(f"✗ zaten çalışan bir nöbetçi var ({kilit})", file=sys.stderr)
        return 3

    gh = Github(token, depo_adi, durum_yolu, gunluk_yolu)
    gunluk(gunluk_yolu, f"nöbetçi başladı · rol={secim.rol} · aralık={secim.aralik}s · depo={depo_adi}")

    if secim.bir_kez:
        return tek_tur(gh, secim.depo, secim.rol, secim.limit, secim.kuru, secim.zaman_asimi, gunluk_yolu)

    hata_sayaci = 0
    while True:
        try:
            kod = tek_tur(gh, secim.depo, secim.rol, secim.limit, secim.kuru, secim.zaman_asimi, gunluk_yolu)
            hata_sayaci = 0 if kod == 0 else hata_sayaci + 1
        except Exception as hata:  # nöbetçi asla ölmesin
            hata_sayaci += 1
            gunluk(gunluk_yolu, f"HATA: {type(hata).__name__}: {hata}")
        bekle = min(secim.aralik * (2 ** min(hata_sayaci, 5)), 600) if hata_sayaci else secim.aralik
        time.sleep(bekle)


if __name__ == "__main__":
    raise SystemExit(main())
