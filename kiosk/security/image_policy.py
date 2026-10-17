"""İndirilen/okunan görseller için güvenlik politikası (Qt bağımlılığı YOK).

NEDEN
-----
Qt'nin görsel çözücüleri bu kurulumda `svg`, `svgz`, `pdf`, `tiff`, `gif` biçimlerini de
çözebiliyor (`QImageReader.supportedImageFormats()`). 2026'da Qt SVG/XML tarafında açıklanan
yüksek önem dereceli açıkların tamamı "güvenilmeyen biçim çözümleme" sınıfındadır:

  * CVE-2026-6210  Qt SVG marker type-confusion + heap taşması (CVSS 8.7, düzeltme 6.11.1+)
  * CVE-2026-78253 QXmlStreamReader sınırsız özyineleme (DoS, düzeltme 6.11.2)
  * CVE-2026-79616 Qt Quick SVG yolu OOB okuma (düzeltme 6.11.2)
  * CVE-2026-79680 Qt VNC parola atlatma (düzeltme 6.11.3 — VNC kullanılmıyorsa eklentiyi kaldır)

Bu yüzden görsel baytları Qt'ye verilmeden ÖNCE burada denetlenir: beyaz liste, bayt sınırı ve
başlıktan okunan piksel bütçesi.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

PNG_IMZA = b"\x89PNG\r\n\x1a\n"
JPEG_IMZA = b"\xff\xd8\xff"
RIFF_IMZA = b"RIFF"
WEBP_IMZA = b"WEBP"

#: Qt'ye verilmesine izin verilen biçimler (biçim adı = QImageReader biçim adı)
IZINLI_BICIMLER = {"png": "PNG", "jpeg": "JPEG", "webp": "WEBP"}

#: Sessizce reddedilecek imzalar (teşhis metni için)
RED_IMZALARI = {
    b"GIF87a": "gif",
    b"GIF89a": "gif",
    b"%PDF": "pdf",
    b"II*\x00": "tiff",
    b"MM\x00*": "tiff",
}

METIN_ONEKLERI = (b"<?xml", b"<svg", b"<!DOCTYPE", b"<html", b"<HTML", b"<body")

#: Kabul edilen içerik türleri (gövde imzası ayrıca denetlenir — çift denetim)
IZINLI_ICERIK_TURLERI = {
    "",
    "application/octet-stream",
    "binary/octet-stream",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
}


@dataclass(frozen=True, slots=True)
class Karar:
    """Politika kararı."""

    kabul: bool
    sebep: str = ""
    bicim: str | None = None
    genislik: int = 0
    yukseklik: int = 0

    @property
    def piksel(self) -> int:
        return self.genislik * self.yukseklik


def bicim_tahmin(baytlar: bytes) -> str | None:
    if baytlar.startswith(PNG_IMZA):
        return "png"
    if baytlar.startswith(JPEG_IMZA):
        return "jpeg"
    if baytlar[:4] == RIFF_IMZA and baytlar[8:12] == WEBP_IMZA:
        return "webp"
    for imza, ad in RED_IMZALARI.items():
        if baytlar.startswith(imza):
            return ad
    return None


def _metin_gibi(baytlar: bytes) -> bool:
    bas = baytlar[:64].lstrip()
    return bas.startswith(METIN_ONEKLERI) or b"<svg" in baytlar[:512].lower()


def png_olcu(baytlar: bytes) -> tuple[int, int] | None:
    if len(baytlar) < 24 or not baytlar.startswith(PNG_IMZA) or baytlar[12:16] != b"IHDR":
        return None
    genislik, yukseklik = struct.unpack(">II", baytlar[16:24])
    return int(genislik), int(yukseklik)


def jpeg_olcu(baytlar: bytes) -> tuple[int, int] | None:
    if not baytlar.startswith(JPEG_IMZA):
        return None
    indeks, uzunluk = 2, len(baytlar)
    while indeks + 9 < uzunluk:
        if baytlar[indeks] != 0xFF:
            indeks += 1
            continue
        isaret = baytlar[indeks + 1]
        if isaret in (0xD8, 0x01) or 0xD0 <= isaret <= 0xD7:
            indeks += 2
            continue
        parca = struct.unpack(">H", baytlar[indeks + 2 : indeks + 4])[0]
        if isaret in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            yukseklik, genislik = struct.unpack(">HH", baytlar[indeks + 5 : indeks + 9])
            return int(genislik), int(yukseklik)
        indeks += 2 + parca
    return None


def webp_olcu(baytlar: bytes) -> tuple[int, int] | None:
    if baytlar[:4] != RIFF_IMZA or baytlar[8:12] != WEBP_IMZA or len(baytlar) < 30:
        return None
    parca = baytlar[12:16]
    if parca == b"VP8X":
        return 1 + int.from_bytes(baytlar[24:27], "little"), 1 + int.from_bytes(baytlar[27:30], "little")
    if parca == b"VP8 " and baytlar[23:26] == b"\x9d\x01\x2a":
        genislik = int.from_bytes(baytlar[26:28], "little") & 0x3FFF
        yukseklik = int.from_bytes(baytlar[28:30], "little") & 0x3FFF
        return genislik, yukseklik
    if parca == b"VP8L":
        bitler = int.from_bytes(baytlar[21:25], "little")
        return (bitler & 0x3FFF) + 1, ((bitler >> 14) & 0x3FFF) + 1
    return None


OLCU_OKUYUCULAR = {"png": png_olcu, "jpeg": jpeg_olcu, "webp": webp_olcu}


def dogrula(
    baytlar: bytes,
    *,
    en_buyuk_bayt: int = 8 * 1024 * 1024,
    en_buyuk_piksel: int = 4096 * 4096,
    icerik_turu: str = "",
) -> Karar:
    """Görsel baytlarını denetler; kabul edilmezse sebebi Türkçe döner."""
    if not baytlar:
        return Karar(False, "boş gövde")
    if len(baytlar) > en_buyuk_bayt:
        return Karar(False, f"görsel çok büyük: {len(baytlar)} > {en_buyuk_bayt} bayt")

    tur = (icerik_turu or "").split(";")[0].strip().lower()
    if "svg" in tur:
        return Karar(False, "SVG içerik türü reddedildi (CVE-2026-6210 sınıfı)")
    if tur.startswith("text/html"):
        return Karar(False, "HTML içerik reddedildi")
    if tur and tur not in IZINLI_ICERIK_TURLERI:
        return Karar(False, f"içerik türü izin listesinde değil: {tur}")

    if _metin_gibi(baytlar):
        return Karar(False, "metin/XML/SVG gövdesi reddedildi (CVE-2026-6210 sınıfı)")

    bicim = bicim_tahmin(baytlar)
    if bicim is None:
        return Karar(False, "tanınmayan görsel imzası")
    if bicim not in IZINLI_BICIMLER:
        return Karar(False, f"biçim izin listesinde değil: {bicim}")

    okuyucu = OLCU_OKUYUCULAR.get(bicim)
    olcu = okuyucu(baytlar) if okuyucu else None
    if olcu is None:
        return Karar(False, f"{bicim} ölçü başlığı okunamadı (bozuk dosya)")
    genislik, yukseklik = olcu
    if genislik <= 0 or yukseklik <= 0:
        return Karar(False, f"geçersiz ölçü: {genislik}x{yukseklik}")
    if genislik * yukseklik > en_buyuk_piksel:
        return Karar(
            False,
            f"piksel bütçesi aşıldı: {genislik * yukseklik} > {en_buyuk_piksel} ({genislik}x{yukseklik})",
        )
    return Karar(True, "kabul edildi", IZINLI_BICIMLER[bicim], genislik, yukseklik)
