import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt
from components.right_content_block import create_right_content_block
import config

class NobetWidget(QWidget):
    """Mevcut nöbetçi ekranı düzenini barındıran bağımsız widget."""
    def __init__(self, app_instance):
        super().__init__()
        self.app_instance = app_instance
        self.active_block_idx = 0
        
        # Orijinal background-color: white buraya taşındı
        self.setStyleSheet("background-color: white;")
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop) # Ana layout'u en üste hizala

        # SOL PANEL
        self.left_panel = QFrame()
        self.left_panel.setFixedWidth(int(app_instance.screen_w * 0.26))
        self.left_layout = QVBoxLayout(self.left_panel)
        self.left_layout.setSpacing(int(10 * app_instance.scale))
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        self.left_layout.setAlignment(Qt.AlignmentFlag.AlignTop) # Hizalamayı en üste sabitle
        self.layout.addWidget(self.left_panel)

        # DİKEY ÇİZGİ
        self.v_line = QFrame()
        self.v_line.setFixedWidth(int(3 * app_instance.scale))
        self.v_line.setStyleSheet("background-color: #c8102e;")
        self.layout.addWidget(self.v_line)

        # SAĞ PANEL
        self.right_panel = QWidget()
        self.right_vbox = QVBoxLayout(self.right_panel)
        self.right_vbox.setContentsMargins(0, 0, 0, 0)
        self.right_vbox.setSpacing(0)
        self.layout.addWidget(self.right_panel)

        # KUŞAK (Sabit)
        self.ribbon_area = QFrame()
        self.ribbon_area.setFixedHeight(int(125 * app_instance.scale))
        self.ribbon_area.setStyleSheet(f"QFrame {{ border-image: url({os.path.join(config.BG_PATH, 'kusak.png').replace('\\','/')}) 0 0 0 0 stretch stretch; border: none; }}")
        self.right_vbox.addWidget(self.ribbon_area)

        # VIEWPORT
        self.viewport = QWidget()
        self.viewport.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.right_vbox.addWidget(self.viewport)

        # İKİ AYRI İÇERİK BLOĞU
        self.ui_blocks = [
            create_right_content_block(self, self.viewport),
            create_right_content_block(self, self.viewport)
        ]
        self.ui_blocks[1]["widget"].move(0, -2000)
