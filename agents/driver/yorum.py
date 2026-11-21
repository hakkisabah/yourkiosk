"""PR yorumları — eski otomasyonun ayrıntılı i5/i3 karar biçimi."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

BT = chr(96)
BLK = BT * 3


def json_blogu(govde: str) -> dict | None:
    m = re.search(BLK + r"json\s*(.*?)\s*" + BLK, govde, re.S)
    if not m:
        return None
    try:
        veri = json.loads(m.group(1))
    except ValueError:
        return None
    return veri if isinstance(veri, dict) else None


def i5_karari(g, no: int, sha: str) -> dict | None:
    for y in reversed(g.yorumlar(no)):
        veri = json_blogu(str(y.get("body", "")))
        if veri and veri.get("makine") == "i5" and str(veri.get("sha")) == sha:
            return veri
    return None


def _hucre(deger) -> str:
    return str(deger if deger is not None else "-").replace("|", "\\|").replace(chr(10), " ")


def inceleme_yorumu(g, no: int, sha: str, karar: dict) -> None:
    bulgular = karar.get("bulgular") or []
    denetlenen = karar.get("denetlenen") or []
    onay = karar.get("karar") == "onay"
    ikon = "✅" if onay else "❌"
    baslik = "onay" if onay else str(karar.get("karar", "-"))
    satirlar = [
        f"🔍 **i5 — güvenlik incelemesi** — {ikon} **{baslik}** (önem: {karar.get('onem', '-')})",
        "",
        f"**Özet:** {karar.get('ozet', '-')}",
        "",
    ]
    if isinstance(bulgular, list) and bulgular:
        satirlar += ["| Dosya | Satır | Önem | Bulgu | Kapanış ölçütü |", "|---|---|---|---|---|"]
        for b in bulgular:
            if isinstance(b, dict):
                satirlar.append(
                    f"| {BT}{_hucre(b.get('dosya'))}{BT} | {_hucre(b.get('satir'))} | "
                    f"{_hucre(b.get('onem'))} | {_hucre(b.get('aciklama'))} | {_hucre(b.get('kabul'))} |")
            else:
                satirlar.append(f"| - | - | - | {_hucre(b)} | - |")
    else:
        satirlar.append("Bulgu yok.")
    satirlar += ["", "**Denetlenen alanlar:** " + ", ".join(
        BT + str(d) + BT for d in denetlenen) if denetlenen else "**Denetlenen alanlar:** belirtilmedi"]
    if karar.get("not"):
        satirlar += ["", f"**Geliştiriciye not:** {karar.get('not')}"]
    govde = {
        "makine": "i5", "karar": karar.get("karar"), "onem": karar.get("onem"),
        "sha": sha, "pr": no, "nonce": karar.get("nonce"),
        "bulgu_sayisi": len(bulgular) if isinstance(bulgular, list) else 0,
        "durum": "success" if onay else "failure",
        "zaman": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ozet": karar.get("ozet"), "bulgular": bulgular, "denetlenen": denetlenen,
        "not": karar.get("not", ""),
    }
    satirlar += [
        "", "<details><summary>makine-okunabilir karar</summary>", "",
        BLK + "json", json.dumps(govde, ensure_ascii=False, indent=1), BLK,
        "", "</details>", "",
        "_otomasyon · elle düzenlemeyin (sonraki koşuda üzerine yazılır)_",
    ]
    etiket = "guvenlik/onay" if onay else "guvenlik/sorun"
    imza = '"sha": "' + sha
    try:
        if not any(imza in str(y.get("body", "")) for y in g.yorumlar(no)):
            g.yorum_yaz(no, chr(10).join(satirlar))
        g.etiket_ekle(no, [etiket])
    except Exception as hata:  # noqa: BLE001
        try:
            g.durum_yaz(sha, "guvenlik/inceleme", "failure",
                        f"yorum/etiket yazılamadı: {str(hata)[:80]}")
        except Exception:  # noqa: BLE001
            pass


def karar_yorumu(g, no: int, sha: str, i5: dict | None, sonuc: dict) -> None:
    kabul = sonuc.get("durum") == "success"
    ikon = "✅" if kabul else "❌"
    baslik = "kabul" if kabul else "duzeltme"
    onem = (i5 or {}).get("onem", "-")
    bulgular = (i5 or {}).get("bulgular") or []
    degisen = {str(d.get("filename")) for d in g.pr_dosyalari(no)}
    satirlar = [
        f"⚖️ **i3 — karar / ikinci görüş** — {ikon} **{baslik}** (önem: {onem})",
        "",
        f"**Özet:** i5'in {len(bulgular)} bulgusu ve head {BT}{sha[:12]}{BT} kontrol edildi; "
        f"karar: {sonuc.get('durum')}.",
        "",
    ]
    if bulgular:
        satirlar += ["#### i5 bulgularının doğrulanması", "",
                     "| i5 bulgusu | Sonuç | Kanıt |", "|---|---|---|"]
        for b in bulgular:
            if not isinstance(b, dict):
                continue
            dosya = str(b.get("dosya", "-"))
            durum = "✅ dosya PR'da" if dosya in degisen else "⚠ dosya PR'da yok"
            satirlar.append(f"| {BT}{dosya}:{b.get('satir', '-')}{BT} — "
                            f"{_hucre(b.get('aciklama'))[:80]} | {durum} | "
                            f"değişen dosyalar: {len(degisen)} |")
    else:
        satirlar.append("i5 bulgusu yok; değişen dosyalar ve durum kontrolleri doğrulandı.")
    alanlar = (i5 or {}).get("denetlenen") or []
    satirlar += ["", "**Denetlenen alanlar:** " + ", ".join(BT + str(d) + BT for d in alanlar)
                 if alanlar else "**Denetlenen alanlar:** belirtilmedi"]
    if i5:
        satirlar += ["", f"**i5 özeti:** {i5.get('ozet', '-')}"]
    govde = {
        "makine": "i3", "karar": baslik, "onem": onem, "sha": sha, "pr": no,
        "bulgu_sayisi": len(bulgular), "durum": sonuc.get("durum"),
        "zaman": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ozet": sonuc.get("durum"), "i5_sha": (i5 or {}).get("sha"),
    }
    satirlar += [
        "", "<details><summary>makine-okunabilir karar</summary>", "",
        BLK + "json", json.dumps(govde, ensure_ascii=False, indent=1), BLK,
        "", "</details>", "",
        "_otomasyon · elle düzenlemeyin (sonraki koşuda üzerine yazılır)_",
    ]
    imza = "i3 — karar / ikinci görüş"
    try:
        if not any(imza in str(y.get("body", "")) and sha in str(y.get("body", ""))
                   for y in g.yorumlar(no)):
            g.yorum_yaz(no, chr(10).join(satirlar))
    except Exception:  # noqa: BLE001
        pass


def govde_eksik_yorumu(g, no: int, sha: str, eksikler: list[str]) -> None:
    """Gövde kapısı reddini PR'a yazar (aynı sha için tek yorum)."""
    imza = "Gövde kapısı · " + sha[:12]
    satirlar = [
        f"## {imza}",
        "",
        "Bu PR birleştirilemez: gövde zorunlu bölümleri taşımıyor.",
        "",
        "### Eksikler",
    ]
    satirlar += [f"- {e}" for e in eksikler]
    satirlar += [
        "",
        "### Beklenen gövde",
        "",
        "```markdown",
        "## Ne",
        "- ne değişti (dosya/ davranış)",
        "",
        "## Doğrulama",
        "- `komut` → çıkış 0",
        "",
        "## Sır",
        "Yok.",
        "```",
        "",
        "_Otomatik kapı (i3). Gövde düzeltilince yeni push gerekmez._",
    ]
    mevcut = g.yorumlar(no)
    if any(imza in str(y.get("body", "")) for y in mevcut):
        return
    g.yorum_yaz(no, "\n".join(satirlar))
