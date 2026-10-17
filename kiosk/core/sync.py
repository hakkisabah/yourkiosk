"""Senkronizasyon: lastupdate kontrolü + cihazın yerini bulma + nöbet günü seçimi.

AKIŞ (kullanıcı spec'i)
-----------------------
1. `lastupdate.json` nöbet verisinin en son ne zaman işlendiğini söyler.
   Cihazda saklanan değerden farklıysa kontroller yapılır (veri yenilenir).
2. Değişiklik varsa `lastSystemData.json` ve `match.json` okunur.
3. `match.json` içinde cihazın kendi kimliği (`makinebilgileri.json` -> clientID)
   aranır: hangi ilçe ve bölge id'sinin içindeyse, `lastSystemData.json` içinde
   o ilçe/bölgeye ait kayıtlar gösterilir.
4. Nöbet günü 08:30 kuralıyla seçilir (T<YYYYMMDD> anahtarı).

Bu modülün saf fonksiyonları Qt olmadan test edilir; `SenkronServisi` yalnızca
saatlik zamanlayıcıyı ve sinyalleri yönetir.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import config

log = logging.getLogger("kiosk.senkron")

#: Cihazın son gördüğü lastupdate değerini sakladığı dosya
DURUM_DOSYASI = ".cache/son_guncelleme.json"


# ------------------------------------------------------------------ yardımcılar
def _metin(deger: object) -> str:
    return deger.strip() if isinstance(deger, str) else ("" if deger is None else str(deger).strip())


def zaman_damgasi(deger: object) -> str:
    """lastupdate değerini karşılaştırılabilir metne çevirir (boşsa '')."""
    return _metin(deger)


def lastupdate_oku(govde: object) -> str:
    """{'lastupdate': ...} gövdesinden zaman damgasını çıkarır."""
    if isinstance(govde, dict):
        return zaman_damgasi(govde.get("lastupdate", govde.get("lastUpdate")))
    return ""


def degisti_mi(yeni: str, onceki: str) -> bool:
    """Zaman damgası değişti mi? (boş/eski değer 'değişti' sayılır)"""
    return zaman_damgasi(yeni) != zaman_damgasi(onceki)


def durum_oku(yol: str | None = None) -> dict:
    hedef = Path(yol or DURUM_DOSYASI)
    try:
        return json.loads(hedef.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def durum_yaz(govde: dict, yol: str | None = None) -> None:
    hedef = Path(yol or DURUM_DOSYASI)
    try:
        hedef.parent.mkdir(parents=True, exist_ok=True)
        hedef.write_text(json.dumps(govde, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as hata:
        log.warning("senkron durumu yazılamadı (%s): %s", hedef, hata)


# ------------------------------------------------------------ cihazın konumu
@dataclass(frozen=True, slots=True)
class CihazKonumu:
    """Cihazın match.json'dan öğrendiği ilçe/bölge kimlikleri."""

    ilce_id: str = ""
    bolge_id: str = ""
    ilce: str = ""
    bolge: str = ""
    bulundu: bool = False


def cihaz_konumunu_bul(match: object, client_id: str) -> CihazKonumu:
    """match.json içinde cihazın ilçe/bölge kimliklerini arar.

    match.json biçimi: { <ilceId>: [ { <bolgeId>: [makine id'leri] }, ... ], "lastUpdate": ... }
    """
    client_id = _metin(client_id)
    if not client_id or not isinstance(match, dict):
        return CihazKonumu()
    for ilce_id, ilce_listesi in match.items():
        if ilce_id.lower() == "lastupdate" or not isinstance(ilce_listesi, list):
            continue
        for bolge_kutusu in ilce_listesi:
            if not isinstance(bolge_kutusu, dict):
                continue
            for bolge_id, makineler in bolge_kutusu.items():
                if isinstance(makineler, list) and client_id in [str(m) for m in makineler]:
                    return CihazKonumu(ilce_id=str(ilce_id), bolge_id=str(bolge_id), bulundu=True)
    log.warning("cihaz kimliği match.json içinde bulunamadı: %s", client_id)
    return CihazKonumu()


def konum_adlarini_bul(sistem_verisi: object, konum: CihazKonumu) -> CihazKonumu:
    """Kayıtlardan ilçe/bölge adlarını bulup konumu zenginleştirir."""
    for kayit in tum_kayitlar(sistem_verisi):
        if str(kayit.get("bolgeId")) == konum.bolge_id:
            return CihazKonumu(
                ilce_id=konum.ilce_id,
                bolge_id=konum.bolge_id,
                ilce=_metin(kayit.get("ilce")),
                bolge=_metin(kayit.get("bolge")),
                bulundu=True,
            )
    return konum


# ------------------------------------------------------------------ nöbet günü
def nobet_anahtari(an: datetime | None = None) -> str:
    """Geçerli nöbet günü anahtarı: 'T20261014' (08:30 kuralı)."""
    an = an or datetime.now()
    saat, dakika = config.NOBET_DEGISIM_SAATI
    degisim = an.replace(hour=saat, minute=dakika, second=0, microsecond=0)
    gun = an.date() if an >= degisim else an.date() - timedelta(days=1)
    return "T" + gun.strftime("%Y%m%d")


def gun_bloklari(nobetler: object) -> dict:
    """{'T...': {...}} içinden yalnızca T-anahtarlı günleri döndürür."""
    if not isinstance(nobetler, dict):
        return {}
    return {k: v for k, v in nobetler.items() if isinstance(k, str) and k.startswith("T")}


def gun_pencereleri(nobetler: object) -> list[tuple[str, datetime | None, datetime | None]]:
    """Her gün bloğu için (anahtar, blok başlangıcı, blok bitişi).

    Blok penceresi = içindeki kayıtların **birleşimi** (en erken başlangıç, en geç bitiş).
    Böylece kısa bir nöbet (ör. 08:30→23:59) bloğun tamamını temsil etmez; aynı gün
    farklı saatlerde çalışan nöbetler (değişken çalışma saatleri) doğru temsil edilir.
    """
    pencereler: list[tuple[str, datetime | None, datetime | None]] = []
    for anahtar, blok in sorted(gun_bloklari(nobetler).items()):
        baslar, bitler = [], []
        for kayit in kayit_dizisi(blok):
            bas = _tarih(kayit.get("start") or kayit.get("baslangic"))
            bit = _tarih(kayit.get("end") or kayit.get("bitis"))
            if bas:
                baslar.append(bas)
            if bit:
                bitler.append(bit)
        pencereler.append((anahtar, min(baslar) if baslar else None, max(bitler) if bitler else None))
    return pencereler


def kayit_aktif_mi(kayit: object, an: datetime) -> bool:
    """Kaydın **kendi** penceresi şu anı kapsıyor mu? (`start ≤ an < end`)

    Sabit bir saat kuralı YOKTUR: nöbet saatleri değişse de (ör. 09:00, 23:59,
    ertesi gün 08:30) davranış kaydın kendi `start`/`end` değerinden türer.
    Penceresi okunamayan kayıt **gösterilir** (veriyi yargılayamıyorsak gizlemeyiz).
    """
    if not isinstance(kayit, dict):
        return False
    bas = _tarih(kayit.get("start") or kayit.get("baslangic"))
    bit = _tarih(kayit.get("end") or kayit.get("bitis"))
    if bas is None or bit is None:
        return True  # eksik pencere: karar veremiyoruz, gizlemiyoruz
    return bas <= an < bit


def aktif_kayitlar(kayitlar: list[dict], an: datetime, *, etiket: str = "nöbet") -> list[dict]:
    """Kayıtları kendi pencerelerine göre süzer (bitmiş/başlamamış olanlar düşer).

    Hiçbir kayıt kalmıyorsa (veri tuhaf/eksik) tümü döner ve uyarı yazılır —
    ekranın boş kalması, yanlış kaydı göstermekten daha kötüdür.
    """
    aktif = [k for k in kayitlar if kayit_aktif_mi(k, an)]
    if aktif:
        return aktif
    if kayitlar:
        log.warning(
            "%s: şu an aktif kayıt yok (%d kayıt süzüldü); blok olduğu gibi gösteriliyor",
            etiket,
            len(kayitlar),
        )
    return kayitlar


def gun_sec(nobetler: object, an: datetime | None = None) -> tuple[str, dict]:
    """Gösterilecek nöbet gününü, **kayıtların kendi pencerelerine** göre seçer.

    Sabit bir saat kuralı yoktur; nöbet saatleri (08:30, 09:00, 23:59, ertesi gün…)
    ne olursa olsun davranış veriden türer.

    Kural (sistematik):
      1. Birleşik penceresi `şimdi`yi kapsayan gün bloğu gösterilir
         (`start ≤ şimdi < end`, yarı açık aralık → kayıt kendi bitiş anında devreder).
      2. Böyle bir blok yoksa: en son **bitmiş** blok gösterilir
         (cihaz veriyi kaçırmışsa ekran boş kalmaz, yanlış güne atlamaz).
      3. Tüm bloklar gelecekteyse: başlamamış en yakın blok gösterilir + uyarı.
    """
    an = an or datetime.now()
    gunler = gun_bloklari(nobetler)
    if not gunler:
        return "", {}

    pencereler = gun_pencereleri(nobetler)

    # 1) şu anı kapsayan nöbet (tercih edilen)
    for anahtar, bas, bit in pencereler:
        if bas and bit and bas <= an < bit:
            return anahtar, gunler[anahtar]

    # 2) şu anki pencere yok: en son biten nöbeti göster (yanlış güne atlama)
    gecmis = [(k, bit) for k, _bas, bit in pencereler if bit and bit <= an]
    if gecmis:
        secili = max(gecmis, key=lambda x: x[1])[0]
        log.warning(
            "şu anki nöbet penceresi veride yok; en son biten nöbet gösteriliyor (%s) — "
            "veri tazelenmeli (tools/fetch_nobet.py)",
            secili,
        )
        return secili, gunler[secili]

    # 3) hepsi gelecekte: en yakın başlayacak nöbet
    gelecek = [(k, bas) for k, bas, _bit in pencereler if bas and bas > an]
    secili = min(gelecek, key=lambda x: x[1])[0] if gelecek else sorted(gunler)[-1]
    log.warning(
        "veride şu anki pencere yok; '%s' gösteriliyor (bu nöbet henüz başlamamış olabilir)",
        secili,
    )
    return secili, gunler[secili]


def _tarih(metin: object) -> datetime | None:
    if not isinstance(metin, str) or not metin.strip():
        return None
    for bicim in ("%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(metin.strip(), bicim)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(metin.strip())
    except ValueError:
        return None


# -------------------------------------------------------------- kayıt seçimi
def kayit_dizisi(blok: object) -> list[dict]:
    """Bir günün bloğundaki TÜM kayıtları (ilçe/bölge katmanlarından) çıkarır."""
    kayitlar: list[dict] = []
    for _ilce_id, ilce_listesi in (blok or {}).items() if isinstance(blok, dict) else []:
        if not isinstance(ilce_listesi, list):
            continue
        for bolge_kutusu in ilce_listesi:
            if not isinstance(bolge_kutusu, dict):
                continue
            for _bolge_id, bolge_kayitlari in bolge_kutusu.items():
                if isinstance(bolge_kayitlari, dict):
                    bolge_kayitlari = [bolge_kayitlari]
                if not isinstance(bolge_kayitlari, list):
                    continue
                kayitlar.extend(k for k in bolge_kayitlari if isinstance(k, dict))
    return kayitlar


def tum_kayitlar(sistem_verisi: object) -> list[dict]:
    """Tüm günlerdeki tüm kayıtlar (ilçe/bölge adlarını bulmak için)."""
    if not isinstance(sistem_verisi, dict):
        return []
    kayitlar: list[dict] = []
    for blok in gun_bloklari(sistem_verisi.get("Nobetler", {})).values():
        kayitlar.extend(kayit_dizisi(blok))
    return kayitlar


def ilce_bolge_filtrele(blok: dict, konum: CihazKonumu, kapsam: str = "") -> list[dict]:
    """Seçilen gün bloğundan cihazın ilçesine/bölgesine ait kayıtları döndürür.

    kapsam: 'bolge' -> yalnızca cihazın bölgesi, 'ilce' -> ilçedeki tüm bölgeler.
    """
    kapsam = (kapsam or config.KAPSAM).lower()
    secili: list[dict] = []
    if not isinstance(blok, dict):
        return secili

    for ilce_id, ilce_listesi in blok.items():
        if konum.ilce_id and str(ilce_id) != konum.ilce_id:
            continue
        for bolge_kutusu in ilce_listesi if isinstance(ilce_listesi, list) else []:
            if not isinstance(bolge_kutusu, dict):
                continue
            for bolge_id, kayitlar in bolge_kutusu.items():
                if kapsam == "bolge" and konum.bolge_id and str(bolge_id) != konum.bolge_id:
                    continue
                if isinstance(kayitlar, dict):
                    kayitlar = [kayitlar]
                if isinstance(kayitlar, list):
                    secili.extend(k for k in kayitlar if isinstance(k, dict))
    return secili


def gosterilecek_kayitlar(
    sistem_verisi: object,
    konum: CihazKonumu,
    an: datetime | None = None,
    kapsam: str = "",
) -> tuple[str, list[dict]]:
    """(nöbet günü anahtarı, cihazın göstereceği kayıtlar) döndürür.

    İki aşamalı süzme:
      1. gün bloğu — bloğun **birleşik** penceresi şu anı kapsayan gün (bkz. `gun_sec`),
      2. kayıt süzme — yalnızca **kendi penceresi** şu anı kapsayan kayıtlar gösterilir
         (ör. 08:30→23:59 nöbeti 23:59'dan sonra listeden düşer; sabit saat kuralı yok).
    """
    an = an or datetime.now()
    anahtar, blok = gun_sec(sistem_verisi.get("Nobetler", {}) if isinstance(sistem_verisi, dict) else {}, an)
    if not blok:
        return anahtar, []
    kayitlar = ilce_bolge_filtrele(blok, konum, kapsam)
    if not kayitlar:
        if konum.bolge_id:
            log.warning(
                "cihazın ilçe/bölgesi için kayıt yok (ilceId=%s bolgeId=%s)", konum.ilce_id, konum.bolge_id
            )
        return anahtar, []
    aktif = aktif_kayitlar(kayitlar, an, etiket=f"{konum.ilce or konum.ilce_id} nöbeti")
    return anahtar, aktif


# ------------------------------------------------------------ yayın seçimi
def aktif_yayinlar(sistem_verisi: object, an: datetime | None = None) -> list[dict]:
    """Zaman aralığında olan yayınları döndürür (start <= şimdi <= end)."""
    an = an or datetime.now()
    yayinlar = sistem_verisi.get("Yayinlar", {}) if isinstance(sistem_verisi, dict) else {}
    if not isinstance(yayinlar, dict):
        return []
    aktif = []
    for yayin in yayinlar.values():
        if not isinstance(yayin, dict):
            continue
        try:
            bas = datetime.fromisoformat(str(yayin["start"]).replace("Z", "+00:00"))
            bit = datetime.fromisoformat(str(yayin["end"]).replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        try:
            if bas <= an <= bit:
                aktif.append(yayin)
        except TypeError:
            continue
    return aktif


# ----------------------------------------------------------------- servis (Qt)
# Not: lastupdate kontrolü `core/data_handler.py` içinde yapılır; referans
# uygulamanın veri zamanlayıcısı (saatte 1) `load_data()` çağırır ve veri
# değişmediyse ekran yeniden kurulmaz. Ayrı bir zamanlayıcıya gerek yok.
