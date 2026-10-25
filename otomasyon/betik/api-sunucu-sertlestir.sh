#!/usr/bin/env bash
# API sunucusunu LAN'a açar AMA kaynak IP ile sınırlar (i5 / i3 makinelerinde çalıştırılır).
#
# NEDEN: `hermes` API sunucusu (varsayılan 127.0.0.1:8642) OpenAI uyumlu bir uçtur ve gelen isteği
# **terminal yetkili bir ajan** olarak çalıştırır. Yani anahtarı bilen kişi o makinede kabuk
# komutu çalıştırabilir. Open WebUI başka bir bilgisayardan bağlanacağı için portu LAN'a açmak
# gerekiyor — ama "0.0.0.0 + zayıf anahtar" kabul edilemez. Bu betik üç şeyi birlikte yapar:
#
#   1. Güçlü anahtar (32 bayt rastgele) üretir/yeniler, `~/.config/hermes-secrets/api-server.key`
#      dosyasına 0600 yazar ve `hermes config set API_SERVER_KEY` ile .env'e işler,
#   2. `API_SERVER_HOST=0.0.0.0` + `API_SERVER_PORT` ayarlarını yazar (LAN'dan erişilebilsin),
#   3. Yalnızca `--kaynak-ip` ile verilen adreslerin portuna izin veren nftables kuralı üretir.
#      (Kuralı uygulamak sudo ister; betik komutu yazdırır, kendisi sudo çalıştırmaz.)
#
# Kullanım:
#   ./otomasyon/betik/api-sunucu-sertlestir.sh --kontrol
#   ./otomasyon/betik/api-sunucu-sertlestir.sh --kaynak-ip 192.168.1.30
#   ./otomasyon/betik/api-sunucu-sertlestir.sh --kaynak-ip 192.168.1.30 --kaynak-ip 192.168.1.31 \
#                                             --anahtar-yenile
#   ./otomasyon/betik/api-sunucu-sertlestir.sh --kaynak-ip 192.168.1.0/24 --port 8642
#
# Notlar:
#   * Open WebUI **aynı makinede Docker ile** çalışıyorsa kaynak IP köprü adresidir → `--kaynak-ip 172.17.0.1`.
#   * Anahtarı asla sohbete/commit'e yazma: `cat ~/.config/hermes-secrets/api-server.key`
#   * Bu betik yalnız kendi makinesini yapılandırır; başka makineye SSH ile dokunmaz.

set -euo pipefail

HERMES="$(command -v hermes || true)"
[ -n "$HERMES" ] || HERMES="$HOME/.local/bin/hermes"
SIR_DIR="$HOME/.config/hermes-secrets"
ANAHTAR_DOSYA="$SIR_DIR/api-server.key"
DURUM_DIR="$HOME/.local/state/yourkiosk-otomasyon"
NFT_DOSYA="$DURUM_DIR/api-sunucu.nft"

PORT=8642
DINLE="0.0.0.0"
KAYNAKLAR=()
KIP="uygula"
YENILE=0
KURU=0

kullanim() {
  sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-2}"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --kaynak-ip)   KAYNAKLAR+=("${2:?--kaynak-ip bir IP/CIDR ister}"); shift 2 ;;
    --port)        PORT="${2:?--port değer ister}"; shift 2 ;;
    --dinle)       DINLE="${2:?--dinle değer ister}"; shift 2 ;;
    --anahtar-yenile) YENILE=1; shift ;;
    --kontrol)     KIP="kontrol"; shift ;;
    --kuru)        KURU=1; shift ;;
    -h|--help)     kullanim 0 ;;
    *) echo "bilinmeyen argüman: $1" >&2; kullanim 2 ;;
  esac
done

cfg_get() { "$HERMES" config get "$1" 2>/dev/null | tail -1 || true; }
cfg_set() {
  if [ "$KURU" -eq 1 ]; then
    case "$1" in *KEY*|*PAROLA*|*TOKEN*) echo "  [KURU] hermes config set $1 <gizli>";; esac
    [ "$1" = "API_SERVER_KEY" ] || echo "  [KURU] hermes config set $1 $2"
    return 0
  fi
  "$HERMES" config set "$1" "$2" >/dev/null
}

anahtar_uzunluk() {
  local deger
  deger="$(cfg_get API_SERVER_KEY)"
  printf '%s' "${#deger}"
}

# ------------------------------------------------------------------ kontrol (hiçbir şeyi değiştirmez)
if [ "$KIP" = "kontrol" ]; then
  sorun=0
  satir() { [ "$1" = 1 ] && printf '✓ %-28s %s\n' "$2" "$3" || { printf '✗ %-28s %s\n' "$2" "$3"; sorun=$((sorun+1)); }; }

  etkin="$(cfg_get API_SERVER_ENABLED)"
  satir "$([ "${etkin,,}" = "true" ] && echo 1 || echo 0)" "API sunucusu açık" "${etkin:-ayarsız}"

  uzunluk="$(anahtar_uzunluk)"
  satir "$([ "${uzunluk:-0}" -ge 32 ] && echo 1 || echo 0)" "anahtar uzunluğu ≥ 32" "${uzunluk} karakter"

  dinle="$(cfg_get API_SERVER_HOST)"
  satir 1 "dinlenen adres" "${dinle:-127.0.0.1 (varsayılan)}"

  if command -v nft >/dev/null 2>&1; then
    if sudo -n nft list table inet hermes_api >/dev/null 2>&1 || nft list table inet hermes_api >/dev/null 2>&1; then
      satir 1 "nftables kuralı" "inet hermes_api var"
    else
      satir 0 "nftables kuralı" "YOK → LAN'a açık, kaynak IP sınırı yok"
    fi
  else
    satir 0 "nftables" "kurulu değil (ufw/iptables ile elle sınırla)"
  fi

  if command -v ss >/dev/null 2>&1; then
    adres="$(ss -tlnH "sport = :$PORT" 2>/dev/null | awk '{print $4}' | head -1)"
    satir "$([ -n "$adres" ] && echo 1 || echo 0)" "port $PORT dinleniyor" "${adres:-hayır}"
  fi

  [ -s "$ANAHTAR_DOSYA" ] && satir 1 "anahtar dosyası" "$ANAHTAR_DOSYA" || \
    satir 0 "anahtar dosyası" "yok: $ANAHTAR_DOSYA (--anahtar-yenile ile üret)"

  echo
  [ "$sorun" -eq 0 ] && echo "✓ kontrol noktaları temiz" || echo "✗ $sorun kontrol noktası sorunlu"
  exit "$([ "$sorun" -eq 0 ] && echo 0 || echo 1)"
fi

# ------------------------------------------------------------------ uygula
if [ "${#KAYNAKLAR[@]}" -eq 0 ]; then
  echo "✗ en az bir --kaynak-ip gerekli (kaynak IP sınırı olmadan LAN'a açmak yasak)." >&2
  echo "  Örnek: $0 --kaynak-ip 192.168.1.30" >&2
  exit 2
fi

echo "== 1/4 anahtar =="
mkdir -p "$SIR_DIR"; chmod 700 "$SIR_DIR"
uzunluk="$(anahtar_uzunluk)"
if [ "$YENILE" -eq 1 ] || [ "${uzunluk:-0}" -lt 32 ]; then
  yeni="$(openssl rand -hex 32)"
  if [ "$KURU" -eq 1 ]; then
    echo "  [KURU] yeni anahtar üretilecek (64 karakter) → $ANAHTAR_DOSYA ve .env"
  else
    (umask 077; printf '%s\n' "$yeni" > "$ANAHTAR_DOSYA"); chmod 600 "$ANAHTAR_DOSYA"
    cfg_set API_SERVER_KEY "$yeni"
    echo "  yeni anahtar üretildi (64 karakter) → $ANAHTAR_DOSYA ve .env"
    echo "  ⚠ eski anahtarla bağlı istemciler (Open WebUI) 401 alacak; yeni anahtarı gir."
  fi
else
  echo "  mevcut anahtar yeterli (${uzunluk} karakter) — korunuyor (yenilemek için --anahtar-yenile)"
  if [ ! -s "$ANAHTAR_DOSYA" ] && [ "$KURU" -eq 0 ]; then
    (umask 077; cfg_get API_SERVER_KEY > "$ANAHTAR_DOSYA"); chmod 600 "$ANAHTAR_DOSYA"
    echo "  anahtar .env'den dosyaya kopyalandı: $ANAHTAR_DOSYA"
  fi
fi

echo "== 2/4 dinleme adresi =="
cfg_set API_SERVER_ENABLED true
cfg_set API_SERVER_HOST "$DINLE"
cfg_set API_SERVER_PORT "$PORT"
echo "  API_SERVER_ENABLED=true · API_SERVER_HOST=$DINLE · API_SERVER_PORT=$PORT"

echo "== 3/4 erişim kuralı (nftables) =="
mkdir -p "$DURUM_DIR"
{
  echo "table inet hermes_api {"
  printf '  set izinli { type ipv4_addr; flags interval; elements = { %s } }\n' "$(IFS=,; echo "${KAYNAKLAR[*]}")"
  echo "  chain giris {"
  echo "    type filter hook input priority -10; policy accept;"
  echo "    ct state established,related accept"
  echo "    iif lo accept"
  echo "    tcp dport $PORT ip saddr @izinli accept"
  echo "    tcp dport $PORT counter drop"
  echo "  }"
  echo "}"
} > "$NFT_DOSYA"
echo "  kural dosyası: $NFT_DOSYA"
echo "  izinli kaynaklar: ${KAYNAKLAR[*]}"
echo
echo "  UYGULAMAK İÇİN (sudo parolası ister, bu yüzden betik kendisi çalıştırmıyor):"
echo "    sudo nft -f \"$NFT_DOSYA\""
echo "    # kalıcı olsun (açılışta da yüklensin):"
echo "    sudo install -D -m644 \"$NFT_DOSYA\" /etc/nftables.d/60-hermes-api.nft"
echo "    sudo systemctl enable --now nftables     # nftables servisi yoksa: sudo pacman -S nftables"
echo
echo "  nftables yerine ufw kullanıyorsan:"
for ip in "${KAYNAKLAR[@]}"; do echo "    sudo ufw allow from $ip to any port $PORT proto tcp"; done
echo "    sudo ufw deny $PORT/tcp"

echo "== 4/4 servisi yeniden başlat =="
if [ "$KURU" -eq 1 ]; then
  echo "  [KURU] hermes gateway restart (atlandı)"
else
  if "$HERMES" gateway restart >/dev/null 2>&1; then
    echo "  hermes gateway restart ✓"
  else
    systemctl --user restart hermes-gateway && echo "  systemctl --user restart hermes-gateway ✓"
  fi
  sleep 3
fi

echo
echo "== doğrulama =="
if [ "$KURU" -eq 0 ]; then
if command -v ss >/dev/null 2>&1; then
  ss -tlnH "sport = :$PORT" 2>/dev/null | awk '{printf "  dinliyor: %s\n", $4}'
fi
kod="$(curl -s -m 3 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/v1/models" || true)"
echo "  anahtarsız istek → HTTP $kod (401 beklenir)"
kod="$(curl -s -m 3 -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $(cat "$ANAHTAR_DOSYA")" \
       "http://127.0.0.1:$PORT/v1/models" || true)"
echo "  anahtarlı istek   → HTTP $kod (200 beklenir)"
else
  echo "  [KURU] doğrulama atlandı (servis yeniden başlatılmadı)"
fi

IPLER="$(ip -4 -o addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | paste -sd' ' -)"
echo
echo "== Open WebUI ayarı =="
echo "  Base URL : http://<bu-makinenin-LAN-IP>:${PORT}/v1     (bu makine: ${IPLER:-?})"
echo "  API Key  : cat $ANAHTAR_DOSYA"
echo
echo "== başka makineden sına (izinli olmayan bir makinede) =="
echo "  curl -m 3 -o /dev/null -w '%{http_code}\\n' http://<bu-makine>:${PORT}/v1/models   # 000/timeout beklenir"
