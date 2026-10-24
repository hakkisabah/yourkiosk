#!/usr/bin/env python3
"""Görselleri WebP'ye çevir (içerik adlı) — panelden yükleme gelene kadar toplu dönüştürme.

NEDEN: ölçüm (gerçek yayın görseli) 2473 KB PNG → 211 KB WebP q82; 1280 px'te 130 KB.
S3 statik dosyayı sıkıştırmaz, CloudFront yalnız metin türlerini sıkıştırır → tek yol dönüştürme.

Kullanım:
    # yalnız ölçüm (dosya yazmaz)
    .venv/bin/python tools/gorsel_webp.py a.png b.jpg
    # dönüştür + çıktı klasörüne yaz
    .venv/bin/python tools/gorsel_webp.py a.png b.jpg --cikti /tmp/webp
    # S3'e yükle (immutable önbellek) + adresleri yazdır
    .venv/bin/python tools/gorsel_webp.py a.png --s3 kova=kiosk/yayin-gorselleri/
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

MAX_KENAR = 1920
KALITE = 82

# PyQt6 zorunlu değil: varsa hızlı ve bağımlılıksız dönüştürme yapar (kiosk venv'inde var).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _qt() -> tuple:
    from PyQt6.QtGui import QGuiApplication, QImage  # noqa: PLC0415

    uygulama = QGuiApplication.instance() or QGuiApplication([])
    return QImage, uygulama


def donustur(yol: Path, max_kenar: int = MAX_KENAR, kalite: int = KALITE) -> tuple[bytes, dict]:
    QImage, _ = _qt()
    resim = QImage(str(yol))
    if resim.isNull():
        raise SystemExit(f"✗ açılamadı: {yol}")
    giris = {"genislik": resim.width(), "yukseklik": resim.height(), "bayt": yol.stat().st_size}
    en_buyuk = max(resim.width(), resim.height())
    if en_buyuk > max_kenar:
        oran = max_kenar / en_buyuk
        resim = resim.scaled(
            max(1, round(resim.width() * oran)), max(1, round(resim.height() * oran)),
            aspectRatioMode=1,  # KeepAspectRatio
            transformMode=1,    # SmoothTransformation
        )
    gecici = yol.with_suffix(".webp.tmp")
    if not resim.save(str(gecici), "WEBP", kalite):
        raise SystemExit(f"✗ WebP yazılamadı: {yol}")
    govde = gecici.read_bytes()
    gecici.unlink(missing_ok=True)
    return govde, {**giris, "cikti_genislik": resim.width(), "cikti_yukseklik": resim.height(), "cikti_bayt": len(govde)}


def main() -> int:
    a = argparse.ArgumentParser(description="görselleri içerik adlı WebP'ye çevir")
    a.add_argument("dosyalar", nargs="+", type=Path)
    a.add_argument("--cikti", type=Path, default=None, help="WebP dosyalarını bu klasöre yaz")
    a.add_argument("--max-kenar", type=int, default=MAX_KENAR)
    a.add_argument("--kalite", type=int, default=KALITE)
    a.add_argument("--s3", default="", help="kova=önek (ör. yourkiosk-veri=kiosk/yayin-gorselleri/)")
    secim = a.parse_args()

    toplam_giris = toplam_cikti = 0
    print(f"{'dosya':<28}{'giriş':>10}{'çıkış':>9}{'kazanç':>9}  {'boyut':>12}  anahtar")
    for yol in secim.dosyalar:
        if not yol.is_file():
            print(f"✗ yok: {yol}")
            continue
        govde, bilgi = donustur(yol, secim.max_kenar, secim.kalite)
        anahtar = hashlib.sha256(govde).hexdigest()[:16]
        kazanc = 100 - bilgi["cikti_bayt"] / max(1, bilgi["bayt"]) * 100
        toplam_giris += bilgi["bayt"]
        toplam_cikti += bilgi["cikti_bayt"]
        print(
            f"{yol.name:<28}{bilgi['bayt']/1024:>9.0f}K{bilgi['cikti_bayt']/1024:>8.0f}K"
            f"{kazanc:>8.0f}%  {bilgi['cikti_genislik']}×{bilgi['cikti_yukseklik']:<8}  {anahtar}.webp"
        )
        if secim.cikti:
            secim.cikti.mkdir(parents=True, exist_ok=True)
            (secim.cikti / f"{anahtar}.webp").write_bytes(govde)

    if toplam_giris:
        print(
            f"\ntoplam: {toplam_giris/1024:.0f} KB → {toplam_cikti/1024:.0f} KB "
            f"(%{100 - toplam_cikti/max(1,toplam_giris)*100:.0f} küçüldü)"
        )

    if secim.s3:
        if "=" not in secim.s3:
            print("✗ --s3 biçimi: kova=önek", file=sys.stderr)
            return 2
        kova, onek = secim.s3.split("=", 1)
        onek = onek.strip("/")
        for yol in secim.dosyalar:
            if not yol.is_file():
                continue
            govde, _ = donustur(yol, secim.max_kenar, secim.kalite)
            anahtar = hashlib.sha256(govde).hexdigest()[:16]
            hedef = f"s3://{kova}/{onek}/{anahtar}.webp"
            gecici = Path(f"/tmp/{anahtar}.webp")
            gecici.write_bytes(govde)
            kod = subprocess.run(
                ["aws", "s3", "cp", str(gecici), hedef,
                 "--cache-control", "public,max-age=31536000,immutable",
                 "--content-type", "image/webp", "--only-show-errors"],
                capture_output=True, text=True,
            )
            gecici.unlink(missing_ok=True)
            if kod.returncode != 0:
                print(f"✗ yüklenemedi: {hedef} — {kod.stderr.strip()[:120]}", file=sys.stderr)
            else:
                print(f"✓ yüklendi: {hedef}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
