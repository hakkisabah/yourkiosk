# yourkiosk · Yönetim Paneli

Kiosk uygulamasının verisini ve ayarlarını **tarayıcıdan** yöneten panel.
Vue 3 + Vuetify 3 + TypeScript; **tüm veri S3'te**, sunucu (Lambda/API) yok.

- Kimlik: **Cognito User Pool** (tek yönetici kullanıcı) → **Cognito Identity Pool** → sınırlı IAM rolüyle alınan **geçici AWS anahtarları**
- Veri: `ayarlar.json`, `kapsam-ayarlari.json`, `lastSystemData.json`, `sablon.json`, `match.json`, `lastupdate.json`, `makinebilgileri.json`
- Yazma güvenliği: kaydetmeden önce dosyanın **ETag**'i karşılaştırılır; bu arada başkası yazdıysa kaydetme reddedilir ve uyarı gösterilir.

---

## 1) Ekranlar

| Ekran | Dosya | Ne yapar |
|---|---|---|
| **Durum** | (tümü) | Bağlantı/dosya durumu, veri özeti, **cihazın şu an ne gösterdiği** (kiosk ile aynı pencere kuralı), bu cihazın etkin özellikleri ve hangi kapsamdan geldiği |
| **Genel Ayarlar** | `ayarlar.json` | Tüm cihazlar için varsayılanlar: özellik aç/kapa, kuşak, görünüm, veri kaynağı, ağ |
| **Kapsam Ayarları** | `kapsam-ayarlari.json` | **İlçe / bölge / cihaz** bazında özellik yönetimi (aşağıya bakın) |
| **Nöbet ve Yayınlar** | `lastSystemData.json` | Nöbet kayıtlarını düzenleme (eczane, telefon, adres, adres tarifi, **nöbet penceresi**) ve yayınları görüntüleme |
| **Cihazlar** | `match.json`, `makinebilgileri.json`, `lastupdate.json` | Hangi cihaz hangi ilçe/bölgede; cihazı başka bölgeye taşıma |
| **Şablon** | `sablon.json` | Veri şablonu (JSON düzenleyici, doğrulamalı) |
| **Gelişmiş** | `ayarlar.json` (`gelismis`, `ag`) | JSON boyut/derinlik/düğüm sınırları, ağ kısıtları; "20–30 MB veri" için tek tuşla öneri |

### Kapsam Ayarları (ilçe / bölge / cihaz)

```
varsayilan  →  ilceler[ilceId]  →  bolgeler[bolgeId]  →  cihazlar[clientID]
   (genel)        (ilçe)              (bölge)              (tek cihaz)
                          en ÖZEL kapsam kazanır
```

Yalnızca **geçersiz kıldığınız** anahtar dosyaya yazılır; diğerleri bir üst kapsamdan devralınır.
Örnek: bir ilçede kayan yazıyı kapatıp, tek bir cihazda puntoyu büyütmek istiyorsanız ilçe kapsamında
`ozellikler.kayan_yazi = false`, cihaz kapsamında `kusak.yazi_punto = 48` yazmanız yeterlidir.

Kiosk tarafı bu dosyayı `ayarlar.kapsam_uygula()` ile okur ve **yalnızca kapsam gruplarını**
(`ozellikler`, `kusak`, `gorunum`, `gelismis`) uygular; aralık dışı değer sessizce kabul edilmez.
Panelde aynı doğrulama vardır: geçersiz değer kırmızı gösterilir ve kaydetme engellenir.

---

## 2) Kurulum

### 2.0 Hangi kimlik modu? (maliyet)

İki mod vardır ve **bu ölçekte ikisi de ücretsizdir** (ayrıntı + kaynaklar: [`MAALIYET.md`](./MAALIYET.md)):

| Mod | Kimlik | Veri erişimi | Bu kullanımda maliyet |
|---|---|---|---|
| `cognito` *(varsayılan)* | Cognito User Pool (tek yönetici) + Identity Pool | Geçici AWS anahtarıyla S3'e doğrudan | **$0** (10.000 MAU/ay ücretsiz, süresiz; Identity Pool ücretsiz) |
| `lambda` | Lambda + şifre özeti + HttpOnly cookie | Presigned S3 URL'leri (tarayıcıda anahtar yok) | **$0** (Lambda kalıcı ücretsiz kota) |

Cognito'yu hiç kullanmak istemiyorsanız `VITE_AUTH_MODU=lambda` seçip [`lambda/README.md`](./lambda/README.md)
adımlarını uygulayın; Cognito hesabınızda hiç görünmez. Geri dönmek için `VITE_AUTH_MODU=cognito` yeterlidir.

### 2.1 Ön koşullar

- Node.js 20+ (`node -v`)
- AWS hesabı, veri kovası (kiosk verisinin tutulduğu kova)
- AWS CLI (kova ayarları için)

### 2.2 Ortam dosyası

```bash
cp .env.ornek .env.local     # sonra doldurun
```

| Değişken | Nereden |
|---|---|
| `VITE_AUTH_MODU` | `cognito` (varsayılan) veya `lambda` |
| `VITE_BUCKET`, `VITE_PREFIX` | Kiosk verisinin tutulduğu kova ve ön ek (ör. `kiosk/`) |
| `VITE_USER_POOL_ID`, `VITE_USER_POOL_CLIENT_ID` | Cognito User Pool (aşağıda) — yalnızca `cognito` modu |
| `VITE_IDENTITY_POOL_ID` | Cognito Identity Pool (aşağıda) — yalnızca `cognito` modu |
| `VITE_AWS_REGION` | Kovanın bölgesi (`eu-central-1` vb.) — yalnızca `cognito` modu |
| `VITE_API_URL` | Lambda Function URL — yalnızca `lambda` modu |

`.env.local` sürüm kontrolüne **girmez**; panelde hiçbir şifre/anahtar saklanmaz.

### 2.3 Cognito: tek yönetici kullanıcı

```bash
# 1) User Pool (e-posta ile giriş, istemci sırrı YOK)
aws cognito-idp create-user-pool --pool-name yourkiosk-admin --username-attributes email --auto-verified-attributes email

# 2) Uygulama istemcisi (sır yok, SPA)
aws cognito-idp create-user-pool-client --user-pool-id <POOL_ID> --client-name panel \
  --no-generate-secret --explicit-auth-flows ALLOW_USER_SRP_AUTH ALLOW_REFRESH_TOKEN_AUTH

# 3) Yönetici kullanıcısı (tek kişilik kullanım)
aws cognito-idp admin-create-user --user-pool-id <POOL_ID> --username admin@example.com \
  --user-attributes Name=email,Value=admin@example.com Name=email_verified,Value=true
aws cognito-idp admin-set-user-password --user-pool-id <POOL_ID> --username admin@example.com --password '<GUCLU_SIFRE>' --permanent

# 4) Identity Pool + rol
aws cognito-identity create-identity-pool --identity-pool-name yourkiosk_panel \
  --no-allow-unauthenticated-identities \
  --cognito-identity-providers ProviderName=cognito-idp.<BOLGE>.amazonaws.com/<POOL_ID>,ClientId=<CLIENT_ID>
```

Identity Pool'un **kimliği doğrulanmış (authenticated)** rolüne `infra/iam-policy.json`
politikasını ekleyin (`KOVA_ADI` / `ON_EK` yer tutucularını doldurun).

### 2.4 Kova ayarları

```bash
aws s3api put-bucket-cors --bucket KOVA_ADI --cors-configuration file://infra/s3-cors.json
# Kova genel erişime AÇILMAZ (block public access açık kalsın) — panel imzalı istekler kullanır.
```

### 2.5 Çalıştırma

```bash
npm install          # not: NODE_ENV=production olan ortamlarda `npm install --include=dev`
npm run dev          # geliştirme: http://localhost:5173
npm run test         # birim testleri (kapsam çözümlemesi, pencere kuralı, şema, oturum)
npm run build        # tip denetimi + üretim derlemesi → dist/
```

**Geliştirme sorun giderme (beyaz ekran / `504 Outdated Optimize Dep`)**

| Belirti | Neden | Çözüm |
|---|---|---|
| Beyaz ekran, konsolda **`Uncaught ReferenceError: global is not defined`** (yanında `node_modules/.vite/deps/amazon-cognito-identity-js.js`) | `amazon-cognito-identity-js` (crypto-js) Node'a özgü `global` nesnesini kullanıyor; tarayıcıda yok → modül değerlendirilirken hata → uygulama hiç mount olmuyor | `vite.config.ts`: `define: { global: 'globalThis' }` **ve** `optimizeDeps.esbuildOptions.define` (hazır) + `index.html` güvenlik ağı. Testle kilitli: `src/regresyon.test.ts` |
| Beyaz ekran, konsolda `504 (Outdated Optimize Dep)` veya `@aws-sdk_...`/`vuetify_components_...` modül hataları | Vite, Vuetify bileşenlerini (otomatik içe aktarma) ve AWS SDK modüllerini **ilk istekte** keşfedip yeniden optimize eder → sayfa kendini yeniler | `optimizeDeps.exclude: ['vuetify','vuetify/locale']` (derin yollar ön-derlenemez) + diğer bağımlılıklar `include` listesinde. Yeni bağımlılık eklerken `include`a da ekleyin |
| Dev sunucusu üretim modunda çalışıyor (`import.meta.env.DEV` → `false`), Vue uyarıları görünmüyor | Kabukta `NODE_ENV=production` tanımlı | `npm run dev` betiği `NODE_ENV=development` verir |
| Tarayıcı `ws://localhost:5173/?token=…` açıyor | Vite'ın **HMR** (sıcak yenileme) kanalı — dev'e özel | Normal; üretim derlemesinde yoktur (`dist` içinde `WebSocket`/`@vite/client` bulunmaz — `src/regresyon.test.ts` de bunu doğrular). Kapatmak isterseniz `server: { hmr: false }` |
| "Kurulum gerekli" ekranı | `panel/.env.local` yok ya da yer tutucu değerler duruyor | Ekrandaki adımlar / `README.md` §2.2; hiçbir AWS isteği yapılmaz, güvenli |

Bir hata oluşursa panel artık **boş ekran yerine** okunabilir bir hata kartı gösterir
(`src/hata.ts` → `App.vue`); kartı kopyalayıp paylaşabilirsiniz.

### 2.6 Yayın temizliği: S3 ve cihaz (son gösterim tarihi)

Yayınların `end` alanı **son gösterim tarihidir**. İki taraf da aynı ölçütle temizler:

| Taraf | Ne zaman | Ne silinir | Kim yapar |
|---|---|---|---|
| **Cihaz (kiosk)** | `end` + `onbellek.gorsel_saklama_gun` (varsayılan 2 gün) sonra, ya da görsel artık veride geçmiyorsa | Diskteki görsel kopyası (`kiosk/onbellek/gorsel/`) | Kiosk otomatik (her veri turunda + açılışta) |
| **S3 (sunucu)** | Panelde "Süresi geçenleri sil" | `lastSystemData.json` içindeki kayıt + **kendi kovamızdaki** görsel nesnesi; ardından `lastupdate.json` tazelenir | Panel → Veri → Yayınlar sekmesi |

- Adres **dış bir kaynağa** aitse (ör. `https://baskasite.com/api/afis.png`) nesne silinemez —
  panel bunu "dış adres (cihaz temizler)" olarak işaretler; cihaz kendi kopyasını temizler.
- `end` alanı okunamayan kayda **dokunulmaz** (yanlışlıkla canlı yayın silinmesin); panel bunları
  "atlanan" olarak sayar.
- Güvenlik payı (varsayılan 2 saat) `end`ten SONRA eklenir: cihaz saati geri kalmışsa yayın bir süre daha görünür.
- Kural testleri: `src/domain/temizlik.test.ts`. Silme yolu yalnızca ön ek (`kiosk/`) altındaki
  anahtarlara izin verir (`src/aws/s3.ts` → `nesneSil`) — veri dosyaları bu yoldan silinemez.

**Lambda modunda** nesne silme kapalıdır (presigned imza yalnızca okuma/yazma içindir). Veri
kaydı yine temizlenir; görsel nesneleri için kovada **yaşam döngüsü kuralı** (güvenlik ağı) tanımlayın:

```bash
# kiosk/yayinlar/ ön eki altındaki görselleri 30 gün sonra otomatik sil
aws s3api put-bucket-lifecycle-configuration --bucket KOVA_ADI --lifecycle-configuration '{
  "Rules": [{
    "ID": "yayin-gorselleri-30g",
    "Status": "Enabled",
    "Filter": { "Prefix": "kiosk/yayinlar/" },
    "Expiration": { "Days": 30 }
  }]
}'
```

> S3 yaşam döngüsü kuralı **sabit gün** sayar (yayının kendi `end` alanını bilemez); bu yüzden
> asıl temizlik panelden yapılır, kural yalnızca "öksüz kalırsa er ya da geç gitsin" güvencesidir.

### 2.7 Yayınlama (S3 + CloudFront)

```bash
npm run build
aws s3 sync dist/ s3://PANEL_KOVASI/ --delete
```

- Panel kovası **statiktir**, kiosk veri kovasıyla aynı olmak zorunda değildir.
- Panel `createWebHashHistory` kullanır → sunucuda yönlendirme kuralı gerekmez.
- Panel adresini `infra/s3-cors.json` içindeki `AllowedOrigins` listesine eklemeyi unutmayın.
- Öneri: paneli CloudFront arkasına alıp erişimi yönetici ağına/VPN'e kısıtlayın; `index.html`'e `noindex` konuldu.

---

## 3) Panel ↔ kiosk ilişkisi

```
S3 (ön ek: kiosk/)                        Kiosk (her veri turunda)
  ayarlar.json            ─────────────►  ayarlar.uygula()          (genel varsayılanlar)
  kapsam-ayarlari.json    ─────────────►  ayarlar.kapsam_uygula()   (ilçe→bölge→cihaz)
  lastSystemData.json     ─────────────►  nöbet penceresi seçimi     (start ≤ şimdi < end)
  match.json              ─────────────►  cihazın ilçe/bölgesi
  lastupdate.json         ─────────────►  değişiklik kontrolü
                                          (+ `onbellek/dizin.json`: disk önbelleği damgası)
```

Cihaz tarafı önbellek (nöbet JSON'u + yayın görselleri) `kiosk/README.md` §1.7'de anlatılır.
Süresi geçen yayınların iki taraflı temizliği için bkz. §2.6.

**Gösterim modu (Qt / tarayıcı).** `ayarlar.json` içindeki **`calistirma`** grubu panelde
*Ayarlar* ekranında otomatik görünür (şema kiosk'tan üretilir): `mod = qt | tarayici`, tarayıcı
yolu, ek bayraklar, yerel sunucu portu ve veri modu. `mod = "tarayici"` yapıldığında cihaz
Qt yerine **Chromium kiosk** modunda açılır (aynı görünüm/davranış; ayrıntı: `web/README.md`,
`kiosk/README.md` §8).

- Panel **aynı kuralları** uygular: nöbet penceresi (`kayitAktifMi`), kapsam çözümlemesi,
  değer doğrulama. Beklentiler ortak test verisiyle iki tarafta da doğrulanır:
  `kiosk/tests/veri/kapsam_ornek.json` → `kiosk/tests/test_kapsam_ayarlari.py` ve `src/domain/kapsam.test.ts`.
- Ayar şeması **kiosk'tan üretilir**: `kiosk/tools/sema_disa_aktar.py` → `src/domain/sema.generated.json`.
  Şema değişirse: `cd kiosk && python3 tools/sema_disa_aktar.py` (kiosk testi güncel değilse uyarır).

## 4) Dosya yapısı

```
panel/
├── src/
│   ├── aws/          config.ts (ortam doğrulama), auth.ts (Cognito), s3.ts (oku/yaz/ETag)
│   ├── domain/       sema.ts + sema.generated.json · kapsam.ts · veri.ts · temizlik.ts · dosyaBilgisi.ts
│   ├── stores/       baglanti.ts (oturum+S3) · dosyalar.ts (okuma/yazma durumu)
│   ├── components/   AyarFormu.vue (şemadan üretilen form) · JsonEditor.vue
│   ├── views/        DurumView · AyarlarView · KapsamView · VeriView · CihazlarView · SablonView · GelismisView · GirisView
│   └── router/       hash geçmişi + oturum koruması
└── infra/            iam-policy.json · s3-cors.json
```

## 5) Güvenlik notları

- Cihazdaki `makinebilgileri.json` bir **kimlik** içerir; kiosk bunu günlüğe ham yazmaz (özetler). Paneli paylaşırken
  ekran görüntülerinde clientID görünmemesine dikkat edin.
- Panel yalnızca `VITE_PREFIX` altına yazar; IAM politikası da yalnızca o ön eki kapsar.
- Kimseye hesap açmayın: kurulum **tek** yönetici içindir. Yeni kullanıcı gerekirse Identity Pool rolünü
  gözden geçirin (aynı yetkiyi alır).
- Oturum Cognito'nun localStorage'ında tutulur; ortak kullanılan bir tarayıcıda **Çıkış** yapın.
- **Uzaktan komut gönderme panelde YOKTUR (bilinçli):** cihaz yalnız HMAC imzalı komut çalıştırır ve
  imza anahtarı bir tarayıcı istemcisine konulamaz (pakete sızardı). Komutlar yönetici aracıyla ya da
  sunucu tarafıyla (Lambda ortam değişkeni `KOMUT_ANAHTARI`) gönderilir; ayrıntı:
  `kiosk/KOMUTLAR.md`. `komut.json` / `tetikle.json` S3 ön ekinde olağan nesnelerdir.
