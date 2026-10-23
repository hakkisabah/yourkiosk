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

## Çözüm A — cihazlar `kiosk/*` okusun (uzun vadeli, CloudFront işi)

1. CloudFront'ta `kiosk/*` için yeni behavior + **OAC** (origin access control).
2. Kova politikasına dağıtımın hizmet sorumlusu (`cloudfront.amazonaws.com`, `SourceArn`) için
   `kiosk/*` okuma izni.
3. Cihazda `veri.dosya_adresi = https://…/kiosk/`.

Avantaj: panel rolü `kiosk/*` ile sınırlı kalır (köke yazamaz). Dezavantaj: 3 AWS adımı.

## Kontrol listesi (her iki çözümde)

- [ ] `./panel/infra/env_denetle.py` → `✓ .env.local tamam`, önek uyarısı **yok**
- [ ] `./panel/infra/yayinla.sh` → `✓ canlı panel doğru derlenmiş`
- [ ] Kiosk `--tani` → `MQTT push … bağlı ✓`
- [ ] Panelden değişiklik + Bildir → kiosk ≤ 2 sn
- [ ] Kiosk log: `tetik: değişiklik alındı → yenileniyor`
