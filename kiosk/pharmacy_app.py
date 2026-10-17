import logging
import os

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QFrame, QVBoxLayout, QLabel, QStackedWidget,
    QScrollArea, QWidget,
)
from PyQt6.QtGui import QFont, QShortcut, QKeySequence, QPixmap, QImage
from PyQt6.QtCore import Qt, QLocale, QDateTime, QPropertyAnimation, QEasingCurve, QTimer

import config
import ayarlar
import utils
from security.network import AgAyarlari, AgHatasi, indir
from security.safe_image import ayirma_limitini_ayarla, piksel_yukle
from security.veri_dogrulama import sayi_sinirla
from ui.nobet_widget import NobetWidget
from ui.yayin_widget import YayinWidget
from core.data_handler import DataHandler
from core.broadcast_manager import BroadcastManager
from core import onbellek
from core import tetik as tetik_modulu
from core import komut as komut_modulu
from core import veri_kaynagi
from core.timer_manager import TimerManager
from core.animation_handler import AnimationHandler
from core.ticker import KusakAnimasyonu

log = logging.getLogger("kiosk.uygulama")


class PharmacyApp(QMainWindow):
    def __init__(self, tam_ekran=True):
        super().__init__()
        ayirma_limitini_ayarla()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        
        screen = QApplication.primaryScreen().availableGeometry()
        self.screen_w = screen.width()
        self.screen_h = screen.height()
        self.scale = self.screen_h / 1080.0
        if tam_ekran:
            self.showFullScreen()

        # Durum Değişkenleri
        self.current_index = 0
        self.pharmacy_widgets = []
        self.is_broadcast_mode = False
        #: Son uygulanan nöbet değişikliği tetikleyicisinin zamanı (aynısı tekrar uygulanmaz)
        self._son_tetik = ""
        self.ticker_x = self.screen_w
        self.ticker_items = []
        self.ticker_index = 0
        # Kuşak animasyonu: sağdan ortaya → dur → soldan çık (nöbet geçişiyle aynı his)
        self.kusak_animasyonu = KusakAnimasyonu(
            giris_ms=getattr(config, "KUSAK_GIRIS_MS", 900),
            durma_ms=getattr(config, "KUSAK_DURMA_MS", 3000),
            cikis_ms=getattr(config, "KUSAK_CIKIS_MS", 900),
            adim_ms=getattr(config, "KUSAK_ADIM_ARALIGI_MS", 30),
        )

        # Bileşenler (Managers)
        self.data_handler = DataHandler()
        self.broadcast_manager = BroadcastManager(self)
        self.animation_handler = AnimationHandler(self)
        
        # UI Kurulumu
        self.setup_ui()
        
        # Zamanlayıcılar
        self.timer_manager = TimerManager(self)
        # Kayan yazı adım aralığı (config'ten; varsayılan referans değeri 30 ms)
        self.timer_manager.ticker_timer.setInterval(getattr(config, "KUSAK_ADIM_ARALIGI_MS", 30))

        self.load_data()
        self.update_clock()
        self.timer_manager.start_all()

        # Kısayollar
        QShortcut(QKeySequence("Ctrl+Q"), self).activated.connect(QApplication.quit)
        QShortcut(QKeySequence("Esc"), self).activated.connect(QApplication.quit)

    def setup_ui(self):
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.nobet_widget = NobetWidget(self)
        self.yayin_widget = YayinWidget(self)

        self.stack.addWidget(self.nobet_widget)
        self.stack.addWidget(self.yayin_widget)

    def load_data(self, zorla: bool = False):
        """Veriyi yükler. `zorla=True` → damga değişmemiş olsa da yenilenir (tetikleyici yolu)."""
        if self.data_handler.load_data(zorla=zorla):
            self.setup_left_panel()
            self.prepare_ticker_text()
            if not self.is_broadcast_mode:
                # Eğer eczane listesi değiştiyse veya ilk yükleme ise ekranı güncelle
                # Basitlik için her yüklemede değil, sadece mod değişmediyse güncelliyoruz
                self.update_display()

    def tetik_kontrol(self):
        """NÖBET DEĞİŞİKLİĞİNİ BEKLEMEDEN yansıt (panel tetikleyicisi ya da damga değişikliği).

        Saatlik `data_timer`'a EK olarak `DAMGA_KONTROL_MS` (varsayılan 20 sn) ile çalışır ve
        yalnızca KÜÇÜK dosyaları okur (`lastupdate.json`, `tetikle.json`, `komut.json`); büyük veri
        dosyası damga değişmedikçe indirilmez:
          · `lastupdate` damgası değiştiyse → veri yenilenir,
          · panelin yazdığı tetikleyici bu cihazı ilgilendiriyorsa → veri yenilenir
            (`core/tetik.uygulanmali`: tüm cihazlar / kendi ilçesi / kendi bölgesi),
          · uzaktan komut varsa (imzalı, beyaz listede) uygulanır (`core/komut.py`).
        """
        # UZAKTAN KOMUT + küçük dosya senkronu (her turda; hızlı ve ucuz)
        self.uzak_kontrol()

        try:
            damga = veri_kaynagi.lastupdate_taze()
        except Exception:  # noqa: BLE001 - denetim hatası gösterimi durdurmamalı
            log.warning("damga denetimi yapılamadı", exc_info=True)
            damga = ""
        onceki = str(getattr(self.data_handler, "lastupdate", "") or "")
        if damga and onceki and damga != onceki:
            log.info("nöbet verisi değişti (damga %s → %s) → hemen yenileniyor", onceki, damga)
            self.load_data()
            return

        tetik = tetik_modulu.oku()
        konum = getattr(self.data_handler, "konum", None)
        ilce = str(getattr(konum, "ilce_id", "") or "")
        bolge = str(getattr(konum, "bolge_id", "") or "")
        if tetik and tetik_modulu.uygulanmali(tetik, ilce, bolge, self._son_tetik):
            self._son_tetik = str(tetik.get("zaman", ""))
            kapsam = tetik.get("ilceId") or "tüm cihazlar"
            log.info("tetikleyici uygulanıyor (%s · kapsam=%s) → hemen yenileniyor", tetik.get("zaman"), kapsam)
            self.load_data(zorla=True)

    def uzak_kontrol(self):
        """Küçük kontrol dosyalarını sunucudan tazeler ve UZAKTAN KOMUT varsa uygular.

        Fazladan güvenlik katmanları `core/komut.py` içindedir: beyaz liste, HMAC imza (fail-closed),
        hedef cihaz, tek seferlik uygulama ve sabit argv (kabuk yok). Komut uygulandığında günlüğe
        yazılır; `ekrani-yenile` ise ekran kendi içinde tazelenir.
        """
        try:
            tetik_modulu.getir()
            komut_modulu.getir()
        except Exception:  # noqa: BLE001 - indirme hatası gösterimi etkilememeli
            log.warning("uzak kontrol dosyaları alınamadı", exc_info=True)

        try:
            _karar, sonuc = komut_modulu.kontrol(cihaz_id=self.cihaz_kimligi())
        except Exception:  # noqa: BLE001
            log.warning("uzaktan komut denetimi yapılamadı", exc_info=True)
            return
        if sonuc is None:
            return
        log.warning("UZAKTAN KOMUT: %s", komut_modulu.sonuc_metni(sonuc))
        if sonuc.uygulama_ici:
            self.update_display()  # ekranı tazele (Qt içi karşılık)
            log.info("ekran tazelendi (uzaktan komut)")

    def cihaz_kimligi(self) -> str:
        """Bu cihazın kimliği (`makinebilgileri.json` → clientID)."""
        try:
            return str(veri_kaynagi.client_id() or "").strip()
        except Exception:  # noqa: BLE001
            return ""

    @property
    def pharmacies(self):
        return self.data_handler.pharmacies

    @property
    def yayinlar(self):
        return self.data_handler.yayinlar

    def setup_left_panel(self):
        layout = self.nobet_widget.left_layout
        self._sol_kaydirmayi_durdur()
        # Temizlik
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self.pharmacy_widgets = []
        self._sol_kaydirma_alani = None
        self._sol_kaydirma_sayfa = 0
        count = len(self.pharmacies)
        if count == 0: return

        m = layout.contentsMargins()
        # Satır yüksekliği HER ZAMAN sabit bir taban sayıya göre hesaplanır: az nöbetçi
        # varsa çerçeveler BÜYÜMEZ, çok nöbetçi varsa KÜÇÜLMEZ (5 kişilik referans
        # görünüm korunur). Tabanı aşan kayıtlar için panel kaydırılabilir olur:
        # ilk `taban` kayıt görünür, kalanlar aşağı kaydırılarak gösterilir.
        taban = max(1, int(getattr(config, "MAKS_GORUNUR_SATIR", 5)))
        available_h = self.screen_h - m.top() - m.bottom() - (layout.spacing() * (taban - 1))
        item_h = int(available_h / taban)

        hedef_yerlesim = layout
        if count > taban:
            hedef_yerlesim, self._sol_kaydirma_alani = self._sol_kaydirma_kabini_olustur(layout)
            log.info(
                "sol panelde %d kayıt var (taban %d): kaydırma etkin "
                "(ilk %d görünür, kalanlar sırayla; satır yüksekliği %d px korunur)",
                count, taban, taban, item_h,
            )

        box_path = os.path.join(config.BG_PATH, "box.png").replace("\\", "/")

        for i in range(count):
            frame = QFrame()
            frame.setObjectName(f"pharmacyFrame_{i}")
            frame.setFixedHeight(item_h)
            frame.setStyleSheet(f"QFrame#pharmacyFrame_{i} {{ border-image: url({box_path}) 0 0 0 0 stretch stretch; border: none; }}")
            
            flayout = QVBoxLayout(frame)
            flayout.setContentsMargins(int(10 * self.scale), 0, int(10 * self.scale), 0)
            flayout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            name = QLabel("-")
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name.setFont(QFont("Arial", int(30 * self.scale), QFont.Weight.Bold))
            name.setStyleSheet("background: transparent; color: black; border: none;")
            name.setWordWrap(True)
            
            phone = QLabel("-")
            phone.setAlignment(Qt.AlignmentFlag.AlignCenter)
            phone.setFont(QFont("Arial", int(35 * self.scale), QFont.Weight.Bold))
            phone.setStyleSheet("background: transparent; color: black; border: none;")

            flayout.addWidget(name)
            flayout.addWidget(phone)
            hedef_yerlesim.addWidget(frame)
            self.pharmacy_widgets.append((name, phone, frame))

        if self._sol_kaydirma_alani is not None:
            # Yeni liste: başa al ve vurgulanan satırı (current_index) görünür yap.
            icerik = self._sol_kaydirma_alani.widget()
            if icerik is not None and icerik.layout() is not None:
                icerik.layout().activate()
            self._sol_kaydirma_alani.verticalScrollBar().setValue(0)
            self._sol_aktifi_gorunur_yap(animasyonsuz=True)

    # ------------------------------------------------------ sol panel kaydırma
    def _sol_kaydirma_kabini_olustur(self, layout):
        """Taban satırdan fazla kayıt varsa çerçeveleri kaydırılabilir alana taşır.

        Yalnızca kaydırma çubuğu biçimlendirilir (genişlik/renkler `config` içinde);
        çerçevelerin görünümü, puntolar ve oranlar DEĞİŞMEZ.
        """
        genislik = int(getattr(config, "SOL_PANEL_KAYDIRMA_CUBUGU_GENISLIK", 12))
        ray = str(getattr(config, "SOL_PANEL_KAYDIRMA_CUBUGU_RENK", "#d9dee5"))
        tutamak = str(getattr(config, "SOL_PANEL_KAYDIRMA_TUTAMAK_RENK", "#6b7280"))
        self._sol_kaydirma_bosluk = int(layout.spacing())

        icerik = QWidget()
        icerik.setObjectName("solPanelIcerik")
        icerik_layout = QVBoxLayout(icerik)
        icerik_layout.setSpacing(layout.spacing())
        icerik_layout.setContentsMargins(0, 0, 0, 0)
        icerik_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        alan = QScrollArea()
        alan.setObjectName("solPanelKaydirma")
        alan.setFrameShape(QFrame.Shape.NoFrame)
        alan.setWidgetResizable(True)
        alan.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        alan.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded if genislik > 0 else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        alan.setStyleSheet("QScrollArea#solPanelKaydirma { background: transparent; border: none; }")
        alan.setWidget(icerik)

        # Kaydırma çubuğu (slider) YALNIZCA kendi stilini alır; diğer widget'lar etkilenmez.
        bar = alan.verticalScrollBar()
        bar.setStyleSheet(
            f"""
            QScrollBar:vertical {{ background: {ray}; width: {genislik}px; margin: 0px; border: none; }}
            QScrollBar::handle:vertical {{ background: {tutamak}; min-height: 40px; border-radius: {max(1, genislik // 2)}px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; border: none; background: transparent; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
            """
        )
        layout.addWidget(alan, 1)
        return icerik_layout, alan

    def sol_kaydirma_hedefi(self, indeks: int | None = None) -> int:
        """Vurgulanan nöbetçinin görünmesi için gereken kaydırma konumu (px).

        Kural: aktif satır görünür alandaysa kaydırma YAPILMAZ; satır alttan taşarsa
        (yani "listenin en aşağısına geldiğinde") panel o satırı içine alacak kadar
        aşağı kayar. Sürekli değil, yalnızca gerektiğinde hareket eder.
        """
        alan = getattr(self, "_sol_kaydirma_alani", None)
        if alan is None or not self.pharmacy_widgets:
            return 0
        bar = alan.verticalScrollBar()
        en_buyuk = max(0, int(bar.maximum()))
        if en_buyuk <= 0:
            return 0

        icerik = alan.widget()
        if icerik is not None and icerik.layout() is not None:
            icerik.layout().activate()  # yerleşim hesaplanmamışsa hemen hesaplansın

        indeks = self.current_index if indeks is None else indeks
        indeks = max(0, min(int(indeks), len(self.pharmacy_widgets) - 1))
        y, yukseklik = self._sol_satir_konumu(indeks)
        konum = int(bar.value())
        gorunur = int(alan.viewport().height())

        if y < konum:
            hedef = y  # satır yukarıda kaldı
        elif y + yukseklik > konum + gorunur:
            hedef = y + yukseklik - gorunur  # satır alttan taştı → aşağı kaydır
        else:
            hedef = konum  # görünür: dokunma
        return max(0, min(int(hedef), en_buyuk))

    def _sol_satir_konumu(self, indeks: int) -> tuple[int, int]:
        """(y, yükseklik): satırın kaydırılabilir içerikteki konumu.

        Yerleşim henüz hesaplanmadıysa (tüm satırlar 0'da) aritmetikle bulunur:
        tüm satırlar eşit yükseklikte olduğundan `indeks * (yükseklik + boşluk)`.
        """
        cerceve = self.pharmacy_widgets[indeks][2]
        yukseklik = int(cerceve.height())
        y = int(cerceve.y())
        if y == 0 and indeks > 0:
            bosluk = int(getattr(self, "_sol_kaydirma_bosluk", 0))
            y = indeks * (yukseklik + bosluk)
        return y, yukseklik

    def _sol_kaydirma_animasyonu(self):
        """Kaydırma için TEK animasyon nesnesi (yoksa oluşturur).

        Nesne yeniden kullanılır ve `DeleteWhenStopped` KULLANILMAZ: aksi hâlde
        animasyon bitince C++ nesnesi silinir, elimizdeki Python referansı ölü kalır ve
        bir sonraki kaydırmada `.stop()` çağrısı
        "wrapped C/C++ object of type QPropertyAnimation has been deleted" hatası atar
        (bu hata Qt olay döngüsünde yükseldiği için uygulamada kaydırma sessizce bozulur).
        """
        anim = getattr(self, "_sol_kaydirma_anim", None)
        if anim is not None:
            try:
                anim.stop()
                return anim
            except RuntimeError:  # nesne silinmiş (beklenmez) → yeniden oluştur
                self._sol_kaydirma_anim = None
        alan = getattr(self, "_sol_kaydirma_alani", None)
        if alan is None:
            return None
        anim = QPropertyAnimation(alan.verticalScrollBar(), b"value", self)
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._sol_kaydirma_anim = anim
        return anim

    def _sol_aktifi_gorunur_yap(self, animasyonsuz: bool = False) -> None:
        """Aktif nöbetçiyi görünür alana getirir.

        Zamanlama: bu çağrı **vurgu değişimiyle aynı anda** yapılır (`update_display`),
        süre ise orta geçiş animasyonuyla aynıdır → iki hareket birlikte görünür.
        Bağımsız zamanlayıcı YOKTUR (eskiden ayrı bir sayaç vardı ve orta slider'dan
        önce/sonra bağımsız hareket ediyordu).
        """
        alan = getattr(self, "_sol_kaydirma_alani", None)
        if alan is None:
            return
        if not bool(getattr(config, "SOL_PANEL_OTOMATIK_KAYDIRMA", True)):
            return
        bar = alan.verticalScrollBar()
        hedef = self.sol_kaydirma_hedefi()
        mevcut = int(bar.value())
        anim = self._sol_kaydirma_animasyonu()
        if anim is None:
            return
        if hedef == mevcut:
            return
        if animasyonsuz:
            bar.setValue(hedef)
            return
        anim.setDuration(int(getattr(config, "SOL_PANEL_KAYDIRMA_SURE_MS", 1800)))
        anim.setStartValue(mevcut)
        anim.setEndValue(hedef)
        anim.start()

    def _sol_kaydirmayi_durdur(self):
        """Yeniden çizim öncesi animasyon temizliği (eski hedefe kayma olmasın)."""
        anim = getattr(self, "_sol_kaydirma_anim", None)
        if anim is not None:
            try:
                anim.stop()
            except RuntimeError:
                pass
        # Nitelikler her zaman tanımlı kalsın (durum sorgulaması güvenli olsun)
        self._sol_kaydirma_anim = None
        self._sol_kaydirma_alani = None
        self._sol_kaydirma_sayfa = 0

    def _ikincil_metin(self, kayit, buyuk=False):
        """Telefon varsa biçimlenmiş telefonu, yoksa bölge adını döndürür.

        Canlı veri (`hakkisabah.com`) telefon/adres yayınlamıyor; ekranın boş
        kalmaması için eksik alan yerine bölge adı gösterilir. Bu davranış
        config.EKSIK_TELEFON_YERINE_BOLGE ile kapatılabilir.
        """
        tel = utils.format_phone(kayit.get("tel", ""))
        if tel != "-":
            return tel
        if not config.EKSIK_TELEFON_YERINE_BOLGE:
            return tel
        return kayit.get("bolge", "") or "-"

    def _nobet_araligi_metni(self, kayit):
        """'26.04.26 08:30 - 27.04.26 08:30 TARİHLER ARASI NÖBETÇİ!' (referans metni)."""
        baslangic = utils.parse_tarih(kayit.get("baslangic"))
        bitis = utils.parse_tarih(kayit.get("bitis"))
        if baslangic is None or bitis is None:
            log.warning("nöbet aralığı okunamadı: %r - %r", kayit.get("baslangic"), kayit.get("bitis"))
            return "-"
        return (
            f"{baslangic.strftime('%d.%m.%y %H:%M:%S')} - "
            f"{bitis.strftime('%d.%m.%y %H:%M:%S')} TARİHLER ARASI NÖBETÇİ!"
        )

    def prepare_ticker_text(self):
        """Kuşakta gösterilecek 'ECZANE - telefon' kayıtlarını hazırlar."""
        self.ticker_items = [
            f"{p.get('eczane', '').upper()} - {self._ikincil_metin(p)}" for p in self.pharmacies
        ] or ["-"]
        self.ticker_index = 0
        self.kusak_animasyonu.sifirla()
        if config.KUSAK_TEKLI:
            # yazı sağ kenardan girecek: şerit genişliği kadar sağda başlar
            self.ticker_x = self._kusak_serit_genisligi()
            metin = self.ticker_items[0]
        else:
            self.ticker_x = self.screen_w
            metin = "        " + config.KUSAK_AYIRICI.join(self.ticker_items) + "        "
        self._ticker_metnini_yerlestir(metin)

    def _kusak_serit_genisligi(self) -> int:
        """Kuşağın (kırmızı şeridin) gerçek genişliği."""
        return self.yayin_widget.ticker_strip.width() or self.screen_w

    def _ticker_metnini_yerlestir(self, metin, x=None):
        """Yazıyı kurar; `x` verilmezse mevcut ticker_x kullanılır."""
        etiket = self.yayin_widget.ticker_label
        etiket.setText(metin)
        etiket.adjustSize()
        konum = self.ticker_x if x is None else x
        etiket.move(konum, (self.yayin_widget.ticker_strip.height() - etiket.height()) // 2)
        return konum

    def scroll_ticker(self):
        """Kuşağı ilerletir (30 ms'lik `ticker_timer` tarafından çağrılır).

        KUSAK_TEKLI = True  : kayıt sağdan ortaya gelir (InOutCubic), ortada
                              bir süre durur, aynı yumuşatmayla soldan çıkar;
                              sonra sıradaki kayıt sağdan girer.
        KUSAK_TEKLI = False : tüm liste tek metin hâlinde kesintisiz akar.
        """
        if not self.is_broadcast_mode:
            return
        if not ayarlar.ozellik("kayan_yazi"):
            return  # kayan yazı kapalı: boşa iş yapma
        etiket = self.yayin_widget.ticker_label

        if config.KUSAK_TEKLI:
            durum = self.kusak_animasyonu.ilerle()
            if self.kusak_animasyonu.dongu_tamamlandi:
                # kayıt soldan tamamen çıktı: sıradakini sağ kenardan başlat
                self.ticker_index = (self.ticker_index + 1) % len(self.ticker_items)
                self.ticker_x = self._kusak_serit_genisligi()
                self._ticker_metnini_yerlestir(self.ticker_items[self.ticker_index], x=self.ticker_x)
                return
            serit = self._kusak_serit_genisligi()
            self.ticker_x = self.kusak_animasyonu.oran_piksele(durum.oran, serit, etiket.width())
            etiket.move(self.ticker_x, etiket.y())
            return

        self.ticker_x -= getattr(config, "KUSAK_HIZ", 3)
        if self.ticker_x < -etiket.width():
            self.ticker_x = self.screen_w
        etiket.move(self.ticker_x, etiket.y())

    def manage_loop(self):
        """Döngü: nöbet listesinde ilerler; liste bittiyse (ve özellik açıksa) yayına geçer.

        Özellik anahtarları (`ayarlar.json`):
          * `nobet_listesi` kapalı → nöbet ekranı hiç gösterilmez (yalnızca yayın/görsel modu),
          * `yayinlar` kapalı → yayın moduna hiç geçilmez.
        """
        if self.is_broadcast_mode:
            self.show_next_broadcast()
            return

        if not ayarlar.ozellik("nobet_listesi"):
            self._yalniz_yayin_dongusu()
            return

        if not ayarlar.ozellik("yayinlar"):
            self.current_index = (self.current_index + 1) % max(1, len(self.pharmacies))
            self.update_display()
            return

        self.current_index += 1
        if self.current_index >= len(self.pharmacies):
            active_yayinlar = self.broadcast_manager.get_active_yayinlar(self.yayinlar)
            if active_yayinlar:
                self.start_broadcast_mode(active_yayinlar)
            else:
                self.current_index = 0
                self.update_display()
        else:
            self.update_display()

    def _yalniz_yayin_dongusu(self):
        """Nöbet ekranı kapalıyken: aktif yayın varsa göster, yoksa sade ekranda bekle."""
        aktif = (
            self.broadcast_manager.get_active_yayinlar(self.yayinlar)
            if ayarlar.ozellik("yayinlar")
            else []
        )
        if aktif:
            self.start_broadcast_mode(aktif)
            return
        if self.stack.currentWidget() is not self.yayin_widget:
            log.info("nöbet listesi kapalı: yayın görünümünde bekleniyor (aktif yayın yok)")
            self.stack.setCurrentWidget(self.yayin_widget)
        self.yayin_widget.kusagi_goster(ayarlar.ozellik("kayan_yazi"))
        self.yayin_widget.kusagi_yerlestir()

    def start_broadcast_mode(self, active_yayinlar):
        if not ayarlar.ozellik("yayinlar"):
            return
        self.is_broadcast_mode = True
        self.broadcast_manager.active_yayin_list = active_yayinlar
        self.broadcast_manager.current_yayin_idx = 0
        self.stack.setCurrentWidget(self.yayin_widget)
        # Küçük panellerde tazele: kuşak yayın görselinin üstüne konumlansın
        self.yayin_widget.kusagi_yerlestir()
        # Kayan yazı özelliği kapalıysa kuşak hiç gösterilmez
        self.yayin_widget.kusagi_goster(ayarlar.ozellik("kayan_yazi"))
        if ayarlar.ozellik("kayan_yazi"):
            # Her girişte yazı sağdan baştan girsin
            self.prepare_ticker_text()
        self.show_current_broadcast()

    def show_current_broadcast(self):
        mgr = self.broadcast_manager
        if not mgr.active_yayin_list:
            self.stop_broadcast_mode()
            return
        y = mgr.active_yayin_list[mgr.current_yayin_idx]
        url = y.get("contentURL") or y.get("contentUrl") or ""
        # Süre sınırlanır: bozuk değer (ör. 99999999) ekranı yayında kilitleyemesin
        duration = (
            sayi_sinirla(
                y.get("duration"),
                alt=getattr(config, "YAYIN_SURE_EN_AZ_S", 1),
                ust=getattr(config, "YAYIN_SURE_EN_COK_S", 60),
                varsayilan=getattr(config, "YAYIN_SURE_VARSAYILAN_S", 10),
            )
            * 1000
        )
        if not self._yayin_gorselini_yukle(url):
            self.show_next_broadcast()
            return
        self.timer_manager.cycle_timer.start(duration)

    def _yayin_gorselini_yukle(self, url):
        """Yayın görselini güvenlik denetiminden geçirerek yükler.

        Denetim: https + izin listesi (ağ katmanı), bayt sınırı, beyaz liste
        (PNG/JPEG/WEBP) ve başlıktan okunan piksel bütçesi (görsel politikası).
        SVG/PDF/TIFF/HTML reddedilir (bkz. security/image_policy.py).
        """
        ayarlar = AgAyarlari(
            zaman_asimi_s=config.HTTP_TIMEOUT_S,
            en_buyuk_bayt=config.MAX_GORSEL_BAYT,
            izinli_hostlar=tuple(config.ALLOWED_HOSTS),
            kullanici_ajani="yourkiosk/1.0",
            izinli_portlar=tuple(getattr(config, "AG_IZINLI_PORTLAR", (443,))),
            yonlendirme_izinli=bool(getattr(config, "AG_YONLENDIRME_IZINLI", False)),
            en_buyuk_url=getattr(config, "MAX_URL_UZUNLUK", 2048),
        )
        # 0) Adres politikası önbellekten GÖSTERİRKEN de geçerli (izin listesi sonradan
        #    daraltılırsa eski önbellek kaydı çalışmaya devam etmesin).
        try:
            ayarlar.dogrula_url(url)
        except AgHatasi as hata:
            log.warning("yayın görseli adresi reddedildi (%s): %s", url, hata)
            return False
        # 1) Cihaz önbelleği: görsel daha önce indirildiyse AĞA HİÇ ÇIKILMAZ.
        baytlar = onbellek.gorsel_oku(url)
        icerik_turu = ""
        if baytlar is not None:
            log.debug("yayın görseli önbellekten okundu: %s", url)
        else:
            # 2) Önbellekte yok/bayat → indir, doğrula, önbelleğe yaz.
            try:
                baytlar, icerik_turu = indir(url, ayarlar)
            except AgHatasi as hata:
                log.warning("yayın görseli indirilemedi (%s): %s", url, hata)
                return False
        pixmap, karar = piksel_yukle(
            baytlar,
            en_buyuk_bayt=config.MAX_GORSEL_BAYT,
            en_buyuk_piksel=config.MAX_GORSEL_PIKSEL,
            icerik_turu=icerik_turu,
        )
        if pixmap is None:
            log.warning("yayın görseli reddedildi (%s): %s", url, karar.sebep)
            if icerik_turu:  # yeni indirilen bozuksa önbelleğe YAZILMAZ
                onbellek.gorsel_temizle(url)
            return False
        if icerik_turu:  # yalnızca yeni indirilen görsel saklanır (doğrulandıktan sonra)
            onbellek.gorsel_yaz(url, baytlar, icerik_turu)
        onbellek.gorsel_gosterildi(url)
        self.yayin_widget.img_lbl.setPixmap(pixmap)
        return True

    def show_next_broadcast(self):
        self.broadcast_manager.current_yayin_idx += 1
        if self.broadcast_manager.current_yayin_idx >= len(self.broadcast_manager.active_yayin_list):
            self.stop_broadcast_mode()
        else:
            self.show_current_broadcast()

    def stop_broadcast_mode(self):
        self.is_broadcast_mode = False
        self.current_index = 0
        if ayarlar.ozellik("nobet_listesi"):
            self.stack.setCurrentWidget(self.nobet_widget)
            self.nobet_widget.update()  # Widget'ı tazele
        else:
            # Nöbet ekranı kapalı: yayın görünümünde kal, görseli temizle
            self.yayin_widget.img_lbl.clear()
        self.timer_manager.cycle_timer.start(config.CYCLE_INTERVAL_MS)
        self.update_display()

    def update_display(self):
        if not ayarlar.ozellik("nobet_listesi"):
            return  # nöbet ekranı kapalı
        if not self.pharmacies: return
        nw = self.nobet_widget
        next_idx = 1 - nw.active_block_idx
        active = nw.ui_blocks[nw.active_block_idx]
        incoming = nw.ui_blocks[next_idx]

        active_path = os.path.join(config.BG_PATH, "activeBox.png").replace("\\", "/")
        box_path = os.path.join(config.BG_PATH, "box.png").replace("\\", "/")
        for i, (name_lbl, phone_lbl, frame) in enumerate(self.pharmacy_widgets):
            p = self.pharmacies[i]
            name_lbl.setText(p.get("eczane", "").upper())
            phone_lbl.setText(self._ikincil_metin(p))
            obj_name = frame.objectName()
            if i == self.current_index:
                frame.setStyleSheet(f"QFrame#{obj_name} {{ border-image: url({active_path}) 0 0 0 0 stretch stretch; border: none; }}")
                name_lbl.setStyleSheet("color: white; background: transparent; border: none;")
                phone_lbl.setStyleSheet("color: white; background: transparent; border: none;")
            else:
                frame.setStyleSheet(f"QFrame#{obj_name} {{ border-image: url({box_path}) 0 0 0 0 stretch stretch; border: none; }}")
                name_lbl.setStyleSheet("color: black; background: transparent; border: none;")
                phone_lbl.setStyleSheet("color: black; background: transparent; border: none;")

        curr = self.pharmacies[self.current_index]
        incoming["big_name_lbl"].setText(curr.get("eczane", "").upper() + " ECZANESİ")
        addr = curr.get("adres", "")
        tarif = curr.get("adres_tarifi", "")
        if tarif: addr += "\n" + tarif
        incoming["address_lbl"].setText(addr.upper())
        incoming["big_phone_lbl"].setText(self._ikincil_metin(curr))
        incoming["date_range_lbl"].setText(self._nobet_araligi_metni(curr))
        incoming["date_range_lbl"].setStyleSheet("color: black; background-color: red;")

        vh = nw.viewport.height()
        self.animation_handler.animate_transition(active["widget"], incoming["widget"], vh)
        nw.active_block_idx = next_idx
        # Sol panel vurguyu TAKİP eder: kaydırma, orta geçişle aynı anda ve aynı süreyle
        # başlar (bağımsız zamanlayıcı yok). Aktif satır görünürse hiç hareket etmez.
        self._sol_aktifi_gorunur_yap()

    def update_clock(self):
        if not ayarlar.ozellik("saat_tarih"):
            # Saat/tarih kapalı: metin boşaltılır (yerleşim bozulmaz)
            for block in self.nobet_widget.ui_blocks:
                block["time_lbl"].setText("")
                block["date_lbl"].setText("")
                block["day_lbl"].setText("")
            return
        now = QDateTime.currentDateTime()
        locale = QLocale(QLocale.Language.Turkish)
        t_str = now.toString("HH:mm")
        d_str = now.toString("dd.MM.yyyy")
        day_str = locale.dayName(now.date().dayOfWeek(), QLocale.FormatType.LongFormat).capitalize()
        for block in self.nobet_widget.ui_blocks:
            block["time_lbl"].setText(t_str)
            block["date_lbl"].setText(d_str)
            block["day_lbl"].setText(day_str)
