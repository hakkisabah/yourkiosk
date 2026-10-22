#!/bin/sh
# yourkiosk kiosk konteyner giriş noktası
set -e

# Fiziksel ekran yoksa sanal ekran aç (başsız test/geliştirme)
if [ ! -S "/tmp/.X11-unix/X${DISPLAY#:}" ] && [ "${DISPLAY#:}" != "$DISPLAY" ]; then
  echo "[entrypoint] X sunucusu yok → Xvfb ${DISPLAY} başlatılıyor"
  Xvfb "${DISPLAY}" -screen 0 1920x1080x24 &
  sleep 1
fi

cd /app/kiosk
echo "[entrypoint] veri modu: ${WEB_VERI_MODU:-yerel} · tarayıcı: ${TARAYICI_YOLU:-chromium}"
exec python3 tools/tarayici_kiosk.py "$@"
