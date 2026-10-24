"""Yayın hedefleme (kapsam): bir yayının BU cihazda gösterilip gösterilmeyeceği.

VERİ MODELİ (geriye uyumlu — alanlar İSTEĞE BAĞLI):

    "Yayinlar": {
      "3": {
        "start": "2026-10-24T08:30:00", "end": "2026-10-24T23:59:00",
        "contentUrl": "https://…/9f2c1ab34de5f607.webp", "duration": 30,

        "ilceId":  "30607352906750376",   // yalnız bu ilçedeki cihazlar (boş = tümü)
        "bolgeId": "73154087615041151",   // yalnız bu bölge (ilçe ile birlikte daraltır)
        "cihazId": "98273648723468273"    // yalnız TEK cihaz (en dar kapsam)
      }
    }

KURALLAR
  • Alan yok/boş  → kısıt yok (bugünkü 60 kayıt böyle → davranış DEĞİŞMEZ).
  • Hepsi dolu    → üçü de eşleşmeli (VE).
  • Eşleşmeyen cihaz yayını HİÇ görmez (indirmez, önbelleğe almaz) → maliyet düşer.
  • Tanınmayan alan yok sayılır (ileride `semt`, `grup` eklenebilir).

NEDEN AYRI MODÜL: aynı kural Qt (`core/broadcast_manager.py`) ve tarayıcı
(`web/src/veri/yayin.ts`) tarafında BİREBİR aynı olmalı; tek yerde tutulur, ikisi de buradan
beslenir (tarayıcı tarafı aynı kuralların TS kopyasını taşır + testleri vardır).
"""

from __future__ import annotations

#: Kapsam alanları ve normalizasyon (anahtar → yayın kaydındaki olası adlar)
KAPSAM_ALANLARI: dict[str, tuple[str, ...]] = {
    "ilceId": ("ilceId", "ilce_id", "ilce"),
    "bolgeId": ("bolgeId", "bolge_id", "bolge"),
    "cihazId": ("cihazId", "cihaz_id", "clientID", "clientId"),
}


def _metin(deger: object) -> str:
    return str(deger or "").strip()


def yayin_kapsami(yayin: dict) -> dict[str, str]:
    """Yayın kaydındaki kapsam alanlarını normalize eder (boş = kısıt yok)."""
    sonuc: dict[str, str] = {}
    for anahtar, adlar in KAPSAM_ALANLARI.items():
        deger = ""
        for ad in adlar:
            aday = _metin(yayin.get(ad))
            if aday:
                deger = aday
                break
        sonuc[anahtar] = deger
    return sonuc


def kapsam_uygun(yayin: dict, ilce_id: str = "", bolge_id: str = "", cihaz_id: str = "") -> bool:
    """Yayın bu cihaz için geçerli mi? (boş kapsam = tüm cihazlar)"""
    kapsam = yayin_kapsami(yayin)
    if kapsam["ilceId"] and kapsam["ilceId"] != _metin(ilce_id):
        return False
    if kapsam["bolgeId"] and kapsam["bolgeId"] != _metin(bolge_id):
        return False
    if kapsam["cihazId"] and kapsam["cihazId"] != _metin(cihaz_id):
        return False
    return True


def kapsam_ozeti(yayin: dict) -> str:
    """İnsan okur kapsam metni (günlük/teşhis için)."""
    kapsam = yayin_kapsami(yayin)
    parcalar = []
    if kapsam["cihazId"]:
        parcalar.append(f"cihaz={kapsam['cihazId']}")
    if kapsam["bolgeId"]:
        parcalar.append(f"bölge={kapsam['bolgeId']}")
    if kapsam["ilceId"]:
        parcalar.append(f"ilçe={kapsam['ilceId']}")
    return " · ".join(parcalar) if parcalar else "tüm cihazlar"
