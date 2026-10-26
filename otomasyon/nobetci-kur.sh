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
# 26 Ekim i5 bulgusu: --profil değeri doğrulanmadan systemd birim METNİNE yazılıyordu; satır sonu
# taşıyan bir ad birime yeni yönerge enjekte edebiliyordu (`--profil "a\nExecStartPre=..."`).
# Hermes profil adları küçük harf/rakam/tire/alt çizgi; birim dosyasına giden her değer bu kapıdan geçer.
profil_gecerli() {  # 1..32 karakter; ilk harf küçük harf/rakam; kalanı a-z 0-9 _ -
  local p="$1"
  [ "${#p}" -ge 1 ] && [ "${#p}" -le 32 ] || return 1
  case "$p" in
    [a-z0-9]*) ;;
    *) return 1 ;;
  esac
  case "$p" in
    *[!a-z0-9_-]*) return 1 ;;
  esac
  return 0
}
if [ -n "$PROFIL" ] && ! profil_gecerli "$PROFIL"; then
  echo "✗ geçersiz --profil değeri: '$PROFIL'" >&2
  echo "  İzinli biçim: 1–32 karakter, ilk harf küçük harf/rakam, kalanı a-z 0-9 _ -" >&2
  echo "  (satır sonu/boşluk/özel karakter kabul edilmez: değer systemd birim METNİNE yazılıyor)" >&2
  exit 2
fi

# ESKİ HATA: yalnız "i5/i3 guvenlik" ADINI arıyordu; "i3 karar" adlı görev silinmiyordu → oturumlar
# iki kaynaktan açılmaya devam ediyordu. Artık ada değil İŞ DİZİNİNE bakıyor ve silmeyi DOĞRULUYOR.
cron_kaldir() {
  "$PYTHON" "$DEPO/otomasyon/betik/cron_temizle.py" --sil
}

DEPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# ── BELLEK TAVANI (26 Ekim dersi: `node-MainThread` V8 FatalProcessOutOfMemory core dump) ────────
# i5'te birim cgroup'unda node abort etti; makinede ~3,8 GB RAM var. V8 tavanı makine RAM'inden
# bağımsız kurulduğunda (Hermes TUI 8 GB ister) takas dolar ve süreç "ölümcül OOM" ile düşer.
# Bu yüzden tavanlar KURULUM ANINDA makineden ölçülür (sabit sayı yazmak 4 GB'lık i5'e 16 GB'lık
# tavan verir). Değerler birimde görünür → "ayarladım" sanıp görünmez bırakmak yok.
RAM_MB="$(awk '/^MemTotal:/ { printf "%d", $2/1024 }' /proc/meminfo 2>/dev/null || true)"
case "${RAM_MB:-}" in ''|*[!0-9]*) RAM_MB=0 ;; esac
if [ "$RAM_MB" -gt 1024 ]; then
  MEM_HIGH_MB=$(( RAM_MB * 60 / 100 ))          # yumuşak: üstünde çekirdek geri- baskı uygular
  MEM_MAX_MB=$(( RAM_MB * 75 / 100 ))           # sert: aşarsa OOM yalnız bu birimi öldürür
  NODE_HEAP_MB=$(( RAM_MB / 4 ))                # V8 old-space tavanı (Node çocukları için)
  [ "$NODE_HEAP_MB" -lt 512 ] && NODE_HEAP_MB=512
  [ "$NODE_HEAP_MB" -gt 2048 ] && NODE_HEAP_MB=2048
else
  # Ölçüm yok/küçük: muhafazakâr varsayılan (görünür uyarı ile)
  MEM_HIGH_MB=1024; MEM_MAX_MB=1280; NODE_HEAP_MB=768
  echo "UYARI: MemTotal okunamadı (${RAM_MB} MB) → muhafazakâr bellek tavanları kullanılıyor" >&2
fi

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
# ÇÖKME DÖNGÜSÜ FRENİ: 26 Ekim'de node OOM'u ardından Restart=always her 5 sn'de yeni oturum
# açtı; her oturum token + core dump üretti. 5 dakikada 5'ten fazla çökme → birim durur (görünür).
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
WorkingDirectory=$DEPO
Environment=PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
Environment=GITHUB_DEPO=hakkisabah/yourkiosk
# Node çocukları (vitest/vue-tsc/vite) ÖLÇÜLÜ V8 tavanı devralır: makine RAM'inin 1/4'ü
# (4 GB makinede ~950 MB). Tavansız V8, RAM'den büyük tavan kurup "FatalProcessOutOfMemory" ile
# abort ediyordu (26 Ekim, casperi5 core dump). Ağır komutlar yine de agir-komut.sh ile koşmalı.
Environment=NODE_OPTIONS=--max-old-space-size=$NODE_HEAP_MB
$([ -n "$PROFIL" ] && echo "Environment=NOBETCI_PROFIL=$PROFIL")
# Ayrı profil + düşük öncelik: Open WebUI/sohbet yükü nöbetçiyi aç bırakmasın (26 Ekim i5 mimarisi)
Nice=10
CPUWeight=50
# BELLEK TAVANI: yumuşak eşikte çekirdek geri-baskı uygular, sert eşikte OOM YALNIZ bu birimi
# öldürür (makine takasa gömülmez, sohbet/panel ayakta kalır). Değerler kurulumda ölçülür.
MemoryAccounting=yes
MemoryHigh=${MEM_HIGH_MB}M
MemoryMax=${MEM_MAX_MB}M
TasksMax=1024
OOMPolicy=stop
TimeoutStopSec=30
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
    echo "bellek tavanı: RAM ${RAM_MB} MB → MemoryHigh ${MEM_HIGH_MB} MB · MemoryMax ${MEM_MAX_MB} MB · NODE_OPTIONS heap ${NODE_HEAP_MB} MB"
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
