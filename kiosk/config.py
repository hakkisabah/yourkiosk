# ==================== AYARLAR ====================
DATA_URL = "https://hakkisabah.com/api/ornekdata.json"
# Veri saatte bir güncelleniyor; cihaz da saatte bir kontrol eder
REFRESH_INTERVAL_MS = 60 * 60 * 1000
CYCLE_INTERVAL_MS = 10000
LOGO_PATH = "logo.png"
BG_PATH = "bg_layout"
FONT_PATH = "font"
# ================================================

# ==================== VERİ KAYNAĞI ====================
# Sunucudaki dosyalar (kiosk cihazı sırayla bunlara bakar):
#   lastupdate.json    -> nöbet verisi en son ne zaman güncellendi
#   match.json         -> ilçe/bölge -> makine id'leri (cihaz kendi yerini buradan öğrenir)
#   lastSystemData.json-> şablon.json doldurulmuş hâli (asıl nöbet verisi)
#   makinebilgileri.json-> bu cihazın kendi kimliği (clientID)
KAYNAK = "dosya"                      # "dosya" | "https"
LASTUPDATE_DOSYASI = "lastupdate.json"
MATCH_DOSYASI = "match.json"
SISTEM_VERISI_DOSYASI = "lastSystemData.json"
MAKINE_DOSYASI = "makinebilgileri.json"
# Cihazın kendi bölgesini bulamazsak hangi kapsam gösterilsin:
#   "ilce"  -> cihazın ilçesindeki tüm bölgelerin nöbetleri (7li örnekteki davranış)
#   "bolge" -> yalnızca cihazın kendi bölgesi
KAPSAM = "ilce"
# Söz konusu dosyaların bulunduğu sunucu (KAYNAK="https" olduğunda kullanılır)
SUNUCU_ADRESI = "https://www.kocaelieo.org.tr/nobet-belediye"
NOBET_VERISI_ADRESI = "https://www.kocaelieo.org.tr/nobet-belediye"
DOSYA_ADRESI = ""                      # ör. "https://ornek.com/kiosk/" (sonunda /)
ALLOWED_HOSTS = ("hakkisabah.com", "www.kocaelieo.org.tr", "kocaelieo.org.tr")
VERI_DOSYASI = "lastSystemData.json"   # geriye uyum: eski ad
VERI_DOSYASI_YEDEK = "data/ornekdata_7li.json"
# Saatte 1 kontrol: lastupdate.json değişmişse veriler yeniden çekilir
LASTUPDATE_KONTROL_MS = 60 * 60 * 1000
# --- NÖBET DEĞİŞİKLİĞİNİ ANINDA YANSITMA (tetikleyici) ---
#: Panelin yazdığı tetikleyici dosyası: {"zaman": ISO, "ilceId": "...", "bolgeId": "..."}
#: Boş/"*" ilceId → tüm cihazlar; doluysa yalnız o ilçenin (ya da bölgenin) cihazları
#: hemen yenilenir. Saatlik kontrole ek olarak çalışır.
TETIK_DOSYASI = "tetikle.json"
#: Damga/tetik yoklama aralığı (ms). Yalnızca KÜÇÜK dosyalar okunur (lastupdate+tetik);
#: büyük veri dosyaları damga değişmedikçe indirilmez.
# Emniyet ağı yoklaması. ANLIK güncelleme MQTT push (tetik.push_*) ve tarayıcıda `/degisiklik`
# uzun yoklamasıyla gelir; bu süre yalnızca "push kaçtı" durumu içindir.
# 600 cihaz ölçeğinde maliyet (3 küçük istek × 86400/süre × 600 cihaz × 30 gün):
#   120 sn (bu değer, push BAĞLI) → ~38,9 M istek/ay (~$29/ay)
#    30 sn (push KOPUK)          → ~155,5 M istek/ay (~$116/ay)
# Ölçü: 20 sn iken ~233 M istek/ay (~$175/ay) idi — 120 sn'ye çekilmesinin nedeni bu.
# Aralığı `pharmacy_app.yoklama_araligi` bağlantı durumuna göre seçer; bu sabit yalnız
# "push kaçtı" emniyet ağının üst sınırıdır, anlıklık MQTT push / `/degisiklik` ucundan gelir.
DAMGA_KONTROL_MS = 120 * 1000
#: MQTT push BAĞLIYKEN yoklama (anlıklık zaten push'tan gelir; bu yalnız emniyet ağı).
#  600 cihaz × (86400/120) × 1 istek × 30 gün ≈ 13,0 M istek/ay ≈ $10/ay
#  (damga+tetik+komut işareti tek dosyada olduğu için 1 istek; eski 3 dosyalı yol ~$29).
DAMGA_KONTROL_MS_PUSH = 120 * 1000
#: MQTT KOPTUYSA yoklama (tek yol yoklama kalır).
DAMGA_KONTROL_MS_PUSH_YOK = 30 * 1000
#: YEREL tetik izleyici: MQTT push `tetikle.json`u yazar; bu izleyici dosya değişimini görüp
#  ANINDA yeniler. Ağa ÇIKMAZ (yalnız stat) → maliyeti sıfır, 600 cihazda da bedava.
#  NEDEN GEREKLİ: yoklama aralığı dakikalara çıkınca push "dosya yazıldı ama kimse okumadı"
#  durumunda kalıyordu; değişiklik ancak uygulama yeniden başlatılınca görünüyordu.
TETIK_IZLEME_MS = 2 * 1000
#: Tarayıcı modunda anlık değişiklik ucu: tek istekte en fazla kaç saniye beklenir
DEGISIKLIK_BEKLEME_S = 30
# --- UZAKTAN KOMUT (S3 → cihaz): yeniden başlat / uygulamayı yeniden başlat / ekranı yenile ---
#: Cihaza indirilen imzalı komut dosyası (panel/S3 yazar, cihaz okur)
KOMUT_DOSYASI = "komut.json"
#: Uygulanan komutların kimliği (tekrar engeli) — cihazın kendi dosyası
KOMUT_DURUM_DOSYASI = "komut-durum.json"
#: HMAC-SHA256 anahtarı (0600; panel/Lambda'da aynı değer). Depoya GİRMEZ.
KOMUT_ANAHTAR_DOSYASI = "komut.anahtar"
#: True: imzasız/yanlış imzalı komut ASLA uygulanmaz (fail-closed — varsayılan ve önerilen)
KOMUT_IMZA_ZORUNLU = True
#: True: komutlar yalnız günlüklenir, hiçbir süreç çalıştırılmaz (deneme/bakım)
KOMUT_KURU_CALISTIRMA = False
#: Tek komut için en fazla çalışma süresi (saniye)
KOMUT_ZAMAN_ASIMI_S = 60
#: Komut adlarının SABİT argv karşılıkları (kabuk kullanılmaz; boş = uygulama içi işlem)
KOMUT_YENIDEN_BASLAT = "systemctl reboot"                  # cihazı yeniden başlat
KOMUT_UYGULAMA_YENIDEN_BASLAT = "systemctl restart kiosk.service"  # yalnız kiosk servisi
KOMUT_EKRANI_YENILE = ""                                   # ekranı tazele (uygulama içi)
# =====================================================

# ==================== GÜVENLİK SINIRLARI ====================
HTTP_TIMEOUT_S = 10.0
MAX_JSON_BAYT = 4 * 1024 * 1024
MAX_GORSEL_BAYT = 8 * 1024 * 1024
MAX_GORSEL_PIKSEL = 4096 * 4096
LOG_DOSYASI = "kiosk.log"
# =====================================================

# ==================== GÜVENLİK SINIRLARI ====================
# Ağ: yalnızca https + izin listesi + bu portlar (varsayılan https portu)
AG_IZINLI_PORTLAR = (443,)
MAX_URL_UZUNLUK = 2048
AG_YONLENDIRME_IZINLI = False        # False: yalnızca aynı ana makineye yönlendirme
# Veri: JSON derinlik/düğüm sınırları (bozuk ya da kötü niyetli dosya belleği şişirmesin)
MAX_JSON_DERINLIK = 32
MAX_JSON_DUGUM = 200_000
MAX_METIN_UZUNLUK = 160              # ekranda gösterilen tek bir alanın (eczane/adres/tel) üst sınırı
MAX_GOSTERILEN_ECZANE = 60           # tek seferde gösterilecek en fazla nöbet kaydı
MAX_AKTIF_YAYIN = 20                 # aynı anda işlenecek en fazla yayın
YAYIN_SURE_VARSAYILAN_S = 10         # duration okunamazsa
YAYIN_SURE_EN_AZ_S = 1               # duration alt sınırı
YAYIN_SURE_EN_COK_S = 60             # duration üst sınırı (bozuk değer ekranı kilitlemesin)
# Günlükte cihaz kimliği (clientID) ham gösterilmesin: kısa özet yazılır
LOG_CLIENT_ID_GIZLE = True
# Tehlikeli Qt eklentileri (svg/pdf/tiff/gif…, vnc platformu) karantinaya alınsın mı
QT_EKLENTI_KARANTINA = True
# Kullanılmayan Qt kütüphaneleri/modülleri (Qml, Quick3D, Pdf, Sql, Multimedia…) karantinaya alınsın mı
QT_MODUL_KARANTINA = True
# ===========================================================

# ==================== GENEL KULLANIM (ÖZELLİK AÇ/KAPA) ====================
# Bu kiosk yalnızca eczane nöbeti için değil: yalnızca görsel yayını yapan bir
# kurum nöbet listesini, kayan yazıyı vb. kapatabilir. Değerler `ayarlar.json`
# (örneği: ayarlar.ornek.json) ile dışarıdan — ileride yönetim panelinden —
# değiştirilebilir; buradakiler VARSAYILANdır.
AYARLAR_DOSYASI = "ayarlar.json"
# Kapsam (ilçe/bölge/cihaz) bazlı ikinci ayar dosyası — yönetim paneli yazar
KAPSAM_AYARLARI_DOSYASI = "kapsam-ayarlari.json"
OZELLIK_NOBET_LISTESI = True   # nöbet listesi + detay ekranı
OZELLIK_YAYINLAR = True        # yayın (görsel) moduna geçiş
OZELLIK_KAYAN_YAZI = True      # yayın görünümündeki alt kuşak/kayan yazı
OZELLIK_SAAT_TARIH = True      # nöbet ekranındaki saat/tarih yazısı
# Sol panelde satır yüksekliği bu sayıya göre hesaplanır: az nöbetçi olsa da
# çerçeveler büyümez (5 kişilik referans görünüm). Bu sayıdan FAZLA nöbetçi varsa
# sol panel kaydırılabilir olur: ilk `MAKS_GORUNUR_SATIR` kayıt görünür, sonra
# aşağı kayarak kalanlar gösterilir (aşağıdaki SOL_PANEL_KAYDIRMA_* ayarları).
MAKS_GORUNUR_SATIR = 5

# ---- Sol panel kaydırma (yalnızca kayıt sayısı tabanı aşınca çalışır) ----
# Kayıt sayısı MAKS_GORUNUR_SATIR'dan fazlaysa sol panel kaydırılabilir olur ve
# VURGULANAN nöbetçiyi TAKİP eder: vurgu görünür alandaki son satıra geldiğinde
# panel bir sonraki satırı içine alacak kadar aşağı kayar; döngü başa dönerse yukarı
# döner. Kaydırma, orta geçiş (nöbetçi değişimi) animasyonuyla AYNI ANDA başlar ve
# aynı süreyi kullanır — bağımsız bir zamanlayıcı yoktur (eski davranış: orta
# slider'dan 1-2 sn önce aşağı/yukarı zıplıyordu).
SOL_PANEL_OTOMATIK_KAYDIRMA = True   # False: yalnızca elle kaydırma (çubuk kalır)
SOL_PANEL_KAYDIRMA_SURE_MS = 1800    # orta geçiş animasyonuyla aynı süre (referans: 1800 ms)
SOL_PANEL_KAYDIRMA_CUBUGU_GENISLIK = 12   # px (0 → çubuk gizlenir, kaydırma sürükleyerek olmaz)
SOL_PANEL_KAYDIRMA_CUBUGU_RENK = "#d9dee5"     # ray (silik)
SOL_PANEL_KAYDIRMA_TUTAMAK_RENK = "#6b7280"    # tutamak

# ==================== ÇALIŞTIRMA MODU (Qt / tarayıcı) ====================
# Gösterim iki yoldan biriyle yapılabilir; ikisi de AYNI veriyi, AYNI kuralları ve
# AYNI görünümü kullanır:
#   "qt"       → PyQt6 penceresi (bu depodaki referans uygulama; varsayılan)
#   "tarayici" → Chromium kiosk modu; `WEB_KLASORU` içindeki HTML/JS arayüzü açılır.
# Tarayıcı şu adresle başlatılır:  http://<adres>:<port>/index.html?clientID=<cihaz>
# Cihazın kendi kimliğini (makinebilgileri.json → clientID) URL'de alması yeterlidir;
# sayfa veriyi kendisi çeker (yerel dosyalardan ya da `DOSYA_ADRESI`'nden).
CALISTIRMA_MODU = "qt"                    # "qt" | "tarayici"
TARAYICI_YOLU = "chromium"                # tarayıcı çalıştırılabilir dosyası
TARAYICI_EK_BAYRAKLAR = ""                # boşlukla ayrılmış ek Chromium bayrakları
TARAYICI_PROFIL_KLASORU = ".tarayici-profil"   # kalıcı profil (disk önbelleği burada kalır)
TARAYICI_PENCERE_BOYUTU = "1920,1080"     # --window-size (kiosk modunda yok sayılır)
TARAYICI_OTOMATIK_DERLE = True      # web/dist bayatsa açılışta `npm run build`
TARAYICI_YENIDEN_BASLAT_S = 5             # tarayıcı kapanırsa kaç saniye sonra yeniden açılsın
WEB_KLASORU = "web"                       # HTML/JS arayüzünün bulunduğu klasör (proje kökü altında)
WEB_SUNUCU_ADRESI = "127.0.0.1"           # yerel sunucu (yalnızca bu makineden erişilir)
WEB_SUNUCU_PORTU = 8090
# ---- Tetikleme (panel yayını → cihaz anında yenilenme)
TETIK_AKTIF = True                       # False: panel tetikleyicisi yok sayılır (normal aralıkta güncellenir)
TETIK_MODLAR = ("qt", "tarayici")        # oto tetiklemenin geçerli olduğu çalışma modları
# ---- MQTT push (600+ cihaz: sabit bağlantı, olay başına mesaj)
TETIK_PUSH_AKTIF = False                 # True: cihaz broker'a bağlanır, yayında ANINDA yenilenir (~100 ms)
TETIK_PUSH_BROKER = ""                   # ör. "xxxxx-ats.iot.eu-central-1.amazonaws.com" ya da kendi sunucunuz
TETIK_PUSH_PORT = 8883                   # 8883 = TLS (önerilir)
TETIK_PUSH_KONU = "yourkiosk/yayin"      # panelin yayın yaptığı konu
TETIK_PUSH_KULLANICI = ""
TETIK_PUSH_PAROLA = ""
# AWS IoT Core gibi X.509 isteyen broker'lar için (boşsa kullanıcı/parola yolu):
TETIK_PUSH_CA = ""                       # kök CA dosyası (ör. AmazonRootCA1.pem)
TETIK_PUSH_SERTIFIKA = ""                # cihaz sertifikası (cert.pem)
TETIK_PUSH_ANAHTAR = ""                  # cihaz özel anahtarı (private.pem.key)
TETIK_KONTROL_MS = 20000                 # TARAYICI modunda uzun yoklama (`/degisiklik`) sırasında
                                         # `tetikle.json`u çekme aralığı. `DAMGA_KONTROL_MS` ile
                                         # TAVANLANIR (tarayici.py: min(TETIK_KONTROL_MS, DAMGA_KONTROL_MS)),
                                         # yani "anlıklık" en kötü 20 sn'de bir tetik çekimiyle gelir.
                                         # Qt modunda kullanılmaz (orada QTimer + yerel izleyici var).
                                         # İndirme KOŞULLU (ETag/Last-Modified → 304): dosya değişmediyse
                                         # gövde inmez, istek başına maliyet birkaç yüz bayt.

WEB_VERI_MODU = "yerel"                   # "yerel": veri dosyaları yerel sunucudan | "https": DOSYA_ADRESI
WEB_YENILEME_MS = 60000                   # sayfanın veriyi kontrol etme aralığı (kiosk: saatlik timer)

# ==================== ÖNBELLEK (maliyet + performans) ====================
# Cihaz, veri dosyalarını ve yayın görsellerini DİSKTE saklar; aynı içerik tekrar
# gösterilirken internet kullanılmaz. `lastupdate.json` değeri değiştiğinde veri
# önbelleği otomatik olarak geçersiz sayılır ve içerik yeniden alınır.
# Süresi geçen (son gösterim tarihi + saklama süresi geçen) görseller cihazdan
# kendiliğinden silinir; toplam boyut üst sınırı aşılırsa en eski kullanılanlar atılır.
ONBELLEK_AKTIF = True                 # ana anahtar (paneldan kapatılabilir)
ONBELLEK_KLASORU = "onbellek"         # proje kökü altındaki klasör (.gitignore)
ONBELLEK_MAKS_BAYT = 512 * 1024 * 1024     # toplam önbellek üst sınırı (512 MB)
ONBELLEK_GORSEL_SAKLAMA_GUN = 2       # son gösterimden sonra kaç gün daha tutulsun
ONBELLEK_VERI_LASTUPDATE_KULLAN = True   # lastupdate değişmediyse veriyi ağdan çekme
ONBELLEK_GORSEL_LASTUPDATE_YENILER = True  # veri değişince görselleri bir kez tazele

# ==================== ÇALIŞMA KURALI ====================
# Kiosk cihazı o günün nöbetçisini 08:30'dan ertesi gün 08:30'a kadar gösterir;
# bu saatten önce hâlâ dünün nöbeti geçerlidir.
NOBET_DEGISIM_SAATI = (8, 30)
# Telefon/adres boşsa liste, detay ve alt kuşakta "-" yerine bölge adı gösterilir
EKSIK_TELEFON_YERINE_BOLGE = True
# =======================================================

# ================= ALT KUŞAK (yayın ekranındaki kayan yazı) =================
# Değerler 1080p için verilmiştir; başka çözünürlükte `scale` ile ölçeklenir.
KUSAK_YUKSEKLIK = 110          # kırmızı şeridin yüksekliği (px)
KUSAK_ALT_BOSLUK = 50         # şeridin ekranın alt kenarından yukarıda kalacağı boşluk (px)
KUSAK_YAZI_PUNTO = 36         # yazı puntosu
KUSAK_HIZ = 5                 # liste modunda her adımda sola kayma (px)
KUSAK_ADIM_ARALIGI_MS = 30    # adımlar arası süre (ms)
# True : eczaneler TEKER TEKER; sağdan ortaya gelir, bir süre durur, soldan çıkar
#        (nöbet listesi geçişiyle aynı InOutCubic yumuşatma)
# False: referans davranış — tüm liste tek metin hâlinde kesintisiz akar
KUSAK_TEKLI = True
KUSAK_GIRIS_MS = 1200         # sağdan ortaya gelme süresi
KUSAK_DURMA_MS = 3000         # ortada durma süresi
KUSAK_CIKIS_MS = 1200         # ortadan sola çıkma süresi
KUSAK_AYIRICI = "    |   "    # yalnızca KUSAK_TEKLI = False iken kullanılır

