"""GEÇİCİ: sol panelde 5'ten fazla nöbetçi görünümünü sınamak için veri üretir.

Kullanıcı isteği: "5 ten fazla nöbet gösterimi için geçici bir data yapmanı istiyorum,
çalışmanı bitirip ben de gördükten sonra silersin."

Ne yapar:
  * mevcut `lastSystemData.json`'u `_arsiv/lastSystemData.gercek.json` olarak yedekler,
  * cihazın **ilçesindeki** kayıt sayısını `--adet`e (varsayılan 8) tamamlar
    (var olanlar korunur, eksikler SAHTE eczane/bölge ile üretilir),
  * `lastSystemData.json`'u bu geçici kopyayla değiştirir.

Geri alma: `python3 tools/gecici_coklu_test.py --geri-al`
(bu betik silinecek; yedeği elle geri kopyalamak da yeterli).

Gerçek veri kaynağı: tools/fetch_nobet.py
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
SISTEM = KOK / "lastSystemData.json"
YEDEK = KOK / "_arsiv" / "lastSystemData.gercek.json"
ISARET = KOK / "_arsiv" / "GECICI-COKLU-TEST.md"

SAHTE_ECZANELER = [
    ("ÖRNEK ECZANESİ", "0262 111 11 11"),
    ("DENEME ECZANESİ", "0262 222 22 22"),
    ("TEST ECZANESİ", "0262 333 33 33"),
    ("NUMUNE ECZANESİ", "0262 444 44 44"),
    ("GEÇİCİ ECZANESİ", "0262 555 55 55"),
]


def _ilce_anahtari(sistem: dict, bolge_id: str | None) -> str:
    """Cihazın bölge id'sinden ilçe id'sini bulur (ilk günden)."""
    gun = sorted(sistem["Nobetler"])[0]
    for ilce_id, ilce_listesi in sistem["Nobetler"][gun].items():
        for kutu in ilce_listesi:
            if bolge_id and bolge_id in kutu:
                return ilce_id
    return next(iter(sistem["Nobetler"][gun]))


def cogalt(sistem: dict, adet: int, bolge_id: str | None = None) -> dict:
    """Hedef ilçedeki kayıt sayısını `adet`e tamamlar (eksikler sahte)."""
    gunler = sorted(sistem["Nobetler"])
    ilce_id = _ilce_anahtari(sistem, bolge_id)
    for sira, gun in enumerate(gunler[:3]):  # ilk 3 gün yeterli (ekranda 1 gün görünür)
        blok = sistem["Nobetler"][gun]
        ilce_listesi = blok.setdefault(ilce_id, [])
        mevcut = sum(len(v) for kutu in ilce_listesi for v in kutu.values())
        if mevcut >= adet:
            continue
        ilk_kayit = next(
            (k for kutu in ilce_listesi for kayitlar in kutu.values() for k in kayitlar), {}
        )
        ilce_ad = ilk_kayit.get("ilce", "TEST")
        for i in range(mevcut, adet):
            eczane, tel = SAHTE_ECZANELER[(i + sira) % len(SAHTE_ECZANELER)]
            bolge_adi = f"{ilce_ad.title()} {i + 1}.Bölge"
            yeni_id = f"9{i:016d}"
            kayit = dict(ilk_kayit)
            kayit.update(
                {
                    "bolge": bolge_adi,
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


def main() -> int:
    ayristirici = argparse.ArgumentParser(description="GEÇİCİ: 5+ nöbetçi görünümü için veri")
    ayristirici.add_argument("--adet", type=int, default=8, help="hedef kayıt sayısı (varsayılan 8)")
    ayristirici.add_argument("--geri-al", action="store_true", help="gerçek veriyi yedekten geri yükle")
    ayarlar = ayristirici.parse_args()

    if ayarlar.geri_al:
        if not YEDEK.is_file():
            print("yedek bulunamadı:", YEDEK)
            return 1
        shutil.copy2(YEDEK, SISTEM)
        ISARET.unlink(missing_ok=True)
        print("gerçek veri geri yüklendi:", SISTEM)
        return 0

    if not SISTEM.is_file():
        print("lastSystemData.json yok; önce tools/fetch_nobet.py çalıştırın")
        return 1
    if json.loads(SISTEM.read_text(encoding="utf-8")).get("_gecici_test"):
        print("görünüşe göre geçici veri zaten üretilmiş; önce --geri-al çalıştırın")
        return 1

    YEDEK.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SISTEM, YEDEK)
    makine = json.loads((KOK / "makinebilgileri.json").read_text(encoding="utf-8"))
    client = str(makine.get("clientID", ""))
    match = json.loads((KOK / "match.json").read_text(encoding="utf-8"))
    bolge_id = next(
        (b for i in match.values() if isinstance(i, list) for kutu in i for b, m in kutu.items()
         if client in [str(x) for x in m]),
        None,
    )
    sistem = cogalt(json.loads(SISTEM.read_text(encoding="utf-8")), ayarlar.adet, bolge_id)
    SISTEM.write_text(json.dumps(sistem, ensure_ascii=False, indent=2), encoding="utf-8")
    ISARET.write_text(
        "# GEÇİCİ TEST VERİSİ (silinecek)\n\n"
        f"* Üretildi: {datetime.now().isoformat(timespec='seconds')}\n"
        f"* Gerçek veri yedeği: `{YEDEK.relative_to(KOK)}`\n"
        f"* Amaç: sol panelde 5'ten fazla nöbetçi görünümünü sınamak (satırlar küçülür; kaydırma sonraki adım)\n"
        "* Geri alma: `python3 tools/gecici_coklu_test.py --geri-al`\n",
        encoding="utf-8",
    )

    gun = sorted(sistem["Nobetler"])[0]
    adet = sum(len(v) for kutu in sistem["Nobetler"][gun][_ilce_anahtari(sistem, bolge_id)] for v in kutu.values())
    print(f"geçici veri yazıldı: ilk günde {adet} kayıt (hedef {ayarlar.adet})")
    print("gerçek veri yedeği :", YEDEK)
    print("geri alma          : python3 tools/gecici_coklu_test.py --geri-al")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
