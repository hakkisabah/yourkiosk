#!/usr/bin/env python3
"""Nöbet verisi çekici + şablon doldurucu.

AKIŞ
----
1. `https://www.kocaelieo.org.tr/nobet-belediye/<baslangic>/<bitis>/` adresinden
   nöbet verisi çekilir. Adresteki tarihler kritiktir:
     * ilk tarih  = veri aralığının BAŞLANGICI (bugün; yarın çekersen yarının tarihi olmalı),
     * ikinci tarih = aralığın BİTİŞİ ve en fazla 30 gün olabilir.
2. Gelen düz veri (ilce/bolge/eczane/tel/adres/…/baslangic/bitis) `sablon.json`
   yapısına çevrilir:

       Nobetler -> "T<YYYYMMDD>" -> { <ilceId>: [ { <bolgeId>: [kayıtlar] } ] }

   Kayıtlarda tarihler `gg/aa/yyyy ss:dd` biçimine döner (şablondaki gibi).
3. `ilceId` / `bolgeId` değerleri **üretilir** (isimden türeyen, kararlı 17 haneli
   sayılar) ve `data/id_eslesme.json` dosyasına yazılır.
4. `match.json` üretilir: ilçe id -> [ { bölge id -> [makine id'leri] } ].
   Cihazın kendi kimliği (`makinebilgileri.json` -> clientID) seçilen bölgeye konur.
5. `Yayinlar` blokları önümüzdeki 30 güne çoğaltılır.
6. Sonuçlar: `lastSystemData.json`, `match.json`, `lastupdate.json`.

KULLANIM
--------
    python3 tools/fetch_nobet.py                          # bugünden 16 gün
    python3 tools/fetch_nobet.py --gun 30                  # en fazla 30 gün
    python3 tools/fetch_nobet.py --baslangic 2026-10-14 --gun 16
    python3 tools/fetch_nobet.py --cihaz-bolge "İzmit-2"   # cihazın konulacağı bölge
    python3 tools/fetch_nobet.py --yerel /tmp/nobet.json   # ağa çıkmadan dosyadan
    python3 tools/fetch_nobet.py --kontrol                 # yalnız ortam/kimlik denetimi
    python3 tools/fetch_nobet.py --cihaz-id 123456789      # makinebilgileri.json yoksa oluştur

ÖNEMLİ: bu araç **kiosk CİHAZI** içindir; `makinebilgileri.json` (cihaz kimliği) depoda
bulunmaz. Kimlik yoksa araç traceback basmaz, ne yapılacağını söyler.
i5/i3 gibi **ajan** makinelerinde nöbet verisi üretmeye gerek yoktur (orada `otomasyon/` kullanılır).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import urllib.error
from datetime import date, datetime, timedelta
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
# Araç `tools/` altından çalıştırıldığı için proje kökünü yola ekle (config/security)
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

import config  # noqa: E402  (yol ayarından sonra)

NOBET_URL = "https://www.kocaelieo.org.tr/nobet-belediye/{baslangic}/{bitis}/"
EN_FAZLA_GUN = 30

log = logging.getLogger("kiosk.veri_cekici")


# --------------------------------------------------------------------- yardımcı
def id_uret(anahtar: str, tip: str) -> str:
    """İsimden türeyen kararlı 17 haneli kimlik (ilceId / bolgeId / makine id)."""
    ozet = hashlib.sha1(f"{tip}:{anahtar}".encode("utf-8")).hexdigest()
    return f"{int(ozet, 16) % 10**17:017d}"


def tarih_url(baslangic: date, gun: int) -> tuple[str, str]:
    """(baslangic_metni, bitis_metni) — bitiş en fazla 30 gün sonrası olabilir."""
    if gun < 1:
        raise ValueError("gün sayısı en az 1 olmalı")
    if gun > EN_FAZLA_GUN:
        raise ValueError(f"en fazla {EN_FAZLA_GUN} günlük veri çekilebilir (istenen: {gun})")
    return baslangic.isoformat(), (baslangic + timedelta(days=gun - 1)).isoformat()


def tarihi_sablona_cevir(metin: str) -> str:
    """'2026-10-14 08:30:00' -> '14/10/2026 08:30' (şablon biçimi)."""
    an = datetime.fromisoformat(metin.strip())
    return an.strftime("%d/%m/%Y %H:%M")


def gun_anahtari(an: date) -> str:
    return f"T{an.strftime('%Y%m%d')}"


# ------------------------------------------------------------------ çevirici
def sablona_cevir(ham: dict) -> dict[str, list[dict]]:
    """Düz nöbet verisini gün -> ilçe -> bölge -> kayıt ağacına çevirir."""
    agac: dict[str, dict] = {}
    for kayit in ham.values():
        if not isinstance(kayit, dict) or not kayit.get("eczane"):
            log.warning("geçersiz kayıt atlandı: %r", kayit)
            continue
        baslangic = datetime.fromisoformat(str(kayit["baslangic"]))
        anahtar = gun_anahtari(baslangic.date())
        ilce = str(kayit.get("ilce", "")).strip()
        bolge = str(kayit.get("bolge", "")).strip()
        ilce_id = id_uret(ilce, "ilce")
        bolge_id = id_uret(f"{ilce}|{bolge}", "bolge")

        yeni = {
            "ilce": ilce,
            "ilceId": ilce_id,
            "bolge": bolge,
            "bolgeId": bolge_id,
            "eczane": str(kayit.get("eczane", "")).strip(),
            "adres": kayit.get("adres", ""),
            "tel": kayit.get("tel", ""),
            "adres_tarifi": kayit.get("adres_tarifi", ""),
            "enlem": kayit.get("enlem", ""),
            "boylam": kayit.get("boylam", ""),
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

    # gün ve ilçe anahtarlarını sırala
    return {anahtar: agac[anahtar] for anahtar in sorted(agac)}


def yayinlari_cogalt(
    sablon_yayinlar: dict,
    gun: int,
    baslangic: date | None = None,
    aralik: tuple[str, str] | None = None,
) -> dict:
    """Şablondaki yayınları önümüzdeki `gun` güne çoğaltır.

    `aralik` verilirse (ör. ("08:30", "23:59")) her günün yayın penceresi o
    saat aralığına yayılır: kiosk o gün boyunca yayın moduna girebilir ve alt
    kuşaktaki kayan yazı görünür. Verilmezse şablondaki saatler korunur.
    """
    baslangic = baslangic or date.today()
    yeni: dict[str, dict] = {}
    sira = 1
    for ofset in range(gun):
        gun_tarihi = baslangic + timedelta(days=ofset)
        for sablon in sablon_yayinlar.values():
            if not isinstance(sablon, dict):
                continue
            baslangic_an = datetime.fromisoformat(str(sablon["start"]))
            bitis_an = datetime.fromisoformat(str(sablon["end"]))
            if aralik is not None:
                bas_saat = datetime.strptime(aralik[0], "%H:%M").time()
                bit_saat = datetime.strptime(aralik[1], "%H:%M").time()
                pencere_bas = datetime.combine(gun_tarihi, bas_saat)
                pencere_bit = datetime.combine(gun_tarihi, bit_saat)
            else:
                sure = bitis_an - baslangic_an
                pencere_bas = datetime.combine(gun_tarihi, baslangic_an.time())
                pencere_bit = pencere_bas + sure
            kayit = dict(sablon)
            # Şablondaki ISO biçimi (milisaniye kesri) korunur
            kayit["start"] = pencere_bas.isoformat(timespec="milliseconds")
            kayit["end"] = pencere_bit.isoformat(timespec="milliseconds")
            yeni[str(sira)] = kayit
            sira += 1
    return yeni


def match_uret(agac: dict, client_id: str, cihaz_ilce: str | None, cihaz_bolge: str | None) -> dict:
    """match.json: ilçe id -> [ { bölge id -> [makine id'leri] } ].

    Cihazın kendi kimliği seçilen bölgeye yerleştirilir (varsayılan: ilk ilçenin
    ilk bölgesi, şablondaki örnekte olduğu gibi).
    """
    ilceler: dict[str, dict[str, dict]] = {}
    for gun in sorted(agac):
        for ilce_id, ilce_listesi in agac[gun].items():
            for bolge_kutusu in ilce_listesi:
                for bolge_id, kayitlar in bolge_kutusu.items():
                    adlar = ilceler.setdefault(ilce_id, {})
                    if bolge_id not in adlar:
                        adlar[bolge_id] = {
                            "ilce": kayitlar[0]["ilce"],
                            "bolge": kayitlar[0]["bolge"],
                            "makineler": [],
                        }

    # hedef bölgeyi bul
    hedef_ilce, hedef_bolge = None, None
    for ilce_id, bolgeler in ilceler.items():
        for bolge_id, bilgi in bolgeler.items():
            if cihaz_bolge and bilgi["bolge"] == cihaz_bolge:
                hedef_ilce, hedef_bolge = ilce_id, bolge_id
            elif cihaz_ilce and bilgi["ilce"] == cihaz_ilce and hedef_bolge is None:
                hedef_ilce, hedef_bolge = ilce_id, bolge_id
    if hedef_bolge is None:
        ilk_ilce = next(iter(ilceler))
        hedef_ilce = ilk_ilce
        hedef_bolge = next(iter(ilceler[ilk_ilce]))

    match: dict = {}
    for ilce_id, bolgeler in ilceler.items():
        liste = []
        for bolge_id, bilgi in bolgeler.items():
            makineler = [id_uret(f"{bolge_id}|{i}", "makine") for i in range(9)]
            if ilce_id == hedef_ilce and bolge_id == hedef_bolge:
                makineler = [client_id] + makineler  # cihazın kendi kimliği ilk sırada
            liste.append({bolge_id: makineler})
        match[ilce_id] = liste
    match["lastUpdate"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return match


# ------------------------------------------------------------------- veri çekme
def verideki_degisim_saati(sistem_verisi: object = None) -> tuple[int, int] | None:
    """Nöbet değişim saatini **mevcut veriden** türetir (sabit saat kuralı yerine).

    Verideki kayıtların `start` saatlerinin en sık görüleni = günün devir saati.
    Nöbet çalışma saatleri değişirse (ör. 09:00) veri bunu yansıtır ve araç kendini
    uyarlar. Veri yoksa/okunamıyorsa `None` döner (çağıran varsayılana düşer).
    """
    if sistem_verisi is None:
        yol = KOK / config.SISTEM_VERISI_DOSYASI
        if not yol.is_file():
            return None
        try:
            sistem_verisi = json.loads(yol.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return None

    from collections import Counter
    from core import sync as _sync

    sayac: Counter = Counter()
    for kayit in _sync.tum_kayitlar(sistem_verisi):
        an = _sync._tarih(kayit.get("start") or kayit.get("baslangic"))
        if an is not None:
            sayac[(an.hour, an.minute)] += 1
    if not sayac:
        return None
    return sayac.most_common(1)[0][0]


def gecerli_baslangic(an: datetime | None = None, sistem_verisi: object = None) -> date:
    """Çekimin başlangıç tarihi: **devam eden nöbeti de kapsayacak** şekilde.

    Devir saati **veriden** türetilir (yoksa `config.NOBET_DEGISIM_SAATI` yalnızca ilk
    kurulum için varsayılandır). Saat devirden ÖNCE ise: dün başlayan nöbet hâlâ
    sürüyordur → başlangıç **dün**. Devirden sonra ise → başlangıç **bugün**.
    Böylece veride devam eden pencere her zaman bulunur; sabit bir saat kuralı yoktur.
    """
    an = an or datetime.now()
    saat, dakika = verideki_degisim_saati(sistem_verisi) or tuple(config.NOBET_DEGISIM_SAATI)
    degisim = an.replace(hour=saat, minute=dakika, second=0, microsecond=0)
    return an.date() - timedelta(days=1) if an < degisim else an.date()


def ham_veriyi_cek(baslangic: date, gun: int, yerel: Path | None = None) -> dict:
    """Site adresinden (veya yerel dosyadan) ham nöbet verisini çeker."""
    if yerel is not None:
        return json.loads(Path(yerel).read_text(encoding="utf-8-sig"))
    from security.network import AgAyarlari, indir

    bas, bit = tarih_url(baslangic, gun)
    url = NOBET_URL.format(baslangic=bas, bitis=bit)
    ayarlar = AgAyarlari(
        zaman_asimi_s=30.0,
        en_buyuk_bayt=16 * 1024 * 1024,
        izinli_hostlar=("www.kocaelieo.org.tr",),
        izinli_portlar=(443,),
        yonlendirme_izinli=False,
    )
    # JSON gövdesi: içerik türü beyaz listesi uygulanmaz (application/json gelebilir),
    # boyut/şema denetimi aşağıdaki json_yukle + şablon dönüşümünde yapılır.
    govde, _tur = indir(url, ayarlar, icerik_turu_denetle=False)
    log.info("veri çekildi: %s (%d bayt)", url, len(govde))
    from security.veri_dogrulama import json_yukle

    return json_yukle(govde, etiket=url, en_buyuk_bayt=ayarlar.en_buyuk_bayt, en_buyuk_dugum=500_000)


EN_AZ_PYTHON = (3, 9)


def surum_yeterli() -> bool:
    return sys.version_info >= EN_AZ_PYTHON


def makine_bilgisi(cihaz_id: str | None = None, kok: Path | None = None) -> dict:
    """`makinebilgileri.json`u okur; yoksa `--cihaz-id` ile oluşturur; yoksa ANLAŞILIR hata verir.

    Bu dosya **cihaza özgüdür** (clientID) ve depoya girmez → temiz klonda yoktur. Ham
    `FileNotFoundError` traceback'i yerine ne yapılacağını yazıyoruz.
    """
    kok = kok or KOK
    yol = kok / "makinebilgileri.json"
    if yol.is_file():
        try:
            veri = json.loads(yol.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as hata:
            print(f"HATA: {yol} okunamadı ({hata}).", file=sys.stderr)
            print("      Dosyayı düzeltin ya da silip --cihaz-id ile yeniden oluşturun.", file=sys.stderr)
            raise SystemExit(3)
        if not str((veri or {}).get("clientID", "")).strip():
            print(f"HATA: {yol} içinde 'clientID' yok.", file=sys.stderr)
            raise SystemExit(3)
        return veri

    if cihaz_id:
        veri = {"clientID": str(cihaz_id).strip()}
        yol.write_text(json.dumps(veri, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"oluşturuldu      : {yol} (clientID={veri['clientID']})")
        return veri

    print("HATA: makinebilgileri.json yok — bu dosya CİHAZ KİMLİĞİNİ taşır (depoya girmez).", file=sys.stderr)
    print("", file=sys.stderr)
    print("  Nereden bulunur?", file=sys.stderr)
    print("    · panel → Cihazlar (clientID) gösterir", file=sys.stderr)
    print("    · S3'teki makinebilgileri.json (cihazın kendi dosyası)", file=sys.stderr)
    print("    · eski kurulum: kiosk/makinebilgileri.json", file=sys.stderr)
    print("", file=sys.stderr)
    print("  Ya da bu komutla oluşturun (kimliği biliyorsanız):", file=sys.stderr)
    print("    python3 tools/fetch_nobet.py --cihaz-id <clientID>", file=sys.stderr)
    print("", file=sys.stderr)
    print("  Not: i5/i3 gibi AJAN makinelerinde nöbet verisi üretmeye gerek yoktur;", file=sys.stderr)
    print("       orada otomasyon/ betikleri kullanılır (topla.py, yaz.py).", file=sys.stderr)
    raise SystemExit(3)


def bolge_degisikligi(makine: dict, cihaz_bolge: str, cihaz_ilce: str | None, cikti: Path) -> tuple[str, str] | None:
    """Mevcut `match.json`daki cihaz bölgesi ile yeni seçilen bölge farklıysa (eski, yeni) döner.

    Kazayı önler: `--cihaz-bolge` verilmeden çalıştırılan bir komut (varsayılan "İzmit-2")
    cihazı sessizce başka bölgeye taşıyor ve yanlış eczaneler gösteriliyordu.
    """
    eski_yol = Path(cikti) / "match.json"
    ad_yolu = Path(cikti) / "data" / "id_eslesme.json"
    if not eski_yol.is_file():
        return None
    client = str(makine.get("clientID", "")).strip()
    if not client:
        return None
    try:
        eski = json.loads(eski_yol.read_text(encoding="utf-8-sig"))
        eslesme = json.loads(ad_yolu.read_text(encoding="utf-8-sig")) if ad_yolu.is_file() else {}
    except (OSError, ValueError):
        return None

    eski_id = ""
    for _ilce_id, ilce_listesi in (eski or {}).items():
        if not isinstance(ilce_listesi, list):
            continue
        for bolge_kutusu in ilce_listesi:
            for bolge_id, makineler in bolge_kutusu.items():
                if client in (makineler or []):
                    eski_id = str(bolge_id)
    if not eski_id:
        return None

    eski_ad = ""
    for ad, kimlik in ((eslesme or {}).get("bolgeler") or {}).items():
        if str(kimlik) == eski_id:
            eski_ad = ad
    if not eski_ad:
        for ad, kimlik in ((eslesme or {}).get("ilceler") or {}).items():
            if str(kimlik) == eski_id:
                eski_ad = ad
    if not eski_ad:
        return None

    yeni_ad = (cihaz_bolge or cihaz_ilce or "").strip()
    if not yeni_ad:
        return None
    if " ".join(eski_ad.casefold().split()) == " ".join(yeni_ad.casefold().split()):
        return None
    return (f"{eski_ad} ({eski_id})", yeni_ad)


def on_denetim(ayarlar) -> int:
    """`--kontrol`: hiçbir şey yazmadan ortamı denetler (uzaktan destek için)."""
    sorun = 0
    print("=== fetch_nobet.py ortam denetimi ===")
    print(f"python           : {sys.version.split()[0]} " + ("✓" if surum_yeterli() else "✗ (3.9+ gerekli)"))
    sorun += 0 if surum_yeterli() else 1
    print(f"proje kökü       : {KOK}")
    sablon = KOK / "sablon.json"
    print(f"sablon.json      : {'✓' if sablon.is_file() else '✗ EKSİK'}")
    sorun += 0 if sablon.is_file() else 1
    makine = KOK / "makinebilgileri.json"
    if makine.is_file():
        try:
            kimlik = str(json.loads(makine.read_text(encoding="utf-8-sig")).get("clientID", "")).strip()
            print(f"cihaz kimliği    : {'✓ ' + kimlik if kimlik else '✗ clientID boş'}")
            sorun += 0 if kimlik else 1
        except (OSError, ValueError):
            print("cihaz kimliği    : ✗ makinebilgileri.json bozuk")
            sorun += 1
    else:
        print("cihaz kimliği    : ✗ makinebilgileri.json yok → --cihaz-id <clientID> ile oluşturun")
        sorun += 1
    cikti = Path(ayarlar.cikti_dizin)
    yazilabilir = os.access(cikti, os.W_OK)
    print(f"çıktı klasörü    : {cikti} {'✓' if yazilabilir else '✗ yazılamıyor'}")
    sorun += 0 if yazilabilir else 1
    print(f"ağ (hedef host)  : www.kocaelieo.org.tr (yalnız https/443)")
    print("sonuç            : " + ("HAZIR ✓" if sorun == 0 else f"{sorun} sorun → yukarıdaki çözümler"))
    return 0 if sorun == 0 else 2


def main() -> int:
    """Kullanıcıya düzgün mesaj veren sarmalayıcı: beklenen hatalar traceback basmaz."""
    if not surum_yeterli():
        print(
            f"HATA: Python {'.'.join(map(str, EN_AZ_PYTHON))}+ gerekli (bulunan {sys.version.split()[0]}).\n"
            "  Ubuntu 20.04 varsayılanı 3.8'dir → 'sudo apt install -y python3.10' + 'python3.10 tools/fetch_nobet.py …'",
            file=sys.stderr,
        )
        return 2
    try:
        return _calistir()
    except SystemExit:
        raise
    except FileNotFoundError as hata:
        print(f"HATA: dosya/klasör bulunamadı: {hata.filename or hata}", file=sys.stderr)
        print("  çözüm: yolu kontrol edin; eksik klasörler otomatik oluşturulur.", file=sys.stderr)
        print("         kimlik dosyası eksikse: --cihaz-id <clientID>", file=sys.stderr)
        return 3
    except PermissionError as hata:
        print(f"HATA: yazma izni yok: {hata.filename or hata}", file=sys.stderr)
        print("  çözüm: --cikti-dizin ile yazılabilir bir klasör verin", file=sys.stderr)
        return 3
    except (urllib.error.URLError, TimeoutError) as hata:
        print(f"HATA: ağ erişimi başarısız ({hata}).", file=sys.stderr)
        print("  kontrol: internet/DNS, kurumsal proxy, güvenlik duvarı (yalnız https/443).", file=sys.stderr)
        print("  ağ yoksa: --yerel <dosya.json> ile eldeki veriyi kullanabilirsiniz.", file=sys.stderr)
        return 4
    except ValueError as hata:
        print(f"HATA: veri biçimi beklenmedik ({hata}).", file=sys.stderr)
        print("  kaynak değişmiş olabilir; --yerel ile kaydedilmiş bir dosyayla deneyin.", file=sys.stderr)
        return 5
    except KeyboardInterrupt:
        return 130
    except Exception:  # noqa: BLE001 - son çare: traceback yerine anlaşılır mesaj + günlük
        log.error("beklenmeyen hata", exc_info=True)
        print("HATA: beklenmeyen bir sorun oluştu (ayrıntı yukarıda).", file=sys.stderr)
        return 1


def _calistir() -> int:
    ayristirici = argparse.ArgumentParser(description="Nöbet verisini çeker ve şablonu doldurur")
    ayristirici.add_argument("--baslangic", help="aralığın ilk günü (YYYY-AA-GG); varsayılan bugün")
    ayristirici.add_argument("--gun", type=int, default=16, help=f"gün sayısı (en fazla {EN_FAZLA_GUN})")
    ayristirici.add_argument("--cihaz-bolge", default="İzmit-2", help="cihazın yerleştirileceği bölge adı")
    ayristirici.add_argument(
        "--yayin-araligi",
        default="08:30-23:59",
        help="yayınların her gün aktif olacağı saat aralığı (ör. 08:30-23:59); 'sablon' derse şablondaki saatler korunur",
    )
    ayristirici.add_argument("--cihaz-ilce", default=None, help="bölge adı verilmezse ilçe adı")
    ayristirici.add_argument("--yerel", type=Path, help="ağa çıkmadan bu JSON dosyasını kullan")
    ayristirici.add_argument("--cikti-dizin", type=Path, default=KOK)
    ayristirici.add_argument("--log-seviyesi", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    ayristirici.add_argument(
        "--cihaz-id", default=os.environ.get("KIOSK_CIHAZ_ID", ""),
        help="cihaz kimliği (clientID); makinebilgileri.json yoksa bu değerle oluşturulur",
    )
    ayristirici.add_argument("--kontrol", action="store_true", help="yalnız ortam/kimlik denetimi yap, çık")
    ayristirici.add_argument(
        "--zorla", action="store_true",
        help="cihazın bölgesi değişiyorsa yine de yaz (varsayılan: dur ve uyar)",
    )
    ayarlar = ayristirici.parse_args()

    logging.basicConfig(level=getattr(logging, ayarlar.log_seviyesi), format="%(levelname)-7s %(message)s")

    if ayarlar.kontrol:
        return on_denetim(ayarlar)

    if ayarlar.baslangic:
        baslangic = date.fromisoformat(ayarlar.baslangic)
    else:
        baslangic = gecerli_baslangic()
        degisim = verideki_degisim_saati()
        log.info(
            "başlangıç tarihi otomatik: %s (devir saati %s; devam eden nöbet kapsanıyor)",
            baslangic,
            f"{degisim[0]:02d}:{degisim[1]:02d} (veriden)" if degisim else "varsayılan",
        )
    bas_metin, bit_metin = tarih_url(baslangic, ayarlar.gun)

    ham = ham_veriyi_cek(baslangic, ayarlar.gun, ayarlar.yerel)
    agac = sablona_cevir(ham)

    sablon = json.loads((KOK / "sablon.json").read_text(encoding="utf-8"))
    yayin_araligi = None
    if ayarlar.yayin_araligi and ayarlar.yayin_araligi.lower() != "sablon":
        parcalar = ayarlar.yayin_araligi.split("-")
        if len(parcalar) != 2:
            raise SystemExit("--yayin-araligi biçimi: 'HH:MM-HH:MM' veya 'sablon'")
        yayin_araligi = (parcalar[0].strip(), parcalar[1].strip())
    yayinlar = yayinlari_cogalt(sablon.get("Yayinlar", {}), 30, baslangic, aralik=yayin_araligi)

    makine = makine_bilgisi(ayarlar.cihaz_id)
    fark = bolge_degisikligi(makine, ayarlar.cihaz_bolge, ayarlar.cihaz_ilce, ayarlar.cikti_dizin)
    if fark and not ayarlar.zorla:
        print("DURDURULDU: bu komut cihazın GÖRÜNEN BÖLGESİNİ değiştiriyor.", file=sys.stderr)
        print(f"  mevcut : {fark[0]}", file=sys.stderr)
        print(f"  yeni   : {fark[1]}", file=sys.stderr)
        print("  Yanlış bölge, cihazda yanlış eczanelerin görünmesi demektir.", file=sys.stderr)
        print("  Bilerek yapıyorsanız: --zorla", file=sys.stderr)
        print('  Doğrusu: --cihaz-bolge "<cihazın gerçek bölgesi>"', file=sys.stderr)
        return 6
    client_id = str(makine.get("clientID", "")).strip()
    match = match_uret(agac, client_id, ayarlar.cihaz_ilce, ayarlar.cihaz_bolge)

    simdi = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    last_system = {"Nobetler": agac, "Yayinlar": yayinlar, "lastUpdate": simdi}

    cikti = Path(ayarlar.cikti_dizin)
    # çıktı klasörü (ve data/) yoksa oluştur: --cikti-dizin ile yeni klasör verilebilsin
    (cikti / "data").mkdir(parents=True, exist_ok=True)
    (cikti / "lastSystemData.json").write_text(
        json.dumps(last_system, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (cikti / "match.json").write_text(json.dumps(match, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (cikti / "lastupdate.json").write_text(
        json.dumps({"lastupdate": simdi}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # id eşlemesi (insan tarafından okunabilir referans)
    eslesme = {"ilceler": {}, "bolgeler": {}}
    for gun in agac:
        for ilce_id, ilce_listesi in agac[gun].items():
            for bolge_kutusu in ilce_listesi:
                for bolge_id, kayitlar in bolge_kutusu.items():
                    eslesme["ilceler"][kayitlar[0]["ilce"]] = ilce_id
                    eslesme["bolgeler"][kayitlar[0]["bolge"]] = bolge_id
    (cikti / "data" / "id_eslesme.json").write_text(
        json.dumps(eslesme, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    hedef = None
    for ilce_id, ilce_listesi in match.items():
        if not isinstance(ilce_listesi, list):
            continue
        for bolge_kutusu in ilce_listesi:
            for bolge_id, makineler in bolge_kutusu.items():
                if client_id in makineler:
                    hedef = f"{bolge_id}"
    print(f"veri kaynağı      : {ayarlar.yerel or NOBET_URL.format(baslangic=bas_metin, bitis=bit_metin)}")
    print(f"aralık            : {bas_metin} .. {bit_metin} ({ayarlar.gun} gün)")
    kayit_sayisi = sum(
        len(records) for gun in agac.values() for ilce in gun.values() for bolge in ilce for records in bolge.values()
    )
    print(f"gün / kayıt / ilçe: {len(agac)} / {kayit_sayisi} / {len({i for gun in agac.values() for i in gun})}")
    print(f"yayın kaydı       : {len(yayinlar)} (30 güne çoğaltıldı, pencere: {ayarlar.yayin_araligi})")
    print(f"cihaz clientID    : {client_id}")
    print(f"cihaz bölgesi     : {hedef} (match.json'da aranacak)")
    print("yazıldı           : lastSystemData.json, match.json, lastupdate.json, data/id_eslesme.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
