---
name: pyqt6-kiosk-hardening
description: Use when hardening or testing PyQt6 kiosk apps.
version: 1.0.0
author: agents
license: MIT
metadata:
  agents:
    tags: [pyqt6, qt6, kiosk, security, headless-testing]
    related_skills: [python-debugpy, requesting-code-review]
---

# PyQt6 kiosk uygulamaları: sertleştirme + görüntüsüz test

## When to Use

Şu durumlarda yükle:

* PyQt6 ile kiosk/ekran uygulaması yazarken veya eski bir PyQt uygulamasını gözden geçirirken,
* güvenilmeyen görsel/JSON akışı olan bir Qt uygulamasını sertleştirirken (CVE triyajı + görsel
  politikası),
* Qt sistem kütüphaneleri kurulu olmayan, root erişimi bulunmayan bir makinede PyQt6 testlerini
  (pytest-qt, offscreen) çalıştırmaya çalışırken.

## 1. Sürüm ve CVE triyajı (ilk iş)

```bash
.venv/bin/python -c "from PyQt6.QtCore import QT_VERSION_STR, PYQT_VERSION_STR; print(QT_VERSION_STR, PYQT_VERSION_STR)"
strings .venv/lib/python*/site-packages/PyQt6/Qt6/lib/libQt6Core.so.6 | grep -E '^6\.[0-9]+\.[0-9]+$' | sort -u
```

`QT_VERSION_STR` derleme zamanı PyQt sürümünü gösterebilir; **gerçek Qt sürümünü** `libQt6Core.so.6`
içindeki sürüm dizesinden doğrula.

Kural: **`QImageReader.supportedImageFormats()` çıktısını yazdır.** PyQt6 tekerleği `svg`, `svgz`,
`pdf`, `tiff` çözücülerini birlikte getirir; güvenilmeyen görsel akışı olan her uygulamada saldırı
yüzeyidir. Qt SVG/XML sınıfı bilinen CVE'ler (düzeltme sürümleriyle): CVE-2026-6210 (marker type
confusion, 6.11.1+), CVE-2026-78253 (QXmlStreamReader özyineleme, 6.11.2), CVE-2026-79616 (Qt Quick
SVG yolu, 6.11.2), CVE-2026-79680 (Qt **VNC** parola atlatma, **6.11.3**). `platforms/` altındaki
`libqvnc.so` kullanılmasa da diskte durur — kaldır veya ≥6.11.3 kullan. Kullanılmayan modülleri
(QtQml, QtQuick, QtWebChannel, QtSql, QtPdf) kurma.

## 2. Güvenilmeyen görsel politikası (Qt'ye dokunmadan)

1. Bayt sınırı + sihirli bayt **beyaz listesi** (png/jpeg/webp); SVG/XML/HTML metin reddi; 
   `Content-Type` denetimi (`image/svg+xml`, `text/html` reddi).
2. Piksel bütçesi **başlıktan** (PNG IHDR, JPEG SOF0/2, WebP VP8X/VP8/VP8L) — çözmeden önce;
   böylece 100 baytlık "40 MP bomba" başlığı reddedilir.
3. Qt tarafında: `QImageReader.setDecideFormatFromContent(False)`, `setFormat(politikadan)`,
   `QImageReader.setAllocationLimit(MB)` ikinci savunma.

Bu kurgu Qt'siz test edilebilir (imza/başlık üretici yardımcılarıyla).

## 3. PyQt6 tuzakları (gerçek çökmeler / sessiz silinmeler)

* `QBuffer(QByteArray())` → **SIGSEGV**: geçici `QByteArray` çöp toplayıcıya düşer. Referansı
  fonksiyon boyunca canlı tut: `ba = QByteArray(data); buf = QBuffer(ba)`.
* **`QPixmap` üretmek `QGuiApplication` ister; yoksa süreç SIGABRT ile ölür**
  (`QPixmap: Must construct a QGuiApplication before a QPixmap`, core dump). Bir görsel doğrulama
  yardımcısını (`piksel_yukle`) hızlı denetim için düz betikten çağırmak süreci çökertir — çıktı
  "kod bozuk" gibi okunur. Harness/test içinde önce uygulamayı kur
  (`QGuiApplication.instance() or QGuiApplication([])`, `QT_QPA_PLATFORM=offscreen`); uygulama
  nesnesi istemeyen doğrulamaları `QImage` düzeyinde yap. Aynı yol toplu görsel küçültme/WebP
  kodlaması için de kullanılır: `QImage(...).scaled(...); img.save(out, "WEBP", 82)`.
* Yerleşime eklenmeyen ebeveyn widget (`layout.addWidget(bottom)` satırı unutulursa) Python
  kapsamından çıkınca **çocuklarını birlikte siler** →
  `RuntimeError: wrapped C/C++ object of type QLabel has been deleted`. Denetim:
  `from PyQt6 import sip; assert not sip.isdeleted(label)` (`import sip` çalışmaz, `PyQt6.sip`).
* Liste yeniden kurulurken `setParent(None) + deleteLater()`; aynı veri için yeniden kurma (imza
  karşılaştırması) yoksa vurgu/animasyon her yenilemede sıfırlanır.

## 4. Görüntüsüz (headless) test ortamı

```python
# conftest.py (kök) — Qt import edilmeden ÖNCE
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_CACHE_HOME", str(ROOT / ".cache"))
```

* `pytest-qt` Qt'yi `pytest_configure` aşamasında import eder; `LD_LIBRARY_PATH`'i conftest ile
  ayarlamak **yetmez**, süreç ortamında hazır olmalı → shell sarmalayıcı betikte (`scripts/test.sh`)
  ihraç et. Aksi hâlde `INTERNALERROR ... ImportError: libGL.so.1`.
* Qt sistem kütüphaneleri yoksa (libGL/libX11/libxkbcommon/fontconfig) ve root yoksa: Arch
  aynasından paketleri indirip proje içine aç (`bsdtar -xf`, `usr/lib` → `.qt-libs/lib`,
  `ldd | grep 'not found'` döngüsüyle çözümle; `https://geo.mirror.pkgbuild.com/<repo>/os/x86_64/`
  ve dosya adı için `https://archlinux.org/packages/<repo>/x86_64/<pkg>/json/`). Yalnızca
  QtCore/QtGui/QtWidgets + QPA/görsel eklentilerini hedefle; QtSql/QtTextToSpeech bağımlılıkları
  (libmysqlclient, libpq, libclntsh, libfbclient…) bilerek atlanır.
* `/etc/fonts/fonts.conf` yoksa Qt yazı tipi altyapısında çöker: `FONTCONFIG_FILE` ile asgari config
  üret (`<dir>font_dir</dir><cachedir>…</cachedir>`).

## 5. Yerleşim doğrulaması: ekran görüntüsü değil, ölçüm

Görsel denetim faydalı ama tekrarlanabilir değil; kalıcı kanıt üret:

* Yerleşim matematiğini Qt'siz sınıfta topla (`LayoutMetrics`) ve **toplam dikey bütçe == ekran
  yüksekliği** eşitliğini test et (taşma imkânsızlaşır). Sabit px toplamları (ör. 125+45+480+3+640)
  yaygın bir taşma kaynağıdır — kalan alanı hesapla, sabit değer kullanma.
* Listelerde `satır_yüksekliği = (kullanılabilir - boşluk*(n-1)) // n`; yazı boyutlarını satıra
  sığacak şekilde orantılı küçült; **okunabilir minimum satır yüksekliği** tanımla ve altına
  inilmesi gerekiyorsa listeyi **sayfala** (sayfa sınırı = kullanılabilir // (min_satır + boşluk)).
* Çalışma anında geometri denetimi: her satırın `y()+height()` değerini panel yüksekliğiyle
  karşılaştıran ve yazı yüksekliklerinin satıra sığdığını doğrulayan betik yaz; bunu birkaç
  çözünürlükte çalıştır. "Ekran görüntüsüne baktım"dan daha güçlü kanıt.
* **"Şu öğe kayboldu" raporunda önce kodu değil durumu ölç.** Öğe bir `QStackedWidget` sayfasında
  yaşıyorsa ve o sayfaya girilmesi veri tarafındaki bir koşula bağlıysa, "eksik" görünen şey hiç
  çizilmemiş olabilir. Canlı durumu dök: `stack.currentWidget().__class__.__name__`,
  `widget.isVisible()`, `geometry().getRect()`, `pixmap().width()`, çocuk öğenin `pos()/.x()`.
  Öğenin kaynak dosyası referansla `diff -q` sonucu **birebir aynıysa hata UI kodunda değil**
  veri/state tarafındadır — widget'ın kodunu kurcalamaya başlama.
* **Veri tarafındaki görünürlük kapısını doğrula.** Zaman penceresiyle açılan ekranlar (yayın,
  duyuru, kampanya) yalnızca pencere içindeyken gösterilir; veri üreteci pencereyi gün dışına
  yazarsa ekran hiç açılmaz ve öğesi "yok" sanılır. Pencereyi üreteçte parametre yap
  (ör. `--yayin-araligi 08:30-23:59`, `sablon` ile şablon saatleri) ve veriyi "şu an aktif kayıt
  var mı" testiyle kilitle.
* **Ekranın alt kenarına yapışan öğeler kiosk panosunda kırpılır (overscan); kuşak şeridi gibi bir
  bindirme katmanı yerleşime EKLENMEZ.** Tam ekran içeriğin (yayın görseli) altına `addWidget`
  ile konan şerit, görselin altında kalır ve altında boş/alakasız arka plan görünür. Doğrusu:
  görsel tek başına yerleşimde kalsın (tam ekran), şerit `QFrame(self)` olarak
  `resizeEvent`/`showEvent` içinde `setGeometry(0, yükseklik - alt_bosluk - şerit_h, genişlik, şerit_h)`
  + `raise_()` ile görselin **üstüne** bindirilsin. Şeride ölçeklenen bir **alt boşluk** ver
  (1080p'de ~30 px) ve biraz kalınlaştır (60→80 px); aksi hâlde "kodda var ama cihazda görünmüyor"
  şikâyeti gelir. Kardeş öğe (tam ekran görsel) kuşağı itemesin: `setMinimumHeight(1)` +
  `QSizePolicy.Ignored/Ignored`. Kanıt: `img_lbl.height() == widget.height()` (görsel tam ekran) ve
  `childAt(x, şerit_merkezi)` şeridi döner; piksel tarafında şerit satırı kırmızı, hemen üstündeki ve
  altındaki satırlar kırmızı değil.
* **Animasyon mantığını Qt'siz saf durum makinesine ayır, Qt'de yalnızca uygula.** Kaydırmalı yazı
  şeritleri istenip "nöbet listesi geçişiyle aynı his" denildiğinde referanstaki yumuşatmayı kopyala
  (ör. `QEasingCurve.Type.InOutCubic`, "nöbet geçişiyle aynı efekt" = InOutCubic). Euler
  yumuşatmasını `core/ticker.py` gibi bir modülde saf fonksiyon olarak yaz
  (`in_out_cubic(p)`), aşamaları adım sayacıyla yürüt (`giris_adim = giris_ms/adim_ms`, oran
  `0→0.5→dur→1.0`) ve konumu orandan hesapla:
  `x = şerit_genişliği - oran * (şerit_genişliği + yazı_genişliği)` — bu formülde **oran 0.5 her
  zaman tam ortaya** denk gelir, ayrı orta hesabı gerekmez. Testlerde `scroll_ticker()`'ı elle
  çağırarak aşamaları doğrula (gerçek zamanlayıcı beklemeden); `QPropertyAnimation` ile yazılan
  animasyon zaman bağımlı olduğu için birim testte kırılgan olur, GC de animasyonu ortada
  öldürebilir. Şerit
  yüksekliği/punto/alt boşluk/hız/adım aralığı ve "tek tek mi liste mi" modu `config` sabiti
  olsun (1080p değeri + `scale` ile çarpım); kullanıcı kod düzenlemeden ayarlayabilsin. Kayan
  yazıda "her kayıt ayrı slayt" isteniyorsa metni tek kayda indir, kayıt tamamen soldan çıkınca
  `index = (index + 1) % len(items)` ile sıradakini `x = screen_w`'den başlat; "liste hâlinde akma"
  davranışını bir config bayrağıyla korunabilir tut.
* **Görsel denetim yoksa/yanıt vermiyorsa kanıtı pikselden üret.** Ekran görüntüsünü
  `QImage(path).pixelColor(x, y)` ile tarayıp bölgenin baskın renklerini ve hedef renk/beyaz yazı
  piksel sayısını raporla (`scripts/ekran_dogrula.py`). "Kırmızı şerit + üstünde beyaz yazı var"
  iddiası böyle sayıyla kanıtlanır; aynı komut regresyonda tekrar çalıştırılır.
* **Mod geçişini test et, yalnızca widget'ı değil.** Kiosk ekranı öğe listesi bitince mod değiştirir
  (`manage_loop()`'u elle çağırarak ya da döngü aralığını kısaltarak) sürükle; sonra şeridin görünürlüğünü,
  görselin **üstünde** bindirilmiş olduğunu (`img_lbl.height() == widget.height()` + `childAt()`),
  alt boşluğu (`widget.height() - (şerit.y()+şerit.height()) == alt_bosluk`), hareketin yönünü ve
  aşamalarını (gir→ortada dur→çık→sıradaki) doğrula. Elle sürüklenen testte ilk konumu açıkça kur,
  çünkü zamanlayıcı arada birkaç piksel kaydırmış olur.

## 5b. Ağ kapısı: izin listesi tek başına yetmez

* **Yönlendirmeler izin listesini atlatır.** `urllib.request.urlopen` varsayılanı `3xx` yanıtlarını
  körü körüne izler: izinli sunucu `Location: https://kotu.example/…` verirse politika delinir.
  `HTTPRedirectHandler` alt sınıfı yaz ve `redirect_request` içinde `newurl`'ü **aynı doğrulama
  fonksiyonundan** geçir; ek olarak varsayılan olarak yalnızca **aynı ana makineye** izin ver
  (config bayrağıyla gevşetilebilir).
* **Ortam vekilleri MITM yoludur.** `build_opener(ProxyHandler({}), …)` ile vekilleri kapat; ayrıca
  `Accept-Encoding: identity` gönder ki sıkıştırılmış gövde bayt sınırını atlatmasın.
* **TLS'i açıkça sıkılaştır:** `ssl.create_default_context()` üstüne `minimum_version = TLSv1_2`,
  `verify_mode = CERT_REQUIRED`, `check_hostname = True`, `options |= OP_NO_COMPRESSION`.
* **URL doğrulamasını daralt:** yalnızca `https`, **yalnızca izinli port** (varsayılan 443 — aksi
  hâlde izinli host üzerindeki başka servislere SSRF), kullanıcı bilgisi yok, `\r\n`/boşluk yok,
  uzunluk sınırı, host karşılaştırmasında küçük harf + **sondaki noktayı** normalleştir
  (`hakkisabah.com.` aynı hosttur). `urlparse`'ın fragment'ı hosta dâhil etmediğini unutma:
  `https://host/x.png#@kotu.example` **geçerli** bir adrestir (testte yanlış beklenti kurma).
* **Test sırasında Python sürüm farkı:** Python 3.14'te `build_opener(ProxyHandler({}))` boş vekil
  tutamacını opener'a **eklemez**; "ProxyHandler var mı" diye test etmek kırılır. Doğru kanıt:
  `urllib.request.getproxies()`'in ortam vekilini gördüğünü göster, sonra hem varsayılan opener'da
  vekil taşıyan tutamaç bulunduğunu hem de **kendi opener'ında hiç vekil taşıyan tutamaç
  olmadığını** doğrula (`getattr(h, "proxies", None)`).

## 5c. Güvenilmeyen veriyi ekrana vermeden önce sınırla

* **Yerel dosya okuma da ağ okuması kadar denetlenmeli.** Aynı JSON kapısından geçir: bayt sınırı +
  **derinlik** ve **düğüm sayısı** sınırı (yığın tabanlı, özyinelemesiz sayaç), `symlink` reddi ve
  dosyanın proje kökü **içinde** olduğunun doğrulanması. Aksi hâlde bozuk tek dosya belleği şişirir.
* **Gösterilen metni temizle.** Kiosk bir *vitrin*dir: sunucu verisi C0/C1 denetim karakterleri,
  satır sonları ve **çift yönlü yazı kontrolleri** (U+202A–U+202E, U+2066–U+2069) taşıyabilir ve
  ekranı yanıltabilir (metni ters çevirme, sahte numara). NFC normalleştir, kontrol karakterlerini
  at, satır sonlarını sadeleştir, uzunluğu sınırla (kısaltıldığını `…` ile belli et).
* **Zamanlayıcıyı besleyen sayısal alanı sınırla.** `duration` gibi bir alan ekranın ne kadar süre
  kilitli kalacağını belirler: `sayi_sinirla(deger, alt, ust, varsayilan)` ile aralığa çek
  (ör. 1–60 sn). Ayrıca gösterilecek kayıt/yayın **sayısını** sınırla.
* **Kimliği günlüğe ham yazma.** `clientID`/cihaz kimliği gibi değerler için `sha256`'nın ilk
  10 hanesi + uzunluk yeter (`9827…(17h, sha256:…)`); tam değer gerekirse ayrı, kısıtlı bir dosyada.
* **Durum dosyalarını atomik yaz:** aynı dizine geçici dosya + `os.fsync` + `os.replace`, izin
  `0o600` (kısmi dosya kalmaz, başka kullanıcı okuyamaz).

## 5d. Qt eklentisi karantinası (CVE sınıfına karşı ikinci katman)

Politika SVG/PDF/TIFF/GIF'i reddetse bile PyQt6 tekerleği bu çözücüleri ve `platforms/libqvnc.so`
(VNC parola atlatma, CVE-2026-79680) diskte bırakır. Politikada bir hata olsa bile çözücü
**yüklenememeli**: riskli eklentileri silmek yerine `.karantina/qt-eklentileri/<alt-dizin>/` altına
`shutil.move` ile taşı (geri alınabilir, idempotent). Bunu **`QApplication` kurulmadan önce** yap ve
`QT_PLUGIN_PATH`'i kendi eklenti dizinine sabitle (kullanıcı dizininden eklenti yüklenmesin).
Kanıt: karantina öncesi/sonrası `QImageReader.supportedImageFormats()` listesini yazdır (`gif`,
`tiff`, `svg`, `pdf` kaybolmalı, `png/jpeg/webp` kalmalı) ve uygulamayı bir kez uçtan uca çalıştır.

## 5e. Sertleştirmeyi "ölçülebilir" kıl: öz kontrol komutu

Kullanıcı "neyi nasıl doğrulayacağım?" diye soruyorsa kod okutmak yerine **ölçen** bir komut ver:
`python3 main.py --guvenlik-denetimi` → Qt sürümü, riskli eklentiler, izin listesi/port/TLS özeti,
ortam vekilleri, veri dosyası izinleri/boyutları, sınırlar, günlük yazılabilirliği. Her madde
`(ad, tamam|uyari|hata, ayrıntı)`; hata varsa çıkış kodu 1 (autostart/systemd ile birleşir).
Rapor üretimi Qt'siz olmalı ki arayüz açılmadan da çalışsın.

## 5f. Qt yüzeyini ölçüp küçült: tekerlek "her şeyi" getirir

* **PyPI tekerleği Qt'nin tamamını taşır** (ölçülen: 96 Qt kütüphanesi, 23 eklenti dizini,
  19 MB QML, 35 PyQt6 modülü). Uygulama QtCore+QtGui+QtWidgets'ten fazlasını kullanmıyorsa
  gerisi **saldırı yüzeyidir**; kaldırmak için tahmin yürütme, **ölç**:
  `ldd` ile tutulacak dosyaların bağımlılık kapanışını hesapla (`subprocess.run(["ldd", f])`,
  `LibYolu`'nu `LD_LIBRARY_PATH` ile ver), kapanışta **olmayan** her `libQt6*.so.6`'yı taşı.
* **Tuzak 1 — tutulan bir eklenti kaldırılacak bir kütüphaneyi çeker:** Wayland *dekorasyon*
  eklentisi `libadwaita.so` üzerinden `libQt6Svg`'yi bağlıyordu; bu yüzden SVG "gerekli"
  görünüyordu. Çerçevesiz tam ekran kiosk dekorasyon istemez → eklenti düşürülünce SVG de gitti.
  Kural: **kapanışı yalnızca gerçekten tutulan dosyalar üzerinden hesapla, sonra tekrar ölç.**
* **Tuzak 2 — Qt dışı bağımlılıklar:** QtMultimedia'nın getirdiği `libavcodec/libswscale`,
  QtCore'un **zorunlu** bağımlılığı olan `libicu*`. Ayırt etme yolu: "hiçbir tutulan dosya
  başvuruyor mu?" sorusunu **her** dosya için (Qt dışı dâhil) sor; ICU kalır (QtCore/Gui/Widgets
  doğrudan bağlı), FFmpeg gider.
* **Tuzak 3 — test altyapısı:** `pytest-qt` için `QtTest` gerekebilir; kaldırma listesine almadan
  önce testleri çalıştır. `QtTest` üretimde kullanılmaz ama testlerde kalır (belge/furç).
* **Sonuç ölçümü raporla:** önce/sonra sayıları (kütüphane, eklenti dizini, modül, QML boyutu) ve
  kanıt: `QImageReader.supportedImageFormats()` (gif/tiff/svg/pdf kaybolmalı), 134 test, uçtan uca
  çalıştırma. Kaldırma **geri alınabilir** olsun: `.karantina/<grup>/` altına `shutil.move`, silme.
* **Paket sürümü tuzağı:** `requirements.txt`'e "düzeltilmiş" bir sürüm yazmak (ör. `PyQt6>=6.11.3`)
  PyPI'da o sürüm yoksa **kurulumu tamamen bozar**. Önce `pip index versions <paket>` ile en yüksek
  sürümü doğrula; düzeltme tekerleği yoksa **azaltıcı önlemi** (eklentiyi kaldır) uygula ve bunu
  belgeye yaz.
* **Saate bağlı test kırılganlığı:** veri penceresi (ör. yayın 08:30–23:59) dışında çalıştırılan
  testler gece yarısı toplu hata verir ve gerçek regresyonu maskeler. Yayın/mod penceresini
  fixture'da sabitle (`monkeypatch.setattr(BroadcastManager, "get_active_yayinlar", …)`), veri
  testini ise "aktif kayıt var mı" değil "pencere tutarlı mı" üzerinden yaz.

## 5g. Genel amaçlı hale getirme: özellik aç/kapa + dışarıdan ayar dosyası

* **Ayar dosyası = `config.py` varsayılanları + `ayarlar.json` üzerine yazma.** Değerleri
  `config`'e **runtime'da yaz** (`setattr(config, ...)`) ki mevcut okuma yerleri değişmesin;
  dosya yoksa davranış birebir aynı kalsın. Ayar dosyasını da aynı güvenlik kapısından geçir
  (boyut/derinlik/düğüm) — ayar dosyası bir saldırı vektörü olmasın.
* **Her anahtarın tipi + alt/üst aralığı olsun.** Panelden gelen `0`, `True` (sayı yerine),
  `"abc"` sessizce kabul edilmemeli: gerekçeyi Türkçe yaz, günlüğe ve öz kontrol raporuna koy,
  varsayılanı koru. Kullanıcı "gizli sınırlar" hissetmesin; hem örnek dosya (`ayarlar.ornek.json`)
  hem "her değeri yazdır" seçeneği (`--ayarlari-yaz`) ver.
* **Özellik kapatmayı yerleşim ameliyatıyla değil, "o görünüme hiç girmeme" ile yap.**
  Nöbet listesini kaldırmak = `QStackedWidget`'ta o sayfaya hiç geçmemek (tasarım birebir kalır).
  Kayan yazı/kuşak = bindirme katmanında `setVisible(False)`. Saat/tarih = metni boşaltmak
  (`setText("")`) — `setVisible(False)` yerleşimi kaydırır, boş metin kaydırmaz.
* **Anlamsız kombinasyonu yakala:** "ilki de kapalı ikincisi de kapalı" gibi durumlarda ekranda
  gösterilecek hiçbir şey kalmaz; tutarlılık kuralı yaz (birini geri aç) ve uyar.
* **Saate/tarihe bağlı testleri veriden türet**, sabit tarih yazma: `sorted(veri["gunler"])[0]`,
  orta gün, son gün gibi. Aksi hâlde veri bir gün kaydığında (veya saat gece yarısını geçtiğinde)
  testler toplu kırılır ve gerçek regresyonu maskeler. Yayın/mod penceresini fixture'da sabitle.
* **Açık kaynak paylaşımı için depo hijyeni:** `.gitignore` ile `.venv/`, `.qt-libs/`,
  `.karantina/`, `_arsiv/`, `.cache/`, günlükler **ve cihaza özel veri** (clientID içeren
  `makinebilgileri.json`, üretilen `lastSystemData.json`/`match.json`/`lastupdate.json`) dışlanır —
  tasarım varlıkları (`bg_layout/`, `font/`) ve `sablon.json` depoya girer. Kanıt: geçici bir
  dizinde `git init` + `git check-ignore -v <yol>` ile tek tek doğrula (`git add -A` sonrası
  `git diff --cached --name-only` listesi gerçekten beklenen mi?).
* **Örnek veri üreteci, gerçek veriyi sessizce ezmesin:** hedefte gerçek cihaz kimliği varsa
  dur ve `--zorla` iste. Aksi hâlde bir demo çalıştırması kullanıcının canlı verisini yok eder
  (bu tuzak gerçekten yaşandı: geri yükleme, doğru `clientID` + veri üretecinin yeniden
  çalıştırılmasıyla yapıldı).

* **Zaman penceresi olan kayıtları "anahtar" ile değil, kaydın KENDİ `start`/`end` aralığıyla seç.**
  Gün anahtarı + "değişim saati" sezgisi ("08:30'dan önce dünün anahtarı") veri bir gün eksikse
  sessizce yanlış güne atlar. Doğru kural: `start <= şimdi < end` olan kayıt gösterilir (yarı açık
  aralık — kayıt kendi bitiş anında devreder). Pencere yoksa sırayla: **en son biten** kayıt →
  başlamamış en yakın kayıt (+ günlüğe "veri tazelenmeli" uyarısı). Bunu üç durumla test et:
  sınır anı (08:29/08:30), yalnızca geçmiş veri, yalnızca gelecek veri.
* **Veri çekicinin başlangıç tarihini "devam eden pencereyi kapsayacak" şekilde otomatik seç.**
  Değişim saatinden önce çekim yapılıyorsa başlangıç **dün**, sonra **bugün** olmalı; aksi hâlde
  gece yarısı çekilen veri devam eden nöbeti içermez ve ekran bir sonraki günün listesine atlar.
  Bu kural aynı zamanda kaynağın "geçmiş başlangıcı yalnızca değişim saatinden önce kabul etme"
  sınırıyla uyumludur; elle geçersiz kılma (`--baslangic`) kapısını açık bırak.
* **Az öğe varken "kalan alanı böl" yaklaşımı öğeleri şişirir.** Satır yüksekliğini
  `kullanılabilir // max(TABAN, n)` ile hesapla: n < TABAN iken referans (ör. 5 satırlık) boyut
  korunur, n > TABAN iken taşmayı önlemek için küçülür (kaydırma sonraki adım). TABAN'ı config/ayar
  dosyasına koy; testte "2 öğe ile 5 öğe aynı yükseklik" ve "7 öğede taşma yok, hepsi eşit"
  iddialarını ölç.

* **Kaydırılabilir liste (liste tabanı aşınca): satır yüksekliğini TABANA göre sabitle, içeriği kaydır.**
  `item_h = (ekran - boşluk - spacing*(taban-1)) / taban` → öğe sayısı azken de çokken de aynı boyut.
  Öğe sayısı tabanı aşınca çerçeveleri bir `QScrollArea` içine taşı (widgetResizable=True, yatay çubuk kapalı)
  ve sayfalar arasında `QPropertyAnimation(scrollbar, b"value")` ile in/out-cubic kaydır; son sayfadan
  sonra başa dön. **Tuzak:** `verticalScrollBar().maximum()` YALNIZCA pencere gerçekten gösterildikten
  sonra hesaplanır — başlangıçta okursan 0 görürsün ve kaydırma hiç başlamaz. Çözüm: içerik yerleşimini
  `layout().activate()` ile zorla, sayfa hedeflerini her geçişte yeniden hesapla ve hedef boşsa
  zamanlayıcıyı yeniden başlat. Testlerde `pencere.show()` + `processEvents()` şart, aksi hâlde
  çubuk aralığı 0 kalır. Kaydırma çubuğunu `verticalScrollBar().setStyleSheet(...)` ile biçimlendir —
  üst widget'a stylesheet vermek çerçevelerin kendi görsel/stil kurallarını etkileyebilir.
* **Kaydırmayı KENDİ zamanlayıcısıyla sürme — vurgu/aktif öğe değişimiyle senkronla.**
  Ayrı bir QTimer ile sayfa sayfa kaydırmak, ana içerik animasyonundan bağımsız çalışır ve
  kullanıcı "orta slider değişmeden 1-2 sn önce sol panel aşağı-yukarı zıplıyor" der. Doğrusu:
  aktif öğe değişimini yapan fonksiyonun (`update_display`) sonunda kaydırmayı tetikle ve animasyon
  süresini ana geçişle AYNI yap (ör. 1800 ms). Hedef hesabı: aktif öğe görünürse DOKUNMA;
  y < konum → y'ye kaydır; y + h > konum + görünür → y + h - görünür'e kaydır (monoton, zıplamaz).
* **Satır konumunu okurken yerleşim henüz hesaplanmamış olabilir:** `çerçeve.y()` tüm satırlar için
  0 dönebilir (özellikle testlerde). Önce `icerik.layout().activate()` çağır; y yine 0 ve indeks > 0 ise
  aritmetiğe düş (`indeks * (yükseklik + spacing)`). Ayrıca `verticalScrollBar().maximum()` 0 ise
  kaydırılacak bir şey yoktur — o durumda hedef 0 dön, sonra yeniden dene.

## 6. Mimari: Qt'siz çekirdek, ince Qt katmanı

`config` / `models` / `phone` / `scaling` / `schedule` / `imagepolicy` / `fetcher` Qt'siz olsun;
`qtimage` / `service` / `ui` Qt'ye dokunsun. Ağ işini mutlaka `QThread` worker'a taşı — ağ çağrısı
GUI iş parçacığında ekranı dondurur ve kiosk'ta saat/kayan yazı durur. UI testlerinde gerçek servis
yerine sinyal/slot arayüzünü taşıyan `FakeService` kullan (ağ yok, deterministik).

## 7. Referans sürümden geçiş (yeniden yazım)

* Eski sürümün **saf mantığını** `tests/reference_impl.py` olarak kopyala (telefon biçimlendirme,
  sıralama, zamanlama kuralları) ve yeni sürümle **birebir karşılaştırmalı** testler yaz — geçişin
  davranışı bozmadığını kanıtlar.
* Amaçlı davranış değişikliklerini (ör. tekrar kayıt ayıklama, pencere seçimi, sayfalama) ayrı
  testlerle ve bir analiz belgesinde gerekçesiyle listele.
* **Canlı API gövdesini mutlaka indirip şemayı doğrula**; eski kodun varsaydığı şema (ör. düz sözlük)
  ile gerçek şema (ör. tarih→bölge→liste) sık sık ayrışır ve uygulama canlıda boş ekran gösterir.
  Doğrulanan gövdeyi proje içinde örnek olarak saklayıp testlerde kullan (`curl` çıktısını dosyaya yaz).
* **Çalışma modelini (cihaz/ilçe/bölge, gün dönümü saati, veri aralığı kuralları) kod yazmadan önce
  netleştir.** Bunları varsaymak iskelet şemasını kaydırır ve iş baştan yapılır; somut cihaz odaklı
  veri akışı için `references/cihaz-veri-akisi.md` dosyasına bak.
* **Tasarıma dokunma kuralı.** Kullanıcı bir referans/tasarım sahibiyse: referansı **birebir kopyala**
  ve yalnızca sana söylenen katmanı değiştir (veri kaynağı, güvenlik, hata yönetimi). Punto, renk,
  oran, `setFixed*`, `setContentsMargins`, ölçek satırlarına **dokunma**; referansın kendi kusurunu
  (ör. dikey taşma) sessizce "düzeltme" — rapor et, kararı kullanıcı verir.
* **Kanıtı mekanik üret, hafızadan değil:** dokunmadığını iddia ettiğin dosyalar için `diff -q`, ve
  tasarım tokenlarını iki sürümden çıkarıp karşılaştır:
  `grep -nE 'QFont\(|#[0-9a-fA-F]{6}|setFixed|setContentsMargins|setSpacing|0\.[0-9]+|int\([0-9]+ \* ' x.py | sed 's/^[0-9]*://;s/^ *//' > /tmp/x.txt` → `diff /tmp/ref.txt /tmp/yeni.txt`.
* Kullanımdan kalkan yaklaşımı (eski veri dosyaları, tarih kaydırıcı aracı) **silme**, `_arsiv/`
  altına taşı; bir sonraki tur baştan yazmak zorunda kalmaz, kullanıcı isterse siler.

## 8. Veri/metin tuzakları (bu ekosistemde tekrar eden)

* **Türkçe karşılaştırma:** `"İzmit".casefold()` birleşik nokta (U+0307) üretir; doğrudan
  `casefold()` eşitliği Türkçe adlarda tutmaz. Karşılaştırmadan önce sadeleştir:
  `str.maketrans("İIıŞşĞğÜüÖöÇç", "iiissgguuoocc")` + `translate` + `.casefold()` + `\u0307` sil.
* **Tarih metni dönüştürürken biçimi koru.** Girdi biçimini her metin için ayrı algıla ve aynı
  desenle yeniden yaz (`%d/%m/%Y %H:%M` → `%d/%m/%Y %H:%M`); ISO'daki kesir hanesini (`.468`)
  koru (`timespec="milliseconds"`). Testte değeri değil **biçimi** kilitle:
  `re.sub(r"\d", "#", yeni) == re.sub(r"\d", "#", eski)` ve uzunluk eşitliği.
* **Offscreen ekran ölçüsü hedef çözünürlük değildir.** `QApplication.primaryScreen()` offscreen
  platformda küçük bir sanal ekran (ör. 800x800) bildirir; referans kod ölçeği buradan hesaplıyorsa
  ölçümler yanıltır. Ya ölçüleri dışarıdan enjekte et (metrics parametresi) ya da raporlarken hangi
  ekran ölçüsüyle üretildiğini açıkça yaz. Hedef çözünürlüğü (ör. 1920x1080 → `scale = 1.0`)
  ölçmek için uygulamayı kurmadan önce ekranı taklit et:
  `QApplication.primaryScreen = staticmethod(lambda: SahteEkran())` (SahteEkran.availableGeometry
  `QRect(0,0,1920,1080)` döner). Pencere gerçekte küçük kalsa bile geometri/punto değerleri hedef
  ölçekle doğrulanır; yazının görünür bölgede olduğu bir kare almak için etiketi elle `move()` et.

## 9. İkinci gösterim modu (tarayıcı / Chromium kiosk)

* Gösterim modu **ayar grubunda** seçilir (`mod = qt | tarayici`); giriş noktası modu okur ve **Qt'yi
  hiç import etmeden** tarayıcı yoluna dispatch eder — yerel araç seti kurulu olmayan cihazda da
  çalışsın, tkinter/PyQt çekirdeğe sızmasın.
* İki mod **tek doğruluk kaynağını** okur: aynı ayar dosyası, aynı veri dosyaları, aynı cihaz kimliği.
  Web tarafına ölçü/punto/renk/görsel yolu **elle yazılmaz** (bu şemada "tasarıma dokunma" kuralının
  tarayıcı karşılığı): yerel koddan üretilir ve üreticinin güncelliği testle kilitlenir.
* Davranış kuralları portlanırken **yapıya** göre yaz (yerel taraf ilçe/bölge süzmeyi ağaç
  anahtarlarıyla yapıyorsa port da öyle yapsın); kayıt içi alanlara göre süzmek, alanların dolu
  olduğu gerçek veride farkı gizler.
* Ayrıntı (yerel sunucu/URL sözleşmesi, kiosk bayrakları, Cache Storage, tarayıcısız doğrulama, boş
  ekran teşhisi): `browser-kiosk-display-mode` şemsiyesi.
