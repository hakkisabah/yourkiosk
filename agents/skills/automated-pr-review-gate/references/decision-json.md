# Karar JSON'u — şema, fail-closed kuralları, kanıt

Kapının yayına almadan önce doğruladığı karar dosyası. Amaç: ajan "baktım" derken bunu hiçbir şeyin
kanıtlamaması ve kararsızlığın sessizce `onay`a dönüşmesi.

## Şema

```json
{
  "makine": "i5|i3",
  "pr": 42,
  "sha": "<PR head — API'den doğrulanır>",
  "karar": "onay|sorun|red" | "kabul|duzeltme|red|sorun",
  "onem": "yuksek|orta|dusuk",
  "ozet": "3 cümleye kadar, ne yapıldı + risk",
  "bulgular": [{"dosya": "yol/dosya.py", "satir": 42, "onem": "orta",
                "aciklama": "neden sömürülebilir/yanlış (>=15 karakter)",
                "kabul": "neyi yapınca bu bulgu KAPANIR (>=15 karakter)"}],
  "denetlenen": ["gömülü sır", "komut çalıştırma", "dosya/yol", "ağ/TLS", "kimlik/yetki",
                 "girdi doğrulama", "sır sızıntısı", "bağımlılık", "DoS/maliyet",
                 "kalıcılık/geri dönüş", "kapsayıcı/servis", "test kanıtı"],
  "not": "geliştiriciye sıralı talimat"
}
```

## Doğrulama kuralları

| # | Kural | Neden |
|---|---|---|
| 1 | Şema + değer kümeleri | serbest metin kararı makineyle okunamaz |
| 2 | Kapsam: inceleyen makine 12 alanın **tamamını**, karar makinesi en az 8'ini ve üç zorunlu alanı (`gömülü sır`, `kimlik/yetki`, `test kanıtı`) bildirir | bakılmayan alan "temiz" sayılmasın |
| 3 | Tutarlılık: `yuksek` bulgu varken `onay`/`kabul` verilemez; `sorun`/`red`/`duzeltme` boş bulguyla verilemez | en pahalı hata: yüksek risk + onay |
| 4 | Fail-closed: özet/notta "emin değilim", "doğrulanmalı", "karar veremedim" geçiyorsa onay/kabul reddedilir | kararsızlık onaya dönüşmesin |
| 5 | Kanıt (ağ): her `dosya:satir` PR head'inde var mı, satır dosyanın içinde mi; dosya PR'da değişmemişse yalnız uyarı | uydurma bulgu satırı yakalanır |
| 6 | Kapanış ölçütü: `sorun`/`red`/`duzeltme` kararlarında her bulgu `kabul` taşır | ölçütsüz reçete ikinci turda aynı bulguyla döner |
| 7 | Şablon/yol tutucu yasak: `yol/dosya.py`, `buraya`, `şablon` gibi değerler reddedilir | kopyalanmış iskelet karar |

## Fail-closed davranışın sınırı

- Kanıt katmanı token yoksa **uyarıyla geçmemeli**: ya `kanit=False` açıkça verilir (gerekçe günlüğe)
  ya da karar reddedilir. "Token yok → atlandı → geçti" sessiz fail-open'dır.
- Kapıyı atlama anahtarı varsa (`--kapi-atla`) her atlama kalıcı günlüğe yazılmalı ve bir kontrol
  noktası bunları SAYMALI; sayılmıyorsa atlama normalleşir.
- Karar JSON'undaki `sha`, PR'ın güncel head'iyle karşılaştırılır; uyuşmazsa yazma yok, "yeniden
  inceleme gerekir".

## Yorum gövdesi

Kapı geçtikten sonra PR yorumu **`kabul` ve `oneri` alanlarını da basmalı** — kapanış ölçütü
zorunluysa ama yoruma hiç yazılmıyorsa ölçüt geliştiriciye ulaşmaz ve kural kâğıt üstünde kalır.
Yorumun sonunda makine-okunur tek satır JSON bloğu bırak (durum, bulgu sayısı, sha).
