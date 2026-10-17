# Yönetim paneli: maliyet analizi ve kimlik doğrulama seçenekleri

Bu belge panelin **kime ne kadar ücret çıkardığını** sayıyla ve kaynakla gösterir, ardından
**Cognito'yu tamamen kaldırma** seçeneğini (Lambda + cookie tabanlı oturum) anlatır.

---

## 1) Kısa cevap

| Bileşen | Bu kullanımda (1 yönetici, ayda birkaç giriş) | Kaynak |
|---|---|---|
| **Cognito User Pool** | **$0,00** — Lite/Essentials katmanlarında **10.000 MAU/ay ücretsiz** ve bu ücretsiz kota **12 aylık süreye bağlı değil** | [AWS Cognito fiyatlandırma](https://aws.amazon.com/cognito/pricing/) |
| **Cognito Identity Pool** | **$0,00** — AWS açıkça "authenticating users and generating unique identifiers is **provided at no charge**" diyor | aynı sayfa |
| **S3 istekleri** (veri okuma/yazma) | Aylık birkaç bin istek → birkaç kuruş (S3 fiyatı: 1.000 PUT ≈ $0,005, GET ≈ $0,0004) | [S3 fiyatlandırma](https://aws.amazon.com/s3/pricing/) |
| **Panelin barındırılması** (S3 + CloudFront) | Aylık birkaç MB trafik → ~$0,01 | CloudFront/S3 fiyatlandırma |

**Sonuç: bu kullanımda Cognito'nun ücreti yoktur.** Ücret ancak aşağıdaki durumlarda başlar:

* ayda **10.000'den fazla farklı kullanıcı** giriş yaparsa (MAU = aylık etkin kullanıcı),
* **Plus** katmanına geçilirse (Plus'ın ücretsiz kotası yok, ~$0,020/MAU — panel bunu kullanmıyor),
* SAML/OIDC federasyonu ile 50'den fazla kullanıcı bağlanırsa (~$0,015/MAU),
* makine-makine (M2M) token akışı kullanılırsa (bunun ücretsiz kotası yok).

Panel **tek yönetici** için tasarlandı (kullanıcı hesabı açma ekranı yok), yani MAU = 1'dir.

> Not: MAU, "o ay içinde giriş/token alışverişi yapan **farklı kullanıcı** sayısı"dır; aynı kullanıcının
> 100 kez girmesi MAU'yu 1 yapar. Ücretsiz kota **hesap/organizasyon geneli**dir (pool başına değil).

---

## 2) Yine de Cognito'suz bir kurgu isterseniz: `auth-modu: lambda`

Cognito'yu **tamamen kaldırmak** bir opsiyon olarak hazır: panel iki kimlik modunu destekler.

```
panel/.env.local
  VITE_AUTH_MODU=cognito   # (varsayılan) User Pool + Identity Pool → geçici AWS anahtarı
  VITE_AUTH_MODU=lambda    # Cognito YOK: Lambda + HttpOnly cookie + presigned S3 URL
```

### 2.1 Lambda modu nasıl çalışır?

```
Tarayıcı (panel)                 Lambda (panel/lambda/)             S3
   │  POST /giris {şifre} ───────────►  şifre özetini doğrular
   │  ◄──── Set-Cookie: oturum=… (HttpOnly, Secure, SameSite=Lax, HMAC imzalı, süreli)
   │
   │  POST /imzala {dosya, işlem} ───►  cookie'yi doğrular, dosya adını beyaz listeden geçirir
   │  ◄──── { url } (presigned GET/PUT, 5 dk geçerli)
   │  GET/PUT ─────────────────────────────────────────────────────►  S3 nesnesi
```

* Tarayıcıda **AWS anahtarı yoktur** (Cognito modundaki geçici anahtarın yerini imzalı URL alır).
* Şifre **düz metin saklanmaz**: `PANEL_SIFRE_OZETI = pbkdf2_sha256$<iterasyon>$<salt>$<özet>`
  (`python3 sifre_ozetle.py` ile üretilir).
* Oturum cookie'si **HMAC-SHA256** ile imzalanır (sunucu sırrı `OTURUM_ANAHTARI`), süresi dolar,
  değiştirilirse geçersiz sayılır → imza testleriyle kilitlidir.
* Yazma yalnızca **beyaz listedeki dosya adlarına** ve ön eke yapılabilir; okuma da aynı şekilde kısıtlıdır.
* Giriş denemeleri basit hız sınırına tabidir (aynı örnek içinde; not: Lambda örnekleri arasında
  paylaşılmaz — ciddi bir gereksinim olursa DynamoDB/WAF eklenir).

### 2.2 Maliyeti

Lambda **kalıcı ücretsiz kota**: ayda 1 milyon istek + 400.000 GB-saniye.
Panel günde ~50 istek yapar → ayda ~1.500 istek → **$0,00**. Function URL ek ücret almaz.
Yani Lambda modu da, Cognito modu da bu kullanımda ücretsizdir; fark **bağımlılık ve yönetim tercihidir**.

### 2.3 Cognito'yu kaldırma adımları

```bash
# 1) Paneli Lambda moduna al
cd panel && cp .env.ornek .env.local
#   VITE_AUTH_MODU=lambda  ve  VITE_API_URL=https://<function-url>  ayarlayın
# 2) Lambda'yı kurun (bkz. panel/lambda/README.md)
# 3) Cognito kaynaklarını silin (opsiyonel, geri dönüşü yoktur)
aws cognito-idp delete-user-pool --user-pool-id <POOL_ID>
aws cognito-identity delete-identity-pool --identity-pool-id <IDENTITY_POOL_ID>
# 4) S3 CORS'ta yöntemleri daraltın (PUT yalnızca panel origin'inden)
```

Geri dönmek isterseniz: `VITE_AUTH_MODU=cognito` yapıp User Pool/Identity Pool'u yeniden oluşturmanız
yeterlidir (adımlar `README.md` §2.3) — panel kodu değişmez.

---

## 3) Neden varsayılan Cognito?

* **Hazır ve yönetilen**: şifre politikası, oturum yenileme, kilitleme, MFA gibi başlıklar AWS'nin;
  panelde şifre/oturum kodu tutulmaz.
* **Panelde uzun ömürlü sır yok**: S3 erişimi geçici AWS anahtarıyla ve IAM ile kısıtlıdır.
* **Ücretsiz**: yukarıdaki gibi bu ölçekte $0.
* En kritik fark: Cognito modunda **S3 anahtarları tarayıcıda geçici olarak bulunur**, Lambda modunda
  tarayıcı hiç anahtar görmez (yalnızca 5 dakikalık imzalı URL). Güvenlik açısından ikisi de kabul
  edilebilir; Lambda modu bir tık daha kapalı, Cognito modu bir tık daha az kod.

İki mod da **aynı panel ekranlarını** kullanır; veri katmanı `src/aws/veriKaynagi.ts` içindeki tek
arayüzle değiştirilir (`oku`, `yaz`, `bilgi`, `liste`, `sil`, `nesneSil`).

---

## 4) Cihaz tarafı önbelleğin maliyet etkisi (ölçülü)

Cihaz, veri dosyalarını ve yayın görsellerini diskte tutar (ayrıntı: `kiosk/README.md` §1.7).
Sunucudaki `lastupdate.json` değişmediyse büyük dosyalar **hiç indirilmez**.

Ölçülen dosya boyutları (bu depo, yerel kopyalar):

| Dosya | Boyut |
|---|---|
| `lastSystemData.json` | 257 KB |
| `match.json` | 8 KB |
| `sablon.json` | 2 KB |
| `makinebilgileri.json` | 1 KB |
| `lastupdate.json` (damga) | ~1 KB |

Cihaz saatte bir kontrol ediyor (günde 24 tur):

| Senaryo | Önbelleksiz (öncesi) | Önbellekli (şimdi) | Kazanç |
|---|---|---|---|
| Şimdiki boyut (≈268 KB veri) | 24 × 268 KB ≈ **6,4 MB/gün** (≈193 MB/ay) | 24 × 1 KB + 268 KB ≈ **0,3 MB/gün** (≈9 MB/ay) | **~%95** |
| Büyüme hedefi (20 MB veri) | 24 × 20 MB ≈ **480 MB/gün** (≈14,4 GB/ay) | 20 MB + 24 KB ≈ **20 MB/gün** (≈0,6 GB/ay) | **~%96** |
| Yayın görseli (200 KB), günde 100 gösterim | ≈ **20 MB/gün** | ≈ **0,2 MB/gün** (bir kez indirilir) | **~%99** |

Her iki senaryoda da kazanç **cihazın internet kotası/trafiği** tarafındadır (S3 istek ücreti zaten
kuruşlar mertebesinde; asıl maliyet sahadaki SIM/ADSL kotasıdır). Verinin büyümesi (20–30 MB)
önbelleksiz durumda **doğrusal** olarak kotayı yer; önbellekli durumda değişim başına bir kez ödenir.

Süresi geçen yayınların görselleri cihazdan ve kovadan silinir (§2.6, `panel/README.md`);
veri kaydı temizlenirken `lastupdate` damgası tazelenir, cihazlar bir sonraki saatlik kontrolde
yeni veriyi alır (ek bir tam indirme, yalnızca gerçek değişiklik olduğunda).
