# Panel — Cognito'suz mod (Lambda + cookie)

Bu klasör, yönetim panelini **Cognito olmadan** çalıştırmak içindir (maliyet/gerekçe: `../MAALIYET.md`).
Panelde `VITE_AUTH_MODU=lambda` seçildiğinde kullanılır.

```
Tarayıcı ──POST /giris {şifre}──► Lambda ──► Set-Cookie: yk_oturum=… (HttpOnly, Secure, HMAC imzalı)
        ──POST /imzala {dosya,işlem}──► Lambda ──► { url } (presigned GET/PUT, 5 dk)
        ──GET/PUT imzalı URL──► S3
```

## Ne kazandırır?

* **Cognito hiç kullanılmaz** → AWS hesabında yönetilen kimlik servisi olmaz; silme/kurma derdi yok.
* Tarayıcı **hiçbir AWS anahtarı görmez** (Cognito modunda geçici anahtar bulunur).
* Maliyeti: Lambda kalıcı ücretsiz kotası (ayda 1 M istek) — panel günde ~50 istek yapar → **$0,00**.

## Dosyalar

| Dosya | Görev |
|---|---|
| `handler.py` | Tüm uç noktalar: `/giris`, `/oturum`, `/cikis`, `/imzala` |
| `sifre_ozetle.py` | Yönetici şifresinden `PANEL_SIFRE_OZETI` üretir (şifre düz metin saklanmaz) |
| `tests/test_handler.py` | şifre özeti, cookie imzası/süresi/kurcalanması, beyaz liste, boyut sınırı, CORS/CSRF, hız sınırı |
| `requirements.txt` | `boto3` (Lambda çalışma zamanında zaten vardır) |

## Dayatılan kurallar (testlerle kilitli)

* Dosya adı **beyaz listede** olmalı: `ayarlar.json`, `kapsam-ayarlari.json`, `lastSystemData.json`,
  `sablon.json`, `match.json`, `lastupdate.json`, `makinebilgileri.json`. Yol kaçışı (`../`) reddedilir.
* Yalnızca `oku` ve `yaz` imzalanır; **silme yoktur**.
* Yazma boyutu en çok **32 MB** (ayrıca Lambda yük limiti 6 MB — büyük veri için panel doğrudan S3'e
  yazmayı Cognito modunda yapmalıdır; bkz. aşağıdaki not).
* Oturum cookie'si **12 saat** (ayarlanabilir), HttpOnly + Secure + SameSite=Lax, HMAC-SHA256 imzalı.
* Giriş denemesi hız sınırı: 5 dakikada 8 hatalı deneme → 429.
* `Origin` başlığı `PANEL_ORIGIN` ile eşleşmezse **403** (CSRF).

> **6 MB notu:** Lambda Function URL gövdesi 6 MB ile sınırlıdır. 20-30 MB'lık `lastSystemData.json`
> yazımı **Cognito modunda** (panel doğrudan S3'e yazar) sorunsuzdur. Lambda modunda bu boyutta veri
> yazmak isterseniz imzalamayı S3'e **yükleme sonrası** değil, panele **çok parçalı yükleme** (multipart)
> imzası verecek şekilde genişletmek gerekir — bu sürümde yoktur, README'de sınır olarak yazılıdır
> (veri yazımı 6 MB'a kadar Lambda modunda, üstü Cognito modunda).

---

## Kurulum

### 1) Şifre özeti

```bash
python3 sifre_ozetle.py            # güçlü bir yönetici şifresi girin
# çıktı: pbkdf2_sha256$260000$<salt>$<özet>
```

### 2) IAM rolü (yalnızca gerekli izin)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::KOVA_ADI/ON_EK*" },
    { "Effect": "Allow", "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::KOVA_ADI",
      "Condition": { "StringLike": { "s3:prefix": ["ON_EK*"] } } }
  ]
}
```

### 3) Lambda

```bash
cd panel/lambda
zip -r fonksiyon.zip handler.py            # boto3 çalışma zamanında hazır
aws lambda create-function --function-name yourkiosk-panel \
  --runtime python3.12 --handler handler.lambda_handler \
  --role arn:aws:iam::<HESAP>:role/<ROL> --zip-file fileb://fonksiyon.zip \
  --timeout 10 --memory-size 256 \
  --environment "Variables={KOVA_ADI=yourkiosk-veri,ON_EK=kiosk/,PANEL_ORIGIN=https://panel.example.com,OTURUM_SURE_S=43200,OTURUM_ANAHTARI=<RASTGELE_64_KARAKTER>,PANEL_SIFRE_OZETI=<1. ADIMDAKI_OZET>}"
```

* `OTURUM_ANAHTARI`: `python3 -c "import secrets;print(secrets.token_urlsafe(48))"` ile üretin.
* **Function URL** (CORS'u biz yönettiğimiz için `--cors` vermeyin, tarayıcıdan cookie gitsin):

```bash
aws lambda create-function-url-config --function-name yourkiosk-panel \
  --auth-type NONE --invoke-mode RESPONSE_STREAM
aws lambda add-permission --function-name yourkiosk-panel \
  --statement-id url --action lambda:InvokeFunctionUrl \
  --principal "*" --function-url-auth-type NONE
```

Function URL'i `panel/.env.local` içindeki `VITE_API_URL` değerine yazın (sonunda `/` olmadan).

> Not: `auth-type NONE` yalnızca uç noktanın açık olması demektir; **yetkilendirmeyi kendi şifre+cookie
> katmanımız** yapıyor. Uç noktayı mümkünse CloudFront/WAF arkasına alıp IP kısıtı ekleyin.

### 4) Panel tarafı

```bash
cd panel
cp .env.ornek .env.local
#   VITE_AUTH_MODU=lambda
#   VITE_BUCKET=yourkiosk-veri
#   VITE_PREFIX=kiosk/
#   VITE_API_URL=https://<function-url>
npm run build && aws s3 sync dist/ s3://PANEL_KOVASI/ --delete
```

Panel ile Lambda **farklı origin**'lerde olduğundan tarayıcı cookie'yi gönderebilmesi için:
`credentials: 'include'` (panelde hazır) + Lambda'da `PANEL_ORIGIN` **tam adres** olmalıdır.
Kendi kovanızda CloudFront kullanıyorsanız aynı alan adı altında `/api/*` yolunu Function URL'e
yönlendirmek de mümkündür.

### 5) Güncelleme / test

```bash
cd panel/lambda
python3 -m venv .venv && .venv/bin/pip install pytest boto3
.venv/bin/python -m pytest tests -q          # handler testleri
aws lambda update-function-code --function-name yourkiosk-panel --zip-file fileb://fonksiyon.zip
```

## Cognito'yu kaldırmak / geri dönmek

* **Kaldırma:** `VITE_AUTH_MODU=lambda` + bu Lambda kurulumu; ardından Cognito kaynaklarını silin
  (`aws cognito-idp delete-user-pool`, `aws cognito-identity delete-identity-pool`) — adımlar `../MAALIYET.md` §2.3.
* **Geri dönme:** `VITE_AUTH_MODU=cognito` yapıp `../README.md` §2.3 adımlarını uyguların; **panel kodu değişmez**,
  her iki mod aynı ekranları ve aynı doğrulamaları kullanır (`src/aws/veriKaynagi.ts`).
