#!/usr/bin/env python3
"""Önbellek aracı: durum göster, bakım yap, temizle.

Kullanım:
    python tools/onbellek_durumu.py                 # durum (klasör, adet, boyut)
    python tools/onbellek_durumu.py --bakim         # süresi geçenleri/artıkları sil, kotayı uygula
    python tools/onbellek_durumu.py --temizle       # tüm önbelleği boşalt
    python tools/onbellek_durumu.py --liste         # kayıtları dök (url, son gösterim, bayt)

Çıktı insan okur biçimdedir; kiosk çalışırken de güvenle çalıştırılabilir (atomik yazma).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from core import onbellek  # noqa: E402


def _mb(bayt: float) -> str:
    return f"{bayt / 1024 / 1024:.2f} MB"


def durum() -> None:
    bilgi = onbellek.istatistik()
    print(f"önbellek      : {'AÇIK' if bilgi['aktif'] else 'kapalı'}")
    print(f"klasör        : {bilgi['klasor']}")
    print(f"veri kaydı    : {bilgi['veri_adet']} dosya, {_mb(bilgi['veri_bayt'])}")
    print(f"görsel kaydı  : {bilgi['gorsel_adet']} dosya, {_mb(bilgi['gorsel_bayt'])}")
    print(f"toplam        : {_mb(bilgi['veri_bayt'] + bilgi['gorsel_bayt'])} / üst sınır {_mb(bilgi['maks_bayt'])}")
    print(f"saklama süresi: son gösterimden sonra {bilgi['saklama_gun']} gün")
    damga = onbellek.kayitli_damga()
    print(f"lastupdate    : {damga or '(henüz kaydedilmedi)'}")


def liste() -> None:
    dizin = onbellek._dizin_oku()
    if not dizin["gorsel"]:
        print("önbellekte görsel yok.")
    for anahtar, kayit in sorted(dizin["gorsel"].items()):
        if not isinstance(kayit, dict):
            continue
        bayat = " (bayat)" if kayit.get("bayat") else ""
        print(
            f"{anahtar[:12]}…  {int(kayit.get('bayt', 0)):>9} bayt  "
            f"gösterim={int(kayit.get('gosterim', 0)):<4} son={kayit.get('son_gosterim', '-')}{bayat}\n"
            f"    {kayit.get('url', '')}"
        )
    if dizin["veri"]:
        print("\nveri kayıtları:")
        for ad, kayit in sorted(dizin["veri"].items()):
            kayit = kayit if isinstance(kayit, dict) else {}
            print(f"  {ad}: {int(kayit.get('bayt', 0))} bayt · lastupdate={kayit.get('lastupdate', '-')}")


def main() -> int:
    ayar = argparse.ArgumentParser(description="Cihaz önbelleği durumu/bakımı")
    ayar.add_argument("--bakim", action="store_true", help="süresi geçen/artık görselleri sil, kotayı uygula")
    ayar.add_argument("--temizle", action="store_true", help="tüm önbelleği boşalt")
    ayar.add_argument("--liste", action="store_true", help="kayıtları dök")
    secenek = ayar.parse_args()

    if secenek.temizle:
        sonuc = onbellek.onbellegi_bosalt()
        print(f"önbellek boşaltıldı: {sonuc['silinen_dosya']} dosya silindi")
    if secenek.bakim:
        ozet = onbellek.bakim()
        print(
            f"bakım: {ozet.get('silinen', 0)} görsel silindi ({_mb(ozet.get('silinen_bayt', 0))}), "
            f"{ozet.get('oksuz_dosya', 0)} öksüz dosya; kalan {_mb(ozet.get('kalan_bayt', 0))}"
        )
    if secenek.liste:
        liste()
    if not (secenek.temizle or secenek.bakim or secenek.liste):
        durum()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
