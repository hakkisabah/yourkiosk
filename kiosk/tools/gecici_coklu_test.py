#!/usr/bin/env python3
"""GEÇİCİ: sol panelde "5'ten fazla nöbetçi" görünümünü sınamak için veri üretir.

NEDEN VAR: cihazın gerçek verisinde günde 1–2 kayıt olur; kaydırmalı görünüm (6. satırda kayma)
ancak 5'ten fazla kayıtla denenebilir.

NE YAPAR:
  * `lastSystemData.json` ve `lastupdate.json` dosyalarını `_arsiv/` altına yedekler,
  * **ekranda gösterilecek bloğu** (uygulamanın kendi kuralı: `core.sync.gun_sec`, 08:30 devri)
    ve istenirse komşu günleri, cihazın **ilçesinde** `--adet` kayda tamamlar,
  * `lastSystemData.json`'u bu geçici veriyle değiştirir ve **`lastupdate.json` damgasını tazeler**
    (damga tazelenmezse arayüz/cihaz önbellekten eski veriyi göstermeye devam eder).

ÖNEMLİ (eski sürümdeki iki hata):
  1. Doldurma sabit olarak "ilk üç gün"e yapılıyordu; uygulama ise **"şimdi"yi içeren bloğu**
     gösterir. Veri 16 günlük olduğunda sahte kayıtlar hiç görünmedi (ekranda cihazın kendi
     kayıtları kaldı). Bu sürüm bloğu uygulamayla AYNI fonksiyonla seçer.
  2. `lastupdate.json` damgası tazelenmiyordu → arayüz damgaya bağlı önbellekten eski gövdeyi
     servis etmeye devam ediyordu.

KULLANIM:
    python3 tools/gecici_coklu_test.py --adet 8            # gösterilecek blok + yarını doldur
    python3 tools/gecici_coklu_test.py --adet 8 --kuru      # yazmadan planı göster
    python3 tools/gecici_coklu_test.py --adet 8 --hepsi     # tüm gün bloklarını doldur
    python3 tools/gecici_coklu_test.py --ilce <ilceId>      # başka ilçeyi hedefle (varsayılan: cihazınki)
    python3 tools/gecici_coklu_test.py --geri-al            # gerçek veriyi + damgayı geri yükle

Geri alma dosyaları: `_arsiv/lastSystemData.gercek.json`, `_arsiv/lastupdate.gercek.json`.
Bu araç geçicidir: iş bitince silinir (yedeği elle kopyalamak da yeterli).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from core import sync  # noqa: E402  (uygulamanın kendi blok/kapsam kuralları — tekrar yazmıyoruz)

SISTEM = KOK / "lastSystemData.json"
LASTUPDATE = KOK / "lastupdate.json"
ARSIV = KOK / "_arsiv"
SISTEM_YEDEK = ARSIV / "lastSystemData.gercek.json"
LASTUPDATE_YEDEK = ARSIV / "lastupdate.gercek.json"
ISARET = ARSIV / "GECICI-COKLU-TEST.md"

SAHTE_ECZANELER = [
    ("ÖRNEK ECZANESİ", "0262 111 11 11"),
    ("DENEME ECZANESİ", "0262 222 22 22"),
    ("TEST ECZANESİ", "0262 333 33 33"),
    ("NUMUNE ECZANESİ", "0262 444 44 44"),
    ("GEÇİCİ ECZANESİ", "0262 555 55 55"),
]


def ozet(yol: Path) -> str:
    """Dosya içeriğinin kısa parmak izi (geri alma doğrulaması için)."""
    return hashlib.sha256(yol.read_bytes()).hexdigest()[:12] if yol.is_file() else "-"


def cihaz_konumu() -> tuple[str, str | None]:
    """Cihazın (ilçe, bölge) kimlikleri — `makinebilgileri.json` + `match.json`."""
    try:
        client = str(json.loads((KOK / "makinebilgileri.json").read_text(encoding="utf-8")).get("clientID", ""))
        match = json.loads((KOK / "match.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "", None
    konum = sync.cihaz_konumunu_bul(match, client)
    return str(konum.ilce_id or ""), (str(konum.bolge_id) if konum.bolge_id else None)


def hedef_bloklar(nobetler: dict, an: datetime, *, hepsi: bool = False, komsu: int = 1) -> list[str]:
    """Doldurulacak gün blokları: ekranda gösterilen blok (+komşuları) ya da hepsi.

    Blok, uygulamayla AYNI kurala göre seçilir (`core.sync.gun_sec` → 08:30 devri).
    """
    gunler = sorted(nobetler)
    if hepsi:
        return gunler
    anahtar, _ = sync.gun_sec(nobetler, an)
    if anahtar not in gunler:  # beklenmedik durum: en yakın bloğa düş
        return gunler[:1]
    i = gunler.index(anahtar)
    return gunler[i : i + 1 + max(0, komsu)]


def cogalt(sistem: dict, adet: int, ilce_id: str, bloklar: list[str]) -> dict:
    """Belirtilen gün bloklarında hedef ilçenin kayıt sayısını `adet`e tamamlar (sahte kayıtlar)."""
    for sira, gun in enumerate(bloklar):
        blok = sistem["Nobetler"].setdefault(gun, {})
        ilce_listesi = blok.setdefault(ilce_id, [])
        mevcut = sum(len(v) for kutu in ilce_listesi for v in kutu.values())
        if mevcut >= adet:
            continue
        ilk_kayit = next((k for kutu in ilce_listesi for kayitlar in kutu.values() for k in kayitlar), {})
        ilce_ad = str(ilk_kayit.get("ilce", "TEST"))
        for i in range(mevcut, adet):
            eczane, tel = SAHTE_ECZANELER[(i + sira) % len(SAHTE_ECZANELER)]
            yeni_id = f"9{i:016d}"
            kayit = dict(ilk_kayit)
            kayit.update(
                {
                    "bolge": f"{ilce_ad.title()} {i + 1}.Bölge",
                    "bolgeId": yeni_id,
                    "eczane": f"{eczane} (geçici)",
                    "tel": tel,
                    "adres": "GEÇİCİ TEST ADRESİ",
                    "adres_tarifi": "",
                }
            )
            ilce_listesi.append({yeni_id: [kayit]})
    sistem["_gecici_test"] = True
    return sistem


def blok_sayisi(sistem: dict, gun: str, ilce_id: str) -> int:
    blok = (sistem.get("Nobetler") or {}).get(gun) or {}
    return sum(len(v) for kutu in blok.get(ilce_id, []) for v in kutu.values())


def main() -> int:
    ap = argparse.ArgumentParser(description="GEÇİCİ: 5+ nöbetçi görünümü için veri üret")
    ap.add_argument("--adet", type=int, default=8, help="hedef kayıt sayısı (varsayılan 8)")
    ap.add_argument("--ilce", default="", help="hedef ilçe kimliği (varsayılan: cihazın ilçesi)")
    ap.add_argument("--hepsi", action="store_true", help="tüm gün bloklarını doldur")
    ap.add_argument("--komsu", type=int, default=1, help="gösterilen bloğa ek kaç komşu gün (varsayılan 1)")
    ap.add_argument("--kuru", action="store_true", help="hiçbir şey yazma; planı göster")
    ap.add_argument("--geri-al", action="store_true", help="gerçek veriyi ve damgayı yedekten geri yükle")
    a = ap.parse_args()

    if a.geri_al:
        if not SISTEM_YEDEK.is_file():
            print("yedek bulunamadı:", SISTEM_YEDEK)
            return 1
        shutil.copy2(SISTEM_YEDEK, SISTEM)
        if LASTUPDATE_YEDEK.is_file():
            shutil.copy2(LASTUPDATE_YEDEK, LASTUPDATE)
        ISARET.unlink(missing_ok=True)
        print("gerçek veri geri yüklendi:", SISTEM)
        print(f"  lastSystemData özeti: {ozet(SISTEM)}  (yedek: {ozet(SISTEM_YEDEK)})")
        damga = LASTUPDATE.read_text(encoding="utf-8").strip() if LASTUPDATE.is_file() else "-"
        print(f"  lastupdate: {damga}")
        return 0

    if not SISTEM.is_file():
        print("lastSystemData.json yok; önce tools/fetch_nobet.py çalıştırın")
        return 1
    ham = json.loads(SISTEM.read_text(encoding="utf-8"))
    if ham.get("_gecici_test"):
        print("görünüşe göre geçici veri zaten üretilmiş; önce --geri-al çalıştırın")
        return 1

    nobetler = ham.get("Nobetler")
    if not isinstance(nobetler, dict) or not nobetler:
        print("veri beklenen biçimde değil (Nobetler yok)")
        return 1

    an = datetime.now()
    cihaz_ilce, cihaz_bolge = cihaz_konumu()
    ilce_id = a.ilce or cihaz_ilce or next(iter(nobetler[sorted(nobetler)[0]]))
    bloklar = hedef_bloklar(nobetler, an, hepsi=a.hepsi, komsu=a.komsu)

    print(f"cihaz          : ilçe={cihaz_ilce or '?'} bölge={cihaz_bolge or '?'}")
    print(f"hedef ilçe     : {ilce_id}{'   (--ilce ile verildi)' if a.ilce else '   (cihazın ilçesi)'}")
    print(f"şimdi          : {an.isoformat(timespec='seconds')}")
    print(f"gösterilecek   : {sync.gun_sec(nobetler, an)[0]}   ← uygulamanın seçtiği blok")
    print(f"doldurulacak   : {', '.join(bloklar)}")

    sistem = cogalt(ham, a.adet, ilce_id, bloklar)
    for gun in bloklar:
        print(f"  · {gun}: {blok_sayisi(sistem, gun, ilce_id)} kayıt")

    if a.kuru:
        print("\n--kuru: hiçbir şey yazılmadı.")
        return 0

    ARSIV.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SISTEM, SISTEM_YEDEK)
    if LASTUPDATE.is_file():
        shutil.copy2(LASTUPDATE, LASTUPDATE_YEDEK)

    SISTEM.write_text(json.dumps(sistem, ensure_ascii=False, indent=2), encoding="utf-8")
    # DAMGA TAZELE: arayüz/cihaz önbelleği damgaya bağlı; tazelenmezse eski veri görünür.
    damga = sync.zaman_damgasi(datetime.now())
    LASTUPDATE.write_text(json.dumps({"lastupdate": damga}, ensure_ascii=False), encoding="utf-8")

    ISARET.write_text(
        "# GEÇİCİ TEST VERİSİ (silinecek)\n\n"
        f"* Üretildi: {datetime.now().isoformat(timespec='seconds')}\n"
        f"* Hedef ilçe: `{ilce_id}` · doldurulan bloklar: {', '.join(bloklar)} · adet: {a.adet}\n"
        f"* Gerçek veri yedeği: `{SISTEM_YEDEK.relative_to(KOK)}` (+ `{LASTUPDATE_YEDEK.name}`)\n"
        "* Amaç: sol panelde 5'ten fazla nöbetçi görünümünü sınamak (6. satırda kaydırma başlar)\n"
        "* Geri alma: `python3 tools/gecici_coklu_test.py --geri-al`\n",
        encoding="utf-8",
    )

    print(f"\ngeçici veri yazıldı · damga tazelendi: {damga}")
    print(f"gerçek veri yedeği : {SISTEM_YEDEK}")
    print("geri alma          : python3 tools/gecici_coklu_test.py --geri-al")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
