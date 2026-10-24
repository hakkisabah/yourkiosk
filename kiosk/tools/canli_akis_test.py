#!/usr/bin/env python3
"""CANLI AKIŞ KANITI — panel yazınca uygulama GERÇEKTEN yenileniyor mu?

Uçtan uca, yerel bir HTTP sunucusuyla (S3/CloudFront taklidi):

  1. `durum.json` + `lastSystemData.json` servis edilir (damga A).
  2. Qt uygulaması offscreen başlatılır, A verisi yüklenir.
  3. Sunucudaki damga B'ye çevrilir ve veri içeriği değiştirilir (panel "Bildir" taklidi).
  4. Uygulama **yeniden başlatılmadan** B'yi ne kadar sürede aldığı ölçülür.

Kullanım:
    QT_QPA_PLATFORM=offscreen .venv/bin/python tools/canli_akis_test.py
Çıkış 0 = canlı güncelleme çalışıyor.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

DAMGA_A = "2026-10-24 10:00:00"
DAMGA_B = "2026-10-24 10:05:00"

VERI_A = {
    "Nobetler": {
        "T20261024": {
            "I1": [
                {
                    "B1": [
                        {
                            "eczane": "ESKİ ECZANE",
                            "tel": "111",
                            "adres": "ESKİ ADRES",
                            "adres_tarifi": "",
                            "start": "2026-10-24T08:30:00",
                            "end": "2026-10-24T23:59:00",
                            "ilce": "TEST",
                            "ilceId": "I1",
                            "bolge": "Test",
                            "bolgeId": "B1",
                        }
                    ]
                }
            ]
        }
    }
}


def _veri_b() -> dict:
    v = json.loads(json.dumps(VERI_A))
    v["Nobetler"]["T20261024"]["I1"][0]["B1"][0]["eczane"] = "YENİ ECZANE"
    v["Nobetler"]["T20261024"]["I1"][0]["B1"][0]["adres"] = "YENİ ADRES"
    return v


class Sunucu:
    """Bellekte tutulan dosyaları servis eden minik HTTP sunucusu."""

    def __init__(self) -> None:
        self.dosyalar: dict[str, bytes] = {}
        self.istekler: list[str] = []
        dis = self

        class Isleyici(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                ad = self.path.lstrip("/").split("?")[0]
                dis.istekler.append(ad)
                govde = dis.dosyalar.get(ad)
                if govde is None:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(govde)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(govde)

            def log_message(self, *_a):  # sessiz
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Isleyici)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def yaz(self, ad: str, belge: dict) -> None:
        self.dosyalar[ad] = json.dumps(belge, ensure_ascii=False).encode()

    def kapat(self) -> None:
        self.httpd.shutdown()


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["XDG_CACHE_HOME"] = str(KOK / ".cache")

    sunucu = Sunucu()
    taban = f"http://127.0.0.1:{sunucu.port}"
    sunucu.yaz("durum.json", {"zaman": "2026-10-24T07:00:00Z", "lastupdate": DAMGA_A, "tetik": {}})
    sunucu.yaz("lastupdate.json", {"lastupdate": DAMGA_A})
    sunucu.yaz("lastSystemData.json", VERI_A)
    # GERÇEK yapı: match.json = {ilceId: [{bolgeId: [cihazId, ...]}]}
    sunucu.yaz("match.json", {"I1": [{"B1": ["98273648723468273"]}]})
    sunucu.yaz("makinebilgileri.json", {"clientID": "98273648723468273"})

    import config

    # ayarlar.json testi EZMESİN: uygula() no-op
    import ayarlar

    ayarlar.uygula = lambda *a, **k: None  # type: ignore[assignment]

    # TEST İÇİN: yerel http sunucusu (üretimde yalnız https). Şema denetimini bu süreçte açarız.
    import security.network as ag

    ag.IZINLI_SEMALAR = ("https", "http")

    config.DOSYA_ADRESI = taban
    config.KAYNAK = "https"
    config.ALLOWED_HOSTS = ("127.0.0.1", "localhost")
    config.AG_IZINLI_PORTLAR = (443, 80, sunucu.port)
    config.TETIK_PUSH_AKTIF = False
    config.DAMGA_KONTROL_MS = 5_000          # test: hızlı yoklama
    config.DAMGA_KONTROL_MS_PUSH = 5_000
    config.DAMGA_KONTROL_MS_PUSH_YOK = 5_000
    # AYRI önbellek klasörü: gerçek cihaz önbelleği testi kirletmesin, eski damga karışmasın.
    import shutil

    config.ONBELLEK_KLASORU = "canli-test-onbellek"
    shutil.rmtree(KOK / "canli-test-onbellek", ignore_errors=True)

    from PyQt6.QtWidgets import QApplication

    import pharmacy_app

    uygulama = QApplication.instance() or QApplication([])
    pencere = pharmacy_app.PharmacyApp()
    basladi = time.monotonic()

    # 1) İlk veri yüklenene kadar bekle
    ilk = ""
    while time.monotonic() - basladi < 25:
        uygulama.processEvents()
        ilk = str(getattr(pencere.data_handler, "lastupdate", "") or "")
        if ilk:
            break
        time.sleep(0.2)

    print(f"1) ilk yükleme : damga={ilk!r} · süre={time.monotonic() - basladi:.1f} sn")
    if ilk != DAMGA_A:
        print(f"✗ beklenen damga {DAMGA_A!r} gelmedi (gelen {ilk!r})")
        sunucu.kapat()
        return 1

    # 2) PANEL YAZDI: damga + veri değişti (uygulama AYAKTA)
    degisim = time.monotonic()
    sunucu.yaz("durum.json", {"zaman": "2026-10-24T07:05:00Z", "lastupdate": DAMGA_B,
                              "tetik": {"zaman": "2026-10-24T07:05:00Z", "ilceId": "", "bolgeId": "",
                                        "aciklama": "panel: lastSystemData.json"}})
    sunucu.yaz("lastupdate.json", {"lastupdate": DAMGA_B})
    sunucu.yaz("lastSystemData.json", _veri_b())

    yeni = ""
    while time.monotonic() - degisim < 40:
        uygulama.processEvents()
        yeni = str(getattr(pencere.data_handler, "lastupdate", "") or "")
        if yeni == DAMGA_B:
            break
        time.sleep(0.2)
    gecen = time.monotonic() - degisim

    print(f"2) panel yazdı : damga {DAMGA_A} → {DAMGA_B}")
    if yeni == DAMGA_B:
        print(f"✓ YENİDEN BAŞLATMADAN alındı · {gecen:.1f} sn içinde")
        print(f"   yoklama istekleri: {len(sunucu.istekler)} · örnek: {sunucu.istekler[-3:]}")
        pencere.close()
        sunucu.kapat()
        return 0

    print(f"✗ 40 sn içinde alınamadı (son damga {yeni!r}) — canlı akış KOPUK")
    print(f"   yoklama istekleri: {len(sunucu.istekler)} · son: {sunucu.istekler[-5:]}")
    pencere.close()
    sunucu.kapat()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
