from PyQt6.QtCore import QTimer
import config

class TimerManager:
    def __init__(self, app_instance):
        self.app_instance = app_instance
        
        self.data_timer = QTimer(app_instance)
        self.data_timer.timeout.connect(app_instance.load_data)

        self.cycle_timer = QTimer(app_instance)
        self.cycle_timer.timeout.connect(app_instance.manage_loop)

        self.clock_timer = QTimer(app_instance)
        self.clock_timer.timeout.connect(app_instance.update_clock)

        self.ticker_timer = QTimer(app_instance)
        self.ticker_timer.timeout.connect(app_instance.scroll_ticker)

        # Hızlı değişiklik denetimi: lastupdate damgası + panel tetikleyicisi (AĞ)
        self.tetik_timer = QTimer(app_instance)
        self.tetik_timer.timeout.connect(app_instance.tetik_kontrol)

        # YEREL tetik izleyici (AĞ YOK): MQTT push dosyayı yazar, bu izleyici ANINDA görür.
        self.tetik_izleyici = QTimer(app_instance)
        self.tetik_izleyici.timeout.connect(app_instance.tetik_izle)

    def start_all(self):
        self.data_timer.start(config.REFRESH_INTERVAL_MS)
        self.cycle_timer.start(config.CYCLE_INTERVAL_MS)
        self.clock_timer.start(1000)
        self.ticker_timer.start(30)
        # NÖBET DEĞİŞİKLİĞİ: damga + tetikleyici hızlı denetimi (yalnız küçük dosyalar).
        # Saatlik kontrolü beklemeden değişikliği yansıtır (`DAMGA_KONTROL_MS`: push BAĞLI 120 sn,
        # KOPUK 30 sn — `DAMGA_KONTROL_MS_PUSH` / `DAMGA_KONTROL_MS_PUSH_YOK`; aralığı
        # `pharmacy_app.yoklama_araligi` bağlantı durumuna göre seçer, `yoklama_ayarla` uygular).
        self.tetik_timer.start(getattr(config, "DAMGA_KONTROL_MS", 1800 * 1000))
        # ANLIK yol: yerel dosya izleyici (maliyetsiz). Push ölü olsa bile yoklama çalışır.
        self.tetik_izleyici.start(getattr(config, "TETIK_IZLEME_MS", 2000))
        # ÖNEMLİ: aralık, İLK turu beklemeden bugünkü bağlantı durumuna göre kurulur.
        # Aksi hâlde `ayarlar.json`daki `tetik.kontrol_ms` (ör. 300000) yüzünden ilk yoklama
        # 5 dakika sonra yapılıyordu — "değişiklik gelmiyor" şikâyetinin bir kaynağı buydu.
        try:
            app_instance.yoklama_ayarla()
        except Exception:  # noqa: BLE001
            pass
