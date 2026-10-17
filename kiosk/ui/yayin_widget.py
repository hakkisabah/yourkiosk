from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame, QSizePolicy
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt

import config


class YayinWidget(QWidget):
    """Yayın görseli (tam ekran) + ÜSTÜNE bindirilmiş kırmızı kuşak.

    Kuşak yerleşime eklenmez; yayın görselinin üzerinde yüzen bir katmandır
    (`raise_()`), böylece görsel tam ekran kalır, yazı da onun üstünden geçer —
    kuşağın altında boş/alakasız bir arka plan görünmez.

    Yükseklik, ekranın alt kenarından yukarıda kalacağı boşluk ve punto
    `config.py` içindeki KUSAK_* değerlerinden okunur (1080p için verilir,
    `scale` ile ölçeklenir).
    """

    def __init__(self, app_instance):
        super().__init__()
        self.app_instance = app_instance
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Görsel Alanı — tam ekran (kuşak bunun üstüne biner)
        self.img_lbl = QLabel()
        self.img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_lbl.setStyleSheet("background-color: black;")
        self.img_lbl.setScaledContents(True)
        self.img_lbl.setMinimumHeight(1)
        self.img_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.layout.addWidget(self.img_lbl, 1)

        # Alt Kaya Yazı Şeridi (Kırmızı) — görselin ÜSTÜNDE yüzer
        self.ticker_strip = QFrame(self)
        self.ticker_strip.setFixedHeight(
            int(getattr(config, "KUSAK_YUKSEKLIK", 60) * app_instance.scale)
        )
        self.ticker_strip.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.ticker_strip.setStyleSheet("background-color: #c8102e; border: none;")

        self.ticker_label = QLabel(self.ticker_strip)
        self.ticker_label.setStyleSheet("color: white; background: transparent; border: none;")
        self.ticker_label.setFont(
            QFont(
                "Arial",
                int(getattr(config, "KUSAK_YAZI_PUNTO", 28) * app_instance.scale),
                QFont.Weight.Bold,
            )
        )
        self.ticker_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.kusagi_yerlestir()

    # ------------------------------------------------------------------ #
    @property
    def alt_bosluk(self) -> int:
        """Kuşağın ekranın alt kenarından yukarıda kalacağı boşluk (px)."""
        return int(getattr(config, "KUSAK_ALT_BOSLUK", 0) * self.app_instance.scale)

    def kusagi_goster(self, goster: bool) -> None:
        """Kuşağı (kırmızı şerit + kayan yazı) göster/gizle.

        `ozellikler.kayan_yazi = false` olan kurulumlarda kuşak hiç görünmez.
        Gizlemek yerleşimi değiştirmez: şerit zaten görselin üstüne bindirilmiş
        bağımsız bir katmandır.
        """
        self.ticker_strip.setVisible(bool(goster))
        if goster:
            self.kusagi_yerlestir()

    def kusagi_yerlestir(self) -> None:
        """Kuşağı tam genişlikte, alt boşluğu bırakacak şekilde konumlandırır."""
        y = max(0, self.height() - self.alt_bosluk - self.ticker_strip.height())
        self.ticker_strip.setGeometry(0, y, self.width(), self.ticker_strip.height())
        self.ticker_strip.raise_()  # yayın görselinin üstünde kalsın

    def resizeEvent(self, olay):  # noqa: N802 (Qt adı)
        super().resizeEvent(olay)
        self.kusagi_yerlestir()

    def showEvent(self, olay):  # noqa: N802 (Qt adı)
        super().showEvent(olay)
        self.kusagi_yerlestir()
