"""Ekran görüntüsünden ölçülebilir kanıt üret (görsel denetim/vision yokken).

Neden: kiosk ekranlarında "şerit var mı, yazı hangi renk, hangi bölgede" sorusu göz kararıyla
cevaplanır ve tekrarlanabilir değildir. Bu betik görüntüyü piksel piksel tarar, bölgenin baskın
renklerini ve hedef renk / beyaz yazı piksel sayısını yazdırır. Böylece "kırmızı kuşak + beyaz
kayan yazı görünüyor" iddiası sayıyla kanıtlanır ve regresyonda aynı komut tekrar çalıştırılır.

Kullanım
--------
    python ekran_dogrula.py .cache/ekran_1920x1080.png                 # tüm görüntü
    python ekran_dogrula.py ekran.png --satir 60                       # yalnızca alt 60 satır (şerit)
    python ekran_dogrula.py ekran.png --bolge 1036,1080                # y1,y2 aralığı
    python ekran_dogrula.py ekran.png --renk c8102e                    # hedef rengi say
    python ekran_dogrula.py ekran.png --satir 60 --renk c8102e --adim 3

Çıktı: görüntü ölçüsü, taranan bölge, en sık 5 renk (sayıyla), hedef renk sayısı, beyaz (yazı)
piksel sayısı ve tek satır yargı (`KUSAK VAR`, `YAZI VAR` gibi). Çıkış kodu: 1 -> hedef renk ya da
beyaz yazı beklenen eşiğin altında (CI'da doğrudan kullanılabilir).

Not: PyQt6 yoksa PIL'e düşer; ikisi de yoksa anlaşılır bir hata verir (sessizce boş sonuç döndürmez).
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter


class GoruntuOkunamadi(RuntimeError):
    pass


def _pikseller_pyqt(yol: str, y1: int, y2: int, adim: int):
    from PyQt6.QtGui import QImage

    img = QImage(yol)
    if img.isNull():
        raise GoruntuOkunamadi(f"QImage açamadı: {yol}")
    genislik, yukseklik = img.width(), img.height()
    for y in range(y1, y2, max(1, adim // 3)):
        for x in range(0, genislik, max(1, adim)):
            c = img.pixelColor(x, y)
            yield c.red(), c.green(), c.blue()
    return


def _pikseller_pil(yol: str, y1: int, y2: int, adim: int):
    try:
        from PIL import Image
    except ImportError as hata:  # pragma: no cover - ortama bağlı
        raise GoruntuOkunamadi("ne PyQt6 ne PIL bulundu; birini kur (pip install pillow)") from hata

    with Image.open(yol) as img:
        rgb = img.convert("RGB")
        genislik, yukseklik = rgb.size
        for y in range(y1, y2, max(1, adim // 3)):
            for x in range(0, genislik, max(1, adim)):
                yield rgb.getpixel((x, y))


def _yukseklik(yol: str) -> int:
    try:
        from PyQt6.QtGui import QImage

        img = QImage(yol)
        if not img.isNull():
            return img.height()
    except ImportError:
        pass
    try:
        from PIL import Image

        with Image.open(yol) as img:
            return img.height
    except ImportError as hata:
        raise GoruntuOkunamadi("görüntü ölçüsü okunamadı (PyQt6/PIL yok)") from hata


def _renk_ayristir(metin: str) -> tuple[int, int, int]:
    temiz = metin.strip().lstrip("#")
    if len(temiz) != 6:
        raise SystemExit("--renk 6 haneli olmalı, ör. c8102e")
    return int(temiz[0:2], 16), int(temiz[2:4], 16), int(temiz[4:6], 16)


def main(argv: list[str] | None = None) -> int:
    ayristirici = argparse.ArgumentParser(description="Ekran görüntüsünden piksel kanıtı üret")
    ayristirici.add_argument("goruntu", help="PNG/JPEG yol")
    ayristirici.add_argument("--satir", type=int, help="görüntünün en altından bu kadar satırı tara")
    ayristirici.add_argument("--bolge", help="taranacak dikey aralık: y1,y2")
    ayristirici.add_argument("--renk", help="sayılacak hedef renk (RRGGBB)")
    ayristirici.add_argument("--tolerans", type=int, default=12, help="renk yakınlık toleransı (varsayılan 12)")
    ayristirici.add_argument("--adim", type=int, default=3, help="yatay örnekleme adımı (varsayılan 3)")
    ayristirici.add_argument("--beyaz-esik", type=int, default=240, help="yazı sayılan beyaz eşiği (varsayılan 240)")
    ayristirici.add_argument("--min-beyaz", type=int, default=200, help="yazı var demek için en az beyaz piksel")
    ayristirici.add_argument("--min-renk", type=int, default=500, help="hedef renk var demek için en az piksel")
    ayarlar = ayristirici.parse_args(argv)

    yukseklik = _yukseklik(ayarlar.goruntu)
    if ayarlar.bolge:
        parcalar = [int(p) for p in ayarlar.bolge.split(",")]
        if len(parcalar) != 2:
            raise SystemExit("--bolge biçimi: y1,y2")
        y1, y2 = parcalar
    elif ayarlar.satir:
        y1, y2 = max(0, yukseklik - ayarlar.satir), yukseklik
    else:
        y1, y2 = 0, yukseklik
    y2 = min(y2, yukseklik)

    uretici = _pikseller_pyqt if _pyqt_var() else _pikseller_pil
    sayac: Counter[tuple[int, int, int]] = Counter()
    beyaz = 0
    hedef = 0
    hedef_renk = _renk_ayristir(ayarlar.renk) if ayarlar.renk else None
    toplam = 0
    for r, g, b in uretici(ayarlar.goruntu, y1, y2, ayarlar.adim):
        toplam += 1
        sayac[(r, g, b)] += 1
        if r >= ayarlar.beyaz_esik and g >= ayarlar.beyaz_esik and b >= ayarlar.beyaz_esik:
            beyaz += 1
        if hedef_renk and all(abs(k - h) <= ayarlar.tolerans for k, h in zip((r, g, b), hedef_renk)):
            hedef += 1

    print(f"görüntü      : {ayarlar.goruntu} ({yukseklik} satır)")
    print(f"taranan bölge: y={y1}..{y2} · {toplam} piksel (adım {ayarlar.adim})")
    print("baskın renkler:")
    for (r, g, b), adet in sayac.most_common(5):
        print(f"  #{r:02x}{g:02x}{b:02x}  {adet}")
    if hedef_renk:
        print(f"hedef #{''.join(f'{h:02x}' for h in hedef_renk)} : {hedef} piksel")
    print(f"beyaz (yazı) piksel: {beyaz}")

    yargi = []
    if hedef_renk:
        yargi.append("RENK VAR" if hedef >= ayarlar.min_renk else "RENK YOK")
    yargi.append("YAZI VAR" if beyaz >= ayarlar.min_beyaz else "YAZI YOK")
    print("yargı        : " + " · ".join(yargi))

    basarisiz = beyaz < ayarlar.min_beyaz or (hedef_renk is not None and hedef < ayarlar.min_renk)
    return 1 if basarisiz else 0


def _pyqt_var() -> bool:
    try:
        import PyQt6.QtGui  # noqa: F401
    except ImportError:
        return False
    return True


if __name__ == "__main__":
    try:
        sys.exit(main())
    except GoruntuOkunamadi as hata:
        print(f"hata: {hata}", file=sys.stderr)
        sys.exit(2)
