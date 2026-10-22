# Tetikleme ölçeği — 600+ cihazda maliyet

## Sorun

Cihaz başına yoklama, cihaz sayısıyla **doğrusal** maliyet demektir. Ölçüm (CloudFront HTTPS istek
$0,0075/10k · S3 GET $0,0004/1k · önbellek kapalı):

| Yoklama aralığı | İstek/ay (600 cihaz) | CloudFront | S3 GET | **Toplam/ay** |
|---|---|---|---|---|
| 3 sn | 518.400.000 | $388,80 | $207,36 | **$596,16** |
| 10 sn | 155.520.000 | $116,64 | $62,21 | $178,85 |
| 20 sn | 77.760.000 | $58,32 | $31,10 | $89,42 |
| 60 sn | 25.920.000 | $19,44 | $10,37 | $29,81 |
| 5 dk | 5.184.000 | $3,89 | $2,07 | $5,96 |

**Sonuç:** yoklama ile "anlık" davranış 600 cihazda ayda yüzlerce dolar. Doğru mimari **push**.

## Çözüm: MQTT push + emniyet ağı yoklama

```
Panel (Kaydet) ──publish──► MQTT broker ──message──► 600 cihaz (kalıcı bağlantı)
                                   │                     │
                                   │              yerel tetikle.json yazılır
                                   │                     ▼
                                   └──────────► mevcut imza/uzun yoklama → ANINDA yenileme
```

- Gecikme: **~100 ms** (yoklamada 3–20 sn).
- Maliyet: cihaz başına **tek bağlantı**; mesaj yalnız yayın başına.

| Seçenek | Aylık maliyet (600 cihaz) | Not |
|---|---|---|
| **AWS IoT Core** | ≈ **$2,10** (25,9 M cihaz-dakika × $0,08/M) + mesaj ≈ $0,02 | Yönetilen, AWS içinde; cihaz sertifikası gerekir |
| **Kendi Mosquitto'nuz (VPS)** | ≈ **$5** sabit | Kurulumu basit, kullanıcı/parola |
| Yoklama 20 sn (push yok) | ≈ $89 | Yalnız emniyet ağı olarak kabul edilebilir |

## Cihaz ayarları (panelden yazılır, `tetik` grubu)

| Anahtar | Değer |
|---|---|
| `tetik.aktif` | `true` |
| `tetik.modlar` | `["qt","tarayici"]` (veya yalnız biri) |
| `tetik.push_aktif` | **`true`** |
| `tetik.push_broker` | `xxxxx-ats.iot.eu-central-1.amazonaws.com` ya da kendi sunucunuz |
| `tetik.push_port` | `8883` (TLS) |
| `tetik.push_konu` | `yourkiosk/yayin` |
| `tetik.push_kullanici` / `_parola` | Mosquitto için dolu; AWS IoT Core X.509 kullanıyorsa boş |
| `tetik.kontrol_ms` | push açıkken **60000–300000** (emniyet ağı; maliyeti düşük tutar) |

Cihazda `paho-mqtt` gerekir: `pip install paho-mqtt` (yoksa push sessizce devre dışı kalır,
yoklama emniyet ağı çalışmaya devam eder).

## Panel tarafı (`.env.local`)

```bash
VITE_MQTT_URL=wss://broker.example:8084/mqtt
VITE_MQTT_KONU=yourkiosk/yayin
VITE_MQTT_KULLANICI=panel
VITE_MQTT_PAROLA=…
```

Tanımlı değilse panel sessizce atlar (cihazlar yoklamayla çalışır). `mqtt` paketi **dinamik**
yüklenir; yapılandırma yoksa ana pakete girmez.

## Mosquitto ile hızlı kurulum (VPS)

```bash
# sunucuda
apt install mosquitto mosquitto-clients
mosquitto_passwd -c /etc/mosquitto/passwd panel          # panel kullanıcısı
mosquitto_passwd /etc/mosquitto/passwd cihaz             # cihaz kullanıcısı (salt-okunur değil, konu ACL'i ile)
cat >/etc/mosquitto/conf.d/yourkiosk.conf <<'EOF'
listener 8883
cafile   /etc/letsencrypt/live/broker.example/chain.pem
certfile /etc/letsencrypt/live/broker.example/fullchain.pem
keyfile  /etc/letsencrypt/live/broker.example/privkey.pem
allow_anonymous false
password_file /etc/mosquitto/passwd
listener 8084
protocol websockets
EOF
systemctl restart mosquitto
```

Konu ACL'i ile cihazların yalnız **abone** olması sağlanır (`acl_file`), panel yalnız **publish** eder.

## AWS IoT Core ile kurulum

1. IoT Core → **Connect device** → tek seferde bir **thing + sertifika** üretin; 600 cihaz için
   sertifikaları betikle üretip cihaz başına bir tane koyun (dosya: `cert.pem`, `key.pem`, `CA`).
2. Cihaz ayarlarında broker = `xxxxx-ats.iot.<bölge>.amazonaws.com`, port `8883`.
3. `paho-mqtt` istemcisinde sertifika yolu verilmesi gerekir (bu sürümde kullanıcı/parola yolu
   kullanılıyor; X.509 için `core/push.py` içindeki `tls_set()` çağrısına `certfile/keyfile`
   eklenmeli — küçük bir yama, ihtiyaç olduğunda eklenir).

## Doğrulama

```bash
# cihazda
python3 -c "from core import push; print(push.baslat(), push.durum())"
mosquitto_pub -h broker -p 8883 --cafile ca.pem -u panel -P … -t yourkiosk/yayin -m '{"kaynak":"test"}'
# cihaz günlüğü: "MQTT tetikleyicisi yazıldı (panel)"
```

Testler: `kiosk/tests/test_push.py` (mesaj → tetikleme, kapalı mod, mod listesi, push açıkken
yoklama yapılmaması).
