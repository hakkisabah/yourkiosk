#!/usr/bin/env python3
"""NÖBET DEĞİŞİKLİĞİ TETİKLEYİCİSİ — panelin cihaza yaptığı işi elle yapar (test/bakım).

Panel bir nöbet değişikliği yaptığında S3'e `tetikle.json` yazar; cihaz bu dosyayı görünce
**beklemeden** verisini yeniler (tarayıcı modunda uzun yoklama ile ~1 sn, Qt modunda en çok
`DAMGA_KONTROL_MS` = 120 sn — push kopuksa 30 sn — içinde). Bu araç aynı dosyayı cihazda üretir:

    python3 tools/nobet_tetikle.py --ilce 30607352906750376   # yalnız o ilçenin cihazları
    python3 tools/nobet_tetikle.py                            # tüm cihazlar
    python3 tools/nobet_tetikle.py --bolge 73154087615041151  # tek bölge (daha dar)
    python3 tools/nobet_tetikle.py --durum                    # mevcut tetikleyiciyi göster
    python3 tools/nobet_tetikle.py --sil                      # tetikleyiciyi kaldır

Kural tek yerde: `core/tetik.py` (Qt uygulaması, web sunucusu ve bu araç aynı kuralı kullanır).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import tetik  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Nöbet değişikliği tetikleyicisi yaz/sil/göster")
    ap.add_argument("--ilce", default="", help="ilçe kimliği (boş: tüm cihazlar)")
    ap.add_argument("--bolge", default="", help="bölge kimliği (isteğe bağlı, daha dar kapsam)")
    ap.add_argument("--aciklama", default="", help="panelde/günlükte görünecek kısa not")
    ap.add_argument("--durum", action="store_true", help="mevcut tetikleyiciyi yazdır ve çık")
    ap.add_argument("--sil", action="store_true", help="tetikleyiciyi kaldır")
    a = ap.parse_args()

    if a.durum:
        mevcut = tetik.oku()
        if not mevcut:
            print(f"tetikleyici yok ({tetik.dosya_yolu()})")
            return 0
        print(json.dumps(mevcut, ensure_ascii=False, indent=1))
        print(f"imza: {tetik.imza()}")
        return 0
    if a.sil:
        print("tetikleyici kaldırıldı" if tetik.sil() else "tetikleyici zaten yoktu")
        return 0

    belge = tetik.yaz(a.ilce, a.bolge, a.aciklama)
    kapsam = belge["ilceId"] or "TÜM CİHAZLAR"
    print(f"tetikleyici yazıldı: {tetik.dosya_yolu()}")
    print(f"  zaman  : {belge['zaman']}")
    print(f"  kapsam : {kapsam}" + (f" · bölge={belge['bolgeId']}" if belge["bolgeId"] else ""))
    print(
        "  etki   : tarayıcı modunda uzun yoklama ~1 sn, Qt modunda en çok "
        f"{getattr(__import__('config'), 'DAMGA_KONTROL_MS', 120_000)} ms (push kopuksa "
        f"{getattr(__import__('config'), 'DAMGA_KONTROL_MS_PUSH_YOK', 30_000)} ms) içinde yenilenir"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
