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
`DAMGA_KONTROL_MS` yalnız "push kaçtı" durumu içindir.

| Kurulum | Aralık | İstek/ay | CloudFront | S3 GET | Toplam |
|---|---|---|---|---|---|
| 600 · push **kapalı (bugünkü varsayılan)** | **30 sn** | 51,8 M | $38,88 | $20,74 | **$59,62** |
| 600 · push **bağlı** | 120 sn | 13,0 M | $9,72 | $5,18 | **$14,90** |
| 600 · tarihsel (20 sn, eski) | 20 sn | 77,8 M | $58,32 | $31,10 | **$89,42** |
| 600 · tarihsel (300 sn, eski) | 300 sn | 5,2 M | $3,89 | $2,07 | **$5,96** |
| 1000 · push bağlı | 120 sn | 21,6 M | $16,20 | $8,64 | **$24,84** |

(**1 istek/cihaz/tur** — **Qt modu**: cihaz `durum.json`u tek istekte okur — damga + tetikleyici +
komut işareti aynı belgede. **Tarayıcı modu tur başına en çok 2 istek** yapar: `lastupdate.json`
(+ değiştiyse `durum.json`) ve `tetikle.json`; o modda CloudFront maliyetini 2 ile çarpın
(`web/src/veri/kaynak.ts`). Tablodaki değerler Qt modunun tabanıdır.
CloudFront $0,0075/10k · S3 GET $0,0004/1k · tur = 2.592.000 sn/ay.
Eski tablo "3 küçük istek/tur" varsayıyordu; 26 Ekim i5 ölçümü bu yüzden 3 kat şişikti.)

> **Varsayılan bugün 30 sn** çünkü `config.TETIK_PUSH_AKTIF = False` (MQTT push kurulu değil).
> Push açıldığında `yoklama_araligi()` 120 sn'ye geçer. 600 cihazda fark: **$59,62 → $14,90/ay**.

Ayarlamak için `ayarlar.json` → `calistirma.degisiklik_kontrol_ms` (5000–3600000). Bu anahtar
`config.DAMGA_KONTROL_MS`u yazar; Qt **çalışma anında** `DAMGA_KONTROL_MS_PUSH` /
`DAMGA_KONTROL_MS_PUSH_YOK` kullanır (`pharmacy_app.yoklama_araligi`), yani tek başına Qt'yi
bağlantıya göre seçimden çıkarmaz.

## AWS tarafı

| Bileşen | Ayar | Durum |
|---|---|---|
| **S3 yaşam döngüsü** | `kiosk/yayin-gorseller/` 45 gün · eski sürümler 30 gün · yarım multipart 7 gün | `panel/infra/s3-lifecycle.json` (kurulu) |
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
