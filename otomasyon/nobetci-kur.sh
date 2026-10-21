#!/usr/bin/env bash
# Nöbetçi servisini kurar: systemd --user, 7/24, açılışta kendiliğinden.
#
#   ./otomasyon/nobetci-kur.sh i5                 # kur + başlat
#   ./otomasyon/nobetci-kur.sh i3                 # (i3 makinesinde)
#   ./otomasyon/nobetci-kur.sh i5 --cron-kaldir   # eski 'i5 guvenlik' cron görevini de sil
#   ./otomasyon/nobetci-kur.sh i5 --durum         # servis durumu
#   ./otomasyon/nobetci-kur.sh i5 --kaldir        # servisi durdur + sil
set -euo pipefail

ROL="${1:-}"; shift || true
if [ "$ROL" != "i5" ] && [ "$ROL" != "i3" ]; then
  echo "kullanım: $0 <i5|i3> [--cron-kaldir|--durum|--kaldir|--kuru]" >&2
  exit 2
fi
KIP="kur"
CRON_KALDIR=0
for a in "$@"; do
  case "$a" in
    # --cron-kaldir EK bir işlemdir: servisi kurmayı ENGELLEMEZ (ilk sürümde engelliyordu)
    --cron-kaldir) CRON_KALDIR=1 ;;
    --durum) KIP="durum" ;;
    --kaldir) KIP="kaldir" ;;
    --kuru) KIP="kuru" ;;
  esac
done

cron_kaldir() {
  local id
  id="$(hermes cron list 2>/dev/null | grep -B1 -E "Name:.*(i5|i3) [gG]uvenlik" | grep -oE '^[[:space:]]*[0-9a-f]{12}' | head -1 | tr -d ' ')"
  if [ -n "$id" ]; then
    hermes cron remove "$id" >/dev/null 2>&1 && echo "eski cron görevi silindi: $id"
  else
    echo "silinecek cron görevi yok (zaten temiz)"
  fi
}

DEPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_ADI="yourkiosk-nobetci.service"
UNIT_YOL="$HOME/.config/systemd/user/$UNIT_ADI"
# sistem python3 tercih edilir: venv yolu (ör. ~/.hermes/installs/...) güncellemede kırılır
if [ -x /usr/bin/python3 ]; then PYTHON=/usr/bin/python3; else PYTHON="$(command -v python3)"; fi
HERMES="$(command -v hermes || echo "$HOME/.local/bin/hermes")"

unit_metni() {
cat <<UNIT
[Unit]
Description=yourkiosk nobetci ($ROL) - olay gudumlu PR incelemesi
After=network-online.target

[Service]
Type=simple
WorkingDirectory=$DEPO
Environment=PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
Environment=GITHUB_DEPO=hakkisabah/yourkiosk
ExecStart=$PYTHON $DEPO/otomasyon/betik/nobetci.py --rol $ROL --aralik 15
Restart=always
RestartSec=5
StandardOutput=append:$HOME/.local/state/yourkiosk-otomasyon/nobetci-$ROL.log
StandardError=inherit

[Install]
WantedBy=default.target
UNIT
}

case "$KIP" in
  durum)
    systemctl --user status "$UNIT_ADI" --no-pager | head -12 || true
    echo; echo "--- nöbetçi durum dosyası ---"
    "$PYTHON" "$DEPO/otomasyon/betik/nobetci.py" --rol "$ROL" --durum || true
    ;;
  kaldir)
    systemctl --user disable --now "$UNIT_ADI" 2>/dev/null || true
    rm -f "$UNIT_YOL"; systemctl --user daemon-reload
    echo "servis kaldırıldı: $UNIT_ADI"
    ;;
  kuru)
    echo "--- $UNIT_YOL ---"; unit_metni
    ;;
  kur)
    mkdir -p "$HOME/.config/systemd/user" "$HOME/.local/state/yourkiosk-otomasyon"
    unit_metni > "$UNIT_YOL"
    systemctl --user daemon-reload
    systemctl --user enable --now "$UNIT_ADI"
    loginctl enable-linger "$USER" 2>/dev/null || echo "UYARI: loginctl enable-linger başarısız (oturum kapanınca durabilir)"
    sleep 2
    echo
    echo "=== kuruldu ==="
    systemctl --user --no-pager status "$UNIT_ADI" | head -10
    echo
    echo "canlı günlük: journalctl --user -u $UNIT_ADI -f"
    echo "             tail -f $HOME/.local/state/yourkiosk-otomasyon/nobetci-$ROL.log"
    if [ "$CRON_KALDIR" -eq 1 ]; then cron_kaldir; else echo "cron'u kaldırmak için: $0 $ROL --cron-kaldir"; fi
    ;;
esac
