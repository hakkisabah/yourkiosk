# Hızlı kurulum — tek komut

Bu depoyu indiren biri **yalnızca `./kur.sh`** ile uğraşır. Ayrıntıları betik yönetir.

```bash
git clone https://github.com/hakkisabah/yourkiosk.git
cd yourkiosk

./kur.sh kontrol      # ne eksik? (hiçbir şey kurmaz)
./kur.sh kiosk        # çalışma zamanı: venv + PyQt6/paho + web derlemesi
```

Sonra:

```bash
cd kiosk && .venv/bin/python tools/tarayici_kiosk.py --tani   # ön kontrol + push durumu
cd kiosk && .venv/bin/python main.py                          # Qt modu
```

---

## Nerede ne kurulur?

| Bileşen | Makine | Kuran | Ne kurulur |
|---|---|---|---|
| **Kiosk (Qt / tarayıcı)** | gösterim cihazı | `./kur.sh kiosk` | `.venv`, PyQt6, **paho-mqtt**, `web/dist` |
| Tarayıcı modu | gösterim cihazı | sistem | `chromium` (dağıtımın paket yöneticisi) |
| **Panel** | yönetim makinesi | `./kur.sh panel` | npm (dev dahil), `panel/.env.local`, derleme |
| Panel yayını | yönetim makinesi | `./panel/infra/yayinla.sh` | S3 + CloudFront (yayın anahtarı) |
| **MQTT broker** | VPS (Lightsail) | `./kur.sh broker` (root) | mosquitto + certbot + ufw + nginx |
| Docker ile kiosk | herhangi bir Linux | `./kur.sh docker` | imaj: chromium + Xvfb + python |

> **paho-mqtt yalnızca kiosk cihazına kurulur.** Sunucuda broker vardır, istemci yoktur.

---

## Panel

```bash
./kur.sh panel        # .env.local yoksa .env.ornek'ten oluşturur ve UYARIR
$EDITOR panel/.env.local
```

Doldurulacaklar (AWS kurulumundan):

```bash
VITE_AUTH_MODU=cognito
VITE_BUCKET=yourkiosk-veri
VITE_PREFIX=kiosk/
VITE_AWS_REGION=eu-central-1
VITE_USER_POOL_ID=…
VITE_USER_POOL_CLIENT_ID=…
VITE_IDENTITY_POOL_ID=…

# MQTT push (600+ cihazda anlık tetikleme)
VITE_MQTT_URL=wss://yourkiosk.hakkisabah.com:8084/mqtt
VITE_MQTT_KONU=yourkiosk/yayin
VITE_MQTT_KULLANICI=panel
VITE_MQTT_PAROLA=…
```

Yayın: `./panel/infra/yayinla.sh` (AWS yayın anahtarı: `docs/AWS-KURULUM.md §10`).

---

## MQTT broker (VPS)

Sunucuda (Ubuntu 22.04/24.04, root):

```bash
git clone https://github.com/hakkisabah/yourkiosk.git && cd yourkiosk
sudo ./kur.sh broker --host yourkiosk.hakkisabah.com --eposta siz@example.com
```

Yaptıkları: mosquitto + certbot + ufw + nginx; **yalnız TLS** (8883 MQTT, 8084 WebSocket), düz 1883 kapalı,
`panel` (yazar) / `cihaz` (okur) hesapları, konu ACL'i, Let's Encrypt + yenileme kancası.
Sonunda parolalar `/root/yourkiosk-mqtt-credentials.txt` (0600).

**Bulut güvenlik duvarında açılması gerekenler:** 22, 80, 8883, 8084 (Lightsail → Networking → IPv4 Firewall).

Doğrulama (herhangi bir makineden):

```bash
MQTT_PAROLA_PANEL=… MQTT_PAROLA_CIHAZ=… bash deploy/mosquitto/dogrula.sh yourkiosk.hakkisabah.com
```

→ TLS ✓ · panel yayını ✓ · cihaz aboneliği ✓ · **cihaz yayını RED** ✓ · anonim RED ✓ · 1883 kapalı ✓

---

## Docker

```bash
./kur.sh kiosk        # web/dist'i üretir (imaja kopyalanır)
./kur.sh docker       # imajı derler + kiosk konteynerini başlatır
docker compose logs -f kiosk
docker compose down
```

- Fiziksel ekran: compose `/tmp/.X11-unix` soketini bağlar (`DISPLAY=:0`).
- Ekran yoksa entrypoint **Xvfb :99** açar (başsız test).
- Yerel broker (yalnız geliştirme, TLS/parola yok): `docker compose --profile broker up -d`

---

## Cihazda MQTT push'u açma (tek komut)

Yerel veri modunda (`veri.kaynak = dosya`) cihaz, S3'teki ayarları okumaz → push ayarları cihazın
kendi `ayarlar.json`'una yazılmalı. Araç bunu elle JSON düzenlemeden yapar:

```bash
cd kiosk
.venv/bin/python tools/push_ayarla.py \
    --broker yourkiosk.hakkisabah.com --kullanici cihaz --parola 'PAROLA' --dene
```

- `--dene` gerçek TLS bağlantısı kurar (sertifika/parola/host doğrulanır)
- `--goster` mevcut ayarları (parola maskeli) yazdırır
- `--kaldir` push'u kapatır (yoklama emniyet ağına döner)

Sonra kiosk'u yeniden başlat → `tools/tarayici_kiosk.py --tani` çıktısında `MQTT push … bağlı ✓`.

---

## Sorun giderme (kısa)

| Belirti | Bak |
|---|---|
| `chromium yok` | tarayıcı modu çalışmaz, Qt modu çalışır → `chromium` kur veya `--tarayici yol` |
| `paho.mqtt YOK` | `./kur.sh kiosk` (veya `kiosk/.venv/bin/python -m pip install paho-mqtt`) |
| Panel beyaz ekran | `panel/.env.local` eksik/yanlış → `./kur.sh panel` uyarısını oku |
| Cihaz yenilenmiyor | `--tani` çıktısındaki **MQTT push** satırı: `bağlı ✓` mi? |
| Broker'a bağlanamıyor | firewall 8883 + sertifika alan adı + `dogrula.sh` |
| Yayın yaptım, gitmedi | `./panel/infra/yayinla.sh` çıktısındaki “yayındaki paket” satırı |

---

## Geliştirici komutları

```bash
./kur.sh hepsi                        # kiosk + panel + kontrol
kiosk/tools/test.sh tests -q          # kiosk testleri
(cd panel && npm test)                # panel testleri
(cd web && npm test)                  # web testleri
./otomasyon/durum                     # i5/i3 otomasyon panosu
```
