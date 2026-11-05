# Önbellek ve maliyet (600+ cihaz)

## Cihazda (Qt + tarayıcı) — değişiklik yoksa **disk**

| Katman | Nerede | Ne zaman tazelenir |
|---|---|---|
| Veri (`lastSystemData`, `match`, `makinebilgileri`) | `kiosk/onbellek/veri/` (Qt) · Cache Storage (tarayıcı) | `lastupdate` damgası değişince |
| Görseller | `kiosk/onbellek/gorsel/` | **ETag/304 doğrulaması**: sunucu "değişmedi" derse gövde inmez |
| Tetik/komut | bellek + `kiosk/*.json` | MQTT push veya `/degisiklik` uzun yoklama |

Görsel akışı (Qt):
```
gorsel_oku(url)            → diskte ve taze      → AĞA ÇIKMAZ
kayıt bayat + ETag varsa   → kosullu_indir()     → 304 ise GÖVDE İNMEZ, disk kullanılır
                           → 200 ise indir + ETag/Last-Modified sakla
```

> Neden önemli: eskiden `bayat` kayıt her veri güncellemesinde körlemesine yeniden indiriliyordu
> (2,5 MB × 600 cihaz). 304 yanıtının gövdesi yoktur.

## Yoklama aralığı (emniyet ağı)

Anlık güncelleme **MQTT push** (Qt) ve **`/degisiklik` uzun yoklaması** (tarayıcı) ile gelir.
`DAMGA_KONTROL_MS` yalnız "push kaçtı" durumu içindir → varsayılan **300 sn**.

| Cihaz | Aralık | İstek/ay | CloudFront | S3 GET | Toplam |
|---|---|---|---|---|---|
| 600 | 20 sn | 233 M | $174,96 | $93,31 | **$268,27** |
| 600 | **300 sn** | 15,6 M | $11,66 | $6,22 | **$17,88** |
| 1000 | 300 sn | 25,9 M | $19,44 | $10,37 | **$29,81** |

(3 küçük istek/cihaz/tur · CloudFront $0,0075/10k · S3 GET $0,0004/1k)

Ayarlamak için `ayarlar.json` → `calistirma.degisiklik_kontrol_ms` (5000–3600000).

## AWS tarafı

| Bileşen | Ayar | Durum |
|---|---|---|
| **S3 yaşam döngüsü** | **Yalnız `silinebilir=true` etiketli** `kiosk/yayin-gorselleri/` nesneleri 30 gün · eski sürümler 30 gün · `kiosk/tmp/` 7 gün | `deploy/s3/yasam-dongusu.json` (tek doğru kaynak, kurulu) |
| **CORS** | cihaz `GET/HEAD` her origin · panel `PUT` panel origin'leri | `panel/infra/s3-cors.json`, her yayında uygulanır |
| **Panel JS güncellemesi** | `assets/*` 1 yıl `immutable` + `index.html` `no-cache` | `yayinla.sh` |
| **Veri JSON'ları** | `Cache-Control: no-store` (panel yazımı) | edge'de tutulmaz → cihaz her zaman taze okur; push ile anlık |
| **CloudFront invalidation** | panel dağıtımı, yalnız `index.html` değişiminde gerekli | `yayinla.sh` kendisi yapar |

> JSON'ları `no-store` yerine `max-age=30` yapmak origin yükünü 1/30'a indirir ama yayılmayı
> 30 sn geciktirir. Push anlıklığı sağladığı için gerek görülmedi; istenirse panel yazımında
> `CacheControl` değiştirilir.

## Disk bakımı (otomatik silme)

- `onbellek.bakim()` her veri yüklemesinde: veride artık geçmeyen görseller + `son_gosterim + 7 gün`
  geçenler silinir (`onbellek.gorsel_saklama_gun`).
- Kota: `onbellek.maks_bayt` (512 MB) aşılırsa en eski gösterimler atılır.
- S3 tarafında aynı görseller 45 günde otomatik expire.

## Kontrol komutları

```bash
cd kiosk && .venv/bin/python tools/onbellek_durumu.py    # boyut, dosya sayısı, kayıtlar
cd kiosk && .venv/bin/python tools/tarayici_kiosk.py --tani
```
