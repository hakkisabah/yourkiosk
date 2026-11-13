# Chromium kiosk: başlatma bayrakları ve gerekçeleri

Argv sırası: `<tarayıcı> <bayraklar> --kiosk <url>` — URL **konumsal**, en sonda.

| Bayrak | Gerekçe / belirti |
|---|---|
| `--kiosk <url>` | Tam ekran, adres çubuğu yok. `--app=<url>` kullanma. |
| `--user-data-dir=<kalıcı yol>` | Profil kalıcı olur → HTTP/Cache Storage önbelleği ve çerezler yeniden başlatmada korunur. Varsayılan "geçici profil"dir, kiosk için maliyet/performans kaybı. Yol `.gitignore`lanır. |
| `--disable-gpu` + `--disable-gpu-compositing` | GPU/EGL yolu olmayan makinelerde boş/siyah pencere. Kiosk için GPU gerekmez. |
| `--disable-dev-shm-usage` | Küçük `/dev/shm` olan sistemlerde sekme çöker. `/tmp`e yönlendirir. |
| `--disable-background-networking` | Google servislerine arka plan trafiği (GCM, güncelleme, senkron) — gereksiz ağ ve günlük gürültüsü. |
| `--disable-component-update` | Bileşen indirme denemelerini kes. |
| `--disable-sync` | Hesap senkronu yok (kiosk hesabı yok). |
| `--noerrdialogs` | Tarayıcı hata kutuları ekranı kaplamasın. |
| `--disable-breakpad` | Çökme dökümü yazma; disk ve gizlilik. |
| `--autoplay-policy=no-user-gesture-required` | Kioskta kullanıcı etkileşimi yok; sesli/videolu yayın varsa şart. |
| `--enable-logging=stderr --v=1` | **Yalnızca teşhis kipinde**: tarayıcı konsolu terminale düşer. Sorun ayıklandıktan sonra kapat. |
| `--force-device-scale-factor=<n>` | Ekran ölçeklemesini sabitlemek gerekirse. |
| `--window-size=W,H` | Yalnızca pencere modunda anlamlı; kioskta yoksayılır. |

## Zararsız gürültü (arıza DEĞİL)

```
ERROR:google_apis/gcm/engine/registration_request.cc:291] Registration response error message: PHONE_REGISTRATION_ERROR
ERROR:google_apis/gcm/engine/registration_request.cc:291] Registration response error message: DEPRECATED_ENDPOINT
```

Google Cloud Messaging kaydı başarısız oluyor; açma/kapama ile ilgisi yoktur. `--disable-background-networking`
bunları genelde keser. Bu satırları "siyah ekranın sebebi" diye kullanıcıya sunmak, gerçek hatayı
gizler — doğrudan "zararsız, görmezden gelin" deyin.

## Başlatıcı davranışı

1. Tarayıcıyı bul: ayar değeri → `PATH` taraması → yedek adlar (`chromium`, `chromium-browser`,
   `google-chrome`, `brave`). Bulunamazsa **çıkış kodu 2** + net mesaj (`tarayici_yolu` ayarını yaz).
2. Sürümü sor (`--version`) ve asgari sürümün altındaysa uyar (kiosk + Cache Storage davranışı sürüme bağlı).
3. Arayüz kökünü seç (derlenmiş yoksa **açma**, çıkış kodu 4).
4. Veri dosyalarını önden denetle (cihaz kimliği bulundu mu) — sunucu açıldıktan sonra HTTP üzerinden
   de doğrulanabilir.
5. Günlüğe tam URL'i yaz (`…/index.html?clientID=…&veri=…`), süreci `Popen` ile başlat, kapanınca
   ayarlı saniye sonra yeniden başlat; **çökme döngüsü sınırı** koy (ör. 60 sn içinde 5 kez → dur ve
   günlüğe yaz).
6. `--kuru`: 1–4 adımlarını raporla, süreci başlatma.

## Headless doğrulama (gerçek tarayıcıyla test)

jsdom, mantığı sınar; **paketin gerçekten açıldığını, CORS'u ve konsolu** göstermez. Kurulu bir
chromium ikilisi varsa önce onunla doğrula. Ölçülmüş tuzaklar (Chromium/Chrome 130+):

| Deneme | Sonuç |
|---|---|
| `--headless=new` | `Multiple targets are not supported in headless mode` — 132+ sürümlerde bu değer kaldırıldı. Düz `--headless` kullan. |
| `--screenshot <yol>` (boşluklu) | Yol ikinci "target" sayılır → **aynı** hata. `--screenshot=<yol>` yaz (`=` zorunlu). |
| `--user-data-dir=<yol>` | Başsız kipte aynı hata ya da asılma. Başsız doğrulamada **verme**; kalıcı profil yalnız kiosk başlatmasının işidir. |
| `--dump-dom` | DOM'u verir; etiketleri soyup okunabilir metne çevirerek assert et. |

Asgari çalışan çağrı:

```bash
CHROME --headless --no-sandbox --disable-gpu --disable-dev-shm-usage \
       --virtual-time-budget=8000 --window-size=1920,1080 \
       --screenshot=/tmp/sayfa.png "http://127.0.0.1:<port>/index.html?clientID=..."
```

* **`ERR_CONNECTION_REFUSED` test aracının hatasıdır, ürünün değil.** Portu ezberden yazma: uygulama
  boş port seçiyorsa portu **logdan** al ve önce `curl -sI` ile ayakta olduğunu doğrula. Aynı şekilde
  "ekran görüntüsü alınamadı" genelde port/adres hatasıdır.
* Konsol hatalarını `stderr`den süz ama `mime_util_xdg`, `dbus`, `UPower`, GPU/VA-API satırlarını
  **zararsız gürültü** olarak ayıkla — bunları gerçek hata diye kullanıcıya sunmak asıl hatayı gizler.
* `--headless` ekran/GPU/X istemez; kioskun **görünür** moduyla karıştırma (o `--kiosk` ve X/Wayland ister).
* Kütüphane denetimi: `ldd $(command -v chromium) | grep 'not found'`. Eksikse tarayıcı "kurulu ama
  açılmıyor" görünür. Arch paketleri: `nss nspr libx11 libxcb libxcomposite libxdamage libxfixes
  libxrandr libxkbcommon mesa cairo pango at-spi2-core alsa-lib libcups fontconfig ttf-liberation`
  (Arch'ta `atk` → `at-spi2-core` içinde birleşti). `fontconfig` yoksa Chrome açılsa bile metin
  çizimi bozulur.
* Bu denetimi tek komuta indir: `ldd` → `--version` → **boş sayfa render'ı (PNG bayt sayısı)** →
  istenirse `--url` ile gerçek sayfa + konsol + ekran görüntüsü + DOM metni. Böylece "tarayıcı
  yeteneği var mı" sorusu tahmine değil ölçüme dayanır.

## Çıkış kodları (kabuk/autostart ile birleşsin)

| Kod | Anlam |
|---|---|
| 0 | Normal kapanış |
| 1 | Ayar/denedim hatası |
| 2 | Tarayıcı bulunamadı |
| 3 | Sunucu açılamadı (port dolu) |
| 4 | Arayüz derlenmemiş (`dist/index.html` yok) |
