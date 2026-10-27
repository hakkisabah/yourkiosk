# Görsel mimarisi: kimlik, paylaşım, expire, sıkıştırma

Bu belge **ölçüme dayalı** kararları içerir. Sayılar bu depodaki gerçek görsellerle üretildi.

---

## 1) Bugün görsel kimliği nasıl? (ID mimarisi)

**Kısa cevap: içerik değil, ADRES kimlik.** `kiosk/core/onbellek.py`:

```python
gorsel_anahtari(url) = sha256(url)[:32] + uzantı      # ör. 567b9357…1091.png
```

| Durum | Bugünkü sonuç |
|---|---|
| Aynı dosya, **iki farklı adres** | **2 kopya** iner ve saklanır (dedupe yok) |
| Aynı adreste **içerik değişti** | Anahtar aynı kalır → ETag/304 ile fark edilir (23.10'da düzeltildi) |
| Adrese `?v=2` eklendi | **Yeni anahtar** → eski dosya öksüz kalır (bakım siler) |
| 60 yayın kaydı, 2 farklı adres | 2 dosya (adres bazlı dedupe çalışıyor) |

Bugünkü 60 kayıt / 2 adres durumu için yeterli. **Ölçekte yetersiz**: aynı afişi 10 bölge için
10 kez yüklemek 10 kopya demek.

### Öneri: içerik adresli kimlik (content-addressed)

```
kiosk/yayin-gorselleri/<sha256(byte)[:16]>.<ext>     ör. 9f2c1ab34de5f607.webp
```

Kazançlar:
- **Tekilleştirme**: aynı bayt → aynı ad → tek kopya (cihazda ve S3'te)
- **Değişmez URL**: içerik değişirse ad değişir → `Cache-Control: immutable, max-age=1y`;
  cihaz **ETag doğrulaması bile yapmaz** (istek trafiği ~0)
- **Önbellek zehirlenmesi yok**: aynı ad her zaman aynı bayt
- **Silme güvenli**: referans sayımı ile "kimse kullanmıyorsa sil"

Geçiş planı iki adımlı olabilir (kırılma olmadan):
1. Panel yüklerken içerik-adlı yaz (URL zaten hash taşır) → cihazda hiçbir şey değişmez.
2. Cihazda `url → hash` dizini eklenirse dış adresler (ör. `hakkisabah.com/api/x.png`) da
   tekilleştirilebilir; bugün buna gerek yok.

---

## 2) Aynı görsel, farklı bölgeler; bir bölgenin yayını erken bitti

Cihaz temizliği **cihazın kendi verisine** bakar (`core/data_handler.py`):

```python
gecerli_url = { y["contentUrl"] for y in self.yayinlar }        # cihazın verisindeki TÜM adresler
onbellek.bakim(gecerli_url_kumesi=gecerli_url)
```

| Senaryo | Bugünkü davranış | Değerlendirme |
|---|---|---|
| A bölgesi bitti, B devam ediyor | A cihazı kendi verisinde adresi görmez → siler (7 gün sonra). B cihazı görür → **tutmaya devam eder** | ✅ Doğru; bölgeler birbirini etkilemez |
| Aynı adres 2 yayında (biri bitmiş) | Adres hâlâ "geçerli küme"de → **silinmez** | ✅ Doğru (en erken bitişe göre silmek hatalı olurdu) |
| Panel yayını silip 2 dk sonra geri ekledi | Veri setinde yok → cihaz **hemen siler**, geri eklenince **yeniden indirir** | ⚠️ Gereksiz indirme fırtınası |
| Cihaz çevrimdışı, yayın bitti | 7 gün sonra diskten silinir | ✅ |
| Yeni cihaz kurulumu, yayın bitmiş | S3'te nesne yoksa gösteremez (ama göstermesi de gerekmez) | ✅ |

**Bugünkü sınır:** `Yayinlar` kayıtlarında **bölge/ilçe alanı yok** (yalnız `start/end/contentUrl/duration`).
Yani "bölgeye özel yayın" henüz veri modelinde yok; tüm cihazlar 60 kaydı görüyor. Bölge bazlı yayın
istenirse: kayda `ilceId`/`bolgeId` eklenir ve cihaz `gecerli_url` kümesini **kendi kapsamına göre**
süzer (`match.json`'daki ilçe/bölge).

### Öneri
1. **"Artık kullanılmıyor" silmesine 24 saat gecikme** (yanlışlıkla sil→yeniden indirme dalgasını kes).
2. **Referans sayımı**: aynı içerik N yayında → son referans düşene + pay kadar tut.
3. Cihazda **bölge süzgeci** (veri modeline `ilceId` eklendiğinde).

---

## 3) S3'te "yayının bitiş tarihine göre otomatik expire" gerçekten mümkün mü?

**Doğrudan mümkün değil.** S3 yaşam döngüsü kuralları şunları bilir:

| Kural | Ne yapar | Sınır |
|---|---|---|
| `Expiration.Days` | nesne **oluşturulduktan N gün** sonra sil | tarih nesneye özel değil |
| `Expiration.Date` | **sabit bir takvim günü** (kural bazlı) | o kurala uyan TÜM nesneler o gün silinir |
| `Filter.Tag` | etiketle seçim | etiket **değeri** dinamik tarih olamaz |
| Kural sayısı | kova başına **1000** | "her yayın için bir kural" ölçeklenmez |

Yani `end = 2026-10-30` bilgisini S3 kendiliğinden okuyamaz.

### Katmanlı çözüm (önerilen)

| Katman | Ne | Ne zaman |
|---|---|---|
| **1. Asıl** | Panel temizliği (VAR): `end + 2 saat` sonra kaydı veriden çıkarır, nesneyi S3'ten siler | panel açıldığında/yayında |
| **2. Emniyet** | EventBridge + Lambda (günde 1): `lastSystemData.json`'ı okur, `max(end)+pay` geçmiş ve **hiçbir yayında referansı olmayan** nesneleri siler | 1 kez/gün, ~0 maliyet |
| **3. Son çare** | Lifecycle: `kiosk/yayin-gorselleri/` → **90 gün** (45 değil) | sadece öksüzleri toplar |

Önek bazlı hızlı çözüm (Lambda istemezsen): yükleme öneki tarih taşısın —
`kiosk/yayin-gorselleri/2026-10-30/<hash>.webp` + `Expiration.Days=30`. Kaba ama işler;
dezavantajı: 30 günden uzun süren yayın görseli, yayın bitmeden silinebilir.

---

## 4) "S3'te sıkıştırma" var mı? (ölçüm)

- **S3 statik dosyayı sıkıştırmaz.** `Content-Encoding: gzip` yalnız yüklerken sen eklersen olur.
- **CloudFront otomatik sıkıştırma yalnız metin türlerinde** (html/css/js/json/svg). **Görseller hariç.**
- PNG/JPEG zaten sıkıştırılmıştır → yeniden gzip **kazanç vermez**, aksine bozar.

Gerçek kazanç **biçim dönüşümü**. Bu depodaki iki gerçek görselle ölçüm:

| Görsel | Boyut | Bit/piksel | WebP q82 (tam) | WebP q82 (1280px) | JPEG q85 (1280px) |
|---|---|---|---|---|---|
| `havuzlu-bahce.png` (1916×1080) | **2473 KB** | 9,79 | **211 KB (8,5%)** | **130 KB (5,3%)** | 185 KB (7,5%) |
| `filmss.png` (1920×1080) | 366 KB | 1,45 | **30 KB (8,2%)** | **18 KB (4,9%)** | 41 KB (11,2%) |

Qt tarafında **WebP destekli** (`security/image_policy.py` → `IZINLI_BICIMLER`), gerçek dosyayla test:
`211 KB → Qt OK 1916x1080`. Yani istemci tarafında değişiklik gerekmez.

Yan kazanç: **bellek**. 1916×1080 → **7,9 MB RAM**; 1280×721 → **3,5 MB**. Zayıf donanımda önemli.

> AVIF daha küçük olurdu ama bu Qt derlemesinde kayıtlı biçim değil → **WebP** doğru seçim.

---

## 5) Panelden görsel yükleme hattı (henüz yok — tasarım önerisi)

Bugün panel yalnız **adres** yazıyor (`contentUrl`); dosya yükleme yok. Yükleme eklendiğinde:

```
seçilen dosya
  → tarayıcıda decode (createImageBitmap)
  → en uzun kenar ≤ 1920 px (kiosk tam ekran; daha büyüğü boşa RAM)
  → WebP, quality 82, metadata (EXIF/GPS) atılır
  → sha256(byte) hesapla → ad: yayin-gorselleri/<hash16>.webp
  → S3'e PutObject  CacheControl="public,max-age=31536000,immutable"
  → yayın kaydına contentUrl = https://<dağıtım>/<ad>
```

Neden tarayıcıda: sunucu (Lambda) maliyeti yok, 600 cihazlık yayında tek seferlik küçük iş.
Alternatif: aynı işi yapan bir Lambda (tutarlılık + merkezî politika istenirse).

Kurallar:
- **Saydamlık (PNG alpha) varsa WebP korur**, JPEG'e çevirme (arka plan siyah olur).
- Kalite tabanı: fotoğraf için 82, düz renk/afiş için 88–92 (dosya zaten küçük).
- Üst sınır: 8 MB giriş, 1920 px çıkış (kiosk `MAX_GORSEL_BAYT`/`MAX_GORSEL_PIKSEL` ile uyumlu).
- Yükleme sırasında **cihaz ölçeğinde** boyut uyarısı göster: "2,4 MB → 211 KB (%91 küçüldü)".

### 5.1) BUGÜN ÇALIŞAN YOL: panelden görsel adresini değiştirme

Dosya **yükleme** yok (5. bölümdeki öneri), ama **adres düzenleme** var ve WebP geçişi bununla
yapılır. Adımlar (menüdeki adlar görünür; `VeriView` yalnız dosya adıdır):

1. Panelde soldan **Nöbet ve Yayınlar** → üstteki **Yayınlar (N gün)** sekmesi.
2. Değiştirmek istediğiniz satırda **Görsel** düğmesi → *Yayın görseli* penceresi.
3. Adresi yazın. Panel cihazın kurallarını uygular: `https`, kullanıcı adı/parola **yok**, port
   **443**, uzantı varsa `png/jpg/jpeg/webp` (uzantısız adres kabul — cihaz `image/png|jpeg|webp`
   içerik türüne bakar). Hata metni adresi geri basmaz (kimlik bilgisi ekrana sızmasın).
4. **Uygula** (yalnız taslağa yazar) → sayfadaki **Kaydet** (yayına alır) → **Bildir** (cihazları
   hemen tetikler; MQTT yoksa cihaz en geç **30 sn** içinde damgadan alır, MQTT bağlıyken yoklama
   120 sn'lik emniyet ağıdır — anlıklık push'tan gelir).
5. Cihazda doğrulayın: yeni adres önbellekte olmadığı için ilk turda iner.

Kurallar:
- **Aynı dosya adını (hash) yeniden kullanmayın.** Cihaz görseli `yayin-gorselleri/<hash>.webp`
  yolundaki önbellekten gösterir; içerik değişip ad aynı kalırsa eski görsel görünmeye devam eder.
  Yeni sürüm → yeni hash → yeni ad.
- Eski `contentURL`/`url`/`gorsel` alias'ları yazarken **temizlenir** (tek alan, tek gerçek).
  Okuma sırası tüketiciye göre:
  - **Qt**: `contentUrl → contentURL` (`core/data_handler.py:80`, `pharmacy_app.py:819`) — `url`/`gorsel` okunmaz.
  - **Tarayıcı modu**: `contentUrl → contentURL → url` (`web/src/veri/yayin.ts` `ADRES_ALANLARI`).
  (`gorsel` alanı hiçbir tüketicide okunmaz; yalnız eski kayıtları normalleştirmek için bilinir.)
- Kural kaynağı cihaz tarafıdır: `kiosk/security/network.py` (`gorsel_icin_ayarlar`: şema, kullanıcı
  bilgisi, port, herkese açık host) + `kiosk/security/image_policy.py` (içerik türü beyaz listesi
  `image/png|jpeg|webp`). Panel aynı kuralları uygular; tek fark: port, kimlik bilgisi ve host
  denetimi panelde erkenden yapılır ki operatör "kaydettim ama görsel çıkmıyor" durumuna düşmesin.
  (Panel DNS çözemediği için host denetimi literal/yazılı yerel adlarla sınırlıdır — `localhost`,
  `*.local`, `*.internal`, nokta içermeyen ad, 127/8, 10/8, 172.16/12, 192.168/16, 169.254/16, ::1.)

---

## 6) Maliyet: gerçek tablo (dürüst düzeltme)

Önceden "2,5 MB × 600 cihaz × sürekli indirme" varsayımıyla büyük rakam vermiştim. **304 düzeltmesinden
sonra bu geçerli değil**: içerik değişmedikçe gövde inmiyor.

| Kalem | Hesap | Aylık |
|---|---|---|
| Yoklama istekleri (600 cihaz, 300 sn — `durum.json` öncesi 3 dosyalı yolun tabanı) | 15,6 M istek | **$17,88** |
| Yeni kampanya indirmesi | 600 × 2,5 MB = 1,5 GB | **$0,13** (WebP ile $0,011) |
| S3 depolama (100 görsel × 200 KB) | 20 MB | **$0,0005** |
| CloudFront invalidation | `/*` = 1 path, ilk 1.000 ücretsiz | **$0** |

→ **Asıl maliyet istekler**, görsel boyutu değil. Yine de WebP'ye geçmek:
- ilk yükleme gecikmesini ~%90 azaltır (zayıf bağlantıda 2,5 MB → 211 KB),
- cihaz RAM'ini 7,9 MB → 3,5 MB'a indirir (1280 px),
- 600 cihazın eşzamanlı açılışında CDN patlamasını küçültür.

---

## 7) Karar tablosu

| # | İş | Kazanç | Efor | Risk |
|---|---|---|---|---|
| 1 | İçerik-adlı anahtar + `immutable` | dedupe, sıfır doğrulama trafiği | 0,5 gün (panel yükleme ile birlikte) | düşük |
| 2 | Panelde WebP yükleme hattı | %90 küçük dosya, RAM | 1 gün (**UI tasarımı onayı gerekir**) | düşük |
| 3 | Cihazda "kullanılmıyor" silmesine 24 sa grace | indirme fırtınası yok | 2 saat | çok düşük |
| 4 | S3 lifecycle 45 → 90 gün + günlük Lambda süpürücü | öksüz dosya yok | 2 saat + 0,5 gün | düşük |
| 5 | Bölge bazlı yayın (`ilceId`) | bölgesel kampanya | 1 gün (veri modeli + panel) | orta |

Sıralama önerisi: **3 → 1 → 2 → 4 → 5**.

---

## 8) UYGULANANLAR (24.10.2026)

### 8.1 Hedefleme (ilçe / bölge / cihaz) — veri modeli genişletildi

`Yayinlar.<id>` kaydına **isteğe bağlı** alanlar eklendi (geriye uyumlu; mevcut 60 kayıt değişmedi):

```json
{"start":"…","end":"…","contentUrl":"…","duration":30,
 "ilceId":"30607352906750376",   // boş/yok = kısıt yok
 "bolgeId":"73154087615041151",
 "cihazId":"98273648723468273"}  // en dar kapsam
```

| Kural | Davranış |
|---|---|
| Alanlar boş | tüm cihazlar (bugünkü davranış) |
| Birden fazlası dolu | **VE** — hepsi eşleşmeli |
| Eşleşmeyen cihaz | yayını **hiç görmez**, indirmez, önbelleğe almaz (maliyet düşer) |
| Alias'lar | `ilce_id`, `ilce`, `bolge_id`, `bolge`, `cihaz_id`, `clientID` de kabul |

Uygulama noktaları:
- Qt: `core/yayin_kapsam.py` (+ `BroadcastManager.get_active_yayinlar(..., ilce_id, bolge_id, cihaz_id)`)
- Tarayıcı: `web/src/veri/yayin.ts` → `kapsamUygun()` / `aktifYayinlar(..., cihaz)`; **havuza** girmeden süzer
- Testler: `kiosk/tests/test_yayin_kapsam.py` (14) + `web/tests/yayin-kapsam.test.ts`

> Not: `Yayinlar` bugün **bölge alanı taşımıyordu**; bu eklemeyle bölgesel kampanya mümkün.
> Panelde yayınlar salt-okunur görüntülendiği için **arayüz değişmedi**; alanlar veri dosyasından
> (ya da ileride yükleme ekranından) yazılır.

### 8.2 `durum.json` — yoklama turu 3 istek → 1 istek

Panel her kayıtta `durum.json` yazar:

```json
{"zaman":"…","lastupdate":"2026-10-24 09:11:58",
 "tetik":{"zaman":"…","ilceId":"","aciklama":"panel: sistem"},
 "komut":{"zaman":"…","id":"…"}}
```

Cihaz (`kiosk/core/durum.py`): tek istekle damgayı, tetikleyiciyi ve komut işaretini alır.
`durum.json` yoksa (eski kiosk/ilk kurulum) **eski üç dosyalı yola** düşer — kırılma yok.

### 8.3 Uyarlanabilir yoklama (maliyet)

Değerler **koddan** gelir (`kiosk/config.py` + `pharmacy_app.yoklama_araligi()`):

| Durum | Aralık | Kaynak | Gerekçe |
|---|---|---|---|
| MQTT **bağlı** (`TETIK_PUSH_AKTIF=true` ve bağlantı açık) | **120 sn** | `DAMGA_KONTROL_MS_PUSH` | anlıklık push'tan gelir; yoklama emniyet ağı |
| push **kapalı** ya da bağlantı **koptu** | **30 sn** | `DAMGA_KONTROL_MS_PUSH_YOK` | tek yol yoklama; gecikme yarım dakikayı geçmesin |

`TETIK_PUSH_AKTIF` varsayılanı `false` → **bugün sahada etkin aralık 30 sn**'dir. 1800 sn'lik eski
"tasarruf" bilinçli olarak kaldırıldı: push sessizce öldüğünde 30 dakikalık gecikmeye dönüşüyordu.
`calistirma.degisiklik_kontrol_ms` yalnız Qt'nin damga aralığını (`DAMGA_KONTROL_MS`) yazar;
çalışma anındaki aralık yukarıdaki iki sabitten gelir.

### 8.4 WebP hattı

- `panel/src/domain/gorselYukleme.ts`: doğrula → küçült (≤1920 px) → WebP q82 → `sha256[:16]` →
  `kiosk/yayin-gorselleri/<hash>.webp` → `Cache-Control: immutable`.
- `kiosk/tools/gorsel_webp.py`: mevcut görselleri toplu çevirir (`--s3` ile yükler).
  **Gerçek ölçüm (Qt kodlayıcısı):** `a.png 2473 KB → 221 KB (%91)`, `b.png 366 KB → 31 KB (%92)`.

## 9) MALİYET — yeni mimari (600 cihaz)

Birim fiyat: CloudFront $0,75/M istek · S3 GET $0,40/M istek. Qt `durum.json` yolu **1,3 istek/tur** (taban 1 + her 10 turda bir 3 ek istek: `lastupdate.json`,
`tetikle.json`, `komut.json` → 10 tur = 13 istek).
İstek/ay = 600 cihaz × (30,44 gün × 86 400 sn ÷ aralık) × 1,3.

| Senaryo | İstek/ay | CloudFront | S3 GET | **Toplam** |
|---|---|---|---|---|
| Eski: 3 dosya · 300 sn (yoklama öncesi taban) | 15,78 M | $11,84 | $6,31 | **$18,15** |
| `durum.json` · **30 sn — BUGÜNKÜ VARSAYILAN** (`TETIK_PUSH_AKTIF=false`) | 68,38 M | $51,29 | $27,35 | **~$78,64** |
| `durum.json` · 120 sn (push bağlı, `DAMGA_KONTROL_MS_PUSH`) | 17,10 M | $12,82 | $6,84 | **~$19,66** |
| `durum.json` · 300 sn (elle ayarlanırsa) | 6,84 M | $5,13 | $2,74 | **~$7,86** |
| `durum.json` · 1800 sn (elle ayarlanırsa) | 1,14 M | $0,85 | $0,46 | **~$1,31** |

**Sonuç:** tasarruf 1800 sn'den değil, *3 isteğin 1 isteğe inmesinden* ve push'un açık olmasından
gelir. Push kapalıyken (bugünkü varsayılan) filo ~$79/ay yoklama isteği üretir; `tetik.push_*`
açılıp bağlantı 120 sn'lik emniyet ağına geçince ~$20/ay'a iner. Broker maliyeti ayrı kalemdir
(bkz. `docs/ONBELLEK-VE-MALIYET.md`).

Görsel egress (içerik adlı + immutable, 304 yok):

| Kalem | Hesap | Aylık |
|---|---|---|
| Yeni kampanya görseli (600 cihaz) | 600 × 220 KB = 132 MB | **$0,011** |
| Depolama (100 görsel × 220 KB) | 22 MB | ~$0 |
| 304 doğrulama istekleri (içerik değişmedi) | 0 (immutable) | $0 |

**Asıl kalem cihaz başına yoklama isteğiydi; 1 istek + seyrek aralıkla ~$1/ay'a indi.**

---

## 10) HEDEF SEÇİMİ (panel UX) + veri modeli tek kaynağı (24.10.2026)

### 10.1 Panel arayüzü
`Nöbet ve Yayınlar` (dosya: `VeriView.vue`) ekranındaki **Yayınlar** sekmesinde yayın tablosu:

| Kolon | İçerik |
|---|---|
| `#` | yayın kimliği |
| Görsel | adres (satır kırılır) |
| Pencere | `start → end` |
| **Hedef** | chip: `Tüm cihazlar` ya da `Çayırova (…306) · 1. Bölge · 3 cihaz` |
| İşlem | **Hedef** (diyalog) · **Tümü** (temizle) |

Diyalogda üç bağımlı seçim: **İlçe → Bölge → Cihaz (isteğe bağlı)**. Üst seviye değişince alt
seviyeler temizlenir. Seçimler `domain/model.ts` → `yayinDogrula()` ile doğrulanır, `kapsamiYaz()`
boş alanları kayıttan **siler**. "Uygula" taslağa yazar; sayfadaki **Kaydet** yayınlar
(`lastSystemData.json` + `lastupdate.json` + `durum.json`, sonra cihaz tetiklenir).

İlçe/bölge adları nöbet kayıtlarından, cihaz listesi `match.json`'dan gelir (`domain/hedef.ts`).
Kimlik kayıt içinde yoksa **ağaç anahtarından** türetilir (`tumKayitlar` düzeltmesi).

### 10.2 Veri modeli tek kaynağı (DTO)
`kiosk/core/model.py` → `kiosk/tools/model_disa_aktar.py` →
`panel/src/domain/model.generated.json` + `web/src/veri/model.generated.json`.
Ayar şemasındaki (`sema.ts`) desenin aynısı: kiosk testi dosya güncel değilse kırılır.

İçerik: 7 yayın alanı (tip/zorunlu/alias/açıklama), `durum.json` alanları, kapsam kuralları.

### 10.3 Bu turda bulunan iki gerçek hata
| Hata | Neden | Düzeltme |
|---|---|---|
| `Cannot set properties of undefined (setting 'veri')` (panel açılışta) | `DOSYALAR.durum` eklendi, store **state**'ine eklenmedi; `hepsiniYukle` `this['durum'].veri` yazdı | state'e `durum` + `PANEL_OKUMAZ` dışlaması + **regresyon testi** (`dosyalar-tutarlilik.test.ts`): DOSYALAR ↔ state birebir |
| "Bildir" anlık çalışmıyordu | `durum.json` tek-istek yolu, MQTT'nin yazdığı **yerel** `tetikle.json`'u okumuyordu | `durum.secili_tetik()` (uzak → yerel) + her 10 turda `lastupdate.json` çapraz kontrolü |
