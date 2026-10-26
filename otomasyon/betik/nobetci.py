#!/usr/bin/env python3
"""nobetci — olay güdümlü i5/i3 nöbetçisi (cron yerine).

NEDEN: `hermes cron` her turda bir oturum açar; 30 dakikalık aralıkta iş olmasa da oturum sayısı
büyür ve PR'lar en kötü 30 dakika bekler. Nöbetçi tek bir uzun ömürlü süreçtir:

  * GitHub'ı **koşullu istek** (ETag / If-None-Match) ile yoklar → değişiklik yoksa 304 döner,
    yanıt gövdesi indirilmez ve 304'ler oran sınırına sayılmaz (GitHub belgelenmiş davranışı),
  * **yapılacak iş listesi** çıkarır (rol başına: i5 → incelenecek PR'lar, i3 → karar/merge),
  * liste boşsa **hiç oturum açmaz** (0 token),
  * liste doluysa **tek** `hermes chat -q` oturumu açar; o oturum listeden `OTURUM_BASI_PR` kadar
    PR alır (i5: 1, i3: 3) ve kalanlar bir sonraki tura kalır (zaman aşımını önler),
  * liste **en eski PR önce** sıralanır; bu yüzden yeni bir PR eskiyi asla aç bırakmaz,
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
import re
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

# "Bu sha için karar YAZILDI" sayılan durumlar. Yalnız `success`/`failure` terminaldir:
# `pending` (yarım yazım / ağ kesintisi) ve `error` (yaz.py çöktü) KARAR DEĞİLDİR. 26 Ekim i5
# bulgusu: eski kod "inceleme != success" olan her şeyi "karara bağlı" sayıp atlıyordu →
# yarım kalmış bir durum PR'ı yeni commit gelmeden sonsuza kadar kuyruktan düşürüyordu.
YAZILMIS_DURUMLAR = {"success", "failure"}
UNIT_ADI = "yourkiosk-nobetci.service"
SORUN_ETIKETI = "guvenlik/sorun"

# OTURUM BAŞINA PR (zaman aşımı düzeltmesi): iki büyük PR tek oturuma verildiğinde 1200 sn'lik
# bütçe yetmiyordu ve oturum `çıkış 124` ile ölüyordu (günlükte 17:35 ve 17:55 turları). Karar
# yazılmadığı için nöbetçi aynı PR'ları "beklemede" sayıp tekrar deniyordu — sıra ilerlemiyordu.
# Çözüm: i5 bir oturumda TEK PR inceler (derin inceleme zaten PR başına ~20 dk), i3 kararları
# hızlı olduğu için birkaç PR'ı birlikte işler. Kalanlar bir sonraki turda (aralık 15 sn) alınır.
OTURUM_BASI_PR = {"i5": 1, "i3": 3}

# TUR TAVANI (2026-10-25): 60 tur, derin incelemeye YETMİYOR. Günlükte 19:58–20:49 arası
# oturumlar "⚠ Iteration budget reached (60/60) — response may be incomplete" ile bitti ve
# PR'lara YENİ karar yazılmadı: #86/#84/#83 aynı head'lerle kuyrukta dönüp durdu (i3'ün
# "dal güncellenmeli" yorumları i5 kararı gelmediği için birikiyordu). Sebep: inceleme
# 120+ araç çağrısı sürüyor (testler 50-60 sn, çok dosya okuma).
OTURUM_TUR_TAVANI = 120

# TUR ↔ DUVAR SAATİ TUTARLILIĞI (25 Ekim i3 bulgusu): tavan 120'ye çıkarken bütçe sabit kalırsa
# tur başına ~9 sn düşer ve inceleme yine yarıda kesilir. Bu yüzden varsayılan zaman aşımı TÜRETİLİR:
# tavan × tur payı + kapanış payı. Tek sayı değişince diğerleri kendiliğinden uyar.
TUR_SURE_PAYI_S = 15          # tur başına beklenen duvar saati (araç çağrısı + model)
KAPANIS_PAYI_S = 60           # özet/karar yazımı için ayrılan pay
VARSAYILAN_ZAMAN_ASIMI = OTURUM_TUR_TAVANI * TUR_SURE_PAYI_S + KAPANIS_PAYI_S  # 1860 sn
#: Tur başına KABUL EDİLEBİLİR en az duvar saati. Altına inerse tur tavanı anlamsızlaşır
#: (araç çağrısı + model yanıtı yetişmez) → tavan bütçeye göre KISILIR (duvar saati aşılmaz).
EN_AZ_TUR_SURESI_S = 10


def butce_hesapla(zaman_asimi: int) -> dict[str, int]:
    """`--zaman-asimi` → {butce, tur, tur_basi_sn, yeterli} — TEK KAYNAK.

    Kural: duvar saati aşılmaz AMA tavan sessizce yalan söylemez. Bütçe tur başına
    `EN_AZ_TUR_SURESI_S`'den az düşerse etkin tur sayısı kısılır ve bu görünür olur
    (`--tani` + günlük). Böylece `--max-turns 120` yazıp 9,5 sn/tur'a mahkûm olmak bitiyor
    (25 Ekim i3 bulgusu: 1140 sn bütçe / 120 tur).
    """
    butce = max(120, int(zaman_asimi) - KAPANIS_PAYI_S)
    tur = max(1, min(OTURUM_TUR_TAVANI, butce // EN_AZ_TUR_SURESI_S))
    return {
        "butce": butce,
        "tur": tur,
        "tur_basi_sn": butce // tur,
        "yeterli": tur >= OTURUM_TUR_TAVANI,
    }


# AÇLIK EŞİĞİ: GitHub `pulls` listesi EN YENİ PR'ı önce döndürür. Sıralama düzeltilmeden önce
# kuyruk şu şekilde kilitleniyordu (25 Ekim, gerçek vaka): #83 (10:08) ve #84 (10:45) açıldı,
# araya #86 girdi; `limit` ilk N PR'ı aldığı ve oturum başına 1 PR işlendiği için sıra hep #86'ya
# gitti → #83/#84 on saat boyunca `guvenlik/inceleme` durumu OLMADAN bekledi. Çözüm: iş listesi
# PR numarasına/yeniliğe göre değil **yaşa göre (en eski önce)** sıralanır. Bu eşik yalnız
# günlüğe `AÇLIK:` satırı yazmak için (görünürlük); sıralamayı yapan şey sıralamanın kendisi.
ACLIK_ESIGI_DK = 120

# ── AYRI HERMES PROFİLİ (i5 mimarisi, 26 Ekim) ────────────────────────────────────────────────
# Aynı gateway süreci hem Open WebUI sohbetlerini hem nöbetçi oturumunu çalıştırırsa: aynı CPU,
# aynı `max_concurrent_runs`, aynı model kotası ve aynı günlük oturum tavanı paylaşılır. 25 Ekim
# kanıtı: 3 PR tek oturuma verildi, oturum `çıkış 124` ile öldü ve PR'lar saatlerce bekledi.
# Çözüm: nöbetçi AYRI bir profilde (`hermes -p <ad>`) çalışır → kendi config/oturum sayacı/model
# anahtarı. Boşsa davranış eskisi gibi (varsayılan profil).
NOBETCI_PROFIL = os.environ.get("NOBETCI_PROFIL", "").strip()


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
        # DİKKAT (i5 bulgusu 26.10): `gunluk` adı İKİ farklı şeye verilmişti — önce günlük DOSYA
        # YOLU, sonra günlük OTURUM SAYACI sözlüğü. Sözlük kazandığı için `gunluk(self.gunluk, ...)`
        # çağrıları Path bekleyen fonksiyona dict veriyordu → isler() içindeki yeni "karara bağlı"
        # satırı her turda AttributeError ile nöbetçiyi düşürüyordu. Artık iki ad ayrı:
        self.gunluk_yolu: Path | None = gunluk_yolu   # teşhis günlüğü (dosya yolu)
        self.gunluk: dict[str, int] = {}              # günlük OTURUM sayacı (durum dosyasında)
        self.onbellek: dict[str, dict] = {}
        self.denemeler: dict[str, dict] = {}
        self._onceki_veri: dict = {}
        if durum_yolu.exists():
            try:
                eski = json.loads(durum_yolu.read_text(encoding="utf-8"))
                self.onbellek = eski.get("etag", {})
                self.denemeler = eski.get("denemeler", {})
                self.gunluk = eski.get("gunluk", {})
                self._onceki_veri = {"son_karar": eski.get("son_karar", ""), "zaman": eski.get("guncelleme", "")}
            except ValueError:
                pass

    def kaydet(self, ek: dict) -> None:
        self.durum_yolu.parent.mkdir(parents=True, exist_ok=True)
        veri = {"etag": self.onbellek, "denemeler": self.denemeler, "gunluk": self.gunluk,
                **ek, "guncelleme": simdi()}
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
                gunluk(self.gunluk_yolu, f"UYARI: GitHub {hata.code} (kalan {kalan}) — bekleniyor")
            else:
                gunluk(self.gunluk_yolu, f"UYARI: {yol} → HTTP {hata.code} {hata.read()[:160]!r}")
            return hata.code, None
        except (urllib.error.URLError, TimeoutError) as hata:
            gunluk(self.gunluk_yolu, f"UYARI: ağ hatası ({hata}) — bekleniyor")
            return 0, None


def birlesik_durumlar(gh: Github, sha: str) -> dict[str, str | None]:
    """commit'e yazılmış durum kontrolleri → {bağlam: durum}"""
    kod, govde = gh.al(f"/repos/{gh.depo}/commits/{sha}/status")
    if kod in (0, 304) and not govde:
        return {}
    if not isinstance(govde, dict):
        return {}
    return {s.get("context", "?"): s.get("state", "?") for s in govde.get("statuses", [])}


#: Aynı PR+commit için yeniden oturum açmadan önce beklenecek süre (sn). Üstel artar.
BEKLEME_TABANI_S = 600
BEKLEME_TAVAN_S = 3600
#: Günlük en çok oturum (oturum fırtınasına karşı sert fren)
GUNLUK_OTURUM_TAVANI = 120


def anahtar(pr: int, sha: str) -> str:
    return f"{pr}:{sha[:12]}"


def beklemeli_mi(denemeler: dict, pr: int, sha: str, an: float) -> tuple[bool, int]:
    """Bu PR+commit için yakın zamanda denendiyse (True, kalan saniye) döner.

    Neden: karar yazılamadığında (token/izin/geçici hata) nöbetçi her turda yeni bir Hermes
    oturumu açıyordu → i5/i3 panolarında oturum sayısı sürekli artıyordu. Aynı commit'e
    üstel artan bekleme uygulanır (10 dk → 20 → 40 → 60 dk tavan).
    """
    kayit = denemeler.get(anahtar(pr, sha))
    if not kayit:
        return False, 0
    sayi = int(kayit.get("sayi", 1))
    bekleme = min(BEKLEME_TABANI_S * (2 ** max(0, sayi - 1)), BEKLEME_TAVAN_S)
    gecen = an - float(kayit.get("son", 0))
    if gecen < bekleme:
        return True, int(bekleme - gecen)
    return False, 0


def yas_dk(iso: str | None, an: float | None = None) -> int:
    """ISO-8601 zaman damgası → kaç dakika önce (okunamazsa 0)."""
    if not iso:
        return 0
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0
    return max(0, int(((an if an is not None else time.time()) - t) / 60))


def isler(gh: Github, rol: str, limit: int) -> list[dict]:
    """Rol için yapılacak işler — **EN ESKİ PR ÖNCE**.

    Sıralama kritik: GitHub listeyi yeniden-eskiye döndürür. Önceden listeden ilk `limit` PR
    alınıp sonra tek PR işlendiği için, araya giren her yeni PR kuyruğun başına geçiyor ve eski
    PR'lar hiç incelenmiyordu (25 Ekim: #83/#84 → 10 saat `guvenlik/inceleme` olmadan bekledi).
    Bu yüzden: tüm açık PR'lar çekilir (tek istek, `per_page=100`), yaşa göre sıralanır,
    ancak ondan sonra `limit` uygulanır.

    İkinci kural — **aynı sha'ya ikinci karar yazılmaz**: durum kontrolleri commit'e bağlıdır,
    dolayısıyla "bu şerh zaten yazılmış" = "iş geliştiricide". Yeni commit → yeni sha → iş döner.
    """
    kod, govde = gh.al(f"/repos/{gh.depo}/pulls?state=open&per_page=100&sort=created&direction=asc")
    if kod == 304 and govde is None:
        return []
    if not isinstance(govde, list):
        return []

    an = time.time()
    cikti: list[dict] = []
    atlanan = 0  # bu sha için kararı zaten yazılmış PR'lar (top geliştiricide)
    for pr in govde:
        if pr.get("draft"):
            continue
        no = pr["number"]
        sha = pr["head"]["sha"]
        etiketler = {e["name"] for e in pr.get("labels", [])}
        durumlar = birlesik_durumlar(gh, sha)
        inceleme = durumlar.get(ZORUNLU[0])
        karar = durumlar.get(ZORUNLU[1])

        kayit = {"pr": no, "sha": sha, "baslik": pr["title"], "etiketler": sorted(etiketler),
                 "inceleme": inceleme, "karar": karar,
                 "yas_dk": yas_dk(pr.get("created_at"), an),
                 # güncellenme yaşı: PR'a yeni commit geldiyse inceleme de yenilenmeli
                 "guncelleme_dk": yas_dk(pr.get("updated_at"), an)}

        # ── AYNI SHA'YA İKİNCİ KEZ KARAR YAZILMAZ ─────────────────────────────────────────
        # Durum kontrolleri COMMIT'e bağlıdır: yeni commit = yeni sha = durum yok. Yani "bu sha
        # için karar zaten yazılmış" demek, "yapılacak yeni bir şey yok, top geliştiricide" demek.
        # Bu kural olmadan 25 Ekim'de i3 aynı head'e (cc4e4b81) ÜÇ tur üst üste "düzeltme" yazdı
        # ve nöbetçi her turda boşuna oturum açtı; i5 de kendi "sorun" verdiği sha'yı sonsuz
        # yeniden inceliyordu. Geliştirici yeni commit atınca sha değişir → iş kendiliğinden döner.
        if rol == "i5":
            if inceleme not in YAZILMIS_DURUMLAR:
                cikti.append(kayit)
            else:
                atlanan += 1  # karar yazılmış, düzeltme geliştiricide
        else:  # i3 — yalnız i5 onay verdikten sonra çalışır
            if inceleme != "success":
                continue
            etiketsiz_onay = karar == "success" and ONAY_ETIKETI not in etiketler  # yarım yazım: etiket eksik
            if karar not in YAZILMIS_DURUMLAR or etiketsiz_onay:
                cikti.append(kayit)
            else:
                atlanan += 1  # karar verilmiş (düzeltme/red), geliştiricide

    # yaş büyük = daha eski → başa. Eşitlikte PR numarası küçük olan (daha eski) önce.
    cikti.sort(key=lambda i: (-i["yas_dk"], i["pr"]))
    if atlanan:
        gunluk(getattr(gh, "gunluk_yolu", None), f"{rol}: {atlanan} PR bu commit için zaten karara bağlı "
                                            f"→ yeni commit bekleniyor (yeniden karar yazılmaz)")
    return cikti[:limit]



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
        if is_.get("yas_dk"):
            not_.append(f"{is_['yas_dk'] // 60} saattir açık")
        ek = f" ({', '.join(not_)})" if not_ else ""
        satirlar.append(f"- PR #{is_['pr']} · head {is_['sha'][:12]} · {is_['baslik']}{ek}")
    satirlar += ["", "SIRA: liste en eski PR önce sıralıdır; bu sırayı DEĞİŞTİRME."]
    if rol == "i3":
        satirlar += ["", "i5 onayı olan ve birleştirilebilir PR'ları `--birlestir --cift-onay` ile BİRLEŞTİR.",
                     "Bir PR birleşince diğerleri 'behind' kalabilir; o PR'a 'dal güncellenmeli' yorumu bırak."]
    satirlar += ["", "Bitince kısa bir özet yaz: hangi PR'a ne yazdın, ne birleşti."]
    return "\n".join(satirlar) + "\n"


def hermes_komutu(depo: Path, gorev: Path, zaman_asimi: int) -> list[str]:
    """Nöbetçi oturumunun komut satırı (test edilebilir tek nokta)."""
    b = butce_hesapla(zaman_asimi)
    komut = ["hermes"]
    if NOBETCI_PROFIL:                      # ayrı profil: Open WebUI yükü nöbetçiyi aç bırakmasın
        komut += ["-p", NOBETCI_PROFIL]
    komut += ["chat", "--query-file", str(gorev), "--oneshot",
              "--max-turns", str(b["tur"]), "--run-budget", str(b["butce"]),
              "--in", str(depo), "--source", "nobetci"]
    return komut


def hermes_calistir(depo: Path, metin: str, rol: str, zaman_asimi: int, kuru: bool) -> tuple[int, str]:
    if kuru:
        print("\n--- ÇALIŞTIRILACAK GÖREV ---")
        print(metin)
        return 0, "kuru"
    gorev = DURUM_KLASORU / f"gorev-{rol}.md"
    gorev.parent.mkdir(parents=True, exist_ok=True)
    gorev.write_text(metin, encoding="utf-8")
    komut = hermes_komutu(depo, gorev, zaman_asimi)
    try:
        sonuc = subprocess.run(komut, capture_output=True, text=True, timeout=zaman_asimi)
        return sonuc.returncode, (sonuc.stdout or "") + (sonuc.stderr or "")
    except FileNotFoundError:
        return 127, "hermes bulunamadı (PATH)"
    except subprocess.TimeoutExpired:
        return 124, f"zaman aşımı ({zaman_asimi}s)"


def tek_tur(gh: Github, depo: Path, rol: str, limit: int, kuru: bool, zaman_asimi: int,
            gunluk_yolu: Path | None) -> int:
    an = time.time()
    bugun = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    bugun_sayi = int(gh.gunluk.get(bugun, 0))
    if bugun_sayi >= GUNLUK_OTURUM_TAVANI:
        gunluk(gunluk_yolu, f"{rol}: günlük oturum tavanı ({GUNLUK_OTURUM_TAVANI}) doldu → bugün yeni oturum yok")
        gh.kaydet({"rol": rol, "is": 0, "son_karar": "tavan"})
        return 0

    hepsi = isler(gh, rol, limit)
    if hepsi:
        en_eski = hepsi[0]
        if en_eski["yas_dk"] >= ACLIK_ESIGI_DK:
            gunluk(gunluk_yolu, f"AÇLIK: PR #{en_eski['pr']} {en_eski['yas_dk']} dk "
                                f"({en_eski['yas_dk'] / 60:.1f} saat) açık ve hâlâ sırada — "
                                f"kuyruk {len(hepsi)} PR, oturum başına "
                                f"{max(1, OTURUM_BASI_PR.get(rol, 1))} PR işleniyor")
    is_listesi: list[dict] = []
    atlanan: list[tuple[dict, int]] = []
    for is_ in hepsi:
        bekle, kalan = beklemeli_mi(gh.denemeler, is_["pr"], is_["sha"], an)
        (atlanan.append((is_, kalan)) if bekle else is_listesi.append(is_))
    if atlanan:
        gunluk(gunluk_yolu, f"{rol}: {len(atlanan)} PR beklemede — "
                            + ", ".join(f"#{i['pr']} ({k}s)" for i, k in atlanan))
    if not is_listesi:
        if hepsi:
            gh.kaydet({"rol": rol, "is": len(hepsi), "son_karar": "beklemede"})
        else:
            gunluk(gunluk_yolu, f"{rol}: iş yok (0 oturum)")
            gh.kaydet({"rol": rol, "is": 0, "son_karar": "bos"})
        return 0

    cap = max(1, OTURUM_BASI_PR.get(rol, 1))
    if len(is_listesi) > cap:
        sirada, kuyruk = is_listesi[:cap], is_listesi[cap:]
        gunluk(gunluk_yolu, f"{rol}: oturum başına {cap} PR — sıradaki "
                            + ", ".join(f"#{i['pr']}" for i in sirada)
                            + "; kuyrukta " + ", ".join(f"#{i['pr']}" for i in kuyruk))
        is_listesi = sirada
    gunluk(gunluk_yolu, f"{rol}: {len(is_listesi)} iş → oturum açılıyor: "
                        + ", ".join(f"#{i['pr']}" for i in is_listesi))
    b = butce_hesapla(zaman_asimi)
    if not b["yeterli"]:
        gunluk(gunluk_yolu, f"UYARI: --zaman-asimi {zaman_asimi} sn → tur tavanı "
                            f"{OTURUM_TUR_TAVANI} yerine {b['tur']} tur uygulanıyor "
                            f"({b['tur_basi_sn']} sn/tur). Varsayılan: {VARSAYILAN_ZAMAN_ASIMI} sn")
    kod, cikti = hermes_calistir(depo, gorev_metni(rol, depo, is_listesi), rol, zaman_asimi, kuru)
    gunluk(gunluk_yolu, f"{rol}: oturum bitti (çıkış {kod})")

    # Sonuç: iş listesi hâlâ aynı PR'ları içeriyorsa karar YAZILAMAMIŞ demektir → beklemeyi artır.
    if not kuru:
        kalan = {anahtar(x["pr"], x["sha"]) for x in isler(gh, rol, limit)}
        yazilmayan: list[int] = []
        for is_ in is_listesi:
            k = anahtar(is_["pr"], is_["sha"])
            if k in kalan:
                yazilmayan.append(is_["pr"])
                kayit = gh.denemeler.get(k, {"sayi": 0})
                kayit["sayi"] = int(kayit.get("sayi", 0)) + 1
                kayit["son"] = time.time()
                gh.denemeler[k] = kayit
            else:
                gh.denemeler.pop(k, None)
        if yazilmayan:
            # GÖRÜNÜRLÜK: oturum "çıkış 0" ile bitse bile karar yazılmamış olabilir (tur/ömür
            # bütçesi). Bu satır olmadan günlük "her şey yolunda" gibi okunuyordu (2026-10-25).
            gunluk(gunluk_yolu, f"{rol}: KARAR YAZILMADI — " + ", ".join(f"#{p}" for p in yazilmayan)
                                + f" (çıkış {kod}); aynı head tekrar denenecek, bekleme artıyor"
                                + ("" if kod != 0 else " · tur/bütçe tavanı yetmedi mi? (OTURUM_TUR_TAVANI="
                                   f"{OTURUM_TUR_TAVANI})"))
        gh.gunluk[bugun] = bugun_sayi + 1
        for g in list(gh.gunluk):
            if g != bugun:
                gh.gunluk.pop(g)

    gh.kaydet({"rol": rol, "is": len(is_listesi), "son_karar": "calisti" if not kuru else "kuru",
               "cikis": kod, "prlar": [i["pr"] for i in is_listesi],
               "en_eski_dk": is_listesi[0].get("yas_dk") if is_listesi else 0,
               "bugun_oturum": int(gh.gunluk.get(bugun, 0))})
    if kod != 0 and cikti:
        gunluk(gunluk_yolu, "çıktı (son 600 karakter): " + cikti[-600:].replace("\n", " ⏎ "))
    return kod


def kendini_denetle(rol: str, token_yolu: Path = TOKEN_VARSAYILAN, limit: int = 8) -> int:
    """KONTROL NOKTALARI — 'neden hâlâ oturum açılıyor / neden PR bekliyor?' sorusunu tek
    komutta yanıtlar.

    Hiçbir şeyi değiştirmez; her madde ✓/✗ yazar ve ✗ varsa çıkış kodu 1 olur.
    """
    import sqlite3
    from datetime import datetime, timezone

    sorun = 0

    def satir(durum: bool, etiket: str, ayrinti: str = "") -> None:
        nonlocal sorun
        if not durum:
            sorun += 1
        print(f"{'✓' if durum else '✗'} {etiket:<26} {ayrinti}")

    # 1) Projeye ait cron görevleri (oturumların 2. kaynağı)
    temizle = DEPO_VARSAYILAN / "otomasyon" / "betik" / "cron_temizle.py"
    kalan_cron: list = []
    if temizle.is_file():
        try:
            cikti = subprocess.run([sys.executable, str(temizle), "--json"],
                                   capture_output=True, text=True, timeout=40).stdout
            kalan_cron = json.loads(cikti).get("hedef", [])
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    satir(not kalan_cron, "cron görevi yok",
          "temiz" if not kalan_cron else f"{[g['id'] for g in kalan_cron]} → --sadece-cron")

    # 2) systemd servisi
    durum_metni = ""
    try:
        durum_metni = subprocess.run(["systemctl", "--user", "is-active", UNIT_ADI],
                                     capture_output=True, text=True, timeout=15).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        durum_metni = "bilinmiyor"
    satir(durum_metni == "active", "servis aktif", durum_metni or "kapalı")

    # 3) oturum kapanınca durmaması için linger
    linger = ""
    try:
        linger = subprocess.run(["loginctl", "show-user", os.environ.get("USER", ""), "-p", "Linger"],
                                capture_output=True, text=True, timeout=15).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    satir(linger.endswith("yes"), "linger açık", linger or "okunamadı")

    # 4) durum dosyası tazeliği
    dosya = DURUM_KLASORU / f"nobetci-{rol}.json"
    taze = False
    ayrinti = f"yok: {dosya}"
    if dosya.is_file():
        yas = time.time() - dosya.stat().st_mtime
        taze = yas < 3600
        ayrinti = f"{int(yas / 60)} dk önce güncellendi"
    satir(taze, "durum dosyası taze", ayrinti)

    # 5) bugün açılan nöbetçi oturumu (makul üst sınır: 24)
    adet = -1
    try:
        vt = Path.home() / ".hermes" / "state.db"
        if vt.is_file():
            c = sqlite3.connect(f"file:{vt}?mode=ro", uri=True)
            gece = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
            adet = c.execute(
                "select count(*) from sessions where started_at >= ? and coalesce(created_source, source) = 'nobetci'",
                (gece,),
            ).fetchone()[0]
    except (OSError, sqlite3.Error):
        pass
    satir(0 <= adet <= 24, "bugünkü oturum ≤ 24", f"{adet}" if adet >= 0 else "okunamadı")

    # 6) KUYRUK TIKANIKLIĞI: en eski iş ne kadar bekledi? (25 Ekim: #83/#84 → 10 saat görünmez)
    if token_yolu.exists():
        try:
            gh = Github(token_yolu.read_text(encoding="utf-8").strip(),
                        os.environ.get("GITHUB_DEPO", "hakkisabah/yourkiosk"), dosya, None)
            hepsi = isler(gh, rol, limit)
            if hepsi:
                yas = int(hepsi[0].get("yas_dk", 0))
                satir(yas < ACLIK_ESIGI_DK, "en eski iş < 120 dk",
                      f"#{hepsi[0]['pr']} {yas} dk ({len(hepsi)} PR sırada)"
                      + ("" if yas < ACLIK_ESIGI_DK else " → AÇLIK"))
            else:
                satir(True, "en eski iş < 120 dk", "iş yok")
        except (OSError, ValueError) as hata:
            print(f"⚠ en eski iş < 120 dk      okunamadı ({type(hata).__name__}: {hata})")
    else:
        satir(False, "token dosyası", f"yok: {token_yolu}")

    # 7-8) GÜNLÜKTEN: son 24 saatte zaman aşımı ve karar kapısı reddi (sessiz kalmış hatalar)
    sinir = time.time() - 86400
    zaman_asimi = kapi_red = 0
    gunluk_dosya = DURUM_KLASORU / f"nobetci-{rol}.log"
    if gunluk_dosya.is_file():
        for satirl in gunluk_dosya.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"\[(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)\]", satirl)
            if not m:
                continue
            try:
                an = datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
            except ValueError:
                continue
            if an < sinir:
                continue
            if "çıkış 124" in satirl or "zaman aşımı" in satirl:
                zaman_asimi += 1

    # karar kapısı: yaz.py reddettiği/atladığı her kararı kapi-red.log'a yazar
    kapi_dosya = DURUM_KLASORU / "kapi-red.log"
    if kapi_dosya.is_file():
        for satirl in kapi_dosya.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                kayit = json.loads(satirl)
                an = datetime.strptime(str(kayit.get("zaman")), "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=timezone.utc).timestamp()
            except (ValueError, TypeError):
                continue
            if an >= sinir:
                kapi_red += 1

    satir(zaman_asimi == 0, "son 24s zaman aşımı yok", f"{zaman_asimi} olay")
    satir(kapi_red < 3, "karar kapısı reddi < 3", f"{kapi_red} olay → {kapi_dosya}")

    print(f"\n{'✓ tüm kontrol noktaları temiz' if sorun == 0 else f'✗ {sorun} kontrol noktası sorunlu'}")
    return 0 if sorun == 0 else 1


def main() -> int:
    ayar = argparse.ArgumentParser(description="yourkiosk nöbetçi (olay güdümlü i5/i3)")
    ayar.add_argument("--rol", choices=["i5", "i3"], required=True)
    ayar.add_argument("--aralik", type=int, default=15, help="yoklama aralığı sn (varsayılan 15)")
    ayar.add_argument("--limit", type=int, default=8, help="tur başına en çok PR")
    ayar.add_argument("--bir-kez", action="store_true", help="tek tur çalış ve çık (test)")
    ayar.add_argument("--kuru", action="store_true", help="oturum açma, görevi yazdır")
    ayar.add_argument("--durum", action="store_true", help="durum dosyasını yazdır ve çık")
    ayar.add_argument("--tani", action="store_true", help="iş listesi + bekleyenler + günlük oturum sayısı")
    ayar.add_argument("--kendini-denetle", action="store_true",
                      help="kontrol noktaları: kalan cron / servis / linger / oturum sayısı (değiştirmez)")
    ayar.add_argument("--zaman-asimi", type=int, default=VARSAYILAN_ZAMAN_ASIMI,
                      help=f"oturum zaman aşımı sn (varsayılan {VARSAYILAN_ZAMAN_ASIMI} = "
                           f"tavan {OTURUM_TUR_TAVANI} × {TUR_SURE_PAYI_S} sn + {KAPANIS_PAYI_S} sn)")
    ayar.add_argument("--depo", type=Path, default=DEPO_VARSAYILAN)
    ayar.add_argument("--token", type=Path, default=TOKEN_VARSAYILAN)
    ayar.add_argument("--log", type=Path, default=None)
    ayar.add_argument("--profil", default=None,
                      help="nöbetçi oturumunun Hermes profili (varsayılan: NOBETCI_PROFIL env; "
                           "boşsa varsayılan profil). Open WebUI yükünü ayırmak için 'guvenlik'.")

    secim = ayar.parse_args()
    global NOBETCI_PROFIL
    if secim.profil is not None:
        NOBETCI_PROFIL = secim.profil.strip()
    if secim.kendini_denetle:  # kilit gerekmez, hiçbir şeyi değiştirmez
        return kendini_denetle(secim.rol, secim.token, secim.limit)
    durum_yolu = DURUM_KLASORU / f"nobetci-{secim.rol}.json"
    gunluk_yolu = secim.log or (DURUM_KLASORU / f"nobetci-{secim.rol}.log")

    if secim.durum:
        if not durum_yolu.exists():
            print(f"durum yok: {durum_yolu} (nöbetçi hiç çalışmamış)")
            return 1
        veri = json.loads(durum_yolu.read_text(encoding="utf-8"))
        print(f"nöbetçi durumu · {secim.rol} · {durum_yolu}")
        for alan, deger in veri.items():
            if alan == "etag":
                print(f"  etag önbelleği : {len(deger)} adres")
            else:
                print(f"  {alan:15s}: {deger}")
        return 0

    if secim.tani:
        token = secim.token.read_text(encoding="utf-8").strip()
        gh = Github(token, os.environ.get("GITHUB_DEPO", "hakkisabah/yourkiosk"), durum_yolu, gunluk_yolu)
        hepsi = isler(gh, secim.rol, secim.limit)
        an = time.time()
        bugun = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        print(f"nöbetçi tanı · rol={secim.rol}")
        print(f"  hermes profili      : {NOBETCI_PROFIL or '(varsayılan — Open WebUI ile paylaşılır)'}")
        print(f"  bugün açılan oturum : {gh.gunluk.get(bugun, 0)} (tavan {GUNLUK_OTURUM_TAVANI})")
        b = butce_hesapla(secim.zaman_asimi)
        print(f"  oturum bütçesi      : {b['butce']} sn · {b['tur']} tur × {b['tur_basi_sn']} sn"
              + ("" if b["yeterli"] else f" · ⚠ BÜTÇE DAR: tavan {OTURUM_TUR_TAVANI} turdan "
                                          f"{b['tur']} tura kısıldı"))
        print(f"  iş listesi          : {len(hepsi)} PR")
        for is_ in hepsi:
            bekle, kalan = beklemeli_mi(gh.denemeler, is_["pr"], is_["sha"], an)
            durum = f"BEKLEMEDE ({kalan}s)" if bekle else "SIRADA"
            kayit = gh.denemeler.get(anahtar(is_["pr"], is_["sha"]), {})
            print(f"    #{is_['pr']:<3} {is_['sha'][:12]} · {is_['yas_dk']:>4} dk açık · {durum}"
                  f" · deneme={kayit.get('sayi', 0)}")
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
