#!/usr/bin/env bash
# yourkiosk MQTT doğrulama — HERHANGİ bir makineden çalıştırılabilir.
#
#   MQTT_PAROLA_PANEL=… MQTT_PAROLA_CIHAZ=… bash dogrula.sh broker.1.2.3.4.nip.io
#
# Kontroller:
#   1) TLS el sıkışması ve sertifika geçerliliği (openssl s_client)
#   2) panel kullanıcısı YAYIN yapabiliyor mu (beklenen: evet)
#   3) cihaz kullanıcısı ABONE olup mesajı alıyor mu (beklenen: evet)
#   4) cihaz kullanıcısı YAYIN yapamıyor mu (beklenen: HAYIR — ACL)
#   5) anonim bağlantı reddediliyor mu (beklenen: HAYIR)
#   6) düz 1883 kapalı mı (beklenen: bağlantı yok)
set -uo pipefail

HOST="${1:-}"
: "${MQTT_PAROLA_PANEL:?MQTT_PAROLA_PANEL gerekli}"
: "${MQTT_PAROLA_CIHAZ:?MQTT_PAROLA_CIHAZ gerekli}"
KONU="${MQTT_KONU:-yourkiosk/yayin}"
if [ -z "$HOST" ]; then echo "kullanım: bash dogrula.sh <host>" >&2; exit 2; fi

komut_var() { command -v "$1" >/dev/null 2>&1 || { echo "  ✗ '$1' yok (mosquitto-clients kurun)"; return 1; }; }
komut_var mosquitto_pub || exit 2
komut_var mosquitto_sub || exit 2

echo "=== 1) TLS sertifikası ($HOST:8883) ==="
if openssl s_client -connect "$HOST:8883" -servername "$HOST" -brief </dev/null 2>&1 | grep -q "Verification: OK"; then
  echo "  ✓ sertifika geçerli (CA doğrulandı)"
else
  echo "  ✗ TLS doğrulanamadı — sertifika/alan adı sorunu"
fi

echo "=== 2) panel yayın yapabiliyor mu ==="
if mosquitto_pub -h "$HOST" -p 8883 -u panel -P "$MQTT_PAROLA_PANEL" -t "$KONU" -m '{"kaynak":"dogrulama"}' 2>/dev/null; then
  echo "  ✓ evet"
  PANEL_YAZDI=1
else
  echo "  ✗ panel yayın yapamadı"
  PANEL_YAZDI=0
fi

echo "=== 3) cihaz abone olup mesajı alıyor mu ==="
GECICI="$(mktemp)"
timeout 6 mosquitto_sub -h "$HOST" -p 8883 -u cihaz -P "$MQTT_PAROLA_CIHAZ" -t "$KONU" -C 1 >"$GECICI" 2>/dev/null &
ABONE=$!
sleep 2
mosquitto_pub -h "$HOST" -p 8883 -u panel -P "$MQTT_PAROLA_PANEL" -t "$KONU" -m '{"kaynak":"dogrulama-2"}' 2>/dev/null
wait $ABONE 2>/dev/null
if [ -s "$GECICI" ]; then echo "  ✓ mesaj alındı: $(head -c 80 "$GECICI")"; else echo "  ✗ mesaj alınamadı"; fi
rm -f "$GECICI"

echo "=== 4) cihaz YAYIN yapamamalı (ACL) ==="
# MQTT 3.1.1'de reddedilen PUBLISH istemciye HATA DÖNMEZ (sessizce düşürülür) → çıkış koduna bakmak
# yanıltıcı. Doğru test: abone aç, cihaz olarak yayınla, aboneye ULAŞMAMALI.
GECICI2="$(mktemp)"
timeout 8 mosquitto_sub -h "$HOST" -p 8883 -u cihaz -P "$MQTT_PAROLA_CIHAZ" -t "$KONU" -C 1 >"$GECICI2" 2>/dev/null &
ABONE2=$!
sleep 2
mosquitto_pub -h "$HOST" -p 8883 -u cihaz -P "$MQTT_PAROLA_CIHAZ" -t "$KONU" -m '{"kaynak":"cihaz-olmamali"}' 2>/dev/null
wait $ABONE2 2>/dev/null
if [ -s "$GECICI2" ]; then
  echo "  ✗ GÜVENLİK: cihazın yayını aboneye ulaştı (ACL hatalı)"
  head -c 80 "$GECICI2"
else
  echo "  ✓ reddedildi (yayın düşmedi)"
fi
rm -f "$GECICI2"

echo "=== 5) anonim bağlantı reddedilmeli ==="
if timeout 5 mosquitto_pub -h "$HOST" -p 8883 -t "$KONU" -m 'x' 2>/dev/null; then
  echo "  ✗ GÜVENLİK: anonim bağlantı kabul edildi"
else
  echo "  ✓ reddedildi"
fi

echo "=== 7) kalp atışı zinciri (cihaz yazar → panel-izleme okur) ==="
if [ -n "${MQTT_PAROLA_IZLEME:-}" ]; then
  timeout 6 mosquitto_sub -h "$HOST" -p 8883 -u panel-izleme -P "$MQTT_PAROLA_IZLEME" \
    -t "${KONU%%/yayin*}/durum/+" -C 1 >/tmp/izleme-dogrula 2>/dev/null &
  IZLE=$!
  sleep 1
  mosquitto_pub -h "$HOST" -p 8883 -u cihaz -P "$MQTT_PAROLA_CIHAZ" \
    -t "${KONU%%/yayin*}/durum/dogrulama" -r -m '{"cevrimici":true,"zaman":"2026-01-01T00:00:00Z"}'
  wait $IZLE 2>/dev/null
  if grep -q cevrimici /tmp/izleme-dogrula 2>/dev/null; then
    echo "  ✓ cihaz kalp atışı yazdı, panel-izleme okudu"
  else
    echo "  ✗ kalp atışı okunamadı (ACL: cihaz write / panel-izleme read eksik olabilir)"
  fi
  rm -f /tmp/izleme-dogrula
  mosquitto_pub -h "$HOST" -p 8883 -u cihaz -P "$MQTT_PAROLA_CIHAZ" \
    -t "${KONU%%/yayin*}/durum/dogrulama" -r -n 2>/dev/null || true
else
  echo "  - atlandı (MQTT_PAROLA_IZLEME verilmedi)"
fi

echo "=== 8) düz 1883 kapalı olmalı ==="
if timeout 4 bash -c "echo >/dev/tcp/$HOST/1883" 2>/dev/null; then
  echo "  ✗ GÜVENLİK: 1883 açık (TLS'siz MQTT)"
else
  echo "  ✓ kapalı"
fi

echo
[ "$PANEL_YAZDI" -eq 1 ] && echo "SONUÇ: temel akış çalışıyor ✓" || echo "SONUÇ: panel yayını çalışmıyor ✗"
