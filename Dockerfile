# yourkiosk · tarayıcı (Chromium kiosk) modu için imaj
#
#   ./kur.sh docker          # derle + başlat
#   docker compose logs -f kiosk
#
# Notlar:
#  • Fiziksel ekran için X11 soketi bağlanır (compose dosyasında).
#  • Ekran yoksa Xvfb (:99) açılır — başsız test/geliştirme için yeterli.
#  • `web/dist` imaja KOPYALANIR; önce `./kur.sh kiosk` ile derlenmiş olmalı.
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Istanbul

RUN apt-get update && apt-get install -y --no-install-recommends \
        chromium \
        xvfb \
        x11-utils \
        fonts-dejavu-core \
        ca-certificates \
        tzdata \
        curl \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Bağımlılıklar önce (katman önbelleği)
COPY kiosk/requirements.txt /app/kiosk/requirements.txt
RUN pip install --no-cache-dir -r /app/kiosk/requirements.txt paho-mqtt

COPY . /app

RUN chmod +x /app/deploy/docker/entrypoint.sh \
    && test -f /app/web/dist/index.html || echo "UYARI: web/dist yok — önce ./kur.sh kiosk"

EXPOSE 8090
ENTRYPOINT ["/app/deploy/docker/entrypoint.sh"]
