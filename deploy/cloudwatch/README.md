# CloudWatch alarmları — ücretsiz sınır içinde kalarak

Amaç: fatura ve yayın hatalarında **erkenden** haber almak; aylık CloudWatch maliyeti **$0**
kalsın. Bu belge hangi alarmın kurulacağını, hangi izinlerin gerektiğini ve ücretsiz kotanın
nereye kadar yettiğini yazar.

---

## 1. Ücretsiz kota (AWS fiyatlandırma sayfası, Ekim 2026)

| Kalem | Ücretsiz | Bizim kullanım |
|---|---|---|
| **Alarm metrikleri** (standart çözünürlük, Metrics Insights sorgusu YOK) | **10 / ay** | 3 (S3 alarmı açılırsa 4) |
| Özel (custom) metrik | 10 / ay | 0 (AWS servis metriklerini kullanıyoruz) |
| API istekleri | 1.000.000 / ay | birkaç yüz |
| Panolar | 3 | 1 |
| Günlük (Logs) alımı/saklama | 5 GB | kullanmıyoruz |

* Yüksek çözünürlüklü (10 sn) alarm, **anomali** alarmı ve **composite** alarm ücretsiz kotaya
  girmez (sırasıyla $0,30 / $0,30 / $0,50 alarm-metrik ayı). Bu yüzden hepsi **standart (60 sn)**.
* Alarm silinince ücret durur; 10'u aşarsak alarm-metrik başına **$0,10/ay** (4 alarm = $0,40).
* Fatura alarmı **`us-east-1`** bölgesinde ve `AWS/Billing` ad alanında yaşar; başka bölgede
  oluşturursanız **hiç veri gelmez** (sessiz alarm = en kötü alarm).
* **S3 5xx istisnası:** `AWS/S3` günlük depolama metrikleri ücretsizdir ama `5xxErrors` gibi
  **istek metrikleri** kovada "request metrics" açılmadan gelmez; açmak istek başına ücretlidir
  (≈$0.30/1M istek + birkaç sent). Tam `$0` hedefi için `S3_ALARM=0` verin — cihazların gördüğü
  hatayı CloudFront 5xx alarmı zaten yakalar.
* Kotayı aşarsanız alarm-metrik başına **$0.10/ay** ödersiniz; `./alarmlar.sh --sil` ile ücret sıfırlanır.

## 2. Gereken IAM izinleri (ayrı, dar kapsamlı anahtar)

Yayın anahtarı yalnız S3/CloudFront için; CloudWatch için **ikinci bir anahtar** açın. Politika
depoda dosya olarak durur: [`iam-politikasi.json`](iam-politikasi.json) (sohbetten kopyalamayın —
tek doğru kaynak bu dosya):

```bash
aws iam create-policy --policy-name yourkiosk-alarm \
  --policy-document file://deploy/cloudwatch/iam-politikasi.json
```

İçerik özeti: `cloudwatch:PutMetricAlarm|DeleteAlarms|ListTagsForResource` (yalnız bu depodaki
DÖRT alarmın ARN'i), `sns:CreateTopic|Subscribe|SetTopicAttributes|GetTopicAttributes|DeleteTopic`
(yalnız `yourkiosk-alarm` konusunun ARN'i), `cloudwatch:DescribeAlarms`, `sns:ListTopics`,
`cloudwatch:GetMetricStatistics|ListMetrics`. Kaynak ARN'lerinde hesap kimliği IAM politika
değişkeni `${aws:PrincipalAccount}` ile gelir (dosya hesaba bağımlı değildir). `DescribeAlarms`,
`ListTopics`, `GetMetricStatistics`, `ListMetrics` kaynak düzeyi yetkilendirmeyi
DESTEKLEMEDİĞİ için zorunlu olarak `Resource:"*"` kalır — bunların dışında wildcard yoktur
(`kiosk/tests/test_deploy_guvenlik.py` bunu kilitler). `sns:Publish` **bilerek yok** (betik yayın
yapmaz, alarmlar SNS'e AWS servisi olarak yazar). `alarmlar.sh --sil` için `sns:DeleteTopic`
GEREKLİDİR. `KONU_ADI` değiştirirseniz politikadaki SNS ARN'ini de güncelleyin.

> Fatura metriklerini görebilmek için hesapta **Billing → Billing preferences → "Receive Billing
> Alerts"** açık olmalı. Bu bir **hesap ayarıdır**, IAM izniyle açılamaz (kullanıcı yapar).

## 3. Kurulum

```bash
cd deploy/cloudwatch
export AWS_PROFILE=yourkiosk-alarm            # yukarıdaki izinlere sahip profil
export BILDIRIM_EPOSTA=yonetici@ornek.com     # SNS aboneliği (e-postayı onaylamanız gerekir)
export AYLIK_LIMIT_USD=10                     # fatura alarm eşiği
export S3_ALARM=0                             # tam $0: S3 istek metriği açma (CloudFront 5xx yeter)
./alarmlar.sh            # kurar (idempotent: aynı adı varsa günceller)
./alarmlar.sh --liste    # durum
./alarmlar.sh --sil      # temizlik (alarm + konu)
```

Kurulan alarmlar (hepsi standart çözünürlük → ücretsiz kotanın 4'ü):

| # | Alarm | Ne zaman tetikler | Neden |
|---|---|---|---|
| 1 | `fatura-aylik-esik` | Tahmini aylık fatura > `AYLIK_LIMIT_USD` | Sessiz maliyet kaçağı |
| 2 | `s3-5xx-orani` | S3 5xx > 1 (5 dk, 2 ardışık) | Cihazlar veri çekemiyor |
| 3 | `cloudfront-5xx-orani` | CloudFront 5xx oranı > %1 (5 dk) | Yayın bozuk / origin hatası |
| 4 | `lambda-hatalari` | Lambda hata > 0 (10 dk) — yalnız `auth-modu: lambda` | Panel girişi/imzalama bozuk |

`tetik.push_*` (MQTT) kullanıyorsanız 5. alarm olarak **broker bağlantı sayısı** izlenebilir;
kendi Mosquitto'nuzda CloudWatch metriği yoktur — orada `deploy/mosquitto/dogrula.sh` ve panelin
"çevrimiçi" sayacı (bkz. `panel/README.md`) yeterlidir.

## 4. Bölge kuralı (alarmı ölü bırakmamak için)

| Alarm | Bölge | Neden |
|---|---|---|
| `fatura-aylik-esik` | **us-east-1** | `AWS/Billing` metrikleri yalnız us-east-1'de yayınlanır |
| `cloudfront-5xx-orani` | **us-east-1** | `AWS/CloudFront` metrikleri yalnız us-east-1'de yayınlanır |
| `s3-5xx-orani` | varsayılan bölge (profil/`AWS_REGION`) | kova bölgesinde yayınlanır |
| `lambda-hatalari` | varsayılan bölge | fonksiyon bölgesinde yayınlanır |

27 Ekim i5 bulgusu: CloudFront alarmı `--region` VERİLMEDEN kuruluyordu → alarm varsayılan
bölgede (ör. `eu-central-1`) oluşuyor, orada CloudFront metriği hiç gelmediği için
`--treat-missing-data notBreaching` ile **sonsuza kadar OK** kalıyordu (ölü alarm).
`--liste` ve `--sil` de bölge farkındadır: fatura/CloudFront alarmları us-east-1'de sorgulanır,
diğerleri varsayılan bölgede. Tek bölgede sorgulamak alarmları "yok" gösterip silinmelerini
engellerdi.

## 5. Kabul edilen risk — SNS şifrelemesi (BİLGİ, 27 Ekim i5)

SNS konusu varsayılan olarak **AWS tarafından yönetilen** anahtarla (SSE) şifrelenir; konuya ve
aboneliklere erişebilen bir hesap/rol mesajları okuyabilir. Alarm bildirimleri yalnız "eşik
aşıldı" bilgisini taşıdığı ve konuya erişim zaten IAM ile daraltıldığı için bu **kabul edilen
bir risk** olarak yazıldı. Kendi müşteri anahtarınızla (CMK) şifrelemek isterseniz:

```bash
export SNS_KMS_ANAHTAR=alias/yourkiosk-alarm   # ya da tam anahtar ARN'i
./alarmlar.sh                                  # create-topic --attributes KmsMasterKeyId=...
```

Anahtar politikası SNS'in (`sns.amazonaws.com`) `kms:Decrypt`/`kms:GenerateDataKey*` yapmasına
izin vermelidir; aksi hâlde alarm aksiyonu sessizce başarısız olur.

## 6. Doğrulama (kurulumdan sonra)

```bash
aws cloudwatch describe-alarms --state-value INSUFFICIENT_DATA --output table   # ilk 5 dk normal
aws sns list-subscriptions-by-topic \
  --topic-arn "$(cat "${XDG_STATE_HOME:-$HOME/.local/state}/yourkiosk/sns-arn")"   # onay bekliyor mu?
```

* SNS e-postasını **onaylamadan** hiçbir bildirim gelmez (AWS bunu zorunlu tutar).
* Fatura metrigi 6 saatte bir güncellenir; alarmın `INSUFFICIENT_DATA` olması ilk saatlerde
  normaldir. 24 saat sonra hâlâ veri yoksa alarm **yanlış bölgede** kurulmuştur.
