# GÜVENLİK KILAVUZU — yourkiosk (eczane nöbet ekranı)

Bu belge **ne yapıldığını, neden yapıldığını ve nasıl doğrulanacağını** anlatır.
Kod okumadan, ölçümle kontrol edebileceğin şekilde yazıldı.

```bash
./run.sh --guvenlik-denetimi     # arayüz açılmaz, madde madde rapor verir (hata varsa çıkış kodu 1)
```

---

## 1. Tehdit modeli (neye karşı korunuyoruz?)

Kiosk cihazı **güvenilmeyen veri** ile çalışır: nöbet verisi ve yayın görselleri ağdan gelir,
yerel kopyaları diskte durur. Cihaz halka açık bir ekrandır, ağı ve dosyası kurcalanabilir.

| Tehdit | Örnek | Sonuç |
|---|---|---|
| Bozuk/kötü niyetli **görsel** | SVG/PDF/TIFF gövdesi, 40 MP "piksel bombası" | Qt çözücü açığı (CVE-2026-6210 sınıfı) → kod çalıştırma / çökme |
| **Ağ üzerinden yönlendirme** | izinli sunucu `302` ile `kotu.example`'a gönderir | kötü içerik indirme (izin listesi atlatma) |
| **Araya giren vekil (MITM)** | cihazda `https_proxy` tanımlı | trafiğin izlenmesi/değiştirilmesi |
| **Bozuk/aşırı veri** | 500 MB JSON, 60 seviye iç içe düğüm, `duration: 99999999` | bellek şişmesi, ekranın kilitlenmesi |
| **Ekranı yanıltma** | metinde U+202E (sağdan sola) kontrolü, satır sonu enjeksiyonu | sahte "eczane/telefon" gösterimi |
| **Qt eklenti açıkları** | kullanılmayan `libqsvg`, `libqvnc` diskte durur | uzaktan erişim (VNC) / çözücü CVE'leri |
| **Kimlik sızması** | günlüğe ham `clientID` yazılması | cihaz kimliğinin paylaşılması |
| **Dosya kurcalama** | veri dosyasının sembolik bağ ile değiştirilmesi | beklenmeyen dosya okuma |

---

## 2. Veri akışı ve denetim noktaları (şema)

```
                       ┌───────────────────────────────────────────┐
                       │  SUNUCU (https, izinli host + 443)         │
                       │  lastupdate.json · match.json ·            │
                       │  lastSystemData.json · makinebilgileri.json│
                       │  yayın görselleri (png/jpeg/webp)          │
                       └───────────────┬───────────────────────────┘
                                       │  (1) AĞ KAPISI  security/network.py
                                       │      • https zorunlu, izin listesi, yalnızca 443
                                       │      • kullanıcı bilgisi/denetim karakteri yok
                                       │      • yönlendirme: yalnızca aynı host
                                       │      • vekil (proxy) yok sayılır
                                       │      • TLS ≥1.2, sertifika doğrulaması
                                       │      • Content-Type beyaz listesi
                                       │      • boyut sınırı (Content-Length + okuma)
                                       ▼
      ┌────────────────────────────────┬──────────────────────────────┐
      │ (2) VERİ KAPISI                │ (2b) GÖRSEL KAPISI           │
      │ security/veri_dogrulama.py     │ security/image_policy.py     │
      │  • JSON bayt sınırı (4 MB)     │  • imza beyaz listesi        │
      │  • derinlik ≤32, düğüm ≤200k   │    (PNG/JPEG/WEBP)           │
      │  • symlink yok, kök dışı yok   │  • SVG/XML/HTML/PDF/GIF reddi│
      │  • metin temizleme (bidi/C0)   │  • başlıktan piksel bütçesi  │
      │  • sayı/liste sınırları        │    (≤4096×4096)              │
      └───────────────┬────────────────┴───────────────┬──────────────┘
                      │                                │
                      ▼                                ▼
        ┌──────────────────────────┐      ┌────────────────────────────┐
        │ (3) İŞ MANTIĞI            │      │ (3b) Qt GÖRSEL ÇÖZME       │
        │ core/sync.py             │      │ security/safe_image.py     │
        │  • lastupdate karşılaştır│      │  • biçim sabitlenir        │
        │  • cihaz ilçe/bölge bul  │      │  • setAllocationLimit(64MB)│
        │  • 08:30 gün kuralı      │      │  • politika geçmezse Qt'ye │
        │  • kayıt/yayın sınırı    │      │    HİÇ dokunulmaz          │
        └───────────────┬──────────┘      └──────────────┬─────────────┘
                        └────────────┬───────────────────┘
                                     ▼
                        ┌──────────────────────────────┐
                        │ (4) EKRAN (PyQt6)            │
                        │  sol liste / orta blok / kuşak│
                        └──────────────────────────────┘

   ┌──────────────────────────────────────────────────────────────────┐
   │ (0) AÇILIŞ ÖNCESİ: Qt EKLENTİ/KÜTÜPHANE KARANTİNASI                │
   │ security/qt_sertlestirme.py — QApplication kurulmadan önce çalışır  │
   │  kullanılmayan her şey .karantina/ altına taşınır (silinmez)        │
   └──────────────────────────────────────────────────────────────────┘
```

**Kural:** her katman kendi başına yeterli olacak şekilde yazıldı (derinlemesine savunma).
Örneğin SVG hem ağ katmanında (Content-Type), hem politika katmanında (imza), hem de
Qt eklentisi diskten kaldırıldığı için **üç kez** engelleniyor.

---

## 3. Sınırlar ne anlama geliyor? (büyüklük sorusu)

Sınırlar "veriyi kısmak" için değil, **absürt girdiyi yakalamak** için var. Bugünkü gerçek
verinin ölçüsü:

| Veri | Gerçek boyut | Not |
|---|---|---|
| `lastSystemData.json` (16 gün, 404 kayıt, 12 ilçe) | **262 KB** | en büyük dosya |
| 30 gün (üst sınır) çekilirse | ≈ **500 KB** | bugünkünün ~2 katı |
| `match.json` | 8 KB | ilçe/bölge/makine eşlemesi |
| `lastupdate.json` / `makinebilgileri.json` | < 100 B | tek alan |
| yayın görseli (havuzlu-bahce.png) | 2,5 MB | tek kare |

Bu yüzden eşikler **bugünkü verinin 8 katı** olacak şekilde seçildi — yani normal büyüme
(30 güne çıkmak, ilçe eklenmesi) sınırlara takılmaz; ancak **onlarca megabaytlık** bir dosya
(bozuk indirme, yanlış yere yazılmış dosya, kötü niyetli içerik) anında reddedilir.

| Ayar (`config.py`; `ayarlar.json` → `gelismis` ile değiştirilebilir) | Varsayılan | Neyi korur | Ne zaman artırılır |
|---|---|---|---|
| `MAX_JSON_BAYT` (`max_json_bayt`) | 4 MB | JSON gövdesinin belleğe alınması | Veri 30 günü aşıp ~2 MB'ı geçerse (ör. 90 gün) |
| `MAX_JSON_DERINLIK` (`max_json_derinlik`) | 32 | iç içe yapı ile özyineleme/DoS | Şema daha derinleşirse (bugün 4 seviye) |
| `MAX_JSON_DUGUM` (`max_json_dugum`) | 200 000 | aşırı büyük ağaç taraması | 30 gün ≈ 25 000 düğüm; 5× pay var |
| `MAX_GORSEL_BAYT` | 8 MB | görsel indirme | 4K poster görselleri eklenirse |
| `MAX_GORSEL_PIKSEL` | 4096×4096 | piksel bombası | 4K+ görsel gerekirse |
| `MAX_METIN_UZUNLUK` | 160 karakter | alan başına metin (adres) | Uzun adresler kırpılıyorsa |
| `MAX_GOSTERILEN_ECZANE` | 60 | tek ekranda liste | İlçede 60'tan çok bölge varsa |
| `MAX_AKTIF_YAYIN` | 20 | aynı anda yayın döngüsü | Aynı anda 20+ yayın olursa |
| `YAYIN_SURE_EN_COK_S` | 60 sn | yayında kilitlenme | Bilerek 1 dk'dan uzun gösterim istenirse |
| `HTTP_TIMEOUT_S` | 10 sn | asılı kalan indirme | Yavaş ağda (uydudan bağlantı) |

**"Yüzlerce megabayt" senaryosu:** veri gerçekten yüzlerce MB'a çıkacaksa (ör. 1 yıllık arşiv,
tüm ilçeler) sınır **config'ten yükseltilir** — ama o zaman bellek de o kadar büyür. Doğru
yaklaşım: veriyi sunucuda **gün bazında bölmek** (cihaz yalnızca bugünü çeker) ya da sıkıştırılmış
(`.json.gz`) aktarım; bu ikisi yapılırsa 4 MB sınırı rahatlıkla yeter.

Sınır aşımı **çökme değil** üretir: günlüğe `uyari`/`hata` yazılır, ekran son geçerli veriyi
göstermeye devam eder (`kiosk.kaynak`/`kiosk.veri_guvenlik` kayıtlarına bakılır).

**Bu sınırlar artık dışarıdan ayarlanabilir** (`ayarlar.json` → `gelismis` grubu; ileride yönetim
panelinden). Panel için "gelişmiş" sayılırlar çünkü standart kullanıcı bunlara dokunmamalıdır;
ancak veri 20–30 MB'a çıktığında tek satırla yükseltilebilir:

```bash
./run.sh --ayarlari-yaz      # ayarlar.json üret (içinde gelismis grubu da var)
# ayarlar.json:  {"gelismis": {"max_json_bayt": 33554432, "max_json_derinlik": 64, "max_json_dugum": 2000000}}
```

Her değerin alt/üst aralığı vardır (`max_json_bayt`: 64 KB – 512 MB, `max_json_derinlik`: 4 – 256,
`max_json_dugum`: 1 000 – 50 M). Aralık dışı ya da yanlış tipte değer **kabul edilmez**; gerekçesi
günlüğe ve `--guvenlik-denetimi` çıktısına yazılır, varsayılan kullanılır. Etkin değerler
`--guvenlik-denetimi` → "Sınırlar (DoS)" maddesinde görünür.

---

## 4. Qt kütüphane/eklenti temizliği (Arch bildirimleri + CVE süpürmesi)

**Arch deposu denetimi** (`security.archlinux.org`, 15.10.2026):

| Paket | Sürüm | Açık bildirim | Sonuç |
|---|---|---|---|
| `python-pyqt6` | 6.11.0-2 | **No issues** | temiz |
| `qt6-base` | 6.12.0-2 | yalnızca 2021'de kapanmış CVE (AVG-2281) | temiz |
| `qt6-svg` | 6.11.1-1 | yalnızca 2021'de kapanmış CVE (AVG-1768) | temiz |
| `qt6-imageformats` | 6.11.1-1 | **No issues** | temiz |
| `qt6-declarative` | 6.11.1-2 | **No issues** | temiz |

Yani **Arch paketlerinde açık bir Qt açığı yok**. Risk, PyPI tekerleğinden gelen Qt 6.11.2'de:
**CVE-2026-79680 (Qt VNC parola atlatma)** — düzeltme 6.11.3, ancak PyPI'da en yüksek sürüm
hâlâ **6.11.0** (yani düzeltilmiş tekerlek yok). Bu yüzden VNC eklentisi **kaldırıldı** ve
kullanılmayan tüm Qt yüzeyi temizlendi.

| Ölçüm | Önce (tekerlek) | Şimdi |
|---|---|---|
| `Qt6/lib` içindeki kütüphane | **96** | **12** (9'u Qt + 3'ü QtCore/Gui/Widgets'in zorunlu bağımlılığı olan ICU) |
| Eklenti dizini | **23** | **4** (platforms, imageformats, wayland-graphics-integration-client, wayland-shell-integration) |
| Platform eklentisi | 9 (vnc, eglfs, linuxfb, minimalegl, vkkhrdisplay, wayland, xcb, offscreen, minimal) | **4** (xcb, wayland, offscreen, minimal) |
| Görsel çözücü | 10 (svg, pdf, tiff, gif, icns, tga, wbmp, jpeg, webp, ico) | **3** (jpeg, webp, ico) |
| PyQt6 Python modülü | 35 | **6** (QtCore, QtGui, QtWidgets, QtDBus, QtTest, sip) |
| QML modül dizini | 19 MB (2160 dosya) | **0** |
| Karantinaya alınan | — | **2352 dosya / 156 MB** |

**Nasıl karar veriliyor (tahmin değil, ölçüm):** tutulacak dosyalar listelenir, sonra
`ldd` ile **gerçek bağımlılık kapanışı** hesaplanır — yalnızca gerçekten bağlı olan Qt
kütüphaneleri kalır, "yetim" kalan her şey (ör. QtMultimedia'nın getirdiği
`libavcodec`/`libicu`, ya da Wayland dekorasyon eklentisinin çektiği `libQt6Svg`) taşınır.

**Neden bunlar güvenli:** kaldırılan modüllerin listesi uygulamanın kullanmadığı
her şeydir (QML/Quick/Quick3D, PDF, SQL sürücüleri, Multimedia+FFmpeg, Sensors,
Bluetooth/NFC, Positioning, RemoteObjects, StateMachine, WebChannel, TextToSpeech,
OpenGL widget'ları, yazdırma, yardım, ağ bilgisi, 3B yükleyiciler). Uygulama yalnızca
**QtCore + QtGui + QtWidgets** kullanır; doğrulama: birim testleri + uçtan uca çalıştırma,
karantina sonrası yapıldı ve geçti.

**Geri alma (istediğin an):**

```bash
# tek bir dosyayı geri koy
cp .karantina/qt-kutuphaneleri/libQt6Svg.so.6 .venv/lib/python3.14/site-packages/PyQt6/Qt6/lib/
# ya da her şeyi
cp -r .karantina/qt-kutuphaneleri/. .venv/lib/python3.14/site-packages/PyQt6/Qt6/lib/
cp -r .karantina/qt-eklentileri/.   .venv/lib/python3.14/site-packages/PyQt6/Qt6/plugins/
cp -r .karantina/pyqt6-modulleri/.  .venv/lib/python3.14/site-packages/PyQt6/
cp -r .karantina/qt-qml/.           .venv/lib/python3.14/site-packages/PyQt6/Qt6/
```

Karantinayı tek seferlik atlamak: `./run.sh --karantina-yok`
(kalıcı kapatmak: `config.py` → `QT_EKLENTI_KARANTINA = False` / `QT_MODUL_KARANTINA = False`).

---

## 5. Doğrulama: ne çalıştırılır, ne görülür?

### 5.1 Güvenlik denetimi (arayüz açılmadan)

```bash
./run.sh --guvenlik-denetimi
```

Beklenen çıktı (bu cihazda alınan gerçek sonuç):

```
=============== GÜVENLİK DENETİMİ ===============
[UYARI] Qt sürümü
          Qt 6.11.2 / PyQt 6.11.0 (VNC CVE-2026-79680 düzeltmesi 6.11.3+)
[ OK ] Qt eklentileri (CVE sınıfı)
          riskli eklenti/kütüphane yok (1 dizin tarandı)
[ OK ] Ağ politikası (https/izin listesi/TLS)
          izinli host: hakkisabah.com, www.kocaelieo.org.tr, kocaelieo.org.tr ·
          port: (443,) · yönlendirme: yalnızca aynı host ·
          TLS min: TLSv1_2 · sertifika doğrulama: açık
[ OK ] Ortam vekil sunucuları
          ortam vekil sunucusu yok
[UYARI] Veri kaynağı
          kaynak: yerel dosya (üretimde https + DOSYA_ADRESI önerilir)
[ OK ] Genel kullanım (özellikler)
          açık: nobet_listesi, yayinlar, kayan_yazi, saat_tarih · KAPALI: - (ayar dosyası: …)
[ OK ] Veri dosyaları
          lastupdate.json: 42 bayt, izinler uygun · match.json: 8169 bayt, izinler uygun · …
[ OK ] Sınırlar (DoS)
          JSON: ≤4194304 bayt, derinlik ≤32, düğüm ≤200000 · metin ≤160 · kayıt ≤60 ·
          yayın ≤20 · yayın süresi 1-60 sn
[ OK ] Günlük
          günlük yazılabiliyor: …/kiosk/kiosk.log
================= 7 tamam · 2 uyarı · 0 hata =================
```

* **hata** varsa çıkış kodu **1** (systemd/autostart ile birleştirilebilir).
* İki `uyarı` bilinçlidir: (1) tekerlek Qt sürümü notu (VNC eklentisi zaten kaldırıldı),
  (2) veri kaynağı yerel dosya — sunucuya geçince kaybolur.

### 5.2 Otomatik testler

```bash
./tools/test.sh          # birim + güvenlik testleri
```

Kapsam: ağ kapısı (yönlendirme/vek/TLS/port/URL), JSON sınırları, symlink/kök denetimi,
metin temizleme (bidi/denetim karakteri), süre/liste sınırları, görsel politikası,
karantina (eklenti + kütüphane + modül), denetim raporu, veri akışı ve ekran davranışı.

### 5.3 Elle hızlı kontroller

```bash
# 1) Riskli Qt eklentisi kaldı mı? (boş çıkmalı)
ls .venv/lib/python3.14/site-packages/PyQt6/Qt6/plugins/platforms/       # vnc OLMAMALI
ls .venv/lib/python3.14/site-packages/PyQt6/Qt6/plugins/imageformats/   # svg/pdf/tiff/gif OLMAMALI

# 2) Qt hangi biçimleri çözebiliyor? (svg/pdf/tiff/gif OLMAMALI)
.venv/bin/python -c "from PyQt6.QtGui import QImageReader; print(sorted(bytes(f).decode() for f in QImageReader.supportedImageFormats()))"

# 3) Karantina içeriği ve boyutu
find .karantina -type f | wc -l ; du -sh .karantina

# 4) Günlükte engelleme izleri (son 50 satır)
tail -50 kiosk.log        # 'reddedildi', 'izin listesinde değil', 'sınırı aştı', 'karantinaya alındı'
```

---

## 6. Üretime alırken kontrol listesi

1. **Veri kaynağını sunucuya çevir:** `KAYNAK = "https"` + `DOSYA_ADRESI = "https://…/kiosk/"`.
   İzin listesini (`ALLOWED_HOSTS`) yalnızca gerçekten kullandığın alan adlarıyla sınırla.
2. **PyQt6 sürümü:** Arch'ta `python-pyqt6` + `qt6-base` (6.12.0) → VNC düzeltmesi dâhil, en temiz yol.
   Tekerlek kullanılıyorsa (bu kurulum) VNC eklentisi kaldırılmıştır; **6.11.3+ yayınlandığında**
   `pip install -U PyQt6` yapıp `--guvenlik-denetimi` ile yeniden doğrula (karantina idempotenttir).
3. **Ayrı kullanıcı:** kiosk'u root ile çalıştırma; veri/günlük dosyaları o kullanıcıya ait olsun
   (izin denetimi `--guvenlik-denetimi` içinde "Veri dosyaları" maddesinde görünür).
4. **Günlük takibi:** `kiosk.log` 512 KB × 3 dosyada döner. Haftalık göz at:
   `grep -E "hata|reddedildi|sınırı aştı" kiosk.log`.
5. **Yedek/geri dönüş:** kaldırılan her şey `.karantina/` altında (156 MB). Yer sıkıntısı olursa
   silinebilir; geri almak istediğinde `§4`'teki `cp` komutları yeterli.
6. **Düzenli kontrol (isteğe bağlı):** günlük bir systemd timer ile `--guvenlik-denetimi`
   çalıştırıp çıkış kodu 1 ise uyarı üret:
   `0 6 * * * cd /opt/yourkiosk && ./run.sh --guvenlik-denetimi || logger -t kiosk "güvenlik denetimi başarısız"`.

### Sorumluluk sınırı (dürüst not)

Bu belge ve kod, **uygulama katmanındaki** riskleri kapatır: güvenilmeyen görsel/JSON,
ağ politikası, ekran bütünlüğü, kullanılmayan Qt yüzeyi. Aşağıdakiler bu kapsamın dışındadır
ve cihaz/dağıtım tarafında ele alınır: fiziksel erişim (USB, klavye), işletim sistemi
güncellemeleri, disk şifreleme, ağ segmentasyonu (yayın sunucusuna erişim), günlüklerin
merkezî toplanması.



