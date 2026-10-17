"""Politika denetimli Qt görsel çözme (tek kapı).

Akış: bayt -> image_policy.dogrula (beyaz liste + bayt + piksel) -> QImageReader
(biçim sabitlenir, içerikten tahmin kapatılır) -> QPixmap.
Denetim başarısızsa Qt'ye hiç dokunulmaz.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QBuffer, QByteArray, QSize, Qt
from PyQt6.QtGui import QImage, QImageReader, QPixmap

from security.image_policy import Karar, dogrula

log = logging.getLogger("kiosk.guvenli_gorsel")

#: Qt'nin toplam ayırma bütçesi (MB) — politikaya ek ikinci savunma
AYIRMA_LIMITI_MB = 64


def ayirma_limitini_ayarla(limit_mb: int = AYIRMA_LIMITI_MB) -> None:
    try:
        QImageReader.setAllocationLimit(limit_mb)
    except (AttributeError, TypeError):  # eski Qt sürümleri
        log.debug("setAllocationLimit desteklenmiyor")


def piksel_yukle(
    baytlar: bytes,
    *,
    en_buyuk_bayt: int = 8 * 1024 * 1024,
    en_buyuk_piksel: int = 4096 * 4096,
    icerik_turu: str = "",
) -> tuple[QPixmap | None, Karar]:
    """Doğrulanmış baytları QPixmap'e çevirir. (pixmap|None, karar) döner."""
    karar = dogrula(
        baytlar, en_buyuk_bayt=en_buyuk_bayt, en_buyuk_piksel=en_buyuk_piksel, icerik_turu=icerik_turu
    )
    if not karar.kabul:
        log.warning("görsel reddedildi: %s", karar.sebep)
        return None, karar

    # QByteArray referansı fonksiyon boyunca canlı tutulmalı:
    # QBuffer(QByteArray()) geçici nesneyle SIGSEGV üretir.
    tampon_baytlari = QByteArray(baytlar)
    tampon = QBuffer(tampon_baytlari)
    if not tampon.open(QBuffer.OpenModeFlag.ReadOnly):
        return None, Karar(False, "tampon açılamadı")

    okuyucu = QImageReader(tampon)
    okuyucu.setDecideFormatFromContent(False)  # biçim kararı politikada verildi
    okuyucu.setFormat(QByteArray((karar.bicim or "").encode("ascii")))
    olcu = okuyucu.size()
    if olcu.isValid() and olcu.width() * olcu.height() > en_buyuk_piksel:
        return None, Karar(False, f"çözücü ölçüsü bütçeyi aşıyor: {olcu.width()}x{olcu.height()}")

    goruntu = QImage()
    if not okuyucu.read(goruntu) or goruntu.isNull():
        return None, Karar(False, f"Qt çözemedi: {okuyucu.errorString()}")
    return QPixmap.fromImage(goruntu), karar


def pixsel_sigdir(pixmap: QPixmap, genislik: int, yukseklik: int) -> QPixmap:
    """Oranı koruyarak hedef alana sığdırır."""
    if genislik <= 0 or yukseklik <= 0:
        return pixmap
    return pixmap.scaled(
        QSize(genislik, yukseklik), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
    )
