"""Güvenlik katmanı testleri: görsel politikası + sınırlandırılmış ağ erişimi."""

from __future__ import annotations

import struct
import zlib

import pytest

from security.image_policy import bicim_tahmin, dogrula
from security.network import AgAyarlari, AgHatasi, indir

# ------------------------------------------------------------ test görselleri
def png_uret(genislik: int = 8, yukseklik: int = 8, veri: bool = True) -> bytes:
    def parca(tur: bytes, icerik: bytes) -> bytes:
        return struct.pack(">I", len(icerik)) + tur + icerik + struct.pack(">I", zlib.crc32(tur + icerik) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", genislik, yukseklik, 8, 2, 0, 0, 0)
    parcalar = [b"\x89PNG\r\n\x1a\n", parca(b"IHDR", ihdr)]
    if veri:
        satir = b"".join(b"\x00" + b"\x40\x80\xc0" * min(genislik, 64) for _ in range(min(yukseklik, 64)))
        parcalar.append(parca(b"IDAT", zlib.compress(satir)))
    parcalar.append(parca(b"IEND", b""))
    return b"".join(parcalar)


def jpeg_uret(genislik: int = 8, yukseklik: int = 8) -> bytes:
    sof0 = b"\xff\xc0" + struct.pack(">HBHHB", 17, 8, yukseklik, genislik, 3) + b"\x01\x11\x00\x02\x11\x00\x03\x11\x00"
    return b"\xff\xd8" + sof0 + b"\xff\xd9"


def svg_uret(marker_saldirisi: bool = True) -> bytes:
    govde = '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
    if marker_saldirisi:
        govde += '<line id="m" x1="0" y1="0" x2="10" y2="10" marker-end="url(#m)"/>'
    return (govde + "</svg>").encode()


# ----------------------------------------------------------------- politikalar
def test_gecerli_png_ve_jpeg_kabul_edilir() -> None:
    png = dogrula(png_uret(64, 48))
    assert png.kabul and png.bicim == "PNG" and (png.genislik, png.yukseklik) == (64, 48)
    jpg = dogrula(jpeg_uret(300, 200))
    assert jpg.kabul and jpg.bicim == "JPEG" and (jpg.genislik, jpg.yukseklik) == (300, 200)


@pytest.mark.parametrize(
    "baytlar",
    [
        svg_uret(True),  # CVE-2026-6210 tetikleyici deseni
        svg_uret(False),
        b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"/>',
        b"  \n<svg xmlns='x'/>",
        b"<html><body>x</body></html>",
    ],
)
def test_svg_ve_xml_reddedilir(baytlar: bytes) -> None:
    sonuc = dogrula(baytlar)
    assert not sonuc.kabul
    assert "reddedildi" in sonuc.sebep or "izin" in sonuc.sebep


def test_svg_content_type_ile_gizlenen_png_reddedilir() -> None:
    sonuc = dogrula(png_uret(8, 8), icerik_turu="image/svg+xml; charset=utf-8")
    assert not sonuc.kabul and "SVG" in sonuc.sebep


@pytest.mark.parametrize(
    ("baytlar", "etiket"),
    [
        (b"GIF89a" + b"\x00" * 20, "gif"),
        (b"%PDF-1.7\n" + b"\x00" * 20, "pdf"),
        (b"II*\x00" + b"\x00" * 40, "tiff"),
    ],
)
def test_izin_listesinde_olmayan_bicimler(baytlar: bytes, etiket: str) -> None:
    sonuc = dogrula(baytlar)
    assert not sonuc.kabul and etiket in sonuc.sebep


def test_bilinmeyen_imza_ve_bos_govde() -> None:
    assert not dogrula(b"\x00\x01\x02\x03" * 50).kabul
    assert dogrula(b"").sebep == "boş gövde"


def test_bayt_siniri() -> None:
    sonuc = dogrula(png_uret(256, 256), en_buyuk_bayt=64)
    assert not sonuc.kabul and "çok büyük" in sonuc.sebep


def test_piksel_butcesi_basliktan_yakalanir() -> None:
    bomba = png_uret(20000, 20000, veri=False)
    assert len(bomba) < 200  # gerçek görsel verisi yok, yalnızca başlık
    sonuc = dogrula(bomba, en_buyuk_piksel=4096 * 4096)
    assert not sonuc.kabul and "piksel bütçesi" in sonuc.sebep


def test_bozuk_dosya_reddedilir() -> None:
    assert not dogrula(png_uret(8, 8)[:16]).kabul
    assert not dogrula(b"\xff\xd8\xff" + b"\x00" * 10).kabul
    assert not dogrula(png_uret(0, 10, veri=False)).kabul


def test_bicim_tahmin() -> None:
    assert bicim_tahmin(png_uret()) == "png"
    assert bicim_tahmin(jpeg_uret()) == "jpeg"
    assert bicim_tahmin(svg_uret()) is None


# ------------------------------------------------------------------- ağ katmanı
def test_https_zorunlu_ve_izin_listesi() -> None:
    ayarlar = AgAyarlari(izinli_hostlar=("hakkisabah.com",))
    assert ayarlar.host_izinli("https://hakkisabah.com/api/x.png")
    assert not ayarlar.host_izinli("http://hakkisabah.com/api/x.png")  # şema https değil
    assert not ayarlar.host_izinli("https://kotu.example/x.png")
    assert not ayarlar.host_izinli("file:///etc/passwd")


def test_izin_listesi_disi_indirme_engellenir() -> None:
    with pytest.raises(AgHatasi, match="izin listesinde"):
        indir("https://kotu.example/x.png", AgAyarlari(izinli_hostlar=("hakkisabah.com",)))
