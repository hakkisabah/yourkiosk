# Panel ↔ cihaz isim alanı (önek) sorunu

## Belirti

Panelde nöbet/yayın değiştirilir, **Bildir**'e basılır, kiosk ekranı değişmez.

## Neden

| Kim | Nereye bakıyor |
|---|---|
| Panel | `s3://yourkiosk-veri/` **+ `VITE_PREFIX`** (şu an `kiosk/`) |
| Cihaz | `DOSYA_ADRESI` = `https://d2dnrvsx5eevod.cloudfront.net/` → **kök** |

İki ayrı isim alanı: panel `kiosk/ayarlar.json`'a yazar, cihaz `/ayarlar.json`'ı okur. Ayrıca
`/kiosk/*` CloudFront'tan anonim okunamıyor (403), bu yüzden cihaz verisi kökte duruyor.

## Çözüm B — panel köke yazsın (hızlı, AWS tarafı 1 politika)

1. Panel rolüne kök yetkisi ver (`panel/infra/panel-rol-politikasi.json`):

   ```bash
   aws iam put-role-policy --role-name yourkiosk-panel-s3-v2 \
     --policy-name yourkiosk-panel-kok \
     --policy-document file://panel/infra/panel-rol-politikasi.json
   ```

   İçerik: kökteki `*.json` + görseller (`png/jpg/webp`) okuma-yazma-silme, `kiosk/*` (eski yol,
   geriye uyum), `ListBucket` için `""` ve `kiosk/*` önekleri.

2. `panel/.env.local` içinde öneki **boşalt**:

   ```bash
   VITE_PREFIX=
   ```

3. Panel'i yeniden yayınla ve canlıyı doğrula:

   ```bash
   ./panel/infra/yayinla.sh          # sonunda: ✓ canlı panel doğru derlenmiş
   ```

4. Test: panel → Nöbetler/Yayınlar → değiştir → **Bildir** → kiosk **~1 sn** içinde güncellenmeli.

## Çözüm A — cihazlar `kiosk/*` okusun (önerilen, uzun vadeli)

Amaç: panel `kiosk/…` yazar, cihaz da **aynı** yerden okur. Panel rolü `kiosk/*` ile sınırlı kalır.

> **Önemli:** CloudFront'ta yeni behavior gerekmiyor. Veri dağıtımı zaten tüm yolları aynı origin'e
> (kova kökü) gönderiyor; `kiosk/match.json` isteği bucket'a `kiosk/match.json` olarak gidiyor.
> 403'ün nedeni **kova politikası**: `kiosk/*` için CloudFront OAC izni yok.

### Otomatik (tek komut, önce plan)

```bash
cd ~/projeler/yourkiosk

./panel/infra/onek_gecis.py                 # PLAN: ne değişecek (hiçbir şey yazmaz)
./panel/infra/onek_gecis.py --uygula        # politika + veri dosyası kopyalama
```

Yaptıkları:
1. Veri dağıtımını alan adından bulur (`d2dnrvsx5eevod.cloudfront.net` → ID + ARN).
2. Kova politikasına `KioskOnekOAC` ifadesini ekler (mevcut ifadeler korunur, tekrar eklemez):
   `Service: cloudfront.amazonaws.com` · `s3:GetObject` · `arn:aws:s3:::yourkiosk-veri/kiosk/*` ·
   `Condition: AWS:SourceArn = <veri dağıtımı ARN>`.
3. `kiosk/` altında eksik veri dosyalarını kökten kopyalar
   (`lastupdate.json`, `lastSystemData.json`, `match.json`, `makinebilgileri.json`, `sablon.json`, `ayarlar.json`).
4. `https://d2dnrvsx5eevod.cloudfront.net/kiosk/match.json` → **200** doğrular.

### Elle (konsoldan yapmak istersen)

1. **CloudFront → Distributions →** `d2dnrvsx5eevod.cloudfront.net` olan dağıtım → **ID** ve **ARN**'i kopyala.
2. **S3 → yourkiosk-veri → Permissions → Bucket policy → Edit**; mevcut listenin sonuna ekle:

   ```json
   {
     "Sid": "KioskOnekOAC",
     "Effect": "Allow",
     "Principal": { "Service": "cloudfront.amazonaws.com" },
     "Action": "s3:GetObject",
     "Resource": "arn:aws:s3:::yourkiosk-veri/kiosk/*",
     "Condition": { "StringEquals": { "AWS:SourceArn": "arn:aws:cloudfront::321255536632:distribution/<VERI_DAGITIM_ID>" } }
   }
   ```

3. `kiosk/` altına veri dosyalarını kopyala (S3 → kopyala/yapıştır ya da `aws s3 cp`).
4. Tarayıcıda doğrula: `https://d2dnrvsx5eevod.cloudfront.net/kiosk/match.json` → JSON gelmeli.
   Gelmiyorsa: CloudFront **Invalidation** `/*` (politika değişikliği 403'ü cache'lemiş olabilir).

### Cihazı yeni öneke çevir

```bash
cd kiosk
.venv/bin/python tools/push_ayarla.py --broker yourkiosk.hakkisabah.com \
    --kullanici cihaz --parola-sor \
    --veri-adresi https://d2dnrvsx5eevod.cloudfront.net/kiosk/ --dene
.venv/bin/python tools/tarayici_kiosk.py --tani | grep -E "cihaz kimliği|match.json eşleşme|paket sürümü"
```

Beklenen: `cihaz kimliği` dolu · `match.json eşleşme: VAR ✓`.

### Panel tarafı

`panel/.env.local` içinde `VITE_PREFIX=kiosk/` **kalır** (artık doğru). Panelde bir değişiklik yap →
**Bildir** → kiosk ≤ 2 sn içinde güncellenmeli.

### Geri dönüş (gerekirse)

- Cihaz: `push_ayarla.py --veri-adresi https://d2dnrvsx5eevod.cloudfront.net/` (öneksiz)
- Politika: `KioskOnekOAC` ifadesini sil (zararsız durur, cihazlar okumazsa da bir şey bozulmaz)

## Kontrol listesi (her iki çözümde)

- [ ] `./panel/infra/env_denetle.py` → `✓ .env.local tamam`, önek uyarısı **yok**
- [ ] `./panel/infra/yayinla.sh` → `✓ canlı panel doğru derlenmiş`
- [ ] Kiosk `--tani` → `MQTT push … bağlı ✓`
- [ ] Panelden değişiklik + Bildir → kiosk ≤ 2 sn
- [ ] Kiosk log: `tetik: değişiklik alındı → yenileniyor`
