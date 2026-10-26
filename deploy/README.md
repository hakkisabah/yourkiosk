# deploy/ — canlı kurulum, sertleştirme, yedek, izleme

Bu dizin **çalışma zamanı altyapısını** kurar. Hepsi `sudo`/`root` ile koşar; hiçbiri kiosk
uygulamasının kendisi değildir (o `kiosk/`, panel `panel/`).

> Nereden başlamalı? Sırayla: **1) cihaz kurulumu** ([`CANLIYA-GECIS.md`](CANLIYA-GECIS.md)) →
> **2) MQTT/anlık bildirim** ([`mosquitto/KURULUM.md`](mosquitto/KURULUM.md), isteğe bağlı) →
> **3) yedek tatbikatı** ([`yedek/README.md`](yedek/README.md)) → **4) maliyet alarmları**
> ([`cloudwatch/README.md`](cloudwatch/README.md)).

---

## 1. Ne var?

| Yol | Ne yapar | Ne zaman gerekir |
|---|---|---|
| [`CANLIYA-GECIS.md`](CANLIYA-GECIS.md) | Uçtan uca canlıya geçiş listesi: S3 kovası, yaşam döngüsü, CloudFront, cihaz kullanıcısı, servisler | **Zorunlu** |
| [`guncelle.sh`](guncelle.sh) | Gece güncellemesi: **imzalı `yayin-*` etiketi** (GPG doğrulamalı) → derleme → servis yeniden başlatma → **sağlık kapısı** (başarısızsa geri döner) | Zorunlu |
| [`kur-guncelle-betigi.sh`](kur-guncelle-betigi.sh) | `guncelle.sh` kopyasını `/usr/local/lib/yourkiosk/` altına **root:root** kurar (birimin çalıştırdığı kopya) | `guncelle.sh` her değiştiğinde |
| [`systemd/`](systemd/) | `yourkiosk-kiosk.service` (ekran) + `yourkiosk-guncelle.service` (güncelleme), sertleştirilmiş | Zorunlu |
| [`mosquitto/`](mosquitto/) | TLS'li MQTT broker kurulumu, kullanıcı/ACL üretimi, cihaz başına kimlik, doğrulama | Anlık bildirim + 600 cihaz izleme istiyorsanız |
| [`yedek/`](yedek/) | S3 sürümlerinden geri dönme + **tatbikat** (zararsız prova); IAM politikası: [`yedek/iam-politikasi.json`](yedek/iam-politikasi.json) | Üretime girmeden **önce** |
| [`cloudwatch/`](cloudwatch/) | Fatura/5xx/Lambda alarmları (ücretsiz kota içinde kalacak şekilde); IAM politikası: [`cloudwatch/iam-politikasi.json`](cloudwatch/iam-politikasi.json) | Üretime girmeden önce |
| [`gorseller-yukle.sh`](gorseller-yukle.sh) | Yayın görsellerini (`<sha>.webp`) S3'e yükler, adresi doğrular, panelde girilecek URL'yi yazar | Görsel yayınlarken |
| [`s3/`](s3/) | Kova yaşam döngüsü politikası (eski sürüm/görsel temizliği) | Zorunlu |
| [`docker/`](docker/) | Panel/web için yerel geliştirme ortamı | Yalnız geliştirme |

## 2. Hangi AWS izni nerede gerekir?

Politikalar **dosya olarak depoda** durur (sohbetten kopyalanacak metin yok):

| Dosya | Kullanıcı | Ne için |
|---|---|---|
| [`yedek/iam-politikasi.json`](yedek/iam-politikasi.json) | `yourkiosk-yedek` | S3 sürüm okuma + aynı baytları geri yazma (tatbikat) |
| [`cloudwatch/iam-politikasi.json`](cloudwatch/iam-politikasi.json) | `yourkiosk-alarm` | Alarm kurma/silme + SNS konusu + fatura metriği okuma |

Kurulum (bir kez, her iş için ayrı kullanıcı):

```bash
for is in yedek alarm; do
  dosya="deploy/$([[ $is == yedek ]] && echo yedek || echo cloudwatch)/iam-politikasi.json"
  aws iam create-policy --policy-name "yourkiosk-$is" --policy-document "file://$dosya"
done
# sonra: IAM kullanıcısı aç, politikayı bağla, erişim anahtarını `aws configure --profile` ile tanımla
```

Özet (ayrıntı ve gerekçe ilgili README'de):

| İş | Ayrı IAM kullanıcısı | Asgari izinler |
|---|---|---|
| Günlük yayın (panel) | `yourkiosk-yayin` | `s3:GetObject`, `s3:PutObject`, `s3:ListBucket`, `cloudfront:CreateInvalidation` — `arn:aws:s3:::yourkiosk-veri/kiosk/*` |
| Yedek tatbikatı | `yourkiosk-yedek` | `s3:GetObject`, `s3:PutObject`, `s3:ListBucketVersions`, `s3:GetObjectTagging`, `s3:PutObjectTagging` |
| Maliyet alarmları | `yourkiosk-alarm` | `cloudwatch:PutMetricAlarm`, `DescribeAlarms`, `DeleteAlarms`, `GetMetricStatistics`, `ListMetrics`; `sns:CreateTopic`, `Subscribe`, `ListTopics` |
| Gece güncellemesi | — (cihazda root) | AWS izni **gerekmez**: yalnız `git`/`npm`/`systemctl` |

> **En az yetki:** yayın anahtarını yedek/alarm işlerine **vermeyin**. Üç iş üç ayrı kullanıcı.

## 2.5 Yayın görselleri (tek komut)

Görseller içerik adlıdır: `kiosk/yayin-gorselleri/<16 hex sha>.webp`. Ad = içerik özeti olduğu için
aynı görsel iki kez yüklenirse aynı anahtara gider; adres değişmediği için CloudFront'ta
`immutable` önbellek güvenlidir ve cihaz önbelleği bozulmaz.

```bash
# 1) PNG/JPEG → WebP (küçültme + kalite; çıktı adı sha'dan gelir)
kiosk/.venv/bin/python kiosk/tools/gorsel_webp.py yayin.png --cikti /tmp/gorsel

# 2) yükle + doğrula (yükleme sonrası panelde girilecek tam adresi yazar)
cd deploy && ./gorseller-yukle.sh --kova yourkiosk-veri \
  --dagitim d2dnrvsx5eevod.cloudfront.net /tmp/gorsel/*.webp
```

Çıktıdaki adres `Yayinlar.<id>.contentUrl` alanına yazılmalıdır. **İki yol var:**

* **Tek görsel (panel):** *Nöbet ve Yayınlar* → yayın satırı → **Görsel** → "Görsel adresi
  (contentUrl)" → **Uygula** → **Kaydet** → **Bildir**. Panel adresi cihaz kurallarından geçirir
  (`https`, port 443, kullanıcı adı/parola yok, uzantı varsa png/jpg/jpeg/webp).
* **Toplu geçiş (araç):** adresi veri dosyasına `gorsel_webp.py --veri --yaz` ile yazıp S3'e
  yükleyin — sıra önemlidir, önce görseller sonra veri dosyası:

```bash
# 1) tüm yayın görsellerini WebP'ye çevir + contentUrl'leri veri dosyasına YAZ (yedek: *.bak)
#    WebP dosyaları lastSystemData.json'un yanındaki yayin-gorselleri/ klasörüne yazılır.
kiosk/.venv/bin/python kiosk/tools/gorsel_webp.py --veri lastSystemData.json \
  --url-taban https://<dağıtım>/kiosk/yayin-gorselleri --yaz

# 2) üretilen WebP'leri S3'e yükle (veri dosyasındaki adresler BUNLARA işaret eder)
cd deploy && ./gorseller-yukle.sh --kova yourkiosk-veri \
  --dagitim d2dnrvsx5eevod.cloudfront.net ../yayin-gorselleri/*.webp && cd ..

# 3) veri dosyasını yükle + damgayı tazele → cihazlar ≤1 turda yeni adresi çeker
aws s3 cp lastSystemData.json s3://yourkiosk-veri/kiosk/lastSystemData.json \
  --cache-control "public,max-age=60"
printf '{"lastupdate": "%s"}\n' "$(date '+%Y-%m-%d %H:%M:%S')" > lastupdate.json
aws s3 cp lastupdate.json s3://yourkiosk-veri/kiosk/lastupdate.json --cache-control "no-cache"
```

Panel güncellemesi (#88) yayınlandıktan sonra aynı adres panelde **"Nöbet ve Yayınlar"** ekranından
doğrudan girilebilecek; o zamana kadar yukarıdaki üç adım kullanılır. `aws` CLI yoksa:
`python3 -m pip install --user awscli`. `--kuru` (yükleme betiğinde) hiçbir şey yüklemeden ne
yapacağını gösterir.

## 3. Doğrulama (kurulumdan sonra)

```bash
# servisler
systemctl status yourkiosk-kiosk.service --no-pager
systemctl list-timers yourkiosk-guncelle.timer      # gece güncellemesi planlı mı

# güncelleme betiği ne yapacağını göstersin (hiçbir şeyi değiştirmez)
sudo /usr/local/lib/yourkiosk/guncelle.sh --kuru

# MQTT zinciri (broker kurulduysa)
MQTT_PAROLA_PANEL=… MQTT_PAROLA_CIHAZ=… MQTT_PAROLA_IZLEME=… \
MQTT_CIHAZ_KULLANICI=cihaz-C1 MQTT_CIHAZ_PAROLA=… \
  bash deploy/mosquitto/dogrula.sh <broker-adresi>

# yedek tatbikatı (zararsız: aynı baytları geri yazar)
cd deploy/yedek && ./geri_donme.sh --kova yourkiosk-veri --anahtar kiosk/lastSystemData.json --kuru
```

## 4. Güvenlik modeli (özet)

* **Güncelleme:** birim `root` ama **root'a ait kopyayı** çalıştırır
  (`/usr/local/lib/yourkiosk/guncelle.sh`); depo işlemleri `runuser -u kiosk` ile ayrıcalıksız.
  Root yalnız `systemctl restart` yapar.
  **Yalnız imzalı yayın etiketinden günceller:** `origin/main` üzerindeki `yayin-*` desenli
  ANNOTATED + GPG imzalı en yeni etiket `git verify-tag` ile doğrulanır; doğrulanmazsa (imza yok,
  anahtar yok) güncelleme **reddedilir** (çıkış 6) ve günlüğe açık satır yazılır — `main` ucu
  imzasız çekilip çalıştırılmaz. Anahtar kurulumu (cihaz başına bir kez):
  ```bash
  sudo runuser -u kiosk -- gpg --import yayin-anahtari.asc   # yayın imza anahtarının AÇIK anahtarı
  ```
  Anahtarı olmayan cihazda `--kuru` uyarı verir, gerçek koşu güncellemeyi atlar (fail-closed).
  **Kopya kendini yenilemez** (bilerek): root'un, `kiosk` kullanıcısının yazabildiği dosyayı
  `/usr/local/lib`'e kopyalaması yerel yetki yükseltmesi olurdu; ayrıca `ProtectSystem=full`
  altında `/usr` salt-okunur olduğu için böyle bir kopyalama `EROFS` ile düşerdi.
  `guncelle.sh` her değiştiğinde deploy adımı olarak root çalıştırın:
  `sudo deploy/kur-guncelle-betigi.sh` (depo temiz değilse kurmaz). Fark varsa gece koşusu
  günlüğe "kopya depodaki sürümden farklı" uyarısı yazar — sessiz kalmaz.
* **MQTT:** paylaşılan `cihaz` hesabı yalnız yayın konusunu **okur**; kalp atışı için **cihaz
  başına** kullanıcı (`cihaz-ekle.sh`) gerekir. Aksi hâlde bir cihaz diğerini taklit edebilirdi.
* **Panel:** broker parolası derleme paketine **gömülmez** (CloudFront paketi kimlik
  doğrulamasız indirilebilir). Panelde iki sır da çalışma anında bir kez sorulur ve yalnız
  `sessionStorage`'da tutulur: yayın parolası (`panel/src/domain/push.ts`) ve izleme kimliği
  (`izlemeKimligi.ts`). Sır yoksa yayın FAIL-CLOSED olur; sayfa yenilenince yeniden sorulur.
* **Sırlar:** SNS ARN gibi hesap kimlikleri çalışma ağacına yazılmaz
  (`${XDG_STATE_HOME:-~/.local/state}/yourkiosk/`).

Bu kuralların sessizce geri alınmaması için metin testleri var:
`kiosk/tests/test_guncelle_yetki.py`, `kiosk/tests/test_mosquitto_acl.py`.
