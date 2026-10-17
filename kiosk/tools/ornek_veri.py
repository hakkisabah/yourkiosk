"""Örnek (demo) veri üretir — ağa çıkmadan, tanıtım amaçlı.

Açık kaynak projeyi indiren kişi tek komutla çalışan bir ekran görebilsin diye
gerçek cihaz verisini taklit eden küçük dosyalar üretir:
`lastupdate.json`, `match.json`, `lastSystemData.json`, `makinebilgileri.json`.

  * cihaz kimliği **uydurma** (`ORNEK-CIHAZ-0001`),
  * 2 gün × 2 ilçe × 3 bölge, 08:30 → ertesi gün 08:30 nöbet penceresi,
  * yayınlar **gün boyu** aktif (kuşak hemen görünsün diye).

Gerçek veri için `tools/fetch_nobet.py` kullanılır.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
ORNEK_CIHAZ = "ORNEK-CIHAZ-0001"

ILCELER = {
    "10000000000000001": {
        "ad": "İZMİT",
        "bolgeler": {
            "20000000000000001": "İzmit-1",
            "20000000000000002": "İzmit-2",
            "20000000000000003": "İzmit-3",
        },
        "eczaneler": [
            ("DEVA ECZANESİ", "0262 325 13 35", "ÖMERAĞA MAH. ABDURRAHMAN YÜKSEL CAD. NO:3", ""),
            ("ASLI ECZANESİ", "0262 323 01 42", "CEDİT MAH. CUMHURİYET CAD. NO:12", "Hastane karşısı"),
            ("ETEM ECZANESİ", "0262 323 28 66", "KEMALPAŞA MAH. İSTİKLAL CAD. NO:45", ""),
        ],
    },
    "10000000000000002": {
        "ad": "GEBZE",
        "bolgeler": {
            "20000000000000011": "Gebze-1",
            "20000000000000012": "Gebze-2",
            "20000000000000013": "Gebze-3",
        },
        "eczaneler": [
            ("HAYAT ECZANESİ", "0262 641 10 20", "OSMAN YILMAZ MAH. ATATÜRK CAD. NO:7", "Belediye yanı"),
            ("ŞİFA ECZANESİ", "0262 641 22 33", "GÜZELLER MAH. BAĞDAT CAD. NO:88", ""),
            ("MERKEZ ECZANESİ", "0262 641 44 55", "HACI HALİL MAH. İNÖNÜ CAD. NO:3", "Meydan içi"),
        ],
    },
}


def _tarih_anahtari(gun: date) -> str:
    return "T" + gun.strftime("%Y%m%d")


def _nobet_kaydi(ilce_id: str, bolge_id: str, ad: str, bolge: str, eczane, baslangic: date) -> dict:
    bas = datetime.combine(baslangic, time(8, 30))
    bit = bas + timedelta(days=1)
    return {
        "ilce": ad,
        "ilceId": ilce_id,
        "bolge": bolge,
        "bolgeId": bolge_id,
        "eczane": eczane[0],
        "tel": eczane[1],
        "adres": eczane[2],
        "adres_tarifi": eczane[3],
        "start": bas.strftime("%d/%m/%Y %H:%M"),
        "end": bit.strftime("%d/%m/%Y %H:%M"),
    }


def uret(gun_sayisi: int = 2, baslangic: date | None = None) -> dict[str, object]:
    """Örnek veri dosyalarının içeriklerini (sözlük olarak) döndürür."""
    baslangic = baslangic or date.today()
    nobetler: dict[str, dict] = {}
    for ofset in range(gun_sayisi):
        gun = baslangic + timedelta(days=ofset)
        gun_blok: dict[str, list] = {}
        for ilce_id, ilce in ILCELER.items():
            bolge_listesi = []
            for sira, (bolge_id, bolge_adi) in enumerate(ilce["bolgeler"].items()):
                eczane = ilce["eczaneler"][(ofset + sira) % len(ilce["eczaneler"])]
                bolge_listesi.append(
                    {bolge_id: [_nobet_kaydi(ilce_id, bolge_id, ilce["ad"], bolge_adi, eczane, gun)]}
                )
            gun_blok[ilce_id] = bolge_listesi
        nobetler[_tarih_anahtari(gun)] = gun_blok

    gun_ilk = datetime.combine(baslangic, time(0, 0)).isoformat(timespec="milliseconds")
    gun_son = datetime.combine(baslangic + timedelta(days=gun_sayisi), time(23, 59)).isoformat(
        timespec="milliseconds"
    )
    yayinlar = {
        "1": {
            "start": gun_ilk,
            "end": gun_son,
            "duration": 15,
            "contentURL": "https://hakkisabah.com/api/havuzlu-bahce.png",
            "contentUrl": "https://hakkisabah.com/api/havuzlu-bahce.png",
        }
    }

    sistem = {
        "Nobetler": nobetler,
        "Yayinlar": yayinlar,
        "lastUpdate": f"{baslangic.isoformat()} 08:30:00",
        "_ornek": True,
    }
    match = {
        ilce_id: [{bolge_id: [ORNEK_CIHAZ]} for bolge_id in ilce["bolgeler"]]
        for ilce_id, ilce in ILCELER.items()
    }
    match["lastUpdate"] = sistem["lastUpdate"]
    return {
        "lastSystemData.json": sistem,
        "match.json": match,
        "lastupdate.json": {"lastupdate": sistem["lastUpdate"]},
        "makinebilgileri.json": {"clientID": ORNEK_CIHAZ},
    }


def yaz(
    hedef: Path | None = None,
    gun_sayisi: int = 2,
    baslangic: date | None = None,
    *,
    zorla: bool = False,
) -> list[str]:
    """Örnek dosyaları diske yazar; yazılan dosya adlarını döner.

    GÜVENLİK: hedefte **gerçek cihaz verisi** varsa (clientID örnek kimlikten
    farklıysa) üzerine yazmaz; `zorla=True` (CLI'da `--zorla`) gerekir.
    """
    hedef = Path(hedef) if hedef else KOK
    makine = hedef / "makinebilgileri.json"
    if makine.is_file() and not zorla:
        try:
            mevcut = json.loads(makine.read_text(encoding="utf-8")).get("clientID", "")
        except (OSError, json.JSONDecodeError):
            mevcut = ""
        if mevcut and mevcut != ORNEK_CIHAZ:
            raise SystemExit(
                "bu dizinde gerçek cihaz verisi var (clientID dolu). Örnek veri yazmak "
                "için --zorla kullanın veya --cikti-dizin ile başka bir dizin seçin."
            )
    yazilan: list[str] = []
    for ad, icerik in uret(gun_sayisi, baslangic).items():
        (hedef / ad).write_text(json.dumps(icerik, ensure_ascii=False, indent=2), encoding="utf-8")
        yazilan.append(ad)
    return yazilan


def main() -> int:
    import argparse

    ayristirici = argparse.ArgumentParser(description="Örnek (demo) veri üret")
    ayristirici.add_argument("--gun", type=int, default=2, help="gün sayısı (varsayılan 2)")
    ayristirici.add_argument("--cikti-dizin", type=Path, default=KOK)
    ayristirici.add_argument("--zorla", action="store_true", help="gerçek veri varsa da üzerine yaz")
    ayarlar = ayristirici.parse_args()

    yazilan = yaz(ayarlar.cikti_dizin, ayarlar.gun, zorla=ayarlar.zorla)
    print("örnek veri yazıldı:", ", ".join(yazilan))
    print(f"cihaz kimliği: {ORNEK_CIHAZ} (match.json içinde İzmit-2 bölgesinde)")
    print("çalıştır: ./run.sh --pencere")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
