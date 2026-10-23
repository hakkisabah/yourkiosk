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

---

## 6) Maliyet: gerçek tablo (dürüst düzeltme)

Önceden "2,5 MB × 600 cihaz × sürekli indirme" varsayımıyla büyük rakam vermiştim. **304 düzeltmesinden
sonra bu geçerli değil**: içerik değişmedikçe gövde inmiyor.

| Kalem | Hesap | Aylık |
|---|---|---|
| Yoklama istekleri (600 cihaz, 300 sn) | 15,6 M istek | **$17,88** |
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
