"""Yerleşim doğrulama sondası: gerçek widget geometrilerini denetler.

Görüntü analizine ek olarak (ve ondan bağımsız) satırların panel içinde
kaldığını, üst üste binmediğini ve yazıların satıra sığdığını ölçer.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kiosk.fontconfig import ensure_fontconfig  # noqa: E402

_conf = ensure_fontconfig(ROOT)
if _conf is not None:
    os.environ.setdefault("FONTCONFIG_FILE", str(_conf))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from kiosk.config import Settings  # noqa: E402
from kiosk.fetcher import FetchOutcome  # noqa: E402
from kiosk.models import parse_payload  # noqa: E402
from kiosk.scaling import LayoutMetrics  # noqa: E402

BOYUTLAR = [(1920, 1080), (1366, 768), (800, 600)]


def window_free(view: object) -> None:
    """Qt nesnesini bırak (referansı düşür)."""
    del view


def main() -> int:
    app = QApplication(sys.argv[:1])
    payload = (ROOT / "assets" / "ornekdata_canli.json").read_text(encoding="utf-8")
    import json

    snapshot = parse_payload(json.loads(payload)).snapshot
    hatalar: list[str] = []

    for genislik, yukseklik in BOYUTLAR:
        settings = Settings(data_url="https://hakkisozde.test/a.json", allowed_hosts=("hakkisozde.test",))
        metrics = LayoutMetrics.from_screen(genislik, yukseklik)
        from kiosk.ui.nobet_view import NobetView

        view = NobetView(metrics, settings, {})
        view.resize(metrics.screen_w, metrics.screen_h)
        view.set_pharmacies(snapshot.pharmacies)
        view.show()
        app.processEvents()

        panel = view.left_panel
        satirlar = [row[2] for row in view._rows]
        toplam = 0
        onceki_alt = 0
        for i, satir in enumerate(satirlar):
            y = satir.y()
            h = satir.height()
            if y < onceki_alt - 1:
                hatalar.append(f"{genislik}x{yukseklik}: {i}. satır öncekiyle çakışıyor (y={y}, önceki_alt={onceki_alt})")
            onceki_alt = y + h
            toplam = max(toplam, y + h)
            isim, ikincil, _ = view._rows[i]
            if isim.height() + ikincil.height() > h:
                hatalar.append(
                    f"{genislik}x{yukseklik}: {i}. satır yazıları sığmıyor "
                    f"({isim.height()}+{ikincil.height()} > {h})"
                )
        if toplam > panel.height():
            hatalar.append(f"{genislik}x{yukseklik}: liste panelden taşıyor ({toplam} > {panel.height()})")

        print(
            f"{genislik}x{yukseklik}: satır={len(satirlar)} sayfa_boyutu={view.page_size} "
            f"satır_yüksekliği={satirlar[0].height() if satirlar else 0} "
            f"liste_toplam={toplam} panel={panel.height()} taşma_yok={toplam <= panel.height()}"
        )
        window_free(view)
        view.close()

    if hatalar:
        print("\nHATALAR:")
        for hata in hatalar:
            print(" -", hata)
        return 1
    print("\nSONUC: yerleşim denetimleri geçti (çakışma/kırpılma yok)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
