#!/usr/bin/env bash
# Nöbetçi servisini kurar: systemd --user, 7/24, açılışta kendiliğinden.
#
#   ./otomasyon/nobetci-kur.sh i5                 # kur + başlat
#   ./otomasyon/nobetci-kur.sh i3                 # (i3 makinesinde)
#   ./otomasyon/nobetci-kur.sh i5 --cron-kaldir   # bu depoya ait TÜM cron görevlerini sil (+ servisi kur)
#   ./otomasyon/nobetci-kur.sh i5 --sadece-cron   # yalnız cron'ları sil, servise dokunma
#   ./otomasyon/nobetci-kur.sh i5 --denetle       # kontrol noktaları: cron/servis/linger/oturum
#   ./otomasyon/nobetci-kur.sh i5 --durum         # servis durumu
#   ./otomasyon/nobetci-kur.sh i5 --kaldir        # servisi durdur + sil
set -euo pipefail

ROL="${1:-}"; shift || true
if [ "$ROL" != "i5" ] && [ "$ROL" != "i3" ]; then
  echo "kullanım: $0 <i5|i3> [--cron-kaldir|--sadece-cron|--denetle|--durum|--kaldir|--kuru]" >&2
  exit 2
fi
KIP="kur"
CRON_KALDIR=0
PROFIL="${NOBETCI_PROFIL:-}"
for a in "$@"; do
  case "$a" in
    # --cron-kaldir EK bir işlemdir: servisi kurmayı ENGELLEMEZ (ilk sürümde engelliyordu)
    --cron-kaldir) CRON_KALDIR=1 ;;
    --sadece-cron) CRON_KALDIR=2 ;;
    --denetle) KIP="denetle" ;;
    --durum) KIP="durum" ;;
    --kaldir) KIP="kaldir" ;;
    --kuru) KIP="kuru" ;;
    --profil=*) PROFIL="${a#--profil=}" ;;
  esac
done
# --profil <ad> (ayrı boşluklu biçim)
for ((i = 1; i <= $#; i++)); do
  if [ "${!i}" = "--profil" ]; then j=$((i + 1)); PROFIL="${!j:-}"; fi
done
if [ -n "$PROFIL" ] && [ "$PROFIL" = "$ROL" ]; then
  echo "✗ --profil değeri rol adıyla aynı olamaz ($ROL)" >&2; exit 2
fi


# ESKİ HATA: yalnız "i5/i3 guvenlik" ADINI arıyordu; "i3 karar" adlı görev silinmiyordu → oturumlar
# iki kaynaktan açılmaya devam ediyordu. Artık ada değil İŞ DİZİNİNE bakıyor ve silmeyi DOĞRULUYOR.
cron_kaldir() {
  "$PYTHON" "$DEPO/otomasyon/betik/cron_temizle.py" --sil
}

DEPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# --sadece-cron: yalnız cron temizliği yap, systemd'ye DOKUNMA
if [ "$CRON_KALDIR" -eq 2 ]; then
  exec "$(command -v python3)" "$DEPO/otomasyon/betik/cron_temizle.py" --sil
fi
# --denetle: kontrol noktaları (hiçbir şeyi değiştirmez)
if [ "$KIP" = "denetle" ]; then
  exec "$(command -v python3)" "$DEPO/otomasyon/betik/nobetci.py" --rol "$ROL" --kendini-denetle
fi
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
$([ -n "$PROFIL" ] && echo "Environment=NOBETCI_PROFIL=$PROFIL")
# Ayrı profil + düşük öncelik: Open WebUI/sohbet yükü nöbetçiyi aç bırakmasın (26 Ekim i5 mimarisi)
Nice=10
CPUWeight=50
ExecStart=$PYTHON $DEPO/otomasyon/betik/nobetci.py --rol $ROL --aralik 15${PROFIL:+ --profil $PROFIL}
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
    if [ -n "$PROFIL" ] && ! "$HERMES" profile list 2>/dev/null | grep -qw "$PROFIL"; then
      echo "✗ Hermes profili yok: '$PROFIL'"
      echo "  Önce oluşturun, sonra tekrar çalıştırın:"
      echo "    hermes profile create $PROFIL"
      echo "    hermes -p $PROFIL config set platforms.api_server.enabled false   # bu profilde API sunucusu YOK"
      exit 3
    fi
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
    echo
    echo "=== kontrol noktaları ==="
    "$PYTHON" "$DEPO/otomasyon/betik/nobetci.py" --rol "$ROL" --kendini-denetle || echo "(denetim uyarı verdi — yukarıya bak)"
    ;;
esac
