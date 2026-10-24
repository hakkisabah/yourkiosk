"""VERİ MODELİ — tek kaynak (kiosk + panel ayrışamasın).

`ayarlar.py` şeması ile aynı desen: alanlar burada tanımlı, panel ve web için JSON üretilir.
Üretilen dosya elle düzenlenmez; model değişince:

    cd kiosk && python3 tools/model_disa_aktar.py            # yazar
    cd kiosk && python3 tools/model_disa_aktar.py --kontrol  # yalnız denetler (testler kullanır)

NEDEN: yayın hedefleme alanları (ilceId/bolgeId/cihazId) hem Qt'de hem panelde hem tarayıcıda
AYNI adlarla, aynı tipte ve aynı kurallarla kullanılmalı. Bu dosya olmadan üç taraf sessizce
ayrışıyor (yaşandı: `durum.json` state'te yoktu → panel açılışta çöktü).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

SURUM = 1

#: Yayın kaydı alanları. `alias`: veri sağlayıcı farklı adlar kullanabiliyor (okurken kabul edilir).
YAYIN_ALANLARI: list[dict] = [
    {
        "ad": "start",
        "tip": "tarih",
        "zorunlu": True,
        "etiket": "Başlangıç",
        "aciklama": "Yayının gösterilmeye başladığı an (ISO 8601).",
        "alias": ["baslangic"],
    },
    {
        "ad": "end",
        "tip": "tarih",
        "zorunlu": True,
        "etiket": "Bitiş (son gösterim)",
        "aciklama": "Son gösterim anı. Bu andan sonra yayın cihazda ve sunucuda temizlenir.",
        "alias": ["bitis", "gosterimBitis"],
    },
    {
        "ad": "contentUrl",
        "tip": "https_adres",
        "zorunlu": True,
        "etiket": "Görsel adresi",
        "aciklama": "https adres. Kendi kovamızdaysa içerik adlı (sha256) yol önerilir.",
        "alias": ["contentURL", "url", "gorsel"],
    },
    {
        "ad": "duration",
        "tip": "saniye",
        "zorunlu": False,
        "etiket": "Gösterim süresi",
        "aciklama": "Saniye; kiosk ayarındaki en az/en çok aralığa kıstırılır.",
        "alias": ["sure"],
    },
    {
        "ad": "ilceId",
        "tip": "metin",
        "zorunlu": False,
        "etiket": "İlçe",
        "aciklama": "Boş = kısıt yok. Yalnız bu ilçedeki cihazlar gösterir.",
        "alias": ["ilce_id", "ilce"],
    },
    {
        "ad": "bolgeId",
        "tip": "metin",
        "zorunlu": False,
        "etiket": "Bölge",
        "aciklama": "Boş = kısıt yok. İlçe ile birlikte daraltır.",
        "alias": ["bolge_id", "bolge"],
    },
    {
        "ad": "cihazId",
        "tip": "metin",
        "zorunlu": False,
        "etiket": "Cihaz",
        "aciklama": "Boş = kısıt yok. Tek cihaza özel yayın (en dar kapsam).",
        "alias": ["cihaz_id", "clientID", "clientId"],
    },
]

#: `durum.json` (panel yazar, cihaz tek istekte okur).
DURUM_ALANLARI: list[dict] = [
    {"ad": "zaman", "tip": "tarih", "zorunlu": True, "etiket": "Üretim anı", "aciklama": "Belgenin yazıldığı an (ISO, UTC)."},
    {"ad": "lastupdate", "tip": "metin", "zorunlu": True, "etiket": "Veri damgası", "aciklama": "`lastupdate.json` ile AYNI değer olmalı."},
    {"ad": "tetik", "tip": "nesne", "zorunlu": False, "etiket": "Tetikleyici", "aciklama": "{zaman, ilceId, bolgeId, aciklama}."},
    {"ad": "komut", "tip": "nesne", "zorunlu": False, "etiket": "Komut işareti", "aciklama": "{zaman, id} — gövde ayrı dosyada."},
]

#: Kapsam kuralları (panel arayüzü ve doğrulama aynı metni kullanır).
KAPSAM_KURALLARI: dict = {
    "bos_kisit_yok": True,
    "coklu_alan": "VE",
    "en_dar": ["cihazId", "bolgeId", "ilceId"],
    "bilinmeyen_cihaz": "hedefli yayın gösterilmez (fail-closed)",
}


def belge() -> dict:
    return {
        "_aciklama": "ÜRETİLMİŞ DOSYA — elle düzenlemeyin. Kaynak: kiosk/core/model.py "
                     "(üret: cd kiosk && python3 tools/model_disa_aktar.py)",
        "surum": SURUM,
        "yayin_alanlari": YAYIN_ALANLARI,
        "durum_alanlari": DURUM_ALANLARI,
        "kapsam_kurallari": KAPSAM_KURALLARI,
    }


def metin() -> str:
    return json.dumps(belge(), ensure_ascii=False, indent=2) + "\n"


HEDEFLER = (
    Path(__file__).resolve().parents[2] / "panel" / "src" / "domain" / "model.generated.json",
    Path(__file__).resolve().parents[2] / "web" / "src" / "veri" / "model.generated.json",
)


def main() -> int:
    a = argparse.ArgumentParser(description="veri modelini panel/web'e aktar")
    a.add_argument("--kontrol", action="store_true", help="yalnız denetle (yazmaz)")
    secim = a.parse_args()
    icerik = metin()
    eksik = []
    for hedef in HEDEFLER:
        if secim.kontrol:
            if not hedef.is_file() or hedef.read_text(encoding="utf-8") != icerik:
                eksik.append(hedef)
        else:
            hedef.parent.mkdir(parents=True, exist_ok=True)
            hedef.write_text(icerik, encoding="utf-8")
    if secim.kontrol:
        if eksik:
            print("✗ model güncel değil — çalıştır: cd kiosk && python3 tools/model_disa_aktar.py")
            for yol in eksik:
                print(f"   {yol}")
            return 1
        print(f"✓ model güncel ({len(HEDEFLER)} hedef)")
        return 0
    print(f"✓ model yazıldı ({len(HEDEFLER)} hedef, {len(YAYIN_ALANLARI)} yayın alanı)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
