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
import stat
import subprocess
import time
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

TABAN = "https://api.github.com"
BASLIKLAR = {"Accept": "application/vnd.github+json", "User-Agent": "yourkiosk-otomasyon"}
#: Karar kapısı reddi/atlaması buraya JSON satırları olarak yazılır (nobetci denetler).
#: 26 Ekim i5 bulgusu: yol `YAZ_KAPI_LOG` ortam değişkeninden geliyordu → ajan `/dev/null` verip
#: kapı atlamasının izini silebiliyor, `--kendini-denetle`nin 8. noktası kör kalıyordu. Aynı sınıf
#: hata bilet yolunda kapatılmıştı; burada da yol SABİT. (Testler modül özniteliğini enjekte eder;
#: üretim CLI'ında yolu taşıyan bir anahtar YOKTUR.)
KAPI_LOG = Path.home() / ".local" / "state" / "yourkiosk-otomasyon" / "kapi-red.log"

#: MAKİNE KİMLİĞİ — operatörün kurduğu ROOT sahipli dosya (`i5` ya da `i3`).
#: 26 Ekim i5 bulgusu: kimlik karar dosyasının KENDİ `makine` alanından okunuyordu; i5 oturumu
#: "i3" yazıp iki kapıyı da tek başına geçirebiliyordu (AGENTS.md:52-53 yasaklıyor). Artık kimlik
#: dosyadan okunur, karar dosyasındaki değerle uyuşmazsa yazım reddedilir (çıkış 5).
KIMLIK_VARSAYILAN = Path("/etc/yourkiosk-makine-kimligi")

#: Kapı atlama BİLETİ — operatörün ürettiği, ajanın üretemediği ikinci anahtar.
#: Neden: ortam değişkenini ajan kendi kabuğundan verebiliyor (terminal yetkisi var). Bilet
#: /run altında ROOT sahipli olmalı; root olmayan kullanıcı orada dosya oluşturamaz.
BILET_VARSAYILAN = Path("/run/yourkiosk-kapi-atla.bilet")
#: Bilet TTL'i (saniye): eski bir bilet kazara kalıcı arka kapıya dönüşmesin.
BILET_TTL_SN = 600

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
    if karar.get("kanit_yok"):
        # Kanıt katmanı kapatıldıysa bu yorumda GÖRÜNÜR olmalı (denetlenebilirlik).
        satirlar += [f"⚠️ **KANIT KATMANI ATLANDI** (--kanit-yok) — gerekçe: {karar['kanit_yok']}", ""]
    if karar.get("kapi_atlandi"):
        satirlar += [f"⚠️ **KARAR KAPISI ATLANDI** — gerekçe: {karar['kapi_atlandi']}", ""]
    bulgular = karar.get("bulgular") or []
    if bulgular:
        # `kabul` (kapanış ölçütü) yorumda GÖRÜNMEK ZORUNDA: 26 Ekim i5 bulgusu — kapı bu alanı
        # zorunlu kılıyordu ama tablo onu basmıyordu, yani ölçüt geliştiriciye hiç ulaşmıyordu.
        satirlar += ["| Dosya | Satır | Önem | Bulgu | Kapanış ölçütü |", "|---|---|---|---|---|"]
        for b in bulgular[:25]:
            aciklama = str(b.get("aciklama", "")).replace("|", "\\|")[:200]
            kabul = str(b.get("kabul", "") or "").replace("|", "\\|")[:220] or "—"
            satirlar.append(
                f"| `{b.get('dosya', '?')}` | {b.get('satir', '')} | {b.get('onem', '')} "
                f"| {aciklama} | {kabul} |")
        if len(bulgular) > 25:
            satirlar.append(f"| … | | | (+{len(bulgular) - 25} bulgu daha) | |")
        satirlar.append("")
    denetlenen = karar.get("denetlenen") or []
    if denetlenen:
        satirlar += ["**Denetlenen alanlar:** " + ", ".join(f"`{d}`" for d in denetlenen[:20]), ""]

    dogrulama = karar.get("i5_dogrulama") or []
    if dogrulama:
        satirlar += ["#### i5 bulgularının doğrulanması", "", "| i5 bulgusu | Sonuç | Kanıt |", "|---|---|---|"]
        for d in dogrulama[:25]:
            durum_simge = {"dogrulandi": "✅", "yanlis": "❌", "eksik_kanit": "⚠️"}.get(str(d.get("durum")), "•")
            satirlar.append(
                f"| {str(d.get('bulgu', '')).replace('|', '\\|')[:120]} | {durum_simge} {d.get('durum', '')} "
                f"| {str(d.get('kanit', '')).replace('|', '\\|')[:160]} |"
            )
        satirlar.append("")

    eksikler = karar.get("eksikler") or []
    if eksikler:
        satirlar += ["#### i5'in kaçırdığı bulgular (i3)", "",
                     "| Dosya | Satır | Önem | Bulgu | Kapanış ölçütü |", "|---|---|---|---|---|"]
        for e in eksikler[:25]:
            kabul = str(e.get("kabul", "") or "").replace("|", "\\|")[:220] or "—"
            satirlar.append(
                f"| `{e.get('dosya', '?')}` | {e.get('satir', '')} | {e.get('onem', '')} "
                f"| {str(e.get('aciklama', '')).replace('|', '\\|')[:200]} | {kabul} |"
            )
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


def _yabanci_commitler(depo: str, token: str, pr_no: int) -> tuple[list[str], str]:
    """Dalın taşıdığı, BAŞKA bir açık PR'a ait commit'ler → (liste, hata).

    Neden: 25 Ekim'de #89 dalı, birleşmemiş #88'in commit'ini (11a5a89) taşıyordu. Squash-merge
    olsa bile "onaylanmamış iş main'e girer" riski doğar ya da PR sonsuza kadar bekler. Kapı bunu
    birleştirme anında makineyle denetler; dal temizlenince (rebase) kendiliğinden geçer.

    FAIL-CLOSED (26 Ekim i5 bulgusu): API 200 dışı kod dönerse (429 kota, 403, 0 ağ hatası) eski
    sürüm BOŞ liste dönüyordu → denetim sessizce atlanıyordu. Artık her başarısız çağrı hata
    döndürür; `birlestir()` bu durumda birleştirmez ve gerekçeyi PR yorumuna yazar.
    """
    kod, digerleri = istek(f"/repos/{depo}/pulls?state=open&per_page=100", token)
    if kod != 200 or not isinstance(digerleri, list):
        return [], f"açık PR listesi denetlenemedi (HTTP {kod})"
    baska: dict[str, int] = {}
    for p in digerleri:
        if not isinstance(p, dict) or p.get("number") == pr_no:
            continue
        sha = ((p.get("head") or {}).get("sha") or "").strip()
        if sha:
            baska[sha] = p.get("number", 0)
    if not baska:
        return [], ""
    kod, commitler = istek(f"/repos/{depo}/pulls/{pr_no}/commits?per_page=100", token)
    if kod != 200 or not isinstance(commitler, list):
        return [], f"PR commit listesi denetlenemedi (HTTP {kod})"
    return [f"#{baska[c['sha']]} ({c['sha'][:7]})" for c in commitler
            if isinstance(c, dict) and c.get("sha") in baska], ""


def birlestir(depo: str, token: str, pr_no: int, sha: str, kuru: bool, cift_onay: bool = False) -> tuple[bool, str]:
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
    yabanci, denetim_hatasi = _yabanci_commitler(depo, token, pr_no)
    if denetim_hatasi:
        # FAIL-CLOSED: denetim yapılamadıysa "yabancı commit yok" sayılmaz (26 Ekim i5 bulgusu).
        return False, f"yabancı commit denetimi yapılamadı — {denetim_hatasi}"
    if yabanci:
        return False, ("dal başka AÇIK PR'ın commit'ini taşıyor: " + ", ".join(yabanci)
                       + " — rebase edin, sonra yeniden karar")
    engel = [e for e in etiketler if e in ENGELLEYEN_ETIKETLER]
    if engel:
        return False, f"engelleyici etiket: {', '.join(engel)}"
    if pr.get("mergeable_state") != "clean":
        # GitHub durum kontrolünü birkaç saniyede yeniden hesaplar (az önce yazdığımız kontrol dâhil)
        for _ in range(4):
            time.sleep(2)
            kod2, pr2 = istek(f"/repos/{depo}/pulls/{pr_no}", token)
            if kod2 == 200 and isinstance(pr2, dict) and pr2.get("mergeable_state") == "clean":
                break
        else:
            return False, f"birleştirilemez durum: {pr.get('mergeable_state')} (çakışma/eksik kontrol olabilir)"

    kod, durum = istek(f"/repos/{depo}/commits/{sha}/status", token)
    kontroller = {s["context"]: s["state"] for s in (durum or {}).get("statuses", [])} if isinstance(durum, dict) else {}
    kotu = [ad for ad, hal in kontroller.items() if hal in ("failure", "pending", "error")]
    if kotu:
        return False, f"başarısız/bekleyen kontroller: {', '.join(kotu)}"
    if cift_onay:
        eksik = [ad for ad in ("guvenlik/inceleme", "guvenlik/karar") if kontroller.get(ad) != "success"]
        if eksik:
            return False, f"çift onay tamam değil (eksik: {', '.join(eksik)})"

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


def _yuksek_bulgular(karar: dict) -> list[dict]:
    """'yüksek'/'kritik' önemdeki bulgular — kapı atlama yolları bunlar varken kapalıdır."""
    return [b for b in (karar.get("bulgular") or []) if isinstance(b, dict)
            and str(b.get("onem", "")).lower() in {"yuksek", "yüksek", "kritik"}]


def bilet_yolu() -> Path:
    """Bilet yolu SABİTTİR — hiçbir ortam değişkeniyle değiştirilemez (26 Ekim i5 bulgusu).

    Önceki sürüm yolu `YAZ_KAPI_ATLA_BILET` ile değiştiriyordu; ajan terminal yetkisiyle bu
    değişkeni kendi kabuğundan verip `/proc/1/stat` gibi root sahipli, dünya-okur,
    grup/dünya-yazılamaz bir sanal dosyayı bilet gibi gösterebiliyordu → iki faktörlü koruma
    tek faktöre (ortam anahtarı) düşüyordu.
    Testler yolu `bilet_denetle(yol=...)` parametresiyle enjekte eder; üretim CLI'ında yol
    anahtarı YOKTUR.
    """
    return BILET_VARSAYILAN


def bilet_dizini_denetimi(st: "os.stat_result") -> bool:
    """Biletin ÜST DİZİNİ root sahipli ve grup/dünya-yazılamaz mı?

    Biletin kendisi sağlam görünse de yazılabilir bir dizinde duruyorsa aynı kullanıcı onu
    silip yeniden koyabilir. Testler bu FONKSİYONU enjekte eder (ortam anahtarı yoktur).
    """
    return st.st_uid == 0 and not (st.st_mode & 0o022)


#: Biletin kabul edilmediği sanal dosya sistemleri — /proc/1/stat gibi "root sahipli, dünya-okur"
#: görünen dosyalar gerçek bir operatör izni değildir.
SANAL_ONEKLER = ("/proc", "/sys", "/dev")


def bilet_denetle(yol: Path | None = None, *, sahip_denetimi=None,
                  dizin_denetimi=None,
                  simdi: float | None = None) -> tuple[bool, str]:
    """Operatör bileti geçerli mi? → (kabul, ret gerekçesi).

    Bilet: normal dosya, ROOT sahipli (uid 0), dünya-okur, grup/dünya-yazılamaz, mtime ≤ 10 dk;
    üst dizini root sahipli ve grup/dünya-yazılamaz; sanal dosya sisteminde (/proc · /sys · /dev)
    olamaz.
    """
    hedef = Path(yol) if yol is not None else bilet_yolu()
    hedef_str = str(hedef)
    if any(hedef_str == onek or hedef_str.startswith(onek + "/") for onek in SANAL_ONEKLER):
        return False, (f"bilet sanal dosya sisteminde ({hedef_str}) — "
                       f"{' · '.join(SANAL_ONEKLER)} altındaki yollar kabul edilmez")
    try:
        st = hedef.lstat()          # sembolik bağı İZLEME: bağ üzerinden root dosyası gösterilemesin
    except OSError as hata:
        return False, f"bilet yok ({hedef}): {hata.strerror or hata}"
    if not stat.S_ISREG(st.st_mode):
        return False, f"bilet normal dosya değil ({hedef})"
    denetim = sahip_denetimi if sahip_denetimi is not None else bilet_sahibi_denetimi
    if not denetim(st):
        return False, f"bilet root sahipli değil (uid {st.st_uid}, yol {hedef})"
    mod = st.st_mode & 0o777
    if not mod & 0o004:
        return False, f"bilet dünya-okur değil (mod {mod:04o}, yol {hedef})"
    if mod & 0o022:
        return False, f"bilet grup/dünya-yazılabilir (mod {mod:04o}, yol {hedef})"
    ust = hedef.parent
    try:
        st_ust = ust.stat()
    except OSError as hata:
        return False, f"bilet dizini okunamıyor ({ust}): {hata.strerror or hata}"
    d_denetim = dizin_denetimi if dizin_denetimi is not None else bilet_dizini_denetimi
    if not d_denetim(st_ust):
        return False, (f"bilet dizini güvenli değil (uid {st_ust.st_uid}, "
                       f"mod {st_ust.st_mode & 0o777:04o}, dizin {ust}) — root sahipli ve "
                       f"grup/dünya-yazılamaz olmalı")
    yas = (simdi if simdi is not None else time.time()) - st.st_mtime
    if yas > BILET_TTL_SN:
        return False, f"bilet bayat ({int(yas)} sn > {BILET_TTL_SN} sn TTL, yol {hedef})"
    return True, ""


def bilet_sahibi_denetimi(st: "os.stat_result") -> bool:
    """Bilet root sahipli mi? (ajan root olmadığı için kendi bileti üretemez).

    Testler bu FONKSİYONU enjekte eder (`bilet_denetle(..., sahip_denetimi=...)` ya da modül
    özniteliği). Ortam değişkeniyle gevşetilebilen bir anahtar YOKTUR: aksi hâlde aynı boşluk
    (ajanın kendi kabuğundan anahtar vermesi) yeni bir adla geri gelirdi.
    """
    return st.st_uid == 0


def kimlik_sahibi_denetimi(st: "os.stat_result") -> bool:
    """Kimlik dosyası root sahipli mi? (ajan root değil → kendi rolünü kuramaz)

    Testler bu FONKSİYONU enjekte eder; biletten AYRI tutulur ki iki mekanizmanın testleri
    birbirini gevşetmesin. Ortam değişkeniyle gevşetilebilen bir anahtar YOKTUR.
    """
    return st.st_uid == 0


def kimlik_dizini_denetimi(st: "os.stat_result") -> bool:
    """Kimlik dosyasının üst dizini root sahipli ve grup/dünya-yazılamaz mı?"""
    return st.st_uid == 0 and not (st.st_mode & 0o022)


def kimlik_yolu() -> Path:
    """Makine kimliği dosyasının yolu — SABİT (ortam değişkeniyle taşınamaz)."""
    return KIMLIK_VARSAYILAN


def makine_kimligi_denetle(yol: Path | None = None, *, sahip_denetimi=None,
                           dizin_denetimi=None) -> tuple[str, str]:
    """Bu makinenin rolü → (`i5` | `i3`, ret gerekçesi boş) ya da (`""`, gerekçe).

    NEDEN DOSYA: karar dosyasındaki `makine` alanı ajanın kendi beyanıydı; i5 oturumu "i3" yazıp
    iki zorunlu kontrolü de tek başına geçirebiliyordu (AGENTS.md:52-53). Kimlik artık operatörün
    kurduğu ROOT sahipli dosyadan okunur; ajan root olmadığı için onu yazamaz.

    Kabul ölçütleri (bilet ile aynı sınıf): normal dosya, ROOT sahipli, grup/dünya-yazılamaz,
    üst dizini root sahipli ve yazılamaz, sanal dosya sistemi (/proc · /sys · /dev) dışında,
    içeriği `i5` ya da `i3`. TTL YOK: kimlik kalıcı bir kurulum bilgisidir (bilet geçicidir).
    """
    hedef = Path(yol) if yol is not None else kimlik_yolu()
    hedef_str = str(hedef)
    if any(hedef_str == onek or hedef_str.startswith(onek + "/") for onek in SANAL_ONEKLER):
        return "", (f"makine kimliği sanal dosya sisteminde ({hedef_str}) — "
                    f"{' · '.join(SANAL_ONEKLER)} altındaki yollar kabul edilmez")
    try:
        st = hedef.lstat()
    except OSError as hata:
        return "", (f"makine kimliği yok ({hedef}): {hata.strerror or hata}; operatör: "
                    f"sudo sh -c 'printf i5 > {hedef}' && sudo chmod 0644 {hedef}")
    if not stat.S_ISREG(st.st_mode):
        return "", f"makine kimliği normal dosya değil ({hedef})"
    denetim = sahip_denetimi if sahip_denetimi is not None else kimlik_sahibi_denetimi
    if not denetim(st):
        return "", (f"makine kimliği root sahipli değil (uid {st.st_uid}, yol {hedef}) — "
                    f"yalnız operatör kurabilir")
    mod = st.st_mode & 0o777
    if mod & 0o022:
        return "", f"makine kimliği grup/dünya-yazılabilir (mod {mod:04o}, yol {hedef})"
    ust = hedef.parent
    try:
        st_ust = ust.stat()
    except OSError as hata:
        return "", f"makine kimliği dizini okunamıyor ({ust}): {hata.strerror or hata}"
    d_denetim = dizin_denetimi if dizin_denetimi is not None else kimlik_dizini_denetimi
    if not d_denetim(st_ust):
        return "", (f"makine kimliği dizini güvenli değil (uid {st_ust.st_uid}, "
                    f"mod {st_ust.st_mode & 0o777:04o}, dizin {ust})")
    try:
        ham = hedef.read_text(encoding="utf-8").strip().lower()
    except OSError as hata:
        return "", f"makine kimliği okunamadı ({hedef}): {hata.strerror or hata}"
    if ham not in MAKINE_AYARI:
        return "", (f"makine kimliği tanınmıyor ({ham!r}) — beklenen: "
                    f"{' | '.join(sorted(MAKINE_AYARI))}")
    return ham, ""


def operator_izi_denetle() -> tuple[bool, str, str]:
    """Kapı atlama/kanıt kapatma izni → (kabul, uzun gerekçe, günlük için kısa gerekçe).

    26 Ekim i5 bulgusu: koruma YALNIZ `YAZ_KAPI_ATLA_ONAY=1` ortam değişkenine bakıyordu; ajanın
    terminal yetkisi olduğu için anahtarı kendi kabuğundan sağlayabiliyordu. Artık iki parça
    birlikte aranır: (1) ortam anahtarı, (2) operatörün ürettiği root sahipli TTL'li bilet.
    """
    if os.environ.get("YAZ_KAPI_ATLA_ONAY", "") != "1":
        return (False,
                "operatör ortam anahtarı yok (YAZ_KAPI_ATLA_ONAY=1)",
                "operatör anahtarı yok")
    gecerli, neden = bilet_denetle()
    if not gecerli:
        return (False,
                f"operatör bileti geçersiz — {neden}; operatör: "
                f"sudo install -m 0644 /dev/null {bilet_yolu()}",
                f"operatör bileti geçersiz: {neden}")
    return True, "", ""


def _kapi_red_yaz(karar: dict, makine: str, hatalar: list[str], atlandi: bool) -> None:
    """Kapı reddi/atlaması kalıcı iz bıraksın.

    `nobetci.py --kendini-denetle` bu dosyayı sayar: ajan karar yazamıyorsa (ya da kapıyı
    sürekli atlıyorsa) sessiz kalmaz, kontrol noktası ✗ verir.
    """
    kayit = {
        "zaman": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "olay": "ATLANDI" if atlandi else "KARAR KAPISI",
        "makine": makine, "pr": karar.get("pr"), "karar": karar.get("karar"),
        "hatalar": hatalar[:6],
    }
    try:
        KAPI_LOG.parent.mkdir(parents=True, exist_ok=True)
        with KAPI_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(kayit, ensure_ascii=False) + "\n")
    except OSError:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="i5/i3 kararını GitHub'a yaz")
    ap.add_argument("karar", nargs="?", default="", help="karar.json yolu")
    ap.add_argument("--ornek", action="store_true", help="geçerli bir örnek karar dosyası yaz (şablon)")
    ap.add_argument("--depo", default="", help="--ornek için: sha'nın alınacağı git deposu")
    ap.add_argument("--depo-adresi", default="hakkisabah/yourkiosk")
    ap.add_argument("--token-dosya", default=str(Path.home() / ".config/hermes-secrets/github-yourkiosk.token"))
    ap.add_argument("--kuru", action="store_true", help="hiçbir istek atmadan göster")
    ap.add_argument(
        "--cift-onay", action="store_true",
        help="birleştirme için 'guvenlik/inceleme' VE 'guvenlik/karar' success olmalı (D modu)",
    )
    ap.add_argument("--kanit-yok", action="store_true",
                    help="karar kapısında dosya:satır kanıtını ağdan denetleme — --kapi-atla ile AYNI "
                         "korumalar: YAZ_KAPI_ATLA_ONAY=1 (operatör) VE root sahipli TTL'li bilet "
                         "/run/yourkiosk-kapi-atla.bilet (ortam anahtarı tek başına yetmez), "
                         "--gerekce ≥20 karakter, 'yüksek' bulgu yokluğu; her kullanım "
                         "kapi-red.log'a ATLANDI satırı yazar")
    ap.add_argument("--kapi-atla", action="store_true",
                    help="karar kapısı hatalarına RAĞMEN yayınla — AYRICA YAZ_KAPI_ATLA_ONAY=1 "
                         "ortam anahtarı VE operatör bileti (/run/yourkiosk-kapi-atla.bilet, root "
                         "sahipli, ≤10 dk) ister; --gerekce zorunlu, 'yüksek' bulgu varsa imkânsız")
    ap.add_argument("--gerekce", default="",
                    help="--kapi-atla / --kanit-yok için gerekçe (≥20 karakter); PR yorumuna ve kapi-red.log'a yazılır")
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
            "denetlenen": [],
            "not": "Şablon: geliştiriciye iletilecek not (yoksa boş bırakın).",
            "zaman": datetime.now().isoformat(timespec="seconds"),
        }
        hedef = Path("karar-ornek.json") if not a.karar else Path(a.karar).expanduser()
        hedef.write_text(json.dumps(ornek, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"örnek karar dosyası yazıldı: {hedef}  (sha: {(sha or 'BULUNAMADI')[:12]})")
        print("düzenleyip: python3 otomasyon/betik/yaz.py " + str(hedef) + " --kuru")
        print("NOT: şablon karar kapısından GEÇMEZ — `denetlenen` 12 alanı doldur, "
              "`bulgular` gerçek dosya:satır içersin.")
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

    # ---- MAKİNE KİMLİĞİ (26 Ekim i5 bulgusu) ------------------------------------------------
    # Karar dosyasındaki `makine` alanı ajanın KENDİ beyanıydı: i5 oturumu "i3" yazıp hem
    # `guvenlik/inceleme` hem `guvenlik/karar` kontrolünü tek başına yeşile çevirebiliyordu
    # (AGENTS.md:52-53 yasaklıyor). Kimlik artık operatörün kurduğu ROOT sahipli dosyadan okunur:
    #   · dosya yok/geçersiz  → çıkış 5 (fail-closed; operatör kurulum komutu hata metninde)
    #   · beyan ≠ dosya       → çıkış 5
    #   · --birlestir yalnız kimlik `i3` iken (karar makinesi) kullanılabilir
    kimlik, kimlik_neden = makine_kimligi_denetle()
    if not kimlik:
        print(f"[yaz] MAKİNE KİMLİĞİ REDDEDİLDİ — {kimlik_neden}", file=sys.stderr)
        print("  Kimlik operatör kurulumudur; ajan kendi rolünü seçemez.", file=sys.stderr)
        _kapi_red_yaz(karar, makine, [f"makine kimliği geçersiz: {kimlik_neden}"], atlandi=False)
        return 5
    if kimlik != makine:
        print(f"[yaz] KİMLİK UYUŞMAZLIĞI — bu makine {kimlik!r}, karar dosyası {makine!r} diyor. "
              "Reddedildi.", file=sys.stderr)
        _kapi_red_yaz(karar, makine,
                      [f"kimlik uyuşmazlığı: makine={kimlik!r}, karar={makine!r}"], atlandi=False)
        return 5
    makine = kimlik
    if a.birlestir and kimlik != "i3":
        print(f"[yaz] --birlestir REDDEDİLDİ — bu makinenin kimliği {kimlik!r}; birleştirme "
              "karar makinesine (i3) aittir.", file=sys.stderr)
        _kapi_red_yaz(karar, makine,
                      [f"--birlestir reddedildi: kimlik {kimlik!r}"], atlandi=False)
        return 5

    # ---- KANIT KATMANI (--kanit-yok) — ajanın tek başına kapatabileceği bir anahtar DEĞİL ---------
    # 26 Ekim i5 bulgusu: bayrak `kanit=not a.kanit_yok` ile dosya:satır kanıtı denetimini tamamen
    # kapatıyordu ve ajanın kendi elindeydi (terminal yetkisi olan ajan kanıtsız karar yayınlayabilir).
    # Artık --kapi-atla ile AYNI üç koruma geçerli:
    #   (1) operatörün ortam anahtarı `YAZ_KAPI_ATLA_ONAY=1` (nöbetçi biriminde tanımlı DEĞİL),
    #   (2) yazılı gerekçe ≥20 karakter, (3) 'yüksek'/'kritik' bulgu varken hiç kullanılamaz.
    # Her kullanım (kabul de ret de) kapi-red.log'a iz bırakır; kabulde olay=ATLANDI.
    if a.kanit_yok:
        gerekce = a.gerekce.strip()
        izin, ret_uzun, ret_kisa = operator_izi_denetle()
        if not izin:
            print(f"[yaz] KANIT KATMANI: --kanit-yok REDDEDİLDİ — {ret_uzun}. Kanıt denetimini "
                  "kapatmak ajanın tek başına verebileceği bir karar değil.", file=sys.stderr)
            _kapi_red_yaz(karar, makine, [f"--kanit-yok reddedildi: {ret_kisa}"], atlandi=False)
            return 5
        if _yuksek_bulgular(karar):
            print(f"[yaz] KANIT KATMANI: --kanit-yok REDDEDİLDİ — {len(_yuksek_bulgular(karar))} "
                  "'yüksek' bulgusu varken kanıt denetimi kapatılamaz.", file=sys.stderr)
            _kapi_red_yaz(karar, makine, ["--kanit-yok reddedildi: yüksek bulgu"], atlandi=False)
            return 5
        if len(gerekce) < 20:
            print("[yaz] KANIT KATMANI: --kanit-yok için --gerekce \"…\" (≥20 karakter) zorunlu.",
                  file=sys.stderr)
            _kapi_red_yaz(karar, makine, ["--kanit-yok reddedildi: gerekçe yok"], atlandi=False)
            return 5
        karar["kanit_yok"] = gerekce
        _kapi_red_yaz(karar, makine, [f"--kanit-yok: kanıt katmanı ATLANDI; gerekçe: {gerekce}"], atlandi=True)
        print(f"[yaz] KANIT KATMANI: ATLANDI (--kanit-yok) → dosya:satır kanıtı ağdan denetlenmiyor; "
              f"gerekçe günlüğe ve yoruma yazıldı")

    # ---- KARAR KAPISI (fail-closed) -------------------------------------------------------
    # Şema + kapsam (12 alan) + tutarlılık + dosya:satır kanıtı. Geçmezse GitHub'a HİÇBİR şey
    # yazılmaz: kararsızlık sessizce "onay"a dönüşmesin (25 Ekim kararı).
    import karar_dogrula  # aynı dizinde
    kapi = karar_dogrula.dogrula_karar(karar, makine, token=token_oku(a.token_dosya),
                                       depo=a.depo_adresi, kanit=not a.kanit_yok)
    for uyari in kapi.uyarilar:
        print(f"[kapı] ⚠ {uyari}")
    if not kapi.gecti:
        for hata in kapi.hatalar:
            print(f"[kapı] ✗ {hata}")
        # Kapıyı atlamak serbest bir anahtar DEĞİL: (a) yazılı gerekçe zorunlu, (b) 'yüksek' önemde
        # bulgu varken hiç atlanamaz, (c) atlama PR yorumunda görünür. 26 Ekim i5 bulgusu: bayrak
        # ajanın kendi elindeydi ve hiçbir makine itiraz etmiyordu.
        yuksek = _yuksek_bulgular(karar)
        gerekce = a.gerekce.strip()
        # 26 Ekim i5 bulgusu: bayrak ajanın KENDİ elindeydi (terminal yetkisi olan ajan --kapi-atla
        # yazıp şemayı/kanıtı devre dışı bırakabiliyordu). Kapı atlama artık ÜÇ parça ister:
        #   (1) operatörün ortam anahtarı `YAZ_KAPI_ATLA_ONAY=1` — nöbetçi biriminde TANIMLI DEĞİL,
        #   (2) operatörün ürettiği ROOT sahipli, TTL'li bilet `/run/yourkiosk-kapi-atla.bilet` —
        #       ortam anahtarı tek başına yetmez, çünkü ajan anahtarı kendi kabuğundan verebilir
        #       ama root sahipli dosyayı üretemez;
        #   (3) yazılı gerekçe + 'yüksek' bulgu yokluğu.
        # Atlama her durumda kapi-red.log'a ve PR yorumuna yazılır (denetlenebilir).
        izin, ret_uzun, ret_kisa = operator_izi_denetle()
        if a.kapi_atla and not izin:
            print(f"[yaz] KARAR KAPISI: --kapi-atla REDDEDİLDİ — {ret_uzun}. Kapı atlama ajanın "
                  "tek başına kullanabileceği bir anahtar değil.", file=sys.stderr)
            _kapi_red_yaz(karar, makine, kapi.hatalar + [f"--kapi-atla reddedildi: {ret_kisa}"],
                          atlandi=False)
            return 5
        if a.kapi_atla and yuksek:
            print(f"[yaz] KARAR KAPISI: atlama REDDEDİLDİ — {len(yuksek)} 'yüksek' bulgusu varken "
                  "kapı atlanamaz (önce düzelt).", file=sys.stderr)
            _kapi_red_yaz(karar, makine, kapi.hatalar + ["--kapi-atla reddedildi: yüksek bulgu"], atlandi=False)
            return 5
        if a.kapi_atla and len(gerekce) < 20:
            print("[yaz] KARAR KAPISI: --kapi-atla için --gerekce \"…\" (≥20 karakter) zorunlu.",
                  file=sys.stderr)
            _kapi_red_yaz(karar, makine, kapi.hatalar + ["--kapi-atla reddedildi: gerekçe yok"], atlandi=False)
            return 5
        if a.kapi_atla:
            print("[yaz] KARAR KAPISI: ATLANDI (--kapi-atla) → yayınlanıyor; gerekçe günlüğe ve yoruma yazıldı")
            karar["kapi_atlandi"] = gerekce
            _kapi_red_yaz(karar, makine, kapi.hatalar + [f"gerekçe: {gerekce}"], atlandi=True)
        else:
            _kapi_red_yaz(karar, makine, kapi.hatalar, atlandi=False)
            print("[yaz] KARAR KAPISI: reddedildi → GitHub'a hiçbir şey yazılmadı.\n"
                  "      Düzelt: karar JSON'unu kanıtlı hâle getir (denetlenen 12 alan, dosya:satır, "
                  "kararsızlıkta 'sorun'), sonra tekrar çalıştır.", file=sys.stderr)
            return 5

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
            # KURU modda da birleştirme kapısını GERÇEKTEN denetle (yazma yok): yabancı commit,
            # eksik çift onay, head sha kayması gibi engeller denenmeden "olur" demek yanıltıcıydı.
            kuru_token = token_oku(a.token_dosya)
            if kuru_token:
                uygun, mesaj = birlestir(a.depo_adresi, kuru_token, karar["pr"],
                                         karar.get("sha") or "", kuru=True, cift_onay=a.cift_onay)
                print(f"[KURU] birleştirme kapısı: {'✓ geçer' if uygun else '✗ engelli'} — {mesaj}")
            else:
                print(f"[KURU] otomatik birleştirme denenecek: PR #{karar['pr']} "
                      "(token yok → kapı denetlenemedi)")
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
            basarili, neden = birlestir(a.depo_adresi, token, int(pr_no), sha, kuru=False, cift_onay=a.cift_onay)
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
