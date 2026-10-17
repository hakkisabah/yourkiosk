#!/usr/bin/env python3
"""BELLEK ÖLÇÜMÜ — kiosk gerçekten ne kadar bellek harcıyor?

Uygulamayı (varsayılan olarak offscreen Qt ile) başlatır, belirli aralıklarla bellek
kullanımını okur ve özetler. Amaç: cihazda "ne kadar RAM gidiyor" sorusunu SAYIYLA
yanıtlamak ve hangi kalemin (Qt kitaplıkları, görsel önbelleği, Python veri yapıları)
ne kadar tuttuğunu göstermek.

Ölçülenler (Linux /proc):
  * **RSS**   — süreç başına toplam yerleşik sayfa (paylaşılan kitaplıklar dahil)
  * **PSS**   — paylaşılan sayfalar paylaşan süreçlere bölünmüş hâli (gerçek "maliyet")
  * **Özel**  — yalnızca bu sürece ait (private) bellek: Python nesneleri, önbellekler
  * **Metin** — kitaplıklardan paylaşılan salt-okunur kod (birden çok süreçle ortak)

Kullanım:
    python3 tools/bellek_olc.py                      # 60 örnek × 1 sn (offscreen)
    python3 tools/bellek_olc.py --sure 120 --aralik 2
    python3 tools/bellek_olc.py --yayinli             # yayın ekranını da gez
    python3 tools/bellek_olc.py --gercek-ekran        # gerçek ekranda çalıştır (cihazda)

Not: offscreen Qt, gerçek GPU/EGL yüzeyi oluşturmaz; bu yüzden ölçüm **alt sınırdır**
(gerçek ekranda grafik yüzeyleri için birkaç MB daha eklenebilir). Cihazda `--gercek-ekran`
ile ölçmek en doğrusudur.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
KONTROL_DOSYASI = KOK / "onbellek" / "_olcum_son.json"
#: `smaps` bölüm başlığı: "7f3c1a2b0000-7f3c1a2c0000 r-xp 00000000 fd:01 1234 /yol/dosya"
_BASLIK_RE = re.compile(r"^[0-9a-f]+-[0-9a-f]+ ")


def _oku_smaps(pid: int) -> dict | None:
    """`/proc/<pid>/smaps_rollup` → bellek kalemleri (KB)."""
    yol = Path(f"/proc/{pid}/smaps_rollup")
    if not yol.is_file():
        return None
    kalemler: dict[str, int] = {}
    for satir in yol.read_text().splitlines():
        parca = satir.split()
        # biçim: "Rss:     12345 kB"
        if len(parca) >= 3 and parca[-1] == "kB":
            try:
                kalemler[parca[0].rstrip(":")] = int(parca[1])
            except ValueError:
                continue
    return {
        "rss_kb": kalemler.get("Rss", 0),
        "pss_kb": kalemler.get("Pss", 0),
        "ozel_kb": kalemler.get("Private_Clean", 0) + kalemler.get("Private_Dirty", 0),
        "paylasilan_kb": kalemler.get("Shared_Clean", 0) + kalemler.get("Shared_Dirty", 0),
    }


def _dosya_kapladigi(pid: int) -> dict[str, float]:
    """Bellekte en çok yer tutan eşlenmiş dosyalar (MB) — 'kim yiyor' sorusu.

    `smaps` bloğu bir adres aralığı başlığıyla başlar ve ardından alanlar gelir;
    bloklar boş satırla ayrılmaz (bu yüzden satır satır gezilir).
    """
    toplam: dict[str, int] = {}
    ad: str | None = None
    try:
        for satir in Path(f"/proc/{pid}/smaps").read_text().splitlines():
            if _BASLIK_RE.match(satir):
                parcalar = satir.split()
                ad = parcalar[-1] if parcalar[-1].startswith("/") else None
            elif satir.startswith("Rss:") and ad:
                try:
                    toplam[ad] = toplam.get(ad, 0) + int(satir.split()[1])
                except (IndexError, ValueError):
                    continue
    except OSError:
        return {}
    return {a: kb / 1024 for a, kb in sorted(toplam.items(), key=lambda x: -x[1])[:12] if kb >= 512}


def olc(sure: int, aralik: float, gercek_ekran: bool) -> int:
    ortam = dict(os.environ)
    if not gercek_ekran:
        ortam["QT_QPA_PLATFORM"] = "offscreen"
    qt_libs = KOK / ".qt-libs" / "lib"
    if qt_libs.is_dir():
        ortam["LD_LIBRARY_PATH"] = f"{qt_libs}{':' + ortam['LD_LIBRARY_PATH'] if ortam.get('LD_LIBRARY_PATH') else ''}"
    ortam.setdefault("XDG_CACHE_HOME", str(KOK / ".cache"))

    python = str(KOK / ".venv" / "bin" / "python")
    if not Path(python).is_file():
        python = sys.executable
    komut = [python, str(KOK / "main.py")]

    print(f"başlatılıyor: {' '.join(komut)}  (QT_QPA_PLATFORM={ortam.get('QT_QPA_PLATFORM', 'gerçek ekran')})")
    surec = subprocess.Popen(
        komut, cwd=str(KOK), env=ortam, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    ornekler: list[dict] = []
    dosya_dagilimi: dict[str, float] = {}
    baslangic = time.time()
    try:
        # açılışın oturmasını bekle
        time.sleep(min(8, max(3, aralik * 2)))
        while time.time() - baslangic < sure:
            if surec.poll() is not None:
                print("!! uygulama beklenmedik şekilde kapandı; çıktı:")
                print((surec.stdout.read() or "")[-2000:])
                return 1
            kayit = _oku_smaps(surec.pid)
            if kayit:
                kayit["s"] = round(time.time() - baslangic, 1)
                ornekler.append(kayit)
            # dosya dağılımını ölçüm SÜRECİ ÇALIŞIRKEN al (sonrasında /proc kaybolur)
            dosya_dagilimi = _dosya_kapladigi(surec.pid) or dosya_dagilimi
            time.sleep(aralik)
    finally:
        surec.terminate()
        try:
            surec.wait(timeout=10)
        except subprocess.TimeoutExpired:
            surec.kill()

    if not ornekler:
        print("ölçüm alınamadı (süreç/smaps okunamadı).")
        return 1

    def _ozet(alan: str) -> tuple[float, float, float]:
        deger = [o[alan] / 1024 for o in ornekler]
        return statistics.mean(deger), max(deger), min(deger)

    print(f"\n=== ÖLÇÜM ({len(ornekler)} örnek, {aralik} sn aralık, {sure} sn) ===")
    print(f"{'kalem':<20}{'ortalama':>12}{'en yüksek':>14}{'en düşük':>12}")
    for alan, etiket in (
        ("rss_kb", "RSS (toplam)"),
        ("pss_kb", "PSS (paylaşımlı böl)"),
        ("ozel_kb", "özel (private)"),
        ("paylasilan_kb", "paylaşılan"),
    ):
        ort, yuk, dus = _ozet(alan)
        print(f"{etiket:<20}{ort:>10.1f} MB{yuk:>12.1f} MB{dus:>10.1f} MB")

    ilk, son = ornekler[0]["rss_kb"] / 1024, ornekler[-1]["rss_kb"] / 1024
    print(f"\nRSS değişimi   : {ilk:.1f} MB → {son:.1f} MB  (fark {son - ilk:+.1f} MB)")

    print("\n--- bellekte en çok yer tutan eşlenmiş dosyalar (MB) ---")
    for ad, mb in dosya_dagilimi.items():
        print(f"  {mb:>8.1f} MB  {ad}")

    KONTROL_DOSYASI.parent.mkdir(parents=True, exist_ok=True)
    KONTROL_DOSYASI.write_text(
        json.dumps({"ornekler": ornekler, "dosyalar": dosya_dagilimi}, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nham örnekler: {KONTROL_DOSYASI}")
    return 0


def main() -> int:
    ayar = argparse.ArgumentParser(description="Kiosk bellek ölçümü")
    ayar.add_argument("--sure", type=int, default=60, help="toplam ölçüm süresi (sn)")
    ayar.add_argument("--aralik", type=float, default=1.0, help="örnekleme aralığı (sn)")
    ayar.add_argument(
        "--gercek-ekran",
        action="store_true",
        help="offscreen yerine gerçek ekranda çalıştır (cihazda önerilen)",
    )
    secenek = ayar.parse_args()
    return olc(secenek.sure, secenek.aralik, secenek.gercek_ekran)


if __name__ == "__main__":
    raise SystemExit(main())
