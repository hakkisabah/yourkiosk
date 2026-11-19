"""Nöbet verisini kaynaktan çekip S3'e yazar (Lambda zamanlanmış görev / panel butonu).

Cihazın beklediği şema: {"Nobetler": {...}, "Yayinlar": {...}, "lastUpdate": "..."}.
Kaynak: https://www.kocaelieo.org.tr/nobet-belediye/<bas>/<bit>/ (JSON).
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any

NOBET_URL = "https://www.kocaelieo.org.tr/nobet-belediye/{baslangic}/{bitis}/"
EN_FAZLA_GUN = 30
IZINLI_HOST = "www.kocaelieo.org.tr"


def id_uret(anahtar: str, tip: str) -> str:
    ozet = hashlib.sha1(f"{tip}:{anahtar}".encode("utf-8")).hexdigest()
    return f"{int(ozet, 16) % 10**17:017d}"


def tarihi_sablona_cevir(metin: str) -> str:
    return datetime.fromisoformat(metin.strip()).strftime("%d/%m/%Y %H:%M")


def gun_anahtari(an: date) -> str:
    return f"T{an.strftime('%Y%m%d')}"


def sablona_cevir(ham: dict) -> dict:
    agac: dict[str, dict] = {}
    for kayit in ham.values():
        if not isinstance(kayit, dict) or not kayit.get("eczane"):
            continue
        baslangic = datetime.fromisoformat(str(kayit["baslangic"]))
        anahtar = gun_anahtari(baslangic.date())
        ilce = str(kayit.get("ilce", "")).strip()
        bolge = str(kayit.get("bolge", "")).strip()
        ilce_id = id_uret(ilce, "ilce")
        bolge_id = id_uret(f"{ilce}|{bolge}", "bolge")
        yeni = {
            "ilce": ilce, "ilceId": ilce_id, "bolge": bolge, "bolgeId": bolge_id,
            "eczane": str(kayit.get("eczane", "")).strip(),
            "adres": kayit.get("adres", ""), "tel": kayit.get("tel", ""),
            "adres_tarifi": kayit.get("adres_tarifi", ""),
            "enlem": kayit.get("enlem", ""), "boylam": kayit.get("boylam", ""),
            "start": tarihi_sablona_cevir(str(kayit["baslangic"])),
            "end": tarihi_sablona_cevir(str(kayit["bitis"])),
        }
        gun = agac.setdefault(anahtar, {})
        ilce_kutusu = gun.setdefault(ilce_id, [])
        bolge_kutusu = next((b for b in ilce_kutusu if bolge_id in b), None)
        if bolge_kutusu is None:
            bolge_kutusu = {bolge_id: []}
            ilce_kutusu.append(bolge_kutusu)
        bolge_kutusu[bolge_id].append(yeni)
    return {a: agac[a] for a in sorted(agac)}


def _url_host_uygun(url: str) -> bool:
    return url.startswith("https://" + IZINLI_HOST + "/")


def ham_veriyi_cek(baslangic: date, gun: int = 16, url: str | None = None) -> dict:
    if gun < 1 or gun > EN_FAZLA_GUN:
        raise ValueError(f"gün 1..{EN_FAZLA_GUN} olmalı")
    hedef = url or NOBET_URL.format(
        baslangic=baslangic.isoformat(),
        bitis=(baslangic + timedelta(days=gun - 1)).isoformat(),
    )
    if not _url_host_uygun(hedef):
        raise ValueError("yalnızca kocaelieo.org.tr https adresi")
    istek = urllib.request.Request(hedef, headers={"User-Agent": "yourkiosk-panel/1"})
    with urllib.request.urlopen(istek, timeout=30) as yanit:  # noqa: S310 - sabit host
        metin = yanit.read(16 * 1024 * 1024).decode("utf-8-sig")
    veri = json.loads(metin)
    if not isinstance(veri, dict):
        raise ValueError("kaynak JSON nesne değil")
    return veri


def _oku(s3: Any, kova: str, anahtar: str) -> dict | None:
    try:
        yanit = s3.get_object(Bucket=kova, Key=anahtar)
        return json.loads(yanit["Body"].read().decode("utf-8"))
    except Exception:  # noqa: BLE001 - yoksa/okunamazsa yeni belge
        return None


def guncelle(s3: Any, kova: str, on_ek: str, ham: dict | None = None,
             baslangic: date | None = None, gun: int = 16) -> dict:
    anahtar = f"{on_ek}lastSystemData.json"
    mevcut = _oku(s3, kova, anahtar) or {}
    ham = ham if ham is not None else ham_veriyi_cek(baslangic or (date.today() - timedelta(days=1)), gun)
    yeni = sablona_cevir(ham)
    if mevcut.get("Nobetler") == yeni:
        return {"degisti": False, "gun": len(yeni), "kayit": _kayit_sayisi(yeni)}
    belge = dict(mevcut)
    belge["Nobetler"] = yeni
    belge.setdefault("Yayinlar", {})
    belge["lastUpdate"] = datetime.now().replace(microsecond=0).isoformat()
    gövde = json.dumps(belge, ensure_ascii=False).encode("utf-8")
    s3.put_object(Bucket=kova, Key=anahtar, Body=gövde,
                  ContentType="application/json; charset=utf-8", CacheControl="no-store")
    damga = belge["lastUpdate"]
    s3.put_object(Bucket=kova, Key=f"{on_ek}lastupdate.json",
                  Body=json.dumps({"lastupdate": damga}, ensure_ascii=False).encode("utf-8"),
                  ContentType="application/json; charset=utf-8", CacheControl="no-store")
    return {"degisti": True, "gun": len(yeni), "kayit": _kayit_sayisi(yeni), "lastupdate": damga}


def _kayit_sayisi(agac: dict) -> int:
    toplam = 0
    for gun in agac.values():
        for ilce in gun.values():
            for bolge in ilce:
                for kayitlar in bolge.values():
                    toplam += len(kayitlar)
    return toplam
