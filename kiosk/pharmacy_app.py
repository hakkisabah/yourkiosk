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
from security.network import AgAyarlari, AgHatasi, gorsel_icin_ayarlar, indir, kosullu_indir
from security.safe_image import ayirma_limitini_ayarla, piksel_yukle
from security.veri_dogrulama import sayi_sinirla
from ui.nobet_widget import NobetWidget
from ui.yayin_widget import YayinWidget
from core.data_handler import DataHandler
from core.broadcast_manager import BroadcastManager
from core import durum as durum_modulu
from core import onbellek
from core import push as push_modulu
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
        self._son_komut_isareti = ""  # durum.json komut işareti (değişince komut indirilir)
        self._yoklama_ms = 0
        self._kopuk_tur = 0
        self._durum_tur = 0
        self._son_yerel_imza = ""
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

        # KOMUT KAPLAMASI (kullanıcı isteği): uzaktan yeniden başlatma sırasında ekran birkaç
        # saniye boşalıyor/kapanıyor; "bozuldu" sanılmasın diye kısa bir bilgi yazısı gösterilir.
        # Süreli: komut bittiğinde (ya da süreç öldüğünde) kalıcı yazı kalmaz.
        self.komut_kaplama = QLabel(self.stack)
        self.komut_kaplama.setObjectName("komut-bildirim")
        self.komut_kaplama.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.komut_kaplama.setStyleSheet(
            "background: rgba(0, 0, 0, 180); color: #ffffff;"
            "font-size: 38px; font-weight: bold;"
        )
        self.komut_kaplama.hide()

    def _komut_bildirimi(self, komut: str) -> None:
        """Komut uygulanmadan ÖNCE kısa bilgiyi gösterir (subprocess öncesi boyanması için
        `processEvents` şart — aksi hâlde ana iş parçacığı bloke olurken yazı hiç görünmez)."""
        try:
            from core import bildirim as bildirim_modulu

            self.komut_kaplama.setText(bildirim_modulu.metin_uret(komut))
            self.komut_kaplama.setGeometry(self.stack.rect())
            self.komut_kaplama.show()
            self.komut_kaplama.raise_()
            QApplication.processEvents()
        except Exception:  # noqa: BLE001 - bildirim gösterimi komutu engellememeli
            pass
        # Emniyet: komut çağrısı geri dönmese bile kaplama en geç 8 sn sonra kalkar.
        QTimer.singleShot(8000, self.komut_kaplama.hide)

    def load_data(self, zorla: bool = False):
        """Veriyi yükler. `zorla=True` → damga değişmemiş olsa da yenilenir (tetikleyici yolu)."""
        if self.data_handler.load_data(zorla=zorla):
            self.setup_left_panel()
            self.prepare_ticker_text()
            if not self.is_broadcast_mode:
                # Eğer eczane listesi değiştiyse veya ilk yükleme ise ekranı güncelle
                # Basitlik için her yüklemede değil, sadece mod değişmediyse güncelliyoruz
                self.update_display()

    def _yerel_imza(self) -> str:
        """Yerel tetikleyici dosyalarının (mtime+boyut) imzası — AĞ YOK."""
        from pathlib import Path as _Yol

        kok = _Yol(__file__).resolve().parent  # kiosk/ klasörü (cihaz dosyaları burada)
        parcalar = []
        for ad in ("tetikle.json", "lastupdate.json", "durum.json"):
            try:
                durum = (kok / ad).stat()
                parcalar.append(f"{ad}:{durum.st_mtime_ns}:{durum.st_size}")
            except OSError:
                parcalar.append(f"{ad}:-")
        return "|".join(parcalar)

    def tetik_izle(self):
        """YEREL tetik dosyası değiştiyse anında yenile (MQTT push'un ANLIK yolu).

        NEDEN: yoklama aralığı maliyet için 1800 sn'ye çıkarıldı; MQTT mesajı yalnız
        `tetikle.json` yazıyordu ve bunu okuyan zamanlayıcı 30 dk sonra çalışıyordu →
        değişiklik ancak uygulama yeniden başlatılınca görünüyordu. Bu izleyici yalnız `stat`
        yapar (ağ yok), değişimi görünce `tetik_kontrol`ü çalıştırır.
        """
        try:
            imza = self._yerel_imza()
        except Exception:  # noqa: BLE001
            return
        if imza == getattr(self, "_son_yerel_imza", ""):
            return
        onceki = getattr(self, "_son_yerel_imza", "")
        self._son_yerel_imza = imza
        if not onceki:  # ilk tur: yalnız imzayı kaydet
            return
        log.debug("yerel tetik dosyası değişti → tetik_kontrol")
        self.tetik_kontrol()

    def yoklama_araligi(self) -> int:
        """Yoklama aralığı — MQTT'nin GERÇEK bağlantı durumuna göre.

        | Durum | Aralık | Gerekçe |
        |---|---|---|
        | MQTT bağlı | 120 sn | anlıklık push'tan gelir; bu emniyet ağı (600 cihazda ~$15/ay) |
        | MQTT kopuk | 30 sn | tek yol yoklama; en kötü gecikme yarım dakika |

        NOT: 1800 sn'lik "tasarruf" push sessizce öldüğünde 30 dakikalık gecikmeye dönüşüyordu
        (kullanıcı: "kapatıp açmadan düzelmiyor"). Emniyet ağı artık gerçekten emniyet ağı.
        """
        try:
            bagli = bool(push_modulu.durum().get("bagli"))
        except Exception:  # noqa: BLE001 - push durumu okunamazsa yoklama sıkı moda düşer
            bagli = False
        if bagli:
            return int(getattr(config, "DAMGA_KONTROL_MS_PUSH", 120_000))
        return int(getattr(config, "DAMGA_KONTROL_MS_PUSH_YOK", 30_000))

    def yoklama_ayarla(self) -> None:
        """Zamanlayıcı aralığını bağlantı durumuna göre günceller (değişmediyse dokunmaz)."""
        hedef = self.yoklama_araligi()
        if hedef == getattr(self, "_yoklama_ms", 0):
            return
        self._yoklama_ms = hedef
        try:
            self.timer_manager.tetik_timer.setInterval(hedef)
            log.info(
                "yoklama aralığı: %d sn (MQTT %s)", hedef // 1000,
                "bağlı" if hedef == getattr(config, "DAMGA_KONTROL_MS_PUSH", 120_000) else "KOPUK",
            )
        except Exception:  # noqa: BLE001
            pass

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
        self.yoklama_ayarla()  # bağlantı durumu değiştiyse aralığı uyarla
        try:
            self._tetik_kontrol_govde()
        except Exception:  # noqa: BLE001
            # TEK bir istisna turu öldürmemeli: aksi hâlde cihaz "kapatıp açılana kadar" donar.
            log.warning("yoklama turu başarısız (sonraki turda yeniden denenecek)", exc_info=True)

    def _tetik_kontrol_govde(self):
        """Yoklama turunun gövdesi (istisna kalkanı `tetik_kontrol` içinde)."""
        # MALİYET: tek istekle damga + tetikleyici + komut işareti (`durum.json`).
        # Yoksa (eski kurulum / 404) eski üç dosyalı yola düşülür.
        belge = durum_modulu.getir()
        if belge is not None:
            self._durum_uygula(belge)
            return

        # UZAKTAN KOMUT + küçük dosya senkronu (eski yol)
        self.uzak_kontrol()

        if not tetik_modulu.otomatik_acik("qt"):
            return

        try:
            damga = veri_kaynagi.lastupdate_taze()
        except Exception:  # noqa: BLE001
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

    def _durum_uygula(self, belge):
        """`durum.json` ile TEK istekte: damga değişimi + tetikleyici + komut işareti."""
        # 1) uzaktan komut: yalnız işaret DEĞİŞTİĞİNDE gövde indirilir (nadir)
        isaret = durum_modulu.komut_isareti(belge)
        if isaret and isaret != self._son_komut_isareti:
            self._son_komut_isareti = isaret
            try:
                komut_modulu.getir()
                _karar, sonuc = komut_modulu.kontrol(
                    cihaz_id=self.cihaz_kimligi(),
                    bildirim_geri_cagri=getattr(self, "_komut_bildirimi", None),
                )
                if sonuc is not None:
                    log.warning("UZAKTAN KOMUT: %s", komut_modulu.sonuc_metni(sonuc))
                    if sonuc.uygulama_ici:
                        self.update_display()
            except Exception:  # noqa: BLE001
                log.warning("uzaktan komut denetimi yapılamadı", exc_info=True)

        if not tetik_modulu.otomatik_acik("qt"):
            return

        # 2) veri damgası
        yeni_damga = durum_modulu.damga(belge)
        # ÇAPRAZ KONTROL: panel `durum.json`ı yazamazsa cihaz 30 dk eski veride kalırdı.
        # Her 10 turda bir `lastupdate.json` da okunur (1800 sn'de ~5 saatte 1 ek istek).
        self._durum_tur = getattr(self, "_durum_tur", 0) + 1
        if self._durum_tur % 10 == 1:
            try:
                capraz = veri_kaynagi.lastupdate_taze()
                if capraz and capraz != yeni_damga:
                    log.debug("durum.json damgası (%s) ile lastupdate.json (%s) farklı → lastupdate kullanılıyor",
                              yeni_damga, capraz)
                    yeni_damga = capraz
            except Exception:  # noqa: BLE001
                pass
            # ÇAPRAZ KONTROL: `tetikle.json`u YALNIZ yazan akışlar (panel "Bildir", elle yazım)
            # `durum.json`a dokunmayabilir. Bu yol artık tetikleyiciyi indirmediği için bu akışlar
            # cihazda SESSİZCE görünmüyordu (Qt kioskta "Bildir" tepkisizdi — yaşandı).
            # MALİYET: `getir()` KOŞULLU indirir (ETag/Last-Modified → 304) — dosya değişmediyse
            # gövde inmez. İndirme yerel dosyanın mtime'ını değiştirirse `tetik_izle` turu tetikler.
            try:
                if tetik_modulu.getir():
                    log.info("tetikle.json sunucudan yenilendi (durum.json tetiği yok/eskimiş olabilir)")
            except Exception:  # noqa: BLE001
                pass
            # ÇAPRAZ KONTROL (komut): `komut.json` panelden BAĞIMSIZ yüklenebiliyor
            # (`tools/komut_gonder.py` doğrudan S3'e yazar). `durum.json` komut İŞARETİ
            # taşımıyorsa komut dosyası HİÇ indirilmiyordu → uzaktan komut sessizce ölüydü.
            # NOT: panel bugün `durum.json`a komut işareti yazmıyor (yalnız zaman/lastupdate/tetik),
            # bu yüzden bu dal HER çapraz kontrolde çalışır — ama çapraz kontrol 10 turda BİRDİR
            # (`self._durum_tur % 10 == 1`), yani tur başına değil. İndirme KOŞULLU (ETag → 304)
            # olduğu için tipik maliyet tur başına ~0, çapraz kontrol başına birkaç yüz bayt.
            # Ölçülen oran (10 tur): 10 durum.json + 1 tetikle.json + 1 komut.json + 1 lastupdate.json.
            # Panel işaret yazmaya başlarsa dal kendiliğinden seyrekleşir.
            if not isaret:
                self._komut_capraz_kontrol()
        onceki = str(getattr(self.data_handler, "lastupdate", "") or "")
        # KALP ATIŞI: her turda INFO. "Neden güncellenmiyor?" sorusunun yanıtı bu satırda:
        # uzak damga ile cihazdaki damga yan yana görünür, MQTT durumu eklenir.
        self._tur = getattr(self, "_tur", 0) + 1
        log.info(
            "yoklama #%d · uzak=%s · cihaz=%s · MQTT=%s",
            self._tur, yeni_damga or "-", onceki or "-",
            "bağlı" if push_modulu.durum().get("bagli") else "kopuk",
        )
        if yeni_damga and onceki and yeni_damga != onceki:
            log.info("nöbet verisi değişti (damga %s → %s) → hemen yenileniyor", onceki, yeni_damga)
            self.load_data()
            return

        # 3) tetikleyici: UZAK (panel → durum.json) VEYA YEREL (MQTT push → tetikle.json)
        #    MQTT mesajı yerel dosyaya yazılır; burada okunmazsa push sessizce ölür.
        tetik = durum_modulu.secili_tetik(belge, tetik_modulu.oku)
        konum = getattr(self.data_handler, "konum", None)
        ilce = str(getattr(konum, "ilce_id", "") or "")
        bolge = str(getattr(konum, "bolge_id", "") or "")
        if tetik and tetik_modulu.uygulanmali(tetik, ilce, bolge, self._son_tetik):
            self._son_tetik = str(tetik.get("zaman", ""))
            log.info(
                "tetikleyici uygulanıyor (%s · kapsam=%s) → hemen yenileniyor",
                tetik.get("zaman"), tetik.get("ilceId") or "tüm cihazlar",
            )
            self.load_data(zorla=True)

    def _komut_capraz_kontrol(self):
        """`durum.json` komut işareti taşımıyorsa komut dosyasını doğrudan indirir ve uygular.

        NEDEN: `komut.json` panelden bağımsız yüklenebiliyor (`tools/komut_gonder.py` doğrudan
        S3'e yazar). `durum.json` içinde `komut` işareti yoksa eski kod komut dosyasını HİÇ
        indirmiyordu → uzaktan komut sessizce ölüydü. 10 turda bir (ucuz) çapraz kontrol yapılır;
        `komut.kontrol` tek seferliktir, aynı komut iki kez uygulanmaz.
        """
        try:
            komut_modulu.getir()
            _karar, sonuc = komut_modulu.kontrol(
                cihaz_id=self.cihaz_kimligi(),
                bildirim_geri_cagri=getattr(self, "_komut_bildirimi", None),
            )
        except Exception:  # noqa: BLE001 - komut denetimi gösterimi durdurmamalı
            log.warning("komut çapraz kontrolü yapılamadı", exc_info=True)
            return
        if sonuc is None:
            return
        log.warning("UZAKTAN KOMUT: %s", komut_modulu.sonuc_metni(sonuc))
        if sonuc.uygulama_ici:
            self.update_display()

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
            _karar, sonuc = komut_modulu.kontrol(
                cihaz_id=self.cihaz_kimligi(),
                bildirim_geri_cagri=getattr(self, "_komut_bildirimi", None),
            )
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
            konum_kapsami = self._kapsam()
            active_yayinlar = self.broadcast_manager.get_active_yayinlar(
                self.yayinlar,
                ilce_id=konum_kapsami[0], bolge_id=konum_kapsami[1], cihaz_id=konum_kapsami[2],
            )
            log.debug("nöbet listesi bitti: havuz=%d · aktif yayın=%d", len(self.yayinlar), len(active_yayinlar))
            if active_yayinlar:
                self.start_broadcast_mode(active_yayinlar)
            else:
                self.current_index = 0
                self.update_display()
        else:
            self.update_display()

    def _kapsam(self):
        """(ilçe, bölge, cihaz) — yayın hedeflemesi için."""
        konum = getattr(self.data_handler, "konum", None)
        return (
            str(getattr(konum, "ilce_id", "") or ""),
            str(getattr(konum, "bolge_id", "") or ""),
            self.cihaz_kimligi(),
        )

    def _yalniz_yayin_dongusu(self):
        """Nöbet ekranı kapalıyken: aktif yayın varsa göster, yoksa sade ekranda bekle."""
        konum_kapsami = self._kapsam()
        aktif = (
            self.broadcast_manager.get_active_yayinlar(
                self.yayinlar,
                ilce_id=konum_kapsami[0], bolge_id=konum_kapsami[1], cihaz_id=konum_kapsami[2],
            )
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
            log.info("yayın moduna geçilmedi: 'yayinlar' özelliği kapalı")
            return
        log.info("yayın modu başladı: %d yayın", len(active_yayinlar))
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
        log.info("yayın gösteriliyor: %d/%d · %s", mgr.current_yayin_idx + 1, len(mgr.active_yayin_list), url or "(adres yok)")
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
            # Veri izin listesi görseller için dar olabilir (cihaz ayarları varsayılanı ezer).
            # Tarayıcı köprüsüyle AYNI kural: herkese açık https host kabul, özel/loopback RED.
            try:
                ayarlar = gorsel_icin_ayarlar(ayarlar, url)
                log.info("yayın görseli: izin listesi dışı herkese açık host kabul edildi (%s) — %s", url, hata)
            except AgHatasi:
                log.warning("yayın görseli adresi reddedildi (%s): %s", url, hata)
                return False
        # 1) Cihaz önbelleği: görsel daha önce indirildiyse AĞA HİÇ ÇIKILMAZ.
        baytlar = onbellek.gorsel_oku(url)
        icerik_turu = ""
        etag_indirilen = tarih_indirilen = ""
        if baytlar is not None:
            log.info("yayın görseli DİSKTEN okundu (%d bayt): %s", len(baytlar), url)
        else:
            # 1b) Kayıt "bayat" ise KÖRLEMESİNE indirme: ETag/Last-Modified ile doğrula.
            #     Sunucu 304 derse gövde gelmez → diskteki kopya kullanılır (bant + AWS maliyeti yok).
            kayit = onbellek.gorsel_kayit(url)
            if isinstance(kayit, dict) and kayit.get("bayat") and (kayit.get("etag") or kayit.get("son_degisiklik")):
                try:
                    yeni, tur304, etag304, tarih304 = kosullu_indir(
                        url, ayarlar, etag=str(kayit.get("etag") or ""),
                        son_degisiklik=str(kayit.get("son_degisiklik") or ""),
                    )
                except AgHatasi as hata:
                    log.warning("görsel doğrulanamadı (%s): %s", url, hata)
                    yeni = None
                    tur304 = ""
                if yeni is None:
                    onbellek.gorsel_bayati_temizle(url, etag304, tarih304)
                    baytlar = onbellek.gorsel_oku(url)
                    if baytlar is not None:
                        onbellek.gorsel_gosterildi(url)
                        log.info("yayın görseli DİSKTEN okundu (304 doğrulandı, %d bayt)", len(baytlar))
            if baytlar is not None and not icerik_turu:
                pass  # diskten geldi: aşağıdaki piksel yüklemesi baytları kullanır
            if baytlar is None:
                # 2) Önbellekte yok / gerçekten değişmiş → indir, doğrula, önbelleğe yaz.
                #    `kosullu_indir` ETag/Last-Modified'i de döndürür → sonraki tazeleme 304 alır.
                try:
                    baytlar, icerik_turu, etag_indirilen, tarih_indirilen = kosullu_indir(url, ayarlar)
                except AgHatasi as hata:
                    log.warning("yayın görseli indirilemedi (%s): %s", url, hata)
                    return False
                if baytlar is None:  # beklenmedik 304 (ETag göndermedik)
                    log.warning("yayın görseli için gövde gelmedi (%s)", url)
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
            onbellek.gorsel_yaz(url, baytlar, icerik_turu, etag=etag_indirilen, son_degisiklik=tarih_indirilen)
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
