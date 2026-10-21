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

## 3. Komut günlüğü

> Her adım buraya **çalıştırılan komut + sonuç** olarak eklenecek.

| Tarih | Adım | Komut | Sonuç |
|---|---|---|---|
| 21.10 | Politika doğrulama | `./panel/infra/politika_dogrula.py panel/infra/kurulum-politikasi.json` | ✓ 6 ifade |
| 21.10 | İlk denemede bulunan hatalar | IAM konsolu | `s3:HeadObject` yok · `s3:*BucketLifecycleConfiguration` yok (doğrusu `s3:Get/PutLifecycleConfiguration`) · `HESAP_ID` ARN'de geçersiz · `_aciklama` alanı IAM'de geçersiz → hepsi düzeltildi |
| — | Anahtar bekleniyor | — | — |

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
