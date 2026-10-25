#!/usr/bin/env bash
# CİHAZ BAŞINA MQTT KULLANICISI — paylaşılan `cihaz` hesabı yerine dar yetkili kimlik.
#
# NEDEN: paylaşılan `cihaz` hesabı `yourkiosk/durum/+` konusuna yazabilir; parola sahada
# paylaşıldığı için bir cihaz başka cihazın durumunu taklit edebilir. Cihaz başına kullanıcı
# açtığınızda her cihaz YALNIZ kendi `durum/<id>` konusuna yazar.
#
# Kullanım (broker'da, root):
#   ./cihaz-ekle.sh C1                 # kullanıcı: cihaz-C1, konu: yourkiosk/durum/C1
#   ./cihaz-ekle.sh C1 --sil           # kullanıcıyı ve ACL satırlarını kaldır
#   ./cihaz-ekle.sh --liste            # tanımlı cihaz kullanıcıları
#
# Çıktı: parola (yalnız bir kez gösterilir) + cihazın ayarlar.json alanları.
set -euo pipefail

AUTH_DIZIN="/etc/mosquitto/auth"
PASSWD="$AUTH_DIZIN/passwd"
ACL="$AUTH_DIZIN/acl"
KONU_TABANI="${KONU_TABANI:-yourkiosk}"

[[ $EUID -eq 0 ]] || { echo "✗ root gerekli (sudo)" >&2; exit 2; }

listele() {
  echo "tanımlı cihaz kullanıcıları:"
  cut -d: -f1 "$PASSWD" | sed -n 's/^cihaz-//p' | sort | sed 's/^/  /'
}

sil() {
  local kimlik="$1" kullanici="cihaz-$1"
  mosquitto_passwd -D "$PASSWD" "$kullanici" >/dev/null 2>&1 || true
  # ACL'de bu kullanıcıya ait 3 satırlık bloğu kaldır
  awk -v u="$kullanici" '
    $1=="user" { atla = ($2==u); if (atla) next }
    atla && /^topic / { next }
    { print }
  ' "$ACL" >"$ACL.yeni"
  install -m 640 -o mosquitto -g mosquitto "$ACL.yeni" "$ACL"
  rm -f "$ACL.yeni"
  systemctl reload mosquitto
  echo "✓ $kullanici silindi (cihaz ayarlarını paylaşılan 'cihaz' hesabına döndürün)"
}

ekle() {
  local kimlik="$1"
  [[ "$kimlik" =~ ^[A-Za-z0-9_-]{1,40}$ ]] || { echo "✗ geçersiz cihaz kimliği: $kimlik" >&2; exit 2; }
  local kullanici="cihaz-$kimlik"
  local parola
  parola="$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)"
  mosquitto_passwd -b "$PASSWD" "$kullanici" "$parola"
  chown root:mosquitto "$PASSWD"
  chmod 640 "$PASSWD"

  if ! grep -q "^user $kullanici\$" "$ACL"; then
    cat >>"$ACL" <<EOF

# cihaz: $kimlik (yalnız kendi durum konusuna yazar)
user $kullanici
topic read $KONU_TABANI/yayin
topic write $KONU_TABANI/durum/$kimlik
EOF
    chown mosquitto:mosquitto "$ACL"
    chmod 640 "$ACL"
  fi
  systemctl reload mosquitto

  cat <<EOF
✓ $kullanici eklendi (yalnız $KONU_TABANI/durum/$kimlik yazabilir)

Cihaz ayarları (kiosk/ayarlar.json → tetik):
  "push_kullanici": "$kullanici",
  "push_parola": "$parola"
EOF
}

case "${1:-}" in
  ""|-h|--help) echo "kullanım: $0 <cihazId>|--sil <cihazId>|--liste" >&2; exit 2 ;;
  --liste) listele ;;
  --sil) [[ -n "${2:-}" ]] || { echo "✗ cihaz kimliği gerekli" >&2; exit 2; }; sil "$2" ;;
  *) ekle "$1" ;;
esac
