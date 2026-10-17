"""Ortak test altyapısı: nöbet ekranı penceresi (offscreen) ve kayıt üreticileri."""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QApplication

from pharmacy_app import PharmacyApp

EKRAN_G, EKRAN_Y = 1920, 1080


def png_uret(genislik: int = 8, yukseklik: int = 8, veri: bool = True) -> bytes:
    """Geçerli, küçük bir PNG üretir (görsel güvenlik/gösterim testleri için)."""
    import struct
    import zlib

    def parca(tur: bytes, icerik: bytes) -> bytes:
        return struct.pack(">I", len(icerik)) + tur + icerik + struct.pack(">I", zlib.crc32(tur + icerik) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", genislik, yukseklik, 8, 2, 0, 0, 0)
    parcalar = [b"\x89PNG\r\n\x1a\n", parca(b"IHDR", ihdr)]
    if veri:
        satir = b"".join(b"\x00" + b"\x40\x80\xc0" * min(genislik, 64) for _ in range(min(yukseklik, 64)))
        parcalar.append(parca(b"IDAT", zlib.compress(satir)))
    parcalar.append(parca(b"IEND", b""))
    return b"".join(parcalar)


def zamanlayicilari_durdur(pencere: PharmacyApp) -> None:
    """Tüm uygulama sayaçlarını durdurur (testler adımları KENDİ sürer).

    `PharmacyApp` açılışta `timer_manager.start_all()` çağırır: kayan yazı 30 ms'de bir
    tetiklenir. Testler `scroll_ticker()`/`manage_loop()`/`update_display()`'i elle çağırdığı
    için arka planda çalışan sayaçlar adımları kaydırır ve testler zamana göre kırılgan olur
    (yük altında farklı sayıda tetik → beklenmedik durum).
    """
    tm = pencere.timer_manager
    tm.data_timer.stop()
    tm.cycle_timer.stop()
    tm.clock_timer.stop()
    tm.ticker_timer.stop()


@pytest.fixture()
def pencere(qapp, monkeypatch):
    """Kapanışta temizlenen PharmacyApp fabrikası (1080p, tam ekran değil)."""
    pencereler: list[PharmacyApp] = []

    def uret() -> PharmacyApp:
        p = PharmacyApp(tam_ekran=False)
        p.resize(EKRAN_G, EKRAN_Y)
        zamanlayicilari_durdur(p)
        pencereler.append(p)
        return p

    yield uret
    for p in pencereler:
        p.close()


def kayit_uret(i: int, bolge: str | None = None) -> dict:
    """Sol panel testleri için asgari nöbet kaydı."""
    return {
        "eczane": f"ECZANE {i}",
        "tel": "0262 000 00 00",
        "adres": "TEST",
        "adres_tarifi": "",
        "bolge": bolge or f"B{i}",
        "ilce": "TEST",
        "baslangic": "",
        "bitis": "",
    }


def paneli_kur(pencere: PharmacyApp, n: int) -> list[int]:
    """Sol paneli `n` kayıtla kurar; çerçeve yüksekliklerini döner.

    Test ortamı gerçek kiosk gibi davransın diye pencere 1080p'ye-normalize edilir:
    satır yüksekliği `screen_h`'den hesaplandığı için ölçülerin örtüşmesi gerekir
    (offscreen ekran 768 px olabilir). `show()` şart: kaydırma alanının görünür
    yüksekliği (ve kaydırma aralığı) ancak gerçek yerleşim hesabıyla oluşur.
    """
    pencere.screen_w, pencere.screen_h = EKRAN_G, EKRAN_Y
    pencere.scale = 1.0
    pencere.show()
    QApplication.processEvents()
    pencere.data_handler.pharmacies = [kayit_uret(i) for i in range(n)]
    pencere.setup_left_panel()
    QApplication.processEvents()
    return [cerceve.height() for _ad, _tel, cerceve in pencere.pharmacy_widgets]
