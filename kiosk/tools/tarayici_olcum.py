#!/usr/bin/env python3
"""TARAYICI MODU ÖLÇÜMÜ — bellek (RSS/PSS) ve ağ trafiği.

NEDEN AYRI ARAÇ: `tools/bellek_olc.py` Qt sürecini ölçer. Tarayıcı modunda bellek tek süreçte
değildir: Chromium ana süreç + renderer/GPU/utility çocukları vardır. Ağ trafiği de farklıdır
(arayüz her turda `durum.json` okur; büyük veri yalnız damga değişince iner).

Kullanım:
    # 1) AĞ: bir yenileme turunun gerçek bayt maliyeti (tarayıcı gerekmez; yerel 304 sunucusu)
    .venv/bin/python tools/tarayici_olcum.py --ag --aralik 30

    # 2) BELLEK: çalışan tarayıcı süreç ağacını örnekle (cihazda, kiosk açıkken)
    .venv/bin/python tools/tarayici_olcum.py --bellek --sure 60 --aralik 2

Çıkış kodları: 0 = ölçüm tamam, 3 = tarayıcı süreci bulunamadı (bellek modu).
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
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

import config  # noqa: E402

#: Ölçüm için sahte büyük veri boyutu (gerçek dosya varsa o kullanılır)
VARSAYILAN_VERI_BAYT = 268 * 1024


# ---------------------------------------------------------------- /proc yardımcıları
def surec_pidleri(desen: str = "chrom") -> list[int]:
    """`/proc` altında komut satırı `desen` içeren süreçlerin pid'leri."""
    bulunan: list[int] = []
    for giris in Path("/proc").iterdir():
        if not giris.name.isdigit():
            continue
        try:
            komut = (giris / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "ignore")
        except OSError:
            continue
        if desen.lower() in komut.lower():
            bulunan.append(int(giris.name))
    return bulunan


def bellek_bayt(pid: int) -> dict:
    """`/proc/<pid>/smaps_rollup` → RSS/PSS/özel; yoksa `status` üzerinden RSS."""
    satirlar: dict[str, int] = {}
    try:
        for satir in Path(f"/proc/{pid}/smaps_rollup").read_text(encoding="utf-8").splitlines():
            parca = satir.split()
            if len(parca) >= 2 and parca[0].endswith(":"):
                satirlar[parca[0].rstrip(":")] = int(parca[1]) * 1024
    except (OSError, ValueError):
        try:
            for satir in Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines():
                if satir.startswith("VmRSS:"):
                    satirlar["Rss"] = int(satir.split()[1]) * 1024
        except (OSError, ValueError, IndexError):
            return {}
    return {
        "rss": satirlar.get("Rss", 0),
        "pss": satirlar.get("Pss", 0),
        "ozel": satirlar.get("Private_Clean", 0) + satirlar.get("Private_Dirty", 0),
    }


def bellek_topla(desen: str) -> dict:
    """Tarayıcı süreç ağacının toplam belleği (paylaşılan sayfalar PSS ile bölünmüş)."""
    toplam = {"rss": 0, "pss": 0, "ozel": 0, "surec": 0}
    for pid in surec_pidleri(desen):
        veri = bellek_bayt(pid)
        if not veri:
            continue
        toplam["surec"] += 1
        for alan in ("rss", "pss", "ozel"):
            toplam[alan] += veri[alan]
    return toplam


# ---------------------------------------------------------------- ağ ölçümü
class _KosulluSunucu(http.server.BaseHTTPRequestHandler):
    """ETag/304 davranışını taklit eder; gönderilen GÖVDE BAYTINI sayar (başlıklar hariç)."""

    protokol_surumu = "HTTP/1.1"
    govde = b""
    etag = '"v1"'
    sayac = {"govde_bayt": 0, "istek": 0, "kalan304": 0}
    kilit = threading.Lock()

    def log_message(self, *_a):
        return

    def do_GET(self):  # noqa: N802
        with self.kilit:
            type(self).sayac["istek"] += 1
        if self.headers.get("If-None-Match") == self.etag:
            with self.kilit:
                type(self).sayac["kalan304"] += 1
            self.send_response(304)
            self.send_header("ETag", self.etag)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(self.govde)))
        self.send_header("ETag", self.etag)
        self.end_headers()
        with self.kilit:
            type(self).sayac["govde_bayt"] += len(self.govde)  # ÖNCE say (yarış yok)
        self.wfile.write(self.govde)


def ag_olc(aralik_s: float, tur: int = 3) -> dict:
    """Bir yenileme turunun gövde baytı: `durum.json` her tur, büyük veri YALNIZ damga değişince.

    Model (web/src/kiosk.ts ile aynı):
      · her tur  : `durum.json` (koşullu, 304 ise 0 bayt)
      · damga değişince: `lastSystemData.json` bir kez (tam gövde)
    """
    kucuk = json.dumps({"zaman": "2026-10-25T10:00:00Z", "lastupdate": "2026-10-25 09:59:58",
                        "tetik": {"zaman": "2026-10-25T09:00:00Z"}}).encode()
    _KosulluSunucu.govde = kucuk
    sunucu = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _KosulluSunucu)
    threading.Thread(target=sunucu.serve_forever, daemon=True).start()
    adres = f"http://127.0.0.1:{sunucu.server_address[1]}/durum.json"
    ilk_bayt = 0
    try:
        for i in range(max(2, tur)):
            # 1. istek KOŞULSUZ (soğuk tur, gövde iner) · sonrakiler koşullu (304 beklenir)
            baslik = {} if i == 0 else {"If-None-Match": _KosulluSunucu.etag}
            istek = urllib.request.Request(adres, headers=baslik)
            try:
                with urllib.request.urlopen(istek, timeout=5) as y:
                    y.read()
            except urllib.error.HTTPError as hata:
                # 304 "hata" değildir: gövde inmedi (maliyet hedefi tam olarak bu)
                if hata.code != 304:
                    raise
            if i == 0:
                ilk_bayt = _KosulluSunucu.sayac["govde_bayt"]
    finally:
        sunucu.shutdown()
        sunucu.server_close()

    tur_sayisi = max(2, tur)
    steady_bayt = (_KosulluSunucu.sayac["govde_bayt"] - ilk_bayt) / (tur_sayisi - 1)
    gunluk_tur = 86400 / max(aralik_s, 1.0)
    veri = VARSAYILAN_VERI_BAYT
    gunluk_kucuk = steady_bayt * gunluk_tur
    # damga günde EN ÇOK birkaç kez değişir (panel yayınları); 5 varsayımı belgede açık
    gunluk_buyuk = veri * 5
    return {
        "durum_json_bayt": len(kucuk),
        "ilk_tur_bayt": ilk_bayt,
        "steady_tur_bayt": steady_bayt,
        "304_sayisi": _KosulluSunucu.sayac["kalan304"],
        "gunluk_kucuk_bayt": gunluk_kucuk,
        "gunluk_buyuk_bayt": gunluk_buyuk,
        "gunluk_toplam_mb": (gunluk_kucuk + gunluk_buyuk) / 1024 / 1024,
        "aylik_toplam_mb": (gunluk_kucuk + gunluk_buyuk) * 30 / 1024 / 1024,
    }


def main(argv: list[str] | None = None) -> int:
    a = argparse.ArgumentParser(description="tarayıcı modu bellek/ağ ölçümü")
    a.add_argument("--bellek", action="store_true", help="çalışan tarayıcı süreç ağacının belleği")
    a.add_argument("--ag", action="store_true", help="bir yenileme turunun ağ maliyeti")
    a.add_argument("--desen", default="", help="süreç adı deseni (varsayılan: config.TARAYICI_YOLU)")
    a.add_argument("--sure", type=float, default=30.0)
    a.add_argument("--aralik", type=float, default=2.0)
    secim = a.parse_args(argv)

    if not secim.bellek and not secim.ag:
        secim.ag = True

    if secim.ag:
        sonuc = ag_olc(max(secim.aralik, 5.0))
        print("AĞ (bir yenileme turu — gövde baytları, başlıklar hariç)")
        print(f"  durum.json gövdesi      : {sonuc['durum_json_bayt']} bayt")
        print(f"  tur başına gövde         : {sonuc['steady_tur_bayt']:.0f} bayt (304 sayısı {sonuc['304_sayisi']})")
        print(f"  soğuk tur (ilk)          : {sonuc['ilk_tur_bayt']} bayt")
        print(f"  günlük küçük dosyalar    : {sonuc['gunluk_kucuk_bayt']/1024:.0f} KB")
        print(f"  günlük büyük veri (5×)   : {sonuc['gunluk_buyuk_bayt']/1024:.0f} KB")
        print(f"  aylık toplam             : {sonuc['aylik_toplam_mb']:.1f} MB")

    if secim.bellek:
        desen = secim.desen or Path(str(getattr(config, "TARAYICI_YOLU", "chromium"))).name
        ornekler: list[dict] = []
        bitis = time.monotonic() + secim.sure
        while time.monotonic() < bitis:
            ornekler.append(bellek_topla(desen))
            time.sleep(max(0.5, secim.aralik))
        if not ornekler or max(o["surec"] for o in ornekler) == 0:
            print(f"✗ '{desen}' süreci bulunamadı — kiosk açıkken ve cihazda çalıştırın.", file=sys.stderr)
            print("  (geliştirme makinesinde Chromium kurulu olmayabilir; '--ag' tarayıcı gerektirmez.)",
                  file=sys.stderr)
            return 3
        rss = [o["rss"] / 1024 / 1024 for o in ornekler]
        pss = [o["pss"] / 1024 / 1024 for o in ornekler]
        ozel = [o["ozel"] / 1024 / 1024 for o in ornekler]
        print(f"BELLEK ({desen}, {len(ornekler)} örnek)")
        print(f"  süreç sayısı : {max(o['surec'] for o in ornekler)}")
        print(f"  RSS  (MB)    : ort {statistics.fmean(rss):.1f} · en yüksek {max(rss):.1f}")
        print(f"  PSS  (MB)    : ort {statistics.fmean(pss):.1f} · en yüksek {max(pss):.1f}")
        print(f"  özel (MB)    : ort {statistics.fmean(ozel):.1f}")
        print(f"  RSS değişimi : {rss[-1] - rss[0]:+.1f} MB (sızıntı göstergesi)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
