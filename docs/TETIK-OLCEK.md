# Tetikleme ölçeği — 600+ cihazda maliyet

## Sorun

Cihaz başına yoklama, cihaz sayısıyla **doğrusal** maliyet demektir. Ölçüm (CloudFront HTTPS istek
$0,0075/10k · S3 GET $0,0004/1k · önbellek kapalı; Qt yolu tur başına **1,3 istek** — taban
`durum.json` + her 10 turda bir 3 çapraz kontrol, `docs/ONBELLEK-VE-MALIYET.md`):

| Yoklama aralığı | İstek/ay (600 cihaz) | CloudFront | S3 GET | **Toplam/ay** |
|---|---|---|---|---|
| 3 sn | 683,80 M | $512,85 | $273,52 | **$786,37** |
| 10 sn | 205,14 M | $153,86 | $82,06 | $235,91 |
| 20 sn | 102,57 M | $76,93 | $41,03 | $117,96 |
| 60 sn | 34,19 M | $25,64 | $13,68 | $39,32 |
| 5 dk | 6,84 M | $5,13 | $2,74 | $7,86 |

Bu tablo **aralık → maliyet** ölçümüdür. Bugünkü etkin değerler — push kapalı **30 sn**
(68,38 M istek/ay ≈ $78,64), push bağlı **120 sn** (17,10 M ≈ $19,66) —
[`ONBELLEK-VE-MALIYET.md`](ONBELLEK-VE-MALIYET.md) tablosundadır.

**Sonuç:** yoklama ile "anlık" davranış 600 cihazda ayda yüzlerce dolar. Doğru mimari **push**.

## Çözüm: MQTT push + emniyet ağı yoklama

```
Panel (Kaydet) ──publish──► MQTT broker ──message──► 600 cihaz (kalıcı bağlantı)
                                   │                     │
                                   │              yerel tetikle.json yazılır
                                   │                     ▼
                                   └──────────► mevcut imza/uzun yoklama → ANINDA yenileme
```

- Gecikme: **~100 ms** (yoklamada push bağlı 120 sn / kopuk 30 sn; yoklama yalnız emniyet ağı).
- Maliyet: cihaz başına **tek bağlantı**; mesaj yalnız yayın başına.

| Seçenek | Aylık maliyet (600 cihaz) | Not |
|---|---|---|
| **AWS IoT Core** | ≈ **$2,10** (25,9 M cihaz-dakika × $0,08/M) + mesaj ≈ $0,02 | Yönetilen, AWS içinde; cihaz sertifikası gerekir |
| **Kendi Mosquitto'nuz (VPS)** | ≈ **$5** sabit | Kurulumu basit, kullanıcı/parola |
| Yoklama 30 sn (push yok, bugünkü varsayılan) | ≈ $78,64 | Bugünkü kurulum; emniyet ağı |

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
```

Parola ve kullanıcı `.env.local`e YAZILMAZ: Vite derleme değişkenleri JS paketine gömülür ve
panel paketi CloudFront'tan kimlik doğrulaması olmadan indirilebilir (27 Ekim i5 bulgusu, yüksek).
Panel yayın parolasını çalışma anında sorar, yalnız o sekmede tutar (`domain/yayinKimligi.ts`).
Kimlik girilmezse yayın fail-closed'dır: broker'a bağlanılmaz, cihazlar yoklama ağıyla yenilenir.

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
