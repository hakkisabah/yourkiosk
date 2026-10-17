import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
)
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtCore import Qt
import config

def create_right_content_block(nobet_widget, parent):
    """Mevcut stil ve yerleşimi koruyarak bir içerik bloğu oluşturur."""
    app_instance = nobet_widget.app_instance
    content = QWidget(parent)
    # Sağ panel genişliği ve yüksekliği (Kuşak hariç)
    w = app_instance.screen_w - int(app_instance.screen_w * 0.26) - int(3 * app_instance.scale)
    h = app_instance.screen_h - int(125 * app_instance.scale)
    content.setFixedSize(w, h)
    
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    # 1. TARİH ARALIĞI
    date_range_lbl = QLabel("-")
    date_range_lbl.setFixedHeight(int(45 * app_instance.scale))
    date_range_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    date_range_lbl.setFont(QFont("Arial", int(20 * app_instance.scale), QFont.Weight.Bold))
    date_range_lbl.setStyleSheet("color: #c8102e; background: transparent;")
    layout.addWidget(date_range_lbl)

    # 2. DETAY KUTUSU
    detail_frame = QFrame()
    detail_frame.setObjectName("detailFrame")
    detail_frame.setFixedHeight(int(480 * app_instance.scale))
    detail_frame.setStyleSheet("""
        QFrame#detailFrame {
            border-top: 3px solid #c8102e;
            background-color: #f5e8c7;
        }
    """)
    detail_layout = QVBoxLayout(detail_frame)
    detail_layout.setContentsMargins(5, 5, 5, 5)
    detail_layout.setSpacing(10)
    detail_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

    big_name_lbl = QLabel("-")
    big_name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    big_name_lbl.setFont(QFont("Arial", int(65 * app_instance.scale), QFont.Weight.Bold))
    big_name_lbl.setStyleSheet("color: #c8102e; border: none; background-color: #f5e8c7;")
    big_name_lbl.setWordWrap(True)
    
    address_lbl = QLabel("-")
    address_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    address_lbl.setFont(QFont("Arial", int(30 * app_instance.scale), QFont.Weight.Bold))
    address_lbl.setWordWrap(True)
    address_lbl.setStyleSheet("color: black; border: none; background-color: #f5e8c7;")
    
    big_phone_lbl = QLabel("-")
    big_phone_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    big_phone_lbl.setFont(QFont("Arial", int(90 * app_instance.scale), QFont.Weight.Bold))
    big_phone_lbl.setStyleSheet("color: #c8102e; border: none; background-color: #f5e8c7;")

    detail_layout.addWidget(big_name_lbl)
    detail_layout.addWidget(address_lbl)
    detail_layout.addWidget(big_phone_lbl)
    layout.addWidget(detail_frame)

    layout.addStretch(1)

    # 3. ALT PANEL (Logo ve Saat)
    bottom_widget = QWidget()
    bottom_widget.setFixedHeight(int(640 * app_instance.scale))
    bottom_layout = QHBoxLayout(bottom_widget)
    bottom_layout.setContentsMargins(0, 0, 0, 0)
    bottom_layout.setSpacing(0)

    h_line = QFrame()
    h_line.setFixedHeight(int(3 * app_instance.scale))
    h_line.setStyleSheet("background-color: #c8102e;")
    layout.addWidget(h_line)
    layout.addWidget(bottom_widget)

    # Logo Alanı
    logo_container = QFrame()
    logo_container.setFixedWidth(int(app_instance.screen_w * 1.15 * 0.54))
    logo_vbox = QVBoxLayout(logo_container)
    logo_lbl = QLabel()
    logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    pix = QPixmap(config.LOGO_PATH)
    if not pix.isNull():
        logo_lbl.setPixmap(pix.scaled(int(330 * app_instance.scale), int(330 * app_instance.scale), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
    logo_vbox.addWidget(logo_lbl)
    bottom_layout.addWidget(logo_container)

    # Saat Alanı
    time_container = QFrame()
    time_container.setStyleSheet("background-color: #f5e8c7; border-left: 3px solid #c8102e; border-right: 3px solid #c8102e; border-bottom: 3px solid #c8102e;")
    time_vbox = QVBoxLayout(time_container)
    time_vbox.setAlignment(Qt.AlignmentFlag.AlignTop)
    time_vbox.setSpacing(20)

    time_lbl = QLabel("")
    time_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    time_lbl.setFont(QFont("Arial", int(50 * app_instance.scale), QFont.Weight.Bold))
    time_lbl.setStyleSheet("color: black; border: none;")
    
    date_lbl = QLabel("")
    date_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    date_lbl.setFont(QFont("Arial", int(20 * app_instance.scale), QFont.Weight.Bold))
    date_lbl.setStyleSheet("color: black; border: none;")
    
    day_lbl = QLabel("")
    day_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    day_lbl.setFont(QFont("Arial", int(20 * app_instance.scale), QFont.Weight.Bold))
    day_lbl.setStyleSheet("color: black; border: none;")

    time_vbox.addWidget(time_lbl)
    time_vbox.addWidget(date_lbl)
    time_vbox.addWidget(day_lbl)
    bottom_layout.addWidget(time_container)

    return {
        "widget": content,
        "date_range_lbl": date_range_lbl,
        "big_name_lbl": big_name_lbl,
        "address_lbl": address_lbl,
        "big_phone_lbl": big_phone_lbl,
        "time_lbl": time_lbl,
        "date_lbl": date_lbl,
        "day_lbl": day_lbl
    }
