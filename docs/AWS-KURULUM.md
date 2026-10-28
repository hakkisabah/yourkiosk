# AWS kurulumu — plan, istenen yetkiler ve komut günlüğü

Bu belge **yapılan her AWS işlemini** komutuyla kaydeder (tekrar üretilebilirlik + geri alma).

---

## 1. Senden istenen (tek sefer)

**IAM erişim anahtarı** (root DEĞİL, konsol şifresi/MFA gerekmiyor):

1. AWS Konsol → **IAM → Policies → Create policy → JSON** → `panel/infra/kurulum-politikasi.json`
   içeriğini **olduğu gibi** yapıştır (yer tutucu YOK) → ad: `yourkiosk-kurulum`.
   Politika kova adını `yourkiosk-*` deseniyle, IAM kaynaklarını `yourkiosk-*` önekiyle sınırlar;
   bu yüzden kova adı **`yourkiosk-` ile başlamalı**.

   Yapıştırmadan önce doğrula (AWS'nin resmî aksiyon listesine karşı, ağ gerekir):

   ```bash
   ./panel/infra/politika_dogrula.py panel/infra/kurulum-politikasi.json
   # ✓ kurulum-politikasi.json: 6 ifade, tüm aksiyonlar geçerli
   ```

   > Aynı betik `panel/infra/iam-policy.json` (panel rolü) için de çalıştırılmalı — orada da
   > `s3:HeadObject` ve `_aciklama` hataları vardı, düzeltildi.
2. **IAM → Users → Create user** → ad: `yourkiosk-kurulum` → *Attach policies directly* →
   `yourkiosk-kurulum` → oluştur.
3. Kullanıcı → **Security credentials → Create access key** → *Application running outside AWS* →
   `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` değerlerini **sohbete yazma**, şu dosyaya koy:

```bash
mkdir -p ~/.config/hermes-secrets && chmod 700 ~/.config/hermes-secrets
cat > ~/.config/hermes-secrets/aws-yourkiosk.credentials <<'EOF'
[default]
aws_access_key_id = BURAYA
aws_secret_access_key = BURAYA
EOF
chmod 600 ~/.config/hermes-secrets/aws-yourkiosk.credentials
```

4. Bana şunları söyle: **bölge** (öneri `eu-central-1`), **kova adı** (öneri `yourkiosk-veri-<hesap-id-kısa>`),
   ve **Cognito kurulsun mu** (öneri: evet, ücretsiz kota) — panel yönetici e-postası da gerekli.

Kurulum bitince bu anahtarı **iptal edeceğiz** (panel Cognito ile geçici anahtar kullanır; kalıcı anahtar tutmaz).

---

## 2. Yapılacaklar (sırayla)

| # | İş | Araç | Doğrulama |
|---|---|---|---|
| 1 | AWS CLI v2'yi yerel kur (sudo yok) | `curl` + `python3 -m zipfile` + `aws/install -i ~/.local/aws-cli -b ~/.local/bin` | `aws --version`, `aws sts get-caller-identity` |
| 2 | Kova oluştur | `aws s3api create-bucket --bucket … --region …` (`eu-central-1` için LocationConstraint gerekmez) | `aws s3api head-bucket` |
| 3 | Public erişimi kapat | `aws s3api put-public-access-block` (4 ayar `true`) | `get-public-access-block` |
| 4 | Sürümleme (yedekleme) | `put-bucket-versioning --versioning-configuration Status=Enabled` | `get-bucket-versioning` |
| 5 | Yaşam döngüsü (maliyet) | `put-bucket-lifecycle-configuration`: `kiosk/yayin-gorseller/` altında `Expiration.InDays=30` + `NoncurrentVersionExpiration` | `get-bucket-lifecycle-configuration` |
| 6 | CORS (panel tarayıcıdan yazar) | `put-bucket-cors` ← `panel/infra/s3-cors.json` | `get-bucket-cors` |
| 7 | Panel rolü (Cognito authenticated) | `iam create-role` + `put-role-policy` ← `panel/infra/iam-policy.json` (KOVA_ADI/ON_EK doldurulur) | `get-role-policy` |
| 8 | Cognito Identity Pool | `cognito-identity create-identity-pool` (kimlik doğrulamalı erişim) + `set-identity-pool-roles` | `get-identity-pool-roles` |
| 9 | Cognito User Pool + istemci + yönetici kullanıcı | `cognito-idp create-user-pool`, `create-user-pool-client`, `admin-create-user` | konsolda giriş denemesi |
| 10 | `panel/.env.local` | değerler 8–9'dan yazılır (dosya `.gitignore`'da) | `npm run build` |
| 11 | Paneli yayına al | `aws s3 sync panel/dist s3://…/panel/ --delete` (+ gerekirse CloudFront) | tarayıcıda giriş |
| 12 | Cihaz tarafı | `kiosk/ayarlar.json` → `DOSYA_ADRESI` (panelden yayınlanan veri kökü) | tarayıcı modu veriyi çeker |
| 13 | Anahtarı iptal et | IAM → kullanıcı → access key → Deactivate → Delete | `sts get-caller-identity` artık hata verir |

---

## 2b. S3 maliyet optimizasyonu — uygulanan ayarlar ve beklenti

İşlemlere başlamadan **önce** kovanın maliyet ayarları kuruldu (sıra: kova → public block → sürümleme →
yaşam döngüsü → CORS). Uygulanan üç kural:

| Kural | Ayar | Neyi engeller |
|---|---|---|
| `iptal-mpu` | 7 günde yarım kalan çok parçalı yükleme iptali | Görünmeyen, silinemeyen depolama şişmesi |
| `eski-surumler` | Eski sürümler 30 günde silinir, **son 3 sürüm saklanır** | Sürümleme açıkken sınırsız büyüme |
| `yayin-gorselleri` | `kiosk/yayin-gorseller/` 45 günde silinir (eski sürümler 15 gün) | Panelin silmediği artık görseller |

Ayrıca: **public erişim tamamen kapalı** (4 ayar `true`) → yanlışlıkla herkese açık nesne olmaz; erişim
yalnız Cognito rolüyle ve `kiosk/*` ön ekiyle.

**Bilinçli olarak YAPILMAYANLAR (gerekçeli):**

| Yapılmadı | Neden |
|---|---|
| Intelligent-Tiering | Nesne sayısı az (yüzler); izleme ücreti (1000 nesne başına $0,0025) tasarrufu aşar |
| Standard-IA / Glacier | Kiosk verisi **sık okunuyor**; IA'da geri getirme ücreti + 30 gün alt sınır zarar ettirir |
| Sürümlemeyi kapatmak | Yedekleme değeri yüksek; yerine ucuz çözüm: eski sürümleri 30 günde sil |
| CloudFront | Şu an cihaz sayısı az; 1 TB/ay ücretsiz kota ilk 12 ay. Cihaz sayısı artınca açılacak (panel yayını için zaten gerekli) |

**Beklenen aylık maliyet (3 cihaz, günde ~20 veri güncellemesi, ~10 görsel):**

| Kalem | Hesap | Aylık |
|---|---|---|
| Depolama | ~0,5 GB (sürümler dahil) × $0,0245/GB | ≈ $0,01 |
| GET isteği | `lastupdate.json` 30 sn'de bir → 3 cihaz ≈ 259 bin istek × $0,0004/1000 | ≈ $0,10 |
| PUT isteği | ~600 yazma/ay | ≈ $0,003 |
| Dışa aktarım | ~200 MB/ay × $0,09/GB | ≈ $0,02 |
| **Toplam** | | **≈ $0,13/ay** |

Tablo **30 sn** (bugünkü varsayılan: `config.TETIK_PUSH_AKTIF = False`, yani
`DAMGA_KONTROL_MS_PUSH_YOK`) tabanıyla hesaplanmıştır. MQTT push açılırsa yoklama 120 sn'ye çıkar
(`DAMGA_KONTROL_MS_PUSH`) → ≈ 65 bin istek ≈ $0,03, toplam **≈ $0,06/ay**.

En büyük kalem **istek sayısı**: cihaz yerel önbellek kullandığı için yalnız `lastupdate.json` yoklanıyor
(42 bayt). Yoklama sıklığı `kiosk/ayarlar.json` → `calistirma.degisiklik_kontrol_ms` ile ayarlanır
(`ayarlar.py` bu anahtarı `config.DAMGA_KONTROL_MS`e yazar; 5 sn – 1 saat). Qt modunda çalışma anındaki
aralık `DAMGA_KONTROL_MS`e değil bağlantı durumuna bağlıdır: push bağlı 120 sn (`DAMGA_KONTROL_MS_PUSH`),
push kapalı/kopuk 30 sn (`DAMGA_KONTROL_MS_PUSH_YOK`).

---

## 3. Komut günlüğü

> Her adım buraya **çalıştırılan komut + sonuç** olarak eklenecek.

| Tarih | Adım | Komut | Sonuç |
|---|---|---|---|
| 21.10 | Politika doğrulama | `./panel/infra/politika_dogrula.py …` | ✓ 6 ifade |
| 21.10 | İlk denemede bulunan hatalar | IAM konsolu | `s3:HeadObject` yok · `s3:*BucketLifecycleConfiguration` yok · `HESAP_ID` geçersiz · `_aciklama` geçersiz → düzeltildi |
| 21.10 | AWS CLI v2 (sudo'suz) | `./aws/install -i ~/.local/aws-cli -b ~/.local/bin` | ✓ aws-cli/2.38.3 (`zipfile` ile açıldı; `chmod +x`) |
| 21.10 | Kimlik | `aws sts get-caller-identity` | ✓ hesap **321255536632**, kullanıcı `yourkiosk-kurulum` |
| 21.10 | Kova | `aws s3api create-bucket --bucket yourkiosk-veri --create-bucket-configuration LocationConstraint=eu-central-1` | ✓ `arn:aws:s3:::yourkiosk-veri` |
| 21.10 | Public erişim | `put-public-access-block` (4 ayar `true`) | ✓ |
| 21.10 | Sürümleme | `put-bucket-versioning Status=Enabled` | ✓ |
| 21.10 | Yaşam döngüsü | `put-bucket-lifecycle-configuration file://panel/infra/s3-lifecycle.json` | ✓ 3 kural |
| 21.10 | CORS | `put-bucket-cors file://panel/infra/s3-cors.json` (`{"CORSRules": […]}`, düz dizi DEĞİL) | ✓ localhost:5173/4173 |
| 21.10 | Şifreleme/ACL | `put-bucket-encryption`, `put-bucket-ownership-controls` | ⚠ `AccessDenied` → **gerek yok**: yeni kovalarda AWS varsayılanı SSE-S3 + BucketOwnerEnforced |
| 21.10 | Panel rolü | `iam create-role yourkiosk-panel-s3-v2` (aud = identity pool) + `put-role-policy` (iam-policy.json) | ✓ |
| 21.10 | Identity pool | `cognito-identity create-identity-pool --cognito-identity-providers …` + `set-identity-pool-roles` | ✓ `eu-central-1:b787f617-…` |
| 21.10 | User pool | `cognito-idp create-user-pool` (e-posta girişi, admin-only, 12 karakter parola) | ✓ `eu-central-1_y4Zlp17ZR` |
| 21.10 | App client | `create-user-pool-client --no-generate-secret` + USER_PASSWORD_AUTH | ✓ `6n7eo6o0acc1fbg6vjr00sbj94` |
| 21.10 | Yönetici | `admin-create-user contact@yourkiosk.io --message-action SUPPRESS` + `admin-set-user-password --permanent` | ✓ (parola: `~/.config/hermes-secrets/cognito-panel.parola`, 0600) |
| 21.10 | **Uçtan uca doğrulama** | InitiateAuth → GetId → GetCredentialsForIdentity → S3 | ✓ giriş · geçici anahtar · `kiosk/*` yazma/okuma/silme · **ön ek dışı yazma reddedildi** |
| 21.10 | Panel | `.env.local` + `npm test` | ✓ 104/104 |


---

## 4. Geri alma / temizlik

```bash
# Kova boşalt + sil (dikkat: veri kaybı)
aws s3 rb s3://KOVA_ADI --force
# IAM: yourkiosk-kurulum kullanıcısı, politikası, rolü
aws iam delete-user --user-name yourkiosk-kurulum
# Cognito: identity pool + user pool (ID ile)
aws cognito-identity delete-identity-pool --identity-pool-id …
aws cognito-idp delete-user-pool --user-pool-id …
```

## 5. Maliyet notu

- S3: depolama + istek ücreti (birkaç GB veri için aylık ≈ 0,1–1 USD).
- Cognito: 10.000 MAU/ay ücretsiz — tek yönetici kullanıcı için **0**.
- CloudFront (opsiyonel): 1 TB/ay ücretsiz kota (ilk 12 ay).

---

## 6. Kurulan kaynaklar (özet)

| Kaynak | Değer |
|---|---|
| Kova | `yourkiosk-veri` (eu-central-1, sürümleme açık, 3 yaşam döngüsü kuralı) |
| Panel rolü | `arn:aws:iam::321255536632:role/yourkiosk-panel-s3-v2` (yalnız `kiosk/*`, GetObject/PutObject/DeleteObject) |
| Identity pool | `eu-central-1:b787f617-a4a0-4169-bb0e-28892d5f6481` |
| User pool | `eu-central-1_y4Zlp17ZR` (e-posta girişi, yalnız yönetici hesap oluşturabilir) |
| App client | `6n7eo6o0acc1fbg6vjr00sbj94` (secret yok — SPA) |
| Yönetici | `contact@yourkiosk.io` — parola `~/.config/hermes-secrets/cognito-panel.parola` (0600) |

### Temizlenecek artıklar (kurulum sırasında oluştu)

İlk denemelerde oluşan ve **kullanılmayan** kaynaklar (silme izinleri politikaya eklendi, yeniden
denenecek): `yourkiosk-panel` rolü, `yourkiosk-panel-s3` rolü, `eu-central-1:67a2b8af-…` identity pool.

```bash
export PATH="$HOME/.local/bin:$PATH" AWS_DEFAULT_REGION=eu-central-1
export AWS_SHARED_CREDENTIALS_FILE="$HOME/.config/hermes-secrets/aws-yourkiosk.credentials"
aws cognito-identity delete-identity-pool --identity-pool-id eu-central-1:67a2b8af-750d-47d9-b81d-a74df364929a
aws iam delete-role --role-name yourkiosk-panel-s3     # önce delete-role-policy
aws iam delete-role --role-name yourkiosk-panel        # önce delete-role-policy
```

---

## 7. Panel yayını — CloudFront (22.10.2026)

| Kaynak | Değer |
|---|---|
| Distribution | `EVR6YMP2UVX8A` |
| Adres | **https://d308vfb9mn2991.cloudfront.net** |
| OAC | `E31ZIOBD0HGXIP` (`sigv4`, `always`) — kovaya yalnız CloudFront erişir |
| Origin | `yourkiosk-veri.s3.eu-central-1.amazonaws.com`, `OriginPath=/panel` |
| PriceClass | `PriceClass_100` (en ucuz Avrupa/ABD) |
| SPA yedeği | 403/404 → `/index.html` (200) |
| Önbellek | varlıklar 1 yıl `immutable`; `index.html` `no-cache` |

Komutlar (sırayla):

```bash
aws cloudfront create-origin-access-control --origin-access-control-config \
  '{"Name":"yourkiosk-panel-oac","SigningProtocol":"sigv4","SigningBehavior":"always","OriginAccessControlOriginType":"s3"}'
aws cloudfront create-distribution --distribution-config file:///tmp/aws-kur/cf-config.json
aws s3api put-bucket-policy --bucket yourkiosk-veri --policy file:///tmp/aws-kur/bucket-policy.json   # Principal: cloudfront.amazonaws.com + SourceArn
# DİKKAT: `file://` yolu ÇALIŞTIĞIN DİZİNE göre çözülür → mutlak yol kullan.
# (Hata: "Unable to load paramfile file://panel/infra/s3-cors.json: No such file or directory")
KOK="$(pwd)/.."; [ -d panel ] && KOK="$(pwd)"        # depo kökündeysek pwd
aws s3api put-bucket-cors --bucket yourkiosk-veri \
  --cors-configuration "file://$KOK/panel/infra/s3-cors.json"

# doğrulama
aws s3api get-bucket-cors --bucket yourkiosk-veri
curl -si -H "Origin: http://127.0.0.1:8090" \
  https://d2dnrvsx5eevod.cloudfront.net/match.json | grep -i access-control
aws s3 sync panel/dist s3://yourkiosk-veri/panel/ --delete --exclude index.html \
  --cache-control "public,max-age=31536000,immutable"
aws s3 cp panel/dist/index.html s3://yourkiosk-veri/panel/index.html --cache-control "no-cache,must-revalidate"
aws cloudfront create-invalidation --distribution-id EVR6YMP2UVX8A --paths "/*"
```

**Doğrulama (gerçek yanıtlar):**

| Test | Sonuç |
|---|---|
| `GET /` | HTTP 200 · `text/html` · 1023 B |
| `GET /veri` (SPA rotası) | HTTP 200 · `text/html` (index'e düşüyor) |
| `GET /assets/index-*.js` | HTTP 200 · 618 KB · `cache-control: public,max-age=31536000,immutable` |
| `http://…` | HTTP 301 → https |
| Kova REST adresi (doğrudan) | **HTTP 403** (yalnız OAC üzerinden erişim) |

## 8. Temizlik (tamamlandı)

| Silinen | Durum |
|---|---|
| `yourkiosk-panel` rolü | ✓ silindi |
| `yourkiosk-panel-s3` rolü | ✓ silindi |
| identity pool `eu-central-1:67a2b8af-…` (sağlayıcısız) | ✓ silindi |

Kalan tek artık: **kurulum erişim anahtarı** — kurulum bitince iptal edilecek (Bölüm 9).

## 9. Kapanış kontrol listesi

1. `panel` yayında mı → https://d308vfb9mn2991.cloudfront.net (giriş: `contact@yourkiosk.io`)
2. Cihaz verisi: cihazlar kovaya doğrudan erişemez (403). Canlı veri için ya ikinci bir cache
   behavior (`kiosk/*` → aynı kova, OAC) açılacak ya da cihazlar panelin yayınladığı yerel dosyayı
   kullanmaya devam edecek.
3. Kurulum anahtarını iptal et: IAM → Users → `yourkiosk-kurulum` → Security credentials →
   Access key → Deactivate → Delete. Sonra `aws sts get-caller-identity` **hata vermeli**.

### 7b. Cihaz verisi için ikinci dağıtım (23.10.2026)

Panel dağıtımı SPA olduğu için **403/404 → `/index.html`** kuralına sahip; bu yüzden olmayan bir
`kiosk/*.json` isteği **200 + HTML** dönüyordu (cihaz JSON sanıp ayrıştırma hatası verirdi).
Veri için ayrı dağıtım açıldı:

| | Panel | Veri |
|---|---|---|
| Dağıtım | `EVR6YMP2UVX8A` | **`E9PU19DSTTWRM`** |
| Adres | https://d308vfb9mn2991.cloudfront.net | **https://d2dnrvsx5eevod.cloudfront.net** |
| Origin | `s3://yourkiosk-veri/panel` | `s3://yourkiosk-veri/kiosk` |
| Yol | `/`, `/veri`, … (SPA) | `/lastupdate.json`, `/match.json`, … |
| Hata | 403/404 → `index.html` (200) | **403** (doğru: dosya yok) |
| Önbellek | varlık 1 yıl, index no-cache | **kapalı** (cihaz güncel veriyi görmeli) |

Cihaz ayarı (`kiosk/ayarlar.json`):

```json
"veri": { "dosya_adresi": "https://d2dnrvsx5eevod.cloudfront.net/" },
"calistirma": { "web_veri_modu": "https" }
```

Doğrulama (gerçek): `lastupdate.json` 200 · `lastSystemData.json` 200 (263.634 B) · `yok.json` **403** ·
panel dağıtımı etkilenmedi (/, /veri → 200).

### 7c. Yeniden yayınlama

```bash
./panel/infra/yayinla.sh          # derle + yükle + invalidation
./panel/infra/yayinla.sh --kuru   # yalnız derle
```

---

## 10. Panel yayını için ayrı anahtar (kurulum anahtarı iptal edildikten sonra)

Kurulum anahtarı iptal edildi; artık paneli yayınlamak için **yalnız yayına yetkili** ayrı bir
kullanıcı gerekir. Bu kullanıcı veri yazamaz, Cognito'yu değiştiremez — sadece `panel/` klasörünü
yükler ve CloudFront önbelleğini temizler.

1. IAM → Policies → Create policy → JSON → `panel/infra/yayin-politikasi.json` (doğrulayıcıdan geçti:
   3 ifade geçerli) → ad: `yourkiosk-yayin`
2. IAM → Users → `yourkiosk-yayin` → politikayı ekle → **Create access key**
3. Anahtarı dosyaya koy (sohbete yazma):

```bash
cat > ~/.config/hermes-secrets/aws-yayin.credentials <<'EOF'
[default]
aws_access_key_id = BURAYA
aws_secret_access_key = BURAYA
EOF
chmod 600 ~/.config/hermes-secrets/aws-yayin.credentials
```

4. Yayınla:

```bash
export PATH="$HOME/.local/bin:$PATH"
export AWS_SHARED_CREDENTIALS_FILE="$HOME/.config/hermes-secrets/aws-yayin.credentials"
export AWS_DEFAULT_REGION=eu-central-1
./panel/infra/yayinla.sh            # derle + yükle + invalidation
```

> Yayın anahtarı yalnız `yourkiosk-veri/panel/*` ve **tek** CloudFront dağıtımına yetkili.
> Cihaz verisi (`kiosk/*`) yazamaz → yanlışlıkla veri bozulamaz.
