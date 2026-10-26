# Yedekten geri dönme — tatbikat ve gerçek geri dönüş

S3 sürümleme açık olduğu hâlde **hiç denenmemişti**. Bu belge tatbikatı (zararsız) ve gerçek
kaza anındaki adımları ayırır.

---

## 0. Ön koşul: sürümleme gerçekten açık mı?

```bash
aws s3api get-bucket-versioning --bucket yourkiosk-veri
# beklenen: {"Status": "Enabled"}
aws s3api get-bucket-lifecycle-configuration --bucket yourkiosk-veri
# beklenen: NoncurrentVersionExpiration (bkz. deploy/s3/yasam-dongusu.json)
```

Sürümleme kapalıysa **önce** açın; açmadan yapılan "tatbikat" hiçbir şeyi kanıtlamaz:

```bash
aws s3api put-bucket-versioning --bucket yourkiosk-veri \
  --versioning-configuration Status=Enabled
```

## 0.5 Gereken IAM izinleri (ayrı, dar kapsamlı anahtar)

Yedek tatbikatı **yayın anahtarını kullanmamalı**: geri dönme işlemi yazma yetkisi ister, günlük
yayın anahtarı ise mümkün olduğunca dar kalmalı. Ayrı bir kullanıcı açın (ör. `yourkiosk-yedek`)
ve yalnız şu politikayı verin — politika depoda dosya olarak durur
([`iam-politikasi.json`](iam-politikasi.json)):

```bash
aws iam create-policy --policy-name yourkiosk-yedek \
  --policy-document file://deploy/yedek/iam-politikasi.json
```

İçerik özeti: nesne düzeyinde `s3:GetObject|PutObject|GetObjectTagging|PutObjectTagging`
(`arn:aws:s3:::yourkiosk-veri/kiosk/*`), kova düzeyinde `s3:ListBucket|ListBucketVersions`.

`aws configure --profile yourkiosk-yedek` ile tanımlayın; betikleri `AWS_PROFILE=yourkiosk-yedek`
ile koşun. Politika `s3:DeleteObject` **içermez** — yanlış sürüm seçilirse silme değil, yeni sürüm
yazma olur (geri dönülebilir).

`--liste` ve `--kuru` yalnız okuma yapar; bu iki komut **üretime dokunmaz**, ilk kez denemek için
güvenlidir.

## 1. Tatbikat (üretimi etkilemez)

Amaç: **hangi sürümün ne kadar sürede geri geldiğini** ölçmek ve yanlış sürüm seçme riskini
görmek. Gerçek veri dosyası üzerinde çalışır ama içerik AYNI olduğu için cihazlarda değişiklik
görünmez (yeni sürüm aynı baytlarla yazılır).

```bash
cd deploy/yedek
KOVA=yourkiosk-veri; ANAHTAR=kiosk/lastSystemData.json

./geri_donme.sh --kova $KOVA --anahtar $ANAHTAR --liste      # sürümler
./geri_donme.sh --kova $KOVA --anahtar $ANAHTAR --kuru       # ne yapacağını göster
time ./geri_donme.sh --kova $KOVA --anahtar $ANAHTAR         # gerçek geri dönüş + doğrulama
```

**Kabul ölçütü:** komut `✓ doğrulandı: N bayt` yazar; boyut, seçilen sürümün boyutuyla aynıdır.
Pano/panelde dosyanın `Son değişiklik` alanı güncellenir (yeni sürüm yazıldı).

### Tatbikat kaydı (her çeyrekte bir kez doldurulur)

| Alan | Değer |
|---|---|
| Tarih / yapan | |
| Geri dönülen sürüm | |
| Süre (komut → doğrulama) | |
| Cihazda görünme süresi (canlı_test) | |
| Sorun / not | |

## 2. Gerçek kaza: veri bozuldu / yanlış yayın gitti

Sıra **önemlidir** — ters sırada yapmak cihazları eski veride bırakır:

1. **Veri dosyasını geri getir**: `./geri_donme.sh --kova K --anahtar kiosk/lastSystemData.json`
2. **`lastupdate.json` damgasını tazele** (yoksa cihaz "değişmedi" sanıp indirmez):
   `./geri_donme.sh --kova K --anahtar kiosk/lastupdate.json` — ya da panelden herhangi bir
   kayıt yapıp damganın tazelenmesini sağla.
3. **Panelden "Bildir"** (ya da `kiosk/tools/nobet_tetikle.py`).
4. **Cihazda doğrula**: `tools/canli_test.py` → tüm halkalar yeşil; ekranda beklenen kayıtlar.
5. **Neden oldu?** `aws s3api list-object-versions` çıktısındaki `LastModified` + panel
   günlüğüyle kimin/neyin yazdığını bul; tekrarını engelleyecek testi ekle.

## 3. Yayın görselleri

Görseller içerik adlıdır (`kiosk/yayin-gorselleri/<sha>.webp`): yanlış bir görsel "üzerine
yazılarak" bozulamaz, yalnız yanlış adres veri dosyasına yazılır. Bu yüzden 2. adımdaki veri
geri dönüşü görselleri de düzeltir; ayrıca görsel geri dönmeye gerek yoktur (aynı sha → aynı nesne).

## 4. Bilinen sınırlar

* Panel Cognito modunda **silme** yapabilir; silinen nesne sürümleme sayesinde geri gelir, ama
  Lambda modunda silme kapalıdır (yaşam döngüsü kuralı kullanılır).
* Sürümler `NoncurrentVersionExpiration` ile **30 gün** sonra silinir (maliyet). Daha uzun
  saklama gerekiyorsa `deploy/s3/yasam-dongusu.json` içindeki değeri büyütün.
* Bu tatbikat **S3 tarafını** kanıtlar; cihazın kendi disk önbelleğinden geri dönüş yolu ayrıdır
  (bozuk önbellek → `onbellek/` klasörü silinip yeniden indirilir; veri kaybı yoktur).
