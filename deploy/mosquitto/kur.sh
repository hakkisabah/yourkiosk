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

echo "=== 6/8 ACL (panel yazar · cihaz okur · cihaz-<id> kendi durumuna yazar · panel-izleme yalnız okur) ==="
cat > /etc/mosquitto/auth/acl <<'EOF'
# Panel yalnızca yayın konusuna YAZABİLİR (tetikleyici).
user panel
topic write yourkiosk/yayin

# Cihazlar yayın konusunu OKUR (tetikleyici).
#
# GÜVENLİK (i5 bulgusu): paylaşılan `cihaz` hesabı `durum/+` konusuna YAZAMAZ. 600 cihaz aynı
# parolayı taşıdığı için yazabilseydi, ele geçirilen tek bir kiosk başka cihazın çevrimiçi
# durumunu taklit edebilirdi. Kalp atışı için cihaz BAŞINA kullanıcı gerekir:
#   ./cihaz-ekle.sh <cihazId>      → user cihaz-<id> + topic write yourkiosk/durum/<id>
# `deny` kuralı önceliklidir; aşağıdaki joker yazma yetkisini kesin olarak kapatır.
user cihaz
topic read yourkiosk/yayin
topic deny write yourkiosk/durum/#

# Panel izleme: SADECE durum konularını OKUR. Yayın yazamaz, ayar göremez.
# Parolası panel paketine gömülmez (çalışma anında girilir) — sızsa bile yalnız durum okunur.
user panel-izleme
topic read yourkiosk/durum/+
topic deny write yourkiosk/durum/#
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
# i5 bulgusu: `max_connections -1` + internete açık 8883/8084 → kimlik doğrulaması bağlantı
# KABULÜNDEN sonra yapıldığı için tek kaynak binlerce TLS el sıkışması açıp broker'ın dosya
# tanıtıcılarını tüketebilir (filo düşer). 600 cihaz + panel + pay: 1200 bağlantı, 20 sn'de
# tekrar deneme ile toparlanır. Sınırsız ASLA.
max_connections 1200

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
cihaz (yalnız yayın okur) : cihaz / $PAROLA_CIHAZ
  → kalp atışı YAZAMAZ; cihaz başına kimlik gerekir: ./cihaz-ekle.sh <cihazId>
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
  tetik.push_kullanici=cihaz-<cihazId>   # ./cihaz-ekle.sh <cihazId> çıktısı (paylaşılan 'cihaz' kalp atışı yazamaz)
  tetik.push_parola=<cihaz parolası>
  tetik.kontrol_ms=300000
EOF
chmod 600 /root/yourkiosk-mqtt-credentials.txt

echo "=== 9/9 bağlantı testleri (kendine TLS) ==="
mosquitto_pub -h 127.0.0.1 -p 8883 --cafile /etc/ssl/certs/ca-certificates.crt \
  -u panel -P "$PAROLA_PANEL" -t yourkiosk/yayin -m '{"kaynak":"kurulum-testi"}' \
  && echo "  ✓ panel yayını çalışıyor"

# --- KALP ATIŞI ZİNCİRİ (i5 bulgusu: ACL yalnız yayın konusunu tanıyordu → izleme üretimde
# hiç çalışmıyordu; ayrıca test kendi kendini çürütüyordu: retained `durum/kurulum-testi`
# mesajı `-C 1` abonesine hemen ulaşıp testi sahte biçimde 'geçti' gösteriyordu).
#
# Sabit /tmp yolu YOK: root olarak `>` ile sabit dosyaya yazmak, /tmp'de sembolik bağ kuran
# yerel kullanıcıya root'un rastgele bir dosyayı kesmesine izin verir (i5 bulgusu).
GECICI_DIZIN="$(mktemp -d)"
trap 'rm -rf "$GECICI_DIZIN"' EXIT
CAFILE=/etc/ssl/certs/ca-certificates.crt
TEST_CIHAZ="kurulumtest$$"
TEST_PAROLA="$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)"

# Cihaz BAŞINA kullanıcı: kalp atışı bu kimlikle yazılır (paylaşılan `cihaz` yazamaz).
mosquitto_passwd -b /etc/mosquitto/auth/passwd "cihaz-$TEST_CIHAZ" "$TEST_PAROLA"
chown root:mosquitto /etc/mosquitto/auth/passwd
chmod 640 /etc/mosquitto/auth/passwd
cat >>/etc/mosquitto/auth/acl <<EOF

# geçici kurulum testi cihazı (kur.sh sonunda silinir)
user cihaz-$TEST_CIHAZ
topic read yourkiosk/yayin
topic write yourkiosk/durum/$TEST_CIHAZ
EOF
chown mosquitto:mosquitto /etc/mosquitto/auth/acl
chmod 640 /etc/mosquitto/auth/acl
systemctl reload mosquitto
sleep 1

# 1) PAYLAŞILAN `cihaz` HESABI BAŞKA CİHAZIN KONUSUNA YAZAMAMALI (cihaz taklidi kapalı).
#    Konu benzersiz ve retained DEĞİL → test yalnız gerçek sızıntıyı görür.
KONU_TAKLIT="yourkiosk/durum/taklit$$"
( timeout 5 mosquitto_sub -h 127.0.0.1 -p 8883 --cafile "$CAFILE" \
    -u panel-izleme -P "$PAROLA_IZLEME" -t "$KONU_TAKLIT" -C 1 \
    >"$GECICI_DIZIN/taklit" 2>/dev/null || true ) &
sleep 1
mosquitto_pub -h 127.0.0.1 -p 8883 --cafile "$CAFILE" \
  -u cihaz -P "$PAROLA_CIHAZ" -t "$KONU_TAKLIT" -m '{"cevrimici":true}' 2>/dev/null || true
sleep 2
if [ -s "$GECICI_DIZIN/taklit" ]; then
  echo "  ✗ GÜVENLİK: paylaşılan cihaz hesabı başka cihazın durum konusuna yazabildi"
else
  echo "  ✓ paylaşılan cihaz hesabı durum konusuna YAZAMIYOR (cihaz başına kimlik)"
fi

# 2) Cihaz kimliği kalp atışını yazabilmeli, panel-izleme okuyabilmeli.
KONU_TEST="yourkiosk/durum/$TEST_CIHAZ"
( timeout 6 mosquitto_sub -h 127.0.0.1 -p 8883 --cafile "$CAFILE" \
    -u panel-izleme -P "$PAROLA_IZLEME" -t "$KONU_TEST" -C 1 \
    >"$GECICI_DIZIN/kalp" 2>/dev/null || true ) &
sleep 1
mosquitto_pub -h 127.0.0.1 -p 8883 --cafile "$CAFILE" \
  -u "cihaz-$TEST_CIHAZ" -P "$TEST_PAROLA" -t "$KONU_TEST" -r \
  -m '{"cevrimici":true,"zaman":"2026-01-01T00:00:00Z","mod":"qt"}' 2>/dev/null || true
wait
if grep -q cevrimici "$GECICI_DIZIN/kalp" 2>/dev/null; then
  echo "  ✓ cihaz kimliği kalp atışı yazdı, panel-izleme okudu"
else
  echo "  ✗ kalp atışı okunamadı (ACL: cihaz-<id> write / panel-izleme read eksik olabilir)"
fi

# 3) panel-izleme YAYIN yapamamalı (salt-okur). Aynı yöntem: benzersiz konu, retained yok.
KONU_SIZINTI="yourkiosk/durum/sizinti$$"
( timeout 5 mosquitto_sub -h 127.0.0.1 -p 8883 --cafile "$CAFILE" \
    -u panel-izleme -P "$PAROLA_IZLEME" -t "$KONU_SIZINTI" -C 1 \
    >"$GECICI_DIZIN/sizinti" 2>/dev/null || true ) &
sleep 1
mosquitto_pub -h 127.0.0.1 -p 8883 --cafile "$CAFILE" \
  -u panel-izleme -P "$PAROLA_IZLEME" -t "$KONU_SIZINTI" -m '{"cevrimici":true}' 2>/dev/null || true
sleep 2
if [ -s "$GECICI_DIZIN/sizinti" ]; then
  echo "  ✗ GÜVENLİK: panel-izleme yayın yapabildi (ACL fazla geniş)"
else
  echo "  ✓ panel-izleme YAYIN yapamıyor (salt-okur)"
fi

# Temizlik: retained test mesajı, geçici cihaz kullanıcısı ve ACL bloğu.
mosquitto_pub -h 127.0.0.1 -p 8883 --cafile "$CAFILE" \
  -u "cihaz-$TEST_CIHAZ" -P "$TEST_PAROLA" -t "$KONU_TEST" -r -n 2>/dev/null || true
mosquitto_passwd -D /etc/mosquitto/auth/passwd "cihaz-$TEST_CIHAZ" >/dev/null 2>&1 || true
awk -v u="cihaz-$TEST_CIHAZ" '
  /^# geçici kurulum testi/ { next }
  $1=="user" { atla = ($2==u); if (atla) next }
  atla && /^topic / { next }
  { print }
' /etc/mosquitto/auth/acl >"$GECICI_DIZIN/acl"
install -m 640 -o mosquitto -g mosquitto "$GECICI_DIZIN/acl" /etc/mosquitto/auth/acl
chown root:mosquitto /etc/mosquitto/auth/passwd
chmod 640 /etc/mosquitto/auth/passwd
systemctl reload mosquitto || true

cat > /root/yourkiosk-mqtt-credentials.txt <<EOF
yourkiosk MQTT (güvenli)
host      : $HOST
port      : 8883 (MQTT/TLS) · 8084 (WebSocket/TLS — panel)
konu      : yourkiosk/yayin

panel (yalnız yazar) : panel / $PAROLA_PANEL
cihaz (yalnız yayın okur) : cihaz / $PAROLA_CIHAZ
  → kalp atışı YAZAMAZ; cihaz başına kimlik gerekir: ./cihaz-ekle.sh <cihazId>
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
  tetik.push_kullanici=cihaz-<cihazId>   # ./cihaz-ekle.sh <cihazId> çıktısı (paylaşılan 'cihaz' kalp atışı yazamaz)
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
