#!/usr/bin/env bash
# yourkiosk · güvenli Mosquitto kurulumu (Debian/Ubuntu VPS)
#
#   sudo bash kur.sh --host broker.1.2.3.4.nip.io --eposta admin@example.com
#
# Ne yapar (idempotent — tekrar çalıştırılabilir):
#   • mosquitto + clients + certbot + ufw kurar
#   • Let's Encrypt sertifikası alır (HTTP-01, port 80) ve /etc/mosquitto/certs'e kopyalar
#   • TLS'li iki dinleyici: 8883 (MQTT) ve 8084 (WebSocket — panel tarayıcıdan yayınlar)
#   • allow_anonymous=false, kullanıcı/parola + konu ACL'i
#   • iki hesap: `panel` (yalnız yazma) ve `cihaz` (yalnız okuma)
#   • güvenlik sıkılaştırma: mesaj boyutu sınırı, bağlantı sınırı, düz 1883 KAPALI
#
# Parolaları /root/yourkiosk-mqtt-credentials.txt (0600) içine yazar ve bir kez ekrana basar.
set -euo pipefail

HOST=""
EPOSTA=""
while [ $# -gt 0 ]; do
  case "$1" in
    --host) HOST="${2:-}"; shift 2 ;;
    --eposta) EPOSTA="${2:-}"; shift 2 ;;
    *) echo "bilinmeyen argüman: $1" >&2; exit 2 ;;
  esac
done

if [ "$(id -u)" -ne 0 ]; then echo "root olarak çalıştırın (sudo)" >&2; exit 2; fi
if [ -z "$HOST" ] || [ -z "$EPOSTA" ]; then
  echo "kullanım: sudo bash kur.sh --host broker.<ip>.nip.io --eposta siz@example.com" >&2
  exit 2
fi

echo "=== 1/8 paketler ==="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq mosquitto mosquitto-clients certbot ufw openssl >/dev/null
systemctl stop mosquitto 2>/dev/null || true   # certbot port 80'i kullanabilsin

echo "=== 2/8 güvenlik duvarı (22/80/8883/8084) ==="
ufw allow 22/tcp >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 8883/tcp >/dev/null
ufw allow 8084/tcp >/dev/null
ufw --force enable >/dev/null

echo "=== 3/8 Let's Encrypt sertifikası: $HOST ==="
if [ -f "/etc/letsencrypt/live/$HOST/fullchain.pem" ]; then
  echo "  sertifika zaten var"
else
  certbot certonly --standalone -d "$HOST" -m "$EPOSTA" --agree-tos -n --keep-until-expiring
fi

echo "=== 4/8 sertifikaları mosquitto'ya kopyala ==="
install -d -o mosquitto -g mosquitto -m 750 /etc/mosquitto/certs
install -o mosquitto -g mosquitto -m 640 "/etc/letsencrypt/live/$HOST/fullchain.pem" /etc/mosquitto/certs/fullchain.pem
install -o mosquitto -g mosquitto -m 640 "/etc/letsencrypt/live/$HOST/privkey.pem"   /etc/mosquitto/certs/privkey.pem
install -o mosquitto -g mosquitto -m 640 "/etc/letsencrypt/live/$HOST/chain.pem"     /etc/mosquitto/certs/chain.pem
# yenileme sonrası otomatik kopyala + mosquitto'yu yeniden yükle
cat > /etc/letsencrypt/renewal-hooks/deploy/yourkiosk-mosquitto.sh <<EOF
#!/bin/sh
set -e
install -o mosquitto -g mosquitto -m 640 /etc/letsencrypt/live/$HOST/fullchain.pem /etc/mosquitto/certs/fullchain.pem
install -o mosquitto -g mosquitto -m 640 /etc/letsencrypt/live/$HOST/privkey.pem   /etc/mosquitto/certs/privkey.pem
install -o mosquitto -g mosquitto -m 640 /etc/letsencrypt/live/$HOST/chain.pem     /etc/mosquitto/certs/chain.pem
systemctl reload mosquitto || systemctl restart mosquitto
EOF
chmod 755 /etc/letsencrypt/renewal-hooks/deploy/yourkiosk-mosquitto.sh

echo "=== 5/8 kullanıcılar (parolalar üretiliyor) ==="
PAROLA_PANEL="$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)"
PAROLA_CIHAZ="$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)"
#: Panel İZLEME kullanıcısı: yalnız `durum/+` OKUR. Parolası panel paketine GÖMÜLMEZ
#: (paket CloudFront'tan kimlik doğrulamasız indirilebiliyor) — yönetici panelde bir kez girer.
PAROLA_IZLEME="$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)"
# mosquitto kullanıcısı dizine GİREBİLMELİ (0700 root:root olsaydı pwfile açılamazdı)
install -m 750 -o mosquitto -g mosquitto -d /etc/mosquitto/auth
mosquitto_passwd -b -c /etc/mosquitto/auth/passwd panel "$PAROLA_PANEL"
mosquitto_passwd -b /etc/mosquitto/auth/passwd cihaz "$PAROLA_CIHAZ"
mosquitto_passwd -b /etc/mosquitto/auth/passwd panel-izleme "$PAROLA_IZLEME"
# mosquitto 2.x parola dosyasının SAHİBİNİN root olmasını bekler (uyarı → ileride hata)
chown root:mosquitto /etc/mosquitto/auth/passwd
chmod 640 /etc/mosquitto/auth/passwd

echo "=== 6/8 ACL (panel yazar · cihaz okur + kalp atışı yazar · panel-izleme yalnız okur) ==="
cat > /etc/mosquitto/auth/acl <<'EOF'
# Panel yalnızca yayın konusuna YAZABİLİR (tetikleyici).
user panel
topic write yourkiosk/yayin

# Cihazlar yayın konusunu OKUR (tetikleyici) ve KENDİ durum konusuna yazar (retained kalp atışı).
# `+` tek seviye joker: cihaz başka cihazın durum konusuna yazabilir; bu yüzden cihaz parolası
# sahada paylaşılmaz. Daha sıkı izolasyon için `cihaz-ekle.sh` ile cihaz başına kullanıcı açın.
user cihaz
topic read yourkiosk/yayin
topic write yourkiosk/durum/+

# Panel izleme: SADECE durum konularını OKUR. Yayın yazamaz, ayar göremez.
# Parolası panel paketine gömülmez (çalışma anında girilir) — sızsa bile yalnız durum okunur.
user panel-izleme
topic read yourkiosk/durum/+
EOF
chown mosquitto:mosquitto /etc/mosquitto/auth/acl
chmod 640 /etc/mosquitto/auth/acl

echo "=== 7/8 yapılandırma ==="
cat > /etc/mosquitto/conf.d/yourkiosk.conf <<'EOF'
# yourkiosk · güvenli MQTT (TLS + kullanıcı/parola + konu ACL)
# per_listener_settings: kimlik doğrulama ayarları HER dinleyicide ayrı verilir
per_listener_settings true

# --- MQTT over TLS (cihazlar) ---
listener 8883
certfile /etc/mosquitto/certs/fullchain.pem
keyfile  /etc/mosquitto/certs/privkey.pem
tls_version tlsv1.2
allow_anonymous false
password_file /etc/mosquitto/auth/passwd
acl_file      /etc/mosquitto/auth/acl
max_connections -1
max_queued_messages 5

# --- WebSocket over TLS (panel, tarayıcıdan yayın) ---
listener 8084
protocol websockets
certfile /etc/mosquitto/certs/fullchain.pem
keyfile  /etc/mosquitto/certs/privkey.pem
tls_version tlsv1.2
allow_anonymous false
password_file /etc/mosquitto/auth/passwd
acl_file      /etc/mosquitto/auth/acl

# Genel sınırlar
message_size_limit 1024
persistence false

# log_dest Ubuntu'nun varsayılan mosquitto.conf'unda zaten tanımlı → TEKRAR ETME (Duplicate hatası)
log_type error
log_type warning
log_type notice
connection_messages true
EOF

echo "=== 8/8 servis ==="
systemctl enable mosquitto >/dev/null 2>&1
systemctl restart mosquitto
sleep 2
systemctl is-active --quiet mosquitto && echo "  ✓ mosquitto çalışıyor" || { echo "  ✗ mosquitto başlamadı"; journalctl -u mosquitto -n 30 --no-pager; exit 1; }

cat > /root/yourkiosk-mqtt-credentials.txt <<EOF
yourkiosk MQTT (güvenli)
host      : $HOST
port      : 8883 (MQTT/TLS) · 8084 (WebSocket/TLS — panel)
konu      : yourkiosk/yayin

panel (yalnız yazar) : panel / $PAROLA_PANEL
cihaz (okur + kalp)  : cihaz / $PAROLA_CIHAZ
panel-izleme (yalnız durum okur) : panel-izleme / $PAROLA_IZLEME
  → panel paketine GÖMÜLMEZ; panelde "İzlemeyi bağla" ile bir kez girilir (sessionStorage).

Panel .env.local:
  VITE_MQTT_URL=wss://$HOST:8084/mqtt
  VITE_MQTT_KONU=yourkiosk/yayin
  VITE_MQTT_KULLANICI=panel
  VITE_MQTT_PAROLA=<panel parolası>

Cihaz ayarları (tetik grubu):
  tetik.push_aktif=true
  tetik.push_broker=$HOST
  tetik.push_port=8883
  tetik.push_konu=yourkiosk/yayin
  tetik.push_kullanici=cihaz
  tetik.push_parola=<cihaz parolası>
  tetik.kontrol_ms=300000
EOF
chmod 600 /root/yourkiosk-mqtt-credentials.txt

echo "=== 9/9 bağlantı testleri (kendine TLS) ==="
mosquitto_pub -h 127.0.0.1 -p 8883 --cafile /etc/ssl/certs/ca-certificates.crt \
  -u panel -P "$PAROLA_PANEL" -t yourkiosk/yayin -m '{"kaynak":"kurulum-testi"}' \
  && echo "  ✓ panel yayını çalışıyor"

# KALP ATIŞI ZİNCİRİ: cihaz durum konusuna yazabilmeli, panel-izleme okuyabilmeli.
# (i5 bulgusu: ACL yalnız yayın konusunu tanıyordu → izleme üretimde hiç çalışmıyordu.)
mosquitto_pub -h 127.0.0.1 -p 8883 --cafile /etc/ssl/certs/ca-certificates.crt \
  -u cihaz -P "$PAROLA_CIHAZ" -t yourkiosk/durum/kurulum-testi -r \
  -m '{"cevrimici":true,"zaman":"2026-01-01T00:00:00Z","mod":"qt"}' \
  && echo "  ✓ cihaz kalp atışı yazabiliyor"

ALINAN="$(timeout 6 mosquitto_sub -h 127.0.0.1 -p 8883 --cafile /etc/ssl/certs/ca-certificates.crt \
  -u panel-izleme -P "$PAROLA_IZLEME" -t 'yourkiosk/durum/+' -C 1 2>/dev/null || true)"
case "$ALINAN" in
  *cevrimici*) echo "  ✓ panel-izleme kalp atışını okuyor" ;;
  *) echo "  ✗ panel-izleme kalp atışını OKUYAMADI (ACL/parola)" ;;
esac
# Panel-izleme YAYIN yapamamalı: abone aç, panel-izleme olarak yaz, aboneye ulaşmamalı.
SIZAN="$( (timeout 4 mosquitto_sub -h 127.0.0.1 -p 8883 --cafile /etc/ssl/certs/ca-certificates.crt \
  -u panel-izleme -P "$PAROLA_IZLEME" -t 'yourkiosk/durum/+' -C 1 >/tmp/izleme-sizinti 2>/dev/null &) ; \
  sleep 1; mosquitto_pub -h 127.0.0.1 -p 8883 --cafile /etc/ssl/certs/ca-certificates.crt \
  -u panel-izleme -P "$PAROLA_IZLEME" -t yourkiosk/durum/sizinti -m '{"cevrimici":true}' 2>/dev/null; \
  sleep 2; grep -c sizinti /tmp/izleme-sizinti 2>/dev/null || true )"
rm -f /tmp/izleme-sizinti
if [ "${SIZAN:-0}" = "0" ]; then echo "  ✓ panel-izleme YAYIN yapamıyor (salt-okur)"; else echo "  ✗ panel-izleme yayın yapabildi (ACL fazla geniş)"; fi

# Test için bırakılan retained durum mesajını temizle (panelde sahte cihaz görünmesin).
mosquitto_pub -h 127.0.0.1 -p 8883 --cafile /etc/ssl/certs/ca-certificates.crt \
  -u cihaz -P "$PAROLA_CIHAZ" -t yourkiosk/durum/kurulum-testi -r -n 2>/dev/null || true

cat > /root/yourkiosk-mqtt-credentials.txt <<EOF
yourkiosk MQTT (güvenli)
host      : $HOST
port      : 8883 (MQTT/TLS) · 8084 (WebSocket/TLS — panel)
konu      : yourkiosk/yayin

panel (yalnız yazar) : panel / $PAROLA_PANEL
cihaz (okur + kalp)  : cihaz / $PAROLA_CIHAZ
panel-izleme (yalnız durum okur) : panel-izleme / $PAROLA_IZLEME
  → panel paketine GÖMÜLMEZ; panelde "İzlemeyi bağla" ile bir kez girilir (sessionStorage).

Panel .env.local:
  VITE_MQTT_URL=wss://$HOST:8084/mqtt
  VITE_MQTT_KONU=yourkiosk/yayin
  VITE_MQTT_KULLANICI=panel
  VITE_MQTT_PAROLA=…

Cihaz ayarları (tetik grubu):
  tetik.push_aktif=true
  tetik.push_broker=$HOST
  tetik.push_port=8883
  tetik.push_konu=yourkiosk/yayin
  tetik.push_kullanici=cihaz
  tetik.push_parola=…
  tetik.kontrol_ms=300000
EOF
chmod 600 /root/yourkiosk-mqtt-credentials.txt

echo
echo "================ KURULUM TAMAM ================"
echo "host      : $HOST"
echo "panel     : panel / $PAROLA_PANEL"
echo "cihaz     : cihaz / $PAROLA_CIHAZ"
echo "kayıt     : /root/yourkiosk-mqtt-credentials.txt (0600)"
echo
echo "Sıradaki: panel .env.local + ./panel/infra/yayinla.sh · cihazlarda pip install paho-mqtt"
