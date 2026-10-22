"""Ayar şemasını yönetim paneline aktarır (tek kaynak: `ayarlar.py`).

Neden: panel ile kiosk aynı anahtarları, aynı aralıkları ve aynı varsayılanları
kullanmalı. Şema Python tarafında tanımlı (`KURALLAR`, `ACIKLAMALAR`) ve bu araç
onu `panel/src/domain/sema.generated.json` dosyasına yazar; panel bu dosyayı okur.
Şema değişirse test kırılır ve "bu aracı çalıştır" der — böylece iki taraf ayrışamaz.

Kullanım:
    python3 tools/sema_disa_aktar.py            # yazar
    python3 tools/sema_disa_aktar.py --kontrol  # yalnızca denetler (testler kullanır)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

import ayarlar  # noqa: E402
import config  # noqa: E402

HEDEF = KOK.parent / "panel" / "src" / "domain" / "sema.generated.json"

GRUP_BASLIKLARI = {
    "ozellikler": "Özellikler (aç/kapa)",
    "kusak": "Kayan yazı kuşağı",
    "gorunum": "Görünüm",
    "veri": "Veri kaynağı",
    "ag": "Ağ (güvenlik)",
    "gelismis": "Gelişmiş (veri hacmi)",
    "onbellek": "Önbellek (maliyet + performans)",
    "calistirma": "Çalıştırma modu (Qt / tarayıcı)",
}

ETIKETLER = {
    "ozellikler.nobet_listesi": "Nöbet listesi",
    "ozellikler.yayinlar": "Yayınlar (görsel modu)",
    "ozellikler.kayan_yazi": "Kayan yazı kuşağı",
    "ozellikler.saat_tarih": "Saat / tarih yazısı",
    "kusak.yukseklik": "Kuşak yüksekliği",
    "kusak.alt_bosluk": "Alt boşluk",
    "kusak.yazi_punto": "Yazı puntosu",
    "kusak.giris_ms": "Giriş süresi",
    "kusak.durma_ms": "Ortada durma süresi",
    "kusak.cikis_ms": "Çıkış süresi",
    "kusak.hiz": "Kayma hızı",
    "kusak.adim_araligi_ms": "Adım aralığı",
    "kusak.tekli": "Tek tek göster",
    "gorunum.sol_panel_satir": "Sol panel taban satır sayısı",
    "veri.kaynak": "Veri kaynağı türü",
    "veri.dosya_adresi": "Dosya adresi",
    "ag.izinli_hostlar": "İzinli ana makineler",
    "ag.izinli_portlar": "İzinli portlar",
    "gelismis.max_json_bayt": "JSON üst boyutu",
    "gelismis.max_json_derinlik": "JSON derinlik sınırı",
    "gelismis.max_json_dugum": "JSON düğüm sınırı",
    "gelismis.max_gorsel_bayt": "Görsel üst boyutu",
    "gelismis.max_gorsel_piksel": "Görsel piksel sınırı",
    "gelismis.max_metin_uzunluk": "Metin uzunluk sınırı",
    "gelismis.max_gosterilen_kayit": "Gösterilen kayıt sınırı",
    "gelismis.max_aktif_yayin": "Aktif yayın sınırı",
    "gelismis.yayin_sure_en_az_s": "En az yayın süresi",
    "gelismis.yayin_sure_en_cok_s": "En çok yayın süresi",
}

BIRIMLER = {
    "kusak.yukseklik": "px",
    "kusak.alt_bosluk": "px",
    "kusak.giris_ms": "ms",
    "kusak.durma_ms": "ms",
    "kusak.cikis_ms": "ms",
    "kusak.adim_araligi_ms": "ms",
    "gelismis.max_json_bayt": "bayt",
    "gelismis.max_gorsel_bayt": "bayt",
    "gelismis.max_gorsel_piksel": "piksel",
    "gelismis.max_metin_uzunluk": "karakter",
    "gelismis.max_json_derinlik": "seviye",
    "gelismis.max_json_dugum": "düğüm",
    "gelismis.yayin_sure_en_az_s": "saniye",
    "gelismis.yayin_sure_en_cok_s": "saniye",
}

#: Gelişmiş/teknik anahtarlar panelde varsayılan olarak katlanmış gösterilir
GELISMIS_ANAHTARLAR = {"derinlik", "dugum", "piksel", "liste", "sayi_listesi"}


def _tip_adi(tip) -> str:
    if tip is bool:
        return "bool"
    if tip is int:
        return "int"
    if tip is float:
        return "float"
    if tip is str:
        return "str"
    if tip == "secim":
        return "secim"
    if tip == "liste":
        return "liste"
    if tip == "sayi_listesi":
        return "sayi_listesi"
    return str(tip)


def sema() -> dict:
    """`KURALLAR` + `ACIKLAMALAR` + config varsayılanları → panel şeması."""
    gruplar: dict[str, dict] = {}
    for (grup, anahtar), kural in ayarlar.KURALLAR.items():
        cfg_ad, tip, alt, ust = kural
        tam = f"{grup}.{anahtar}"
        izinli = list(alt) if tip == "secim" and isinstance(alt, (tuple, list)) else None
        girdi = {
            "ad": anahtar,
            "tam": tam,
            "tip": _tip_adi(tip),
            "etiket": ETIKETLER.get(tam, anahtar.replace("_", " ").capitalize()),
            "aciklama": ayarlar.ACIKLAMALAR.get(tam, ""),
            "birim": BIRIMLER.get(tam, ""),
            "alt": None if izinli else (alt if isinstance(alt, (int, float)) and not isinstance(alt, bool) else None),
            "ust": ust if isinstance(ust, (int, float)) and not isinstance(ust, bool) else None,
            "izinli": izinli,
            "varsayilan": getattr(config, cfg_ad, None),
            "gelismis": anahtar.split("_")[-1] in GELISMIS_ANAHTARLAR
            or tam
            in {
                "gelismis.max_json_bayt",
                "gelismis.max_json_derinlik",
                "gelismis.max_json_dugum",
                "gelismis.max_gorsel_bayt",
                "gelismis.max_gorsel_piksel",
                "ag.izinli_portlar",
            },
        }
        g = gruplar.setdefault(
            grup,
            {
                "ad": grup,
                "baslik": GRUP_BASLIKLARI.get(grup, grup.capitalize()),
                "kapsam": grup in ayarlar.KAPSAM_GRUPLARI,
                "anahtarlar": [],
            },
        )
        g["anahtarlar"].append(girdi)

    return {
        "_aciklama": (
            "OTOMATİK ÜRETİLDİ — elle düzenlemeyin. Kaynak: kiosk/ayarlar.py (KURALLAR, ACIKLAMALAR). "
            "Yenilemek için: python3 tools/sema_disa_aktar.py"
        ),
        "surum": 1,
        "kapsam_gruplari": list(ayarlar.KAPSAM_GRUPLARI),
        "gruplar": [gruplar[g] for g in GRUP_BASLIKLARI if g in gruplar],
    }


def metin() -> str:
    return json.dumps(sema(), ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    ayristirici = argparse.ArgumentParser(description="Ayar şemasını panele aktar")
    ayristirici.add_argument("--kontrol", action="store_true", help="yalnızca güncel mi diye bak")
    ayarlar_arg = ayristirici.parse_args()

    yeni = metin()
    if ayarlar_arg.kontrol:
        eski = HEDEF.read_text(encoding="utf-8") if HEDEF.is_file() else ""
        if eski != yeni:
            print(f"ŞEMA GÜNCEL DEĞİL: {HEDEF}\n  yenilemek için: python3 tools/sema_disa_aktar.py")
            return 1
        print(f"şema güncel: {HEDEF}")
        return 0

    HEDEF.parent.mkdir(parents=True, exist_ok=True)
    HEDEF.write_text(yeni, encoding="utf-8")
    anahtar_sayisi = sum(len(g["anahtarlar"]) for g in sema()["gruplar"])
    print(f"şema yazıldı: {HEDEF}  ({len(sema()['gruplar'])} grup / {anahtar_sayisi} anahtar)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
