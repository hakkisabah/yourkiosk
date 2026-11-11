#!/usr/bin/env bash
# Otonom koordinatörü kurar: DSH geliştirici profili + bwrap runner + systemd user timer.
#
#   bash otomasyon/otonom-kur.sh --kuru      # ne kurulacak, yazmadan göster
#   bash otomasyon/otonom-kur.sh             # kur + timer'ı başlat
#   bash otomasyon/otonom-kur.sh --simdi     # bir tik hemen çalıştır (arka planda)
#   bash otomasyon/otonom-kur.sh --durum     # timer + son durum + son günlük
#   bash otomasyon/otonom-kur.sh --kaldir    # timer'ı durdur, birimleri sil
set -euo pipefail

DEPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KIP="kur"
ARALIK_MIN=20
for a in "$@"; do
  case "$a" in
    --kuru) KIP="kuru" ;;
    --kaldir) KIP="kaldir" ;;
    --durum) KIP="durum" ;;
    --simdi) KIP="simdi" ;;
    --aralik=*) ARALIK_MIN="${a#--aralik=}" ;;
    *) echo "✗ bilinmeyen seçenek: $a" >&2; exit 2 ;;
  esac
done
case "$ARALIK_MIN" in
  ''|*[!0-9]*) echo "✗ --aralik sayı olmalı" >&2; exit 2 ;;
esac
if [ "$ARALIK_MIN" -lt 5 ] || [ "$ARALIK_MIN" -gt 1440 ]; then
  echo "✗ --aralik 5..1440 dakika olmalı" >&2; exit 2
fi

PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  if [ -x /usr/bin/python3 ]; then PYTHON=/usr/bin/python3
  else PYTHON="$(command -v python3)"; fi
fi
BETIK="$DEPO/otomasyon/betik/otonom_tik.py"
RUNNER_KAYNAK="$DEPO/otomasyon/dsh-bwrap-gelistirici"
PROFIL_ADI="otonom-gelistirici"
PROFIL_DIZIN="$HOME/.dsh/profiles/$PROFIL_ADI"
UNIT_DIZIN="$HOME/.config/systemd/user"
UNIT_SERVIS="otonom-tik.service"
UNIT_TIMER="otonom-tik.timer"
DURUM_DIZIN="$HOME/.local/state/yourkiosk-otonom"
OTONOM_DEPO="${OTONOM_DEPO:-$HOME/.local/share/yourkiosk-otonom/depo}"
DSH_CHECKOUT="${DSH_CHECKOUT:-$HOME/deepseek-harness}"
ZAMAN_ASIMI="${OTONOM_ZAMAN_ASIMI:-2700}"
SADECE_PR="${OTONOM_SADECE_PR:-}"
case "$SADECE_PR" in
  ''|*[!0-9,]*) [ -z "$SADECE_PR" ] || { echo "✗ OTONOM_SADECE_PR yalnız sayı ve virgül içermeli" >&2; exit 2; } ;;
esac
RAM_MB="$(awk '/^MemTotal:/ { printf "%d", $2/1024 }' /proc/meminfo 2>/dev/null || true)"
case "${RAM_MB:-}" in ''|*[!0-9]*) RAM_MB=0 ;; esac
if [ "$RAM_MB" -gt 2048 ]; then
  MEM_HIGH_MB=$(( RAM_MB * 60 / 100 ))
  MEM_MAX_MB=$(( RAM_MB * 75 / 100 ))
  NODE_HEAP_MB=$(( RAM_MB / 4 ))
  [ "$NODE_HEAP_MB" -lt 512 ] && NODE_HEAP_MB=512
  [ "$NODE_HEAP_MB" -gt 2048 ] && NODE_HEAP_MB=2048
else
  MEM_HIGH_MB=1024; MEM_MAX_MB=1280; NODE_HEAP_MB=768
fi

soyle() { echo "$*"; }
hata() { printf '✗ %s
' "$*" >&2; }

birim_metni() {
cat <<UNIT
[Unit]
Description=yourkiosk otonom koordinator (zamanli DSH headless)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$DEPO
Environment=PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
Environment=GITHUB_DEPO=hakkisabah/yourkiosk
Environment=DSH_CHECKOUT=$DSH_CHECKOUT
Environment=OTONOM_DEPO=$OTONOM_DEPO
Environment=OTONOM_PROFIL=$PROFIL_ADI
Environment=OTONOM_ZAMAN_ASIMI=$ZAMAN_ASIMI
$([ -n "$SADECE_PR" ] && echo "Environment=OTONOM_SADECE_PR=$SADECE_PR")
Environment=NODE_OPTIONS=--max-old-space-size=$NODE_HEAP_MB
Nice=10
CPUWeight=50
MemoryAccounting=yes
MemoryHigh=${MEM_HIGH_MB}M
MemoryMax=${MEM_MAX_MB}M
NoNewPrivileges=true
TimeoutStartSec=$(( ZAMAN_ASIMI + 300 ))
ExecStart=$PYTHON $BETIK
UNIT
}

zamanlayici_metni() {
cat <<TIMER
[Unit]
Description=otonom koordinator zamanlayici

[Timer]
OnBootSec=10min
OnUnitInactiveSec=${ARALIK_MIN}min
Persistent=true
RandomizedDelaySec=60
AccuracySec=1min

[Install]
WantedBy=timers.target
TIMER
}

on_kontrol() {
  local yumusak="${1:-0}"
  [ -f "$BETIK" ] || { hata "betik yok: $BETIK"; exit 3; }
  [ -f "$RUNNER_KAYNAK" ] || { hata "runner yok: $RUNNER_KAYNAK"; exit 3; }
  [ -f "$DEPO/otomasyon/dsh-gelistirici.cordis.patch.yml" ] || { hata "profil yaması yok"; exit 3; }
  [ -f "$DEPO/otomasyon/dsh-gelistirici-profile.json" ] || { hata "profil package.json yok"; exit 3; }
  if [ ! -f "$DSH_CHECKOUT/apps/cli/lib/bin.js" ]; then
    if [ "$yumusak" = "1" ]; then
      soyle "UYARI: DSH CLI yok: $DSH_CHECKOUT (kurulum için gerekir; --kuru devam ediyor)"
    else
      hata "DSH CLI yok: $DSH_CHECKOUT"; exit 3
    fi
  fi
  "$PYTHON" -m py_compile "$BETIK" || { hata "otonom_tik.py derlenemedi"; exit 3; }
  bash -n "$RUNNER_KAYNAK" || { hata "runner sözdizimi bozuk"; exit 3; }
}

profil_kur() {
  install -d -m 700 "$PROFIL_DIZIN"
  if [ -f "$PROFIL_DIZIN/cordis.patch.yml" ]; then
    cp -p "$PROFIL_DIZIN/cordis.patch.yml" "$PROFIL_DIZIN/cordis.patch.yml.bak-$(date +%Y%m%dT%H%M%S)"
  fi
  sed "s#/home/hakki#$HOME#g" "$DEPO/otomasyon/dsh-gelistirici.cordis.patch.yml" > "$PROFIL_DIZIN/cordis.patch.yml"
  chmod 600 "$PROFIL_DIZIN/cordis.patch.yml"
  install -m 600 "$DEPO/otomasyon/dsh-gelistirici-profile.json" "$PROFIL_DIZIN/package.json"
  if [ -f "$HOME/.dsh/profiles/headless/cordis.yml" ]; then
    cp -p "$HOME/.dsh/profiles/headless/cordis.yml" "$PROFIL_DIZIN/cordis.yml"
  else
    printf '[]
' > "$PROFIL_DIZIN/cordis.yml"
  fi
  if [ -f "$HOME/.dsh/profiles/headless/pnpm-workspace.yaml" ]; then
    cp -p "$HOME/.dsh/profiles/headless/pnpm-workspace.yaml" "$PROFIL_DIZIN/pnpm-workspace.yaml"
  fi
}

kur() {
  on_kontrol
  install -d -m 700 "$HOME/.agents/bin" "$DURUM_DIZIN"
  install -m 0755 "$RUNNER_KAYNAK" "$HOME/.agents/bin/dsh-bwrap-gelistirici"
  profil_kur
  install -d -m 700 "$UNIT_DIZIN"
  birim_metni > "$UNIT_DIZIN/$UNIT_SERVIS"
  zamanlayici_metni > "$UNIT_DIZIN/$UNIT_TIMER"
  chmod 644 "$UNIT_DIZIN/$UNIT_SERVIS" "$UNIT_DIZIN/$UNIT_TIMER"
  systemctl --user daemon-reload
  systemctl --user enable --now "$UNIT_TIMER"
  loginctl enable-linger "$USER" 2>/dev/null || soyle "UYARI: enable-linger başarısız (oturum kapanınca timer durabilir)"
  soyle ""
  soyle "=== kuruldu ==="
  soyle "profil      : $PROFIL_DIZIN ($PROFIL_ADI)"
  soyle "runner      : $HOME/.agents/bin/dsh-bwrap-gelistirici"
  soyle "makine klonu: $OTONOM_DEPO"
  soyle "aralık      : ${ARALIK_MIN} dk · ajan bütçesi ${ZAMAN_ASIMI} sn"
  [ -n "$SADECE_PR" ] && soyle "PR filtresi : ${SADECE_PR} (geçiş dönemi)"
  soyle "günlük      : $DURUM_DIZIN/otonom.log"
  systemctl --user list-timers "otonom-tik*" --no-pager || true
}

kaldir() {
  systemctl --user disable --now "$UNIT_TIMER" 2>/dev/null || true
  systemctl --user stop "$UNIT_SERVIS" 2>/dev/null || true
  rm -f "$UNIT_DIZIN/$UNIT_SERVIS" "$UNIT_DIZIN/$UNIT_TIMER"
  systemctl --user daemon-reload
  soyle "timer ve birimler kaldırıldı (profil/runner/durum korundu)"
}

durum() {
  systemctl --user list-timers "otonom-tik*" --all --no-pager || true
  systemctl --user is-active "$UNIT_TIMER" 2>/dev/null || true
  systemctl --user status "$UNIT_SERVIS" --no-pager -n 8 2>/dev/null || true
  "$PYTHON" "$BETIK" --durum || true
}

case "$KIP" in
  kuru)
    on_kontrol 1
    soyle "--- runner ---"
    soyle "  $RUNNER_KAYNAK -> $HOME/.agents/bin/dsh-bwrap-gelistirici (0755)"
    soyle "--- profil ---"
    soyle "  $PROFIL_ADI -> $PROFIL_DIZIN"
    soyle "--- birim ---"
    birim_metni
    soyle "--- zamanlayici ---"
    zamanlayici_metni
    ;;
  kur) kur ;;
  kaldir) kaldir ;;
  durum) durum ;;
  simdi)
    systemctl --user start --no-block "$UNIT_SERVIS"
    soyle "tik başlatıldı (arka planda). İzle:"
    soyle "  tail -f $DURUM_DIZIN/otonom.log"
    soyle "  systemctl --user status $UNIT_SERVIS --no-pager"
    ;;
esac
