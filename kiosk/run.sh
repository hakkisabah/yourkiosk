#!/usr/bin/env bash
# yourkiosk çalıştırma betiği.
#
# Üretim cihazında (Arch, python-pyqt6 sistem paketi kurulu) yalnızca
# `python3 main.py` yeterlidir. Bu betik geliştirme/test ortamı için eksik
# Qt kütüphanelerini proje içi .qt-libs dizininden tamamlar ve gerekli ortam
# değişkenlerini ayarlar.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

PYTHON="${KIOSK_PYTHON:-$HERE/.venv/bin/python}"
[ -x "$PYTHON" ] || PYTHON="python3"

if [ -d "$HERE/.qt-libs/lib" ]; then
  export LD_LIBRARY_PATH="$HERE/.qt-libs/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HERE/.cache}"

if [ ! -f /etc/fonts/fonts.conf ]; then
  FONT_CONF="$("$PYTHON" -c 'from fontconfig_setup import yerel_yapilandirma; print(yerel_yapilandirma() or "")' 2>/dev/null || true)"
  [ -n "$FONT_CONF" ] && export FONTCONFIG_FILE="$FONT_CONF"
fi

exec "$PYTHON" "$HERE/main.py" "$@"
