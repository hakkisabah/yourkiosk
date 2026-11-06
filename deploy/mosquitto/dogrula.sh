#!/usr/bin/env bash
# yourkiosk MQTT doğrulama — HERHANGİ bir makineden çalıştırılabilir.
#
#   MQTT_PAROLA_PANEL=… MQTT_PAROLA_CIHAZ=… MQTT_PAROLA_IZLEME=… bash dogrula.sh <host>
#
# Kalp atışı zincirini de sınamak için cihaz BAŞINA kimlik verin (kur.sh / cihaz-ekle.sh çıktısı):
#   … MQTT_CIHAZ_ID=C1 MQTT_CIHAZ_PAROLA=… bash dogrula.sh <host>
#
# Değişkenler (TEK ad — 26 Ekim i5 bulgusu: başlık `MQTT_PAROLA_CIHAZ` diyordu, 5. kontrol
# `MQTT_CIHAZ_PAROLA` arıyordu; belgeyi izleyen operatör kontrolleri sessizce atlıyordu):
#   MQTT_PAROLA_PANEL · MQTT_PAROLA_CIHAZ           (zorunlu)
#   MQTT_PAROLA_IZLEME · MQTT_CIHAZ_ID · MQTT_CIHAZ_PAROLA   (5 ve 7 için zorunlu)
#
# Kontroller:
#   1) TLS el sıkışması ve sertifika geçerliliği   2) panel YAYIN yapabiliyor
#   3) cihaz ABONE olup mesajı alıyor              4) cihaz YAYIN yapamıyor
#   5) cihaz kimliği BAŞKA cihazın konusuna yazamıyor (taklit kapalı)
#   6) anonim bağlantı reddediliyor                7) kalp atışı zinciri (cihaz-<id> → panel-izleme)
#   8) düz 1883 kapalı
# "? DOĞRULANAMADI" satırı ✓ DEĞİLDİR: kimlik/parola/ACL hatası var demektir.
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
# ALAN ADI DA DOĞRULANIR (27 Ekim i5 bulgusu): `-brief` çıktısındaki "Verification: OK" yalnız
# ZİNCİRİ doğrular, sertifikanın $HOST'u KAPSADIĞINI doğrulamaz (ölçüm: wrong.host.badssl.com →
# CN=*.badssl.com olmasına rağmen "Verification: OK"). Yanlış uca kurulmuş sertifika kontrolü
# geçiyordu. Bu yüzden ya `-verify_hostname` ya (hedef IP ise) `-verify_ip` verilir; openssl ad
# eşleşmezse "Verify return code" sıfırdan farklı olur.
if printf '%s' "$HOST" | grep -qE '^[0-9]{1,3}(\.[0-9]{1,3}){3}$'; then
  AD_DOGRULA=(-verify_ip "$HOST")
else
  AD_DOGRULA=(-verify_hostname "$HOST")
fi
TLS_CIKTI="$(openssl s_client -connect "$HOST:8883" -servername "$HOST" "${AD_DOGRULA[@]}" -brief </dev/null 2>&1)"
if printf '%s' "$TLS_CIKTI" | grep -q "Verification: OK" \
   && printf '%s' "$TLS_CIKTI" | grep -qE "Verify return code: 0 \(ok\)"; then
  echo "  ✓ sertifika geçerli (CA + alan adı doğrulandı: $HOST)"
else
  echo "  ✗ TLS doğrulanamadı — sertifika/alan adı sorunu"
  printf '%s\n' "$TLS_CIKTI" | sed 's/^/    /' | head -12
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

echo "=== 5) cihaz kimliği BAŞKA cihazın durum konusuna yazamaz ==="
# Cihaz başına kullanıcı izolasyonu: ele geçirilmiş bir kiosk başka cihazın çevrimiçi
# durumunu taklit edememeli. Cihaz kimliği gerektirir (MQTT_CIHAZ_PAROLA).
if [ -n "${MQTT_CIHAZ_PAROLA:-}" ] && [ -n "${MQTT_PAROLA_IZLEME:-}" ] && [ -n "${MQTT_CIHAZ_ID:-}" ]; then
  TABAN5="${KONU%%/yayin*}"
  YABANCI="$TABAN5/durum/yabanci-$$"
  GECICI5="$(mktemp)"
  ( timeout 5 mosquitto_sub -h "$HOST" -p 8883 -u panel-izleme -P "$MQTT_PAROLA_IZLEME" \
    -t "$YABANCI" -C 1 >"$GECICI5" 2>/dev/null ) &
  ABONE5=$!
  sleep 1
  mosquitto_pub -h "$HOST" -p 8883 \
    -u "cihaz-${MQTT_CIHAZ_ID:-bilinmeyen}" -P "$MQTT_CIHAZ_PAROLA" \
    -t "$YABANCI" -m '{"cevrimici":true}' 2>/dev/null || true
  wait "$ABONE5" 2>/dev/null; RC5=$?
  if [ -s "$GECICI5" ]; then
    echo "  ✗ GÜVENLİK: cihaz başka cihazın durum konusuna yazabildi (taklit)"
  elif [ "$RC5" -eq 124 ]; then
    echo "  ✓ reddedildi (her cihaz yalnız kendi konusuna yazar)"
  else
    echo "  ? DOĞRULANAMADI: abone bağlanamadı (çıkış $RC5) — panel-izleme kimliği/ACL denetlenmeli"
  fi
  rm -f "$GECICI5"
else
  echo "  - atlandı (MQTT_PAROLA_IZLEME + MQTT_CIHAZ_ID + MQTT_CIHAZ_PAROLA birlikte verilmedi)"
fi

echo "=== 6) anonim bağlantı reddedilmeli ==="
if timeout 5 mosquitto_pub -h "$HOST" -p 8883 -t "$KONU" -m 'x' 2>/dev/null; then
  echo "  ✗ GÜVENLİK: anonim bağlantı kabul edildi"
else
  echo "  ✓ reddedildi"
fi

echo "=== 7) kalp atışı zinciri (cihaz-<id> yazar → panel-izleme okur) ==="
# Sabit /tmp yolu YOK (i5 bulgusu: sembolik bağ) — mktemp.
# Kalp atışı cihaz BAŞINA kimlikle yazılır (paylaşılan `cihaz` hesabı ACL'de yazamaz).
if [ -n "${MQTT_PAROLA_IZLEME:-}" ] && [ -n "${MQTT_CIHAZ_PAROLA:-}" ]; then
  TABAN="${KONU%%/yayin*}"
  # ACL yalnız `cihaz-<id>` hesabına `durum/<id>` yazma izni verir (cihaz-ekle.sh:59). Sabit
  # `durum/dogrulama-$$` konusuna paylaşılan `cihaz` hesabıyla yazmak HER KOŞUDA ✗ veriyordu
  # (i5 bulgusu). Doğru yol: gerçek cihaz kimliğiyle (MQTT_CIHAZ_ID) kendi konusuna yazmak.
  if [ -z "${MQTT_CIHAZ_ID:-}" ]; then
    echo "  - atlandı: MQTT_CIHAZ_ID verilmedi (ACL, kimliksiz hesaba yazma izni vermez)"
    echo "    Denemek için: MQTT_CIHAZ_ID=C1 MQTT_CIHAZ_PAROLA=... sudo -E $0"
  else
    TEST_KONU="$TABAN/durum/$MQTT_CIHAZ_ID"
    KULLANICI="cihaz-$MQTT_CIHAZ_ID"
    GECICI3="$(mktemp)"
    timeout 6 mosquitto_sub -h "$HOST" -p 8883 -u panel-izleme -P "$MQTT_PAROLA_IZLEME" \
      -t "$TEST_KONU" -C 1 >"$GECICI3" 2>/dev/null &
    IZLE=$!
    sleep 1
    if mosquitto_pub -h "$HOST" -p 8883 -u "$KULLANICI" -P "$MQTT_CIHAZ_PAROLA" \
         -t "$TEST_KONU" -r -m '{"cevrimici":true,"zaman":"2026-01-01T00:00:00Z"}' 2>/dev/null; then
      wait $IZLE 2>/dev/null
      if grep -q cevrimici "$GECICI3" 2>/dev/null; then
        echo "  ✓ $KULLANICI kalp atışı yazdı, panel-izleme okudu"
      else
        echo "  ✗ yayın kabul edildi ama panel-izleme OKUMADI (ACL read: $TEST_KONU değil $TABAN/durum/+)"
      fi
    else
      echo "  ✗ $KULLANICI yazamadı (ACL: topic write $TABAN/durum/$MQTT_CIHAZ_ID eksik olabilir)"
    fi
    mosquitto_pub -h "$HOST" -p 8883 -u "$KULLANICI" -P "$MQTT_CIHAZ_PAROLA" \
      -t "$TEST_KONU" -r -n 2>/dev/null || true
    rm -f "$GECICI3"
  fi
else
  echo "  - atlandı (MQTT_PAROLA_IZLEME ve MQTT_CIHAZ_PAROLA birlikte verilmedi)"
fi

echo "=== 8) düz 1883 kapalı olmalı ==="
if timeout 4 bash -c "echo >/dev/tcp/$HOST/1883" 2>/dev/null; then
  echo "  ✗ GÜVENLİK: 1883 açık (TLS'siz MQTT)"
else
  echo "  ✓ kapalı"
fi

echo
[ "$PANEL_YAZDI" -eq 1 ] && echo "SONUÇ: temel akış çalışıyor ✓" || echo "SONUÇ: panel yayını çalışmıyor ✗"
