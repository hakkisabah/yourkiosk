# Panel ↔ cihaz isim alanı — DURUM: SORUN YOK (originPath ile çözülmüş)

## Gerçek durum (23.10.2026, kanıtlı)

Veri dağıtımının (`d2dnrvsx5eevod.cloudfront.net`, `E9PU19DSTTWRM`) origin'inde **`originPath = /kiosk`**
ayarlı. Yani:

| İstek | S3'te okunan anahtar |
|---|---|
| `https://d2dnrvsx5eevod.cloudfront.net/match.json` | `kiosk/match.json` |
| `https://d2dnrvsx5eevod.cloudfront.net/kiosk/match.json` | `kiosk/kiosk/match.json` → **403** |

Panel `VITE_PREFIX=kiosk/` ile `kiosk/*` yazar; cihaz **kök adresten** okur → aynı nesneler.
**Ek CloudFront/OAC/politika işi GEREKMEZ.**

## Yapılmaması gerekenler

- Cihaza `--veri-adresi https://…/kiosk/` **vermeyin** → çift önek → 403 → “match.json okunamadı”.
- `onek_gecis.py --uygula` **gereksizdir**; yalnız teşhis için `--teshis` kullanılabilir.
- Kova politikasındaki `CloudFrontVeriOku` (`kiosk/*` → E9PU19DSTTWRM) doğrudur, değiştirmeyin.

## "Panelde değiştirdim, cihaz değişmedi" ise bakılacaklar

1. **`lastupdate.json` damgası** — panel kaydı damgayı tazelemeli (23.10.2026'da düzeltildi; eski panel
   sürümü damgayı güncellemiyordu ve cihaz önbellekten eski gövdeyi gösteriyordu).
2. **Tetik/MQTT** — cihaz log'unda `tetik: değişiklik alındı → yenileniyor` var mı; `--tani` çıktısında
   `MQTT push … bağlı ✓`.
3. **Panel sürümü** — `./panel/infra/yayinla.sh` sonunda `✓ canlı panel doğru derlenmiş` görmeli.
4. **Tarayıcı önbelleği** — cihaz `no-store` ile okuyor; sorun olmamalı.

## Invalidation hakkında

Kalıcı bir kural değildir, o anki önbelleği temizler. `/*` = **1 path** (ayda ilk 1.000 path ücretsiz).
JSON'lar `Cache-Control: no-store` ile yüklenir (panel) → normalde invalidation gerekmez; yalnız
`index.html` gibi uzun önbellekli dosyalar değiştiğinde gerekir.
