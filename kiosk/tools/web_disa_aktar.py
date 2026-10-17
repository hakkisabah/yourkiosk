#!/usr/bin/env python3
"""Tarayıcı arayüzü için YERLEŞİM/AYAR VERİSİ dışa aktarır.

Neden: HTML/CSS portunun Qt ile **birebir aynı** kalması için görsel sabitlerin tek
kaynağı `config.py` olmalı. Bu araç, ilgili sabitleri ve ayar varsayılanlarını
`web/src/veri/yerlesim.json` dosyasına yazar; arayüz bu dosyayı okur (elle kopyalanan
değer yoktur, sapma olmaz).

    python3 tools/web_disa_aktar.py            # yaz
    python3 tools/web_disa_aktar.py --denetle  # yalnızca güncel mi diye bak (yazmaz)

`tests/test_web_yerlesim.py` dosyanın güncel olup olmadığını kilitler: config.py
değişip dışa aktarma yenilenmezse test kırmızı olur (bkz. sema_disa_aktar.py deseni).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

import ayarlar  # noqa: E402
import config  # noqa: E402

#: `web/` klasörü proje kökünde (config.WEB_KLASORU)
HEDEF = KOK.parent / str(getattr(config, "WEB_KLASORU", "web")) / "src" / "veri" / "yerlesim.json"

#: Web arayüzünün kullandığı ayar grupları (Qt'de kapsamla yönetilebilenler + veri sınırları)
GRUPLAR = ("ozellikler", "kusak", "gorunum", "gelismis", "onbellek", "veri")

#: Dışa aktarılacak config sabitlerinin ad önekleri (görsel/veri sabitleri)
ONEKLER = (
    "KUSAK_",
    "SOL_PANEL_",
    "KAPSAM",
    "EKSIK_TELEFON_",
    "MAKS_GORUNUR_SATIR",
    "OZELLIK_",
    "NOBET_DEGISIM",
    "EKSIK_TELEFON",
    "YAYIN_SURE",
    "MAX_",
    "ONBELLEK_",
    "REFRESH_INTERVAL_MS",
    "CYCLE_INTERVAL_MS",
    "WEB_",
    "TETIK_",
    "DAMGA_",
    "DEGISIKLIK_",
)

GRUP_ETIKETLERI = {
    "ozellikler": "Özellikler",
    "kusak": "Kayan yazı kuşağı",
    "gorunum": "Görünüm",
    "gelismis": "Gelişmiş (veri hacmi)",
    "onbellek": "Önbellek (maliyet + performans)",
    "veri": "Veri kaynağı",
}

#: Qt kodunda SATIR İÇİ yazılmış yerleşim değerleri (config sabiti değil; ui/ + components/).
#: Her değer (değer, dosya, o dosyada bulunması gereken ifade) üçlüsüdür: `tests/test_web_yerlesim.py`
#: ifadenin hâlâ dosyada olduğunu denetler → Qt tarafı değişirse test kırmızı olur, sessiz sapma olmaz.
ELLE_YERLESIM: dict[str, tuple[object, str, str]] = {
    "sol.genislik_orani": (0.26, "ui/nobet_widget.py", "screen_w * 0.26"),
    "sol.dikey_cizgi": (3, "ui/nobet_widget.py", "int(3 * app_instance.scale)"),
    "sol.satir_bosluk": (10, "ui/nobet_widget.py", "int(10 * app_instance.scale)"),
    "sol.ic_bosluk": (10, "pharmacy_app.py", "int(10 * self.scale)"),
    "sol.kutu_normal": ("bg_layout/box.png", "pharmacy_app.py", "box.png"),
    "sol.kutu_aktif": ("bg_layout/activeBox.png", "pharmacy_app.py", "activeBox.png"),
    "sol.punto_ad": (30, "pharmacy_app.py", "int(30 * self.scale)"),
    "sol.punto_ikincil": (35, "pharmacy_app.py", "int(35 * self.scale)"),
    "orta.serit_yukseklik": (125, "ui/nobet_widget.py", "int(125 * app_instance.scale)"),
    "orta.serit_gorseli": ("bg_layout/kusak.png", "ui/nobet_widget.py", "kusak.png"),
    "orta.tarih_aralik_yukseklik": (45, "components/right_content_block.py", "int(45 * app_instance.scale)"),
    "orta.detay_yukseklik": (480, "components/right_content_block.py", "int(480 * app_instance.scale)"),
    "orta.yatay_cizgi": (3, "components/right_content_block.py", "int(3 * app_instance.scale)"),
    "orta.alt_serit_yukseklik": (640, "components/right_content_block.py", "int(640 * app_instance.scale)"),
    "orta.logo_genislik_orani": (1.15 * 0.54, "components/right_content_block.py", "screen_w * 1.15 * 0.54"),
    "orta.punto_tarih_aralik": (20, "components/right_content_block.py", "int(20 * app_instance.scale)"),
    "orta.punto_ad": (65, "components/right_content_block.py", "int(65 * app_instance.scale)"),
    "orta.punto_adres": (30, "components/right_content_block.py", "int(30 * app_instance.scale)"),
    "orta.punto_telefon": (90, "components/right_content_block.py", "int(90 * app_instance.scale)"),
    "orta.punto_saat": (50, "components/right_content_block.py", "int(50 * app_instance.scale)"),
    "animasyon.sure_ms": (1800, "core/animation_handler.py", "1800"),
    "animasyon.egri": ("InOutCubic", "core/animation_handler.py", "InOutCubic"),
    "font.aile": ("Arial", "components/right_content_block.py", "Arial"),
    "font.kalin": ("bold", "components/right_content_block.py", "QFont.Weight.Bold"),
}

#: Qt renk paleti (satır içi hex değerler; aynı dosya denetimi uygulanır)
ELLE_RENKLER: dict[str, tuple[str, str]] = {
    "kirmizi": ("#c8102e", "ui/yayin_widget.py"),
    "krem": ("#f5e8c7", "components/right_content_block.py"),
}


def _olculer() -> dict[str, int]:
    """Çalışma anında hesaplanan ölçüler (Qt formüllerinin aynısı, 1080p, scale=1)."""
    ekran_g, ekran_y, scale = 1920, 1080, 1
    taban = int(getattr(config, "MAKS_GORUNUR_SATIR", 5))
    bosluk = 10
    available_h = ekran_y - 0 - 0 - bosluk * (taban - 1)
    item_h = int(available_h / taban)
    sol_genislik = int(ekran_g * 0.26)
    sag_genislik = ekran_g - sol_genislik - int(3 * scale)
    serit_yukseklik = int(125 * scale)
    logo_genislik = int(ekran_g * 1.15 * 0.54)
    kusak_yukseklik = int(getattr(config, "KUSAK_YUKSEKLIK", 110) * scale)
    kusak_alt = int(getattr(config, "KUSAK_ALT_BOSLUK", 50) * scale)
    return {
        "satir_yuksekligi": item_h,
        "sol_panel_genislik": sol_genislik,
        "sag_panel_genislik": sag_genislik,
        "viewport_yukseklik": ekran_y - serit_yukseklik,
        #: Sol panel kaydırma alanının görünür yüksekliği (Qt: scroll viewport ≈ 1080)
        "sol_gorunur_yukseklik": taban * item_h + (taban - 1) * bosluk,
        "logo_genislik": logo_genislik,
        "saat_kutusu_genislik": sag_genislik - logo_genislik,
        "kusak_y": max(0, ekran_y - kusak_alt - kusak_yukseklik),
    }


def yerlesim() -> dict[str, Any]:
    """HTML/CSS portunun kullanacağı yerleşim tablosu (Qt ile birebir aynı)."""
    return {
        "ekran": {"genislik": 1920, "yukseklik": 1080, "scale_formulu": "screen_h/1080"},
        "olculer": _olculer(),
        "elle": {ad: deger for ad, (deger, _d, _s) in sorted(ELLE_YERLESIM.items())},
        "renkler": {ad: deger for ad, (deger, _d) in sorted(ELLE_RENKLER.items())},
    }


def sabitler() -> dict[str, Any]:
    """İlgili tüm config sabitlerini (yalnızca JSON'a yazılabilir olanlar) toplar."""
    cikti: dict[str, Any] = {}
    for ad in dir(config):
        if not ad.isupper() or ad.startswith("_"):
            continue
        if not any(ad.startswith(onek) for onek in ONEKLER):
            continue
        deger = getattr(config, ad)
        if isinstance(deger, (str, int, float, bool)) or deger is None:
            cikti[ad] = deger
        elif isinstance(deger, (list, tuple)) and all(isinstance(x, (str, int, float, bool)) for x in deger):
            cikti[ad] = list(deger)
    return dict(sorted(cikti.items()))


def varsayilanlar() -> dict[str, dict[str, Any]]:
    """Ayar gruplarının varsayılan değerleri (config'ten çözülür)."""
    belge = ayarlar.varsayilan_belge() if hasattr(ayarlar, "varsayilan_belge") else {}
    cikti: dict[str, dict[str, Any]] = {}
    for ad, deger in (belge or {}).items():
        if ad in GRUPLAR and isinstance(deger, dict):
            cikti[ad] = dict(sorted(deger.items()))
    if not cikti:  # geri dönüş: KURALLAR üzerinden oku
        for (grup, anahtar), (sabit, _tip, _alt, _ust) in ayarlar.KURALLAR.items():
            if grup not in GRUPLAR:
                continue
            cikti.setdefault(grup, {})[anahtar] = getattr(config, sabit, None)
        for grup in cikti:
            cikti[grup] = dict(sorted(cikti[grup].items()))
    return dict(sorted(cikti.items()))


def belge_uret() -> dict[str, Any]:
    govde = {
        "surum": 1,
        "aciklama": "config.py + ayarlar.py'den ÜRETİLDİ — elle düzenlemeyin (tools/web_disa_aktar.py)",
        "gruplar": {ad: GRUP_ETIKETLERI.get(ad, ad) for ad in GRUPLAR},
        "kapsam_gruplari": list(getattr(ayarlar, "KAPSAM_GRUPLARI", ())),
        "sabitler": sabitler(),
        "varsayilanlar": varsayilanlar(),
        "yerlesim": yerlesim(),
    }
    ozet = hashlib.sha256(json.dumps(govde, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
    govde["surum_ozeti"] = ozet
    return govde


def yaz(hedef: Path = HEDEF) -> Path:
    belge = belge_uret()
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(json.dumps(belge, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return hedef


def guncel_mi(hedef: Path = HEDEF) -> bool:
    if not hedef.is_file():
        return False
    try:
        mevcut = json.loads(hedef.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return mevcut == belge_uret()


def main(argv=None) -> int:
    ayar = argparse.ArgumentParser(description="Tarayıcı arayüzü yerleşim/ayar verisini dışa aktar")
    ayar.add_argument("--denetle", action="store_true", help="yalnızca güncel mi diye denetle (yazmaz)")
    secenek = ayar.parse_args(argv)
    if secenek.denetle:
        guncel = guncel_mi()
        print(f"yerlesim.json {'güncel ✓' if guncel else 'BAYAT ✗'}  ({HEDEF})")
        return 0 if guncel else 1
    hedef = yaz()
    belge = belge_uret()
    print(f"yerleşim verisi yazıldı: {hedef}")
    print(f"  {len(belge['sabitler'])} sabit · {len(belge['varsayilanlar'])} grup · özet {belge['surum_ozeti']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
