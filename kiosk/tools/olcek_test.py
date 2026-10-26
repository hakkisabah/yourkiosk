#!/usr/bin/env python3
"""ÖLÇEK TESTİ — 600 cihazın yoklama yükünü ÖLÇER (tahmin değil).

NEDEN
-----
Sahada 600 cihaz olacak. Cihaz başına yoklama, cihaz sayısıyla DOĞRUSAL büyür:
  600 cihaz × 30 sn  → 1.728.000 istek/gün ≈ 51,8 M istek/ay
  600 cihaz × 300 sn →   172.800 istek/gün ≈  5,2 M istek/ay
Bu araç, seçilen aralıkta gerçek HTTP istekleri atarak sunucunun gecikmesini ve hata oranını
ölçer; aylık istek/maliyet tahminini ÖLÇÜLEN hızdan üretir.

Kullanım
--------
    # yerel sunucu ile (kiosk/tools/olcek_test.py kendi sunucusunu açar)
    .venv/bin/python tools/olcek_test.py --cihaz 600 --aralik 300 --sure 20

    # gerçek adres (S3/CloudFront) — dikkat: buluttan ücret çıkarır
    .venv/bin/python tools/olcek_test.py --adres https://d2dnrvsx5eevod.cloudfront.net/durum.json \\
        --cihaz 600 --aralik 30 --sure 10

Çıktı: hedef/gerçekleşen istek hızı, gecikme p50/p95/p99, hata sayısı, aylık istek ve
yaklaşık S3 GET maliyeti. Sunucu 5xx/429 dönerse "hata" olarak sayılır ve kod 1 döner.
"""

from __future__ import annotations

import argparse
import http.server
import json
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:  # ALLOWED_HOSTS (hedef beyaz listesi) — araç kiosk/ dışından koşulursa boş kalır
    import config  # noqa: E402
except ImportError:  # pragma: no cover - normalde kiosk/ içinden koşulur
    config = None  # type: ignore[assignment]

DURUM_GOVDESI = json.dumps(
    {"zaman": "2026-10-25T10:00:00Z", "lastupdate": "2026-10-25 09:59:58", "tetik": {"zaman": "2026-10-25T09:00:00Z"}},
    ensure_ascii=False,
).encode()

#: S3 GET fiyatı (1.000 istek), CloudFront ayrı. Yaklaşık; bölgeye göre değişir.
S3_GET_USD = 0.0004


def ozet_hesapla(gecikmeler_ms: list[float], hatalar: int, sure_s: float) -> dict:
    """Ölçümlerden özet üretir (saf fonksiyon — test edilebilir)."""
    if not gecikmeler_ms:
        return {"istek": 0, "hata": hatalar, "hiz": 0.0, "p50": None, "p95": None, "p99": None, "en_yuksek": None}
    sirali = sorted(gecikmeler_ms)

    def yuzdelik(p: float) -> float:
        # en yakın sıra (küçük örneklerde de anlamlı)
        idx = min(len(sirali) - 1, max(0, int(round((p / 100) * len(sirali) + 0.5)) - 1))
        return round(sirali[idx], 1)

    return {
        "istek": len(sirali),
        "hata": hatalar,
        "hiz": round(len(sirali) / sure_s, 2) if sure_s > 0 else 0.0,
        "p50": yuzdelik(50),
        "p95": yuzdelik(95),
        "p99": yuzdelik(99),
        "en_yuksek": round(sirali[-1], 1),
        "ortalama": round(statistics.fmean(sirali), 1),
    }


def aylik_tahmin(cihaz: int, aralik_s: float, istek_basina_usd: float = S3_GET_USD / 1000) -> dict:
    """Aylık istek sayısı + yaklaşık S3 GET maliyeti (30 gün)."""
    aralik = max(aralik_s, 1.0)
    gunluk = cihaz * (86400 / aralik)
    aylik = gunluk * 30
    return {"gunluk": int(gunluk), "aylik": int(aylik), "usd": round(aylik * istek_basina_usd, 2)}


class _Sunucu(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_a):  # sessiz
        return

    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(DURUM_GOVDESI)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(DURUM_GOVDESI)


def yerel_sunucu() -> tuple[http.server.ThreadingHTTPServer, str]:
    sunucu = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Sunucu)
    port = sunucu.server_address[1]
    threading.Thread(target=sunucu.serve_forever, daemon=True).start()
    return sunucu, f"http://127.0.0.1:{port}/durum.json"


def olc(adres: str, cihaz: int, aralik_s: float, sure_s: float, isci: int = 64) -> dict:
    """`cihaz/aralik_s` hızında istek atar; gecikmeleri ölçer."""
    hedef_hiz = cihaz / max(aralik_s, 1.0)
    gecikmeler: list[float] = []
    hatalar = 0
    kilit = threading.Lock()
    bitis = time.monotonic() + sure_s
    aralik = 1.0 / hedef_hiz if hedef_hiz > 0 else 1.0
    sonraki = time.monotonic()

    def tek_istek() -> None:
        nonlocal hatalar
        bas = time.monotonic()
        try:
            with urllib.request.urlopen(adres, timeout=10) as yanit:
                yanit.read()
                if yanit.status >= 400:
                    raise urllib.error.HTTPError(adres, yanit.status, "hata", None, None)
            gecen = (time.monotonic() - bas) * 1000
            with kilit:
                gecikmeler.append(gecen)
        except Exception:  # noqa: BLE001 - her hata sayılır
            with kilit:
                hatalar += 1

    with ThreadPoolExecutor(max_workers=max(1, isci)) as havuz:
        while time.monotonic() < bitis:
            havuz.submit(tek_istek)
            sonraki += aralik
            bekle = sonraki - time.monotonic()
            if bekle > 0:
                time.sleep(bekle)
            else:  # yetişemedik: planı şimdiye çek (gerçek hız ölçülür)
                sonraki = time.monotonic()
    return {"ozet": ozet_hesapla(gecikmeler, hatalar, sure_s), "hedef_hiz": round(hedef_hiz, 2)}


def _hedef_guvenli_mi(adres: str) -> tuple[bool, str]:
    """`--adres` yalnız KENDİ uçlarımıza gidebilir (26 Ekim i5 bulgusu).

    Bu araç 64 iş parçacığıyla saniyede yüzlerce istek atar; yanlışlıkla üçüncü taraf bir adrese
    koşulursa dışarıdan gelen bir yük testi gibi görünür (ve başkasının kotasını yakar). Bu yüzden
    hedef beyaz listedir: yerel test sunucusu + izinli alan adları (CloudFront/S3 dağıtımları).
    """
    from urllib.parse import urlparse

    try:
        u = urlparse(adres)
    except ValueError:
        return False, f"adres çözümlenemedi: {adres}"
    if u.scheme not in ("http", "https"):
        return False, f"şema desteklenmiyor: {u.scheme or '(yok)'} — http/https bekleniyor"
    host = (u.hostname or "").lower()
    if not host:
        return False, "adres host içermiyor"
    if host in {"127.0.0.1", "localhost", "::1", "[::1]"}:
        return True, ""
    izinli = {str(h).lower() for h in getattr(config, "ALLOWED_HOSTS", ())}
    if any(host == h or host.endswith("." + h) for h in izinli):
        return True, ""
    # AWS dağıtımları: CloudFront (*.cloudfront.net) ve S3 (*.amazonaws.com)
    if host.endswith(".cloudfront.net") or host.endswith(".amazonaws.com"):
        return True, ""
    return False, (f"hedef izin listesinde değil: {host} — yalnız yerel adresler, "
                   f"{', '.join(sorted(izinli))}, *.cloudfront.net, *.amazonaws.com")


def main(argv: list[str] | None = None) -> int:
    ayristirici = argparse.ArgumentParser(description="600 cihaz yoklama ölçek testi")
    ayristirici.add_argument("--cihaz", type=int, default=600, help="eşzamanlı cihaz sayısı (≤ 2000)")
    ayristirici.add_argument("--aralik", type=float, default=30.0, help="cihaz başına yoklama aralığı (sn)")
    ayristirici.add_argument("--sure", type=float, default=15.0, help="ölçüm süresi (sn, ≤ 300)")
    ayristirici.add_argument("--isci", type=int, default=64, help="eşzamanlı istek sayısı (≤ 128)")
    ayristirici.add_argument("--adres", default="", help="hedef adres (boşsa yerel test sunucusu)")
    ayristirici.add_argument("--json", action="store_true", help="yalnız JSON çıktısı")
    secim = ayristirici.parse_args(argv)

    # ÜST SINIRLAR (i5 bulgusu): sınırsız `--sure`/`--cihaz` ile farkında olmadan bir yük testine
    # dönüşmesin. Değerler ölçüm için fazlasıyla yeterli (600 cihaz · 30 sn · 64 iş parçacığı).
    if not 1 <= secim.cihaz <= 2000:
        print(f"✗ --cihaz 1…2000 aralığında olmalı (gelen: {secim.cihaz})", file=sys.stderr)
        return 2
    if not 1 <= secim.sure <= 300:
        print(f"✗ --sure 1…300 sn aralığında olmalı (gelen: {secim.sure})", file=sys.stderr)
        return 2
    if not 1 <= secim.isci <= 128:
        print(f"✗ --isci 1…128 aralığında olmalı (gelen: {secim.isci})", file=sys.stderr)
        return 2
    if secim.aralik <= 0:
        print(f"✗ --aralik > 0 olmalı (gelen: {secim.aralik})", file=sys.stderr)
        return 2

    sunucu = None
    adres = secim.adres.strip()
    if not adres:
        sunucu, adres = yerel_sunucu()
    else:
        guvenli, neden = _hedef_guvenli_mi(adres)
        if not guvenli:
            print(f"✗ {neden}", file=sys.stderr)
            return 2

    try:
        sonuc = olc(adres, secim.cihaz, secim.aralik, secim.sure, secim.isci)
    finally:
        if sunucu is not None:
            sunucu.shutdown()
            sunucu.server_close()

    tahmin = aylik_tahmin(secim.cihaz, secim.aralik)
    rapor = {
        "adres": adres,
        "cihaz": secim.cihaz,
        "aralik_s": secim.aralik,
        "sure_s": secim.sure,
        "hedef_hiz": sonuc["hedef_hiz"],
        **sonuc["ozet"],
        "aylik": tahmin,
        "karsilastirma": {f"{s} sn": aylik_tahmin(secim.cihaz, s) for s in (30, 120, 300)},
    }
    if secim.json:
        print(json.dumps(rapor, ensure_ascii=False, indent=1))
    else:
        o = sonuc["ozet"]
        print(f"adres            : {adres}")
        print(f"cihaz / aralık   : {secim.cihaz} cihaz · {secim.aralik:g} sn (hedef {sonuc['hedef_hiz']:g} istek/sn)")
        print(f"ölçüm            : {secim.sure:g} sn · {o['istek']} istek · {o['hata']} hata · {o['hiz']:g} istek/sn")
        print(f"gecikme (ms)     : p50={o['p50']} p95={o['p95']} p99={o['p99']} en yüksek={o['en_yuksek']}")
        print(f"aylık istek      : {tahmin['aylik']:,} · yaklaşık S3 GET ≈ ${tahmin['usd']}")
        print("karşılaştırma    : " + " · ".join(
            f"{k}: {v['aylik']:,}/ay (${v['usd']})" for k, v in rapor["karsilastirma"].items()
        ))

    # Hata oranı %1'i aşarsa başarısız say (yük altında sunucu yanıt veremiyor demektir).
    toplam = sonuc["ozet"]["istek"] + sonuc["ozet"]["hata"]
    if toplam == 0 or sonuc["ozet"]["hata"] / toplam > 0.01:
        print("✗ hata oranı yüksek ya da hiç istek tamamlanmadı", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
