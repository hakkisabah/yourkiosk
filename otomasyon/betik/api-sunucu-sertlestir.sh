#!/usr/bin/env bash
# Hermes API sunucusunu Open WebUI için hazırla — GÜVENLİK DUVARI KULLANMADAN.
#
# TASARIM KARARI (v2 — v1'deki nftables yaklaşımı TERK EDİLDİ):
#   v1 portu 0.0.0.0'a açıp kaynağı nftables ile sınırlıyordu. Yanlış IP yazılınca erişim
#   tamamen kesildi ve uzaktan teşhis imkânsız hâle geldi (25 Ekim'de yaşandı).
#   v2 güvenlik duvarına HİÇ dokunmaz: portu **docker0 köprü adresine** (172.17.0.1) bağlar.
#   Uç yalnız konteyner ağından görünür, LAN'dan ulaşılamaz → yanlış kural riski yok.
#
# Kullanım:
#   ./api-sunucu-sertlestir.sh --kontrol          # durumu göster, hiçbir şeyi değiştirme
#   ./api-sunucu-sertlestir.sh --kuru             # ne yapacağını göster, değiştirme
#   ./api-sunucu-sertlestir.sh                    # uygula: güçlü anahtar + docker0'a bağla
#   ./api-sunucu-sertlestir.sh --dinle 127.0.0.1  # yalnız yerel (konteyner kullanmıyorsan)
#   ./api-sunucu-sertlestir.sh --anahtar-yenile   # anahtarı değiştir (istemciler 401 alır)
#
# Bu betik gateway'i YENİDEN BAŞLATMAZ (ajan süreci içinden güvenli değil); komutu yazdırır.

set -uo pipefail

HERMES="$(command -v hermes || true)"
[ -n "$HERMES" ] || HERMES="$HOME/.local/bin/hermes"
SIR_DIR="$HOME/.config/hermes-secrets"
ANAHTAR_DOSYA="$SIR_DIR/api-server.key"

PORT=8642
DINLE="172.17.0.1"          # docker0 köprüsü — LAN'dan görünmez
KIP="uygula"
YENILE=0
KURU=0
ANAHTAR=""

kullanim() { sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-2}"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --kontrol) KIP="kontrol"; shift ;;
    --kuru)    KURU=1; shift ;;
    --dinle)   DINLE="${2:?--dinle bir IP ister}"; shift 2 ;;
    --anahtar-yenile) YENILE=1; shift ;;
    -h|--help) kullanim 0 ;;
    *) echo "bilinmeyen argüman: $1" >&2; kullanim 2 ;;
  esac
done

cfg_get() { "$HERMES" config get "$1" 2>/dev/null | tail -1 || true; }
cfg_set() {
  if [ "$KURU" -eq 1 ]; then
    if [ "$1" = "API_SERVER_KEY" ]; then echo "  [KURU] config set API_SERVER_KEY <gizli>"
    else echo "  [KURU] config set $1 $2"; fi
    return 0
  fi
  "$HERMES" config set "$1" "$2" >/dev/null
}

# Dosya içeriği bash yerleşik yönlendirmesiyle okunur: anahtar hiçbir zaman bir komut
# satırında görünmez (süreç listesi / günlük sızıntısı olmasın).
anahtar_oku() { if [ -s "$ANAHTAR_DOSYA" ]; then ANAHTAR="$(<"$ANAHTAR_DOSYA")"; else ANAHTAR=""; fi; }

kod_al() {  # kod_al <url> [anahtar]
  if [ -n "${2:-}" ]; then
    curl -s -m 4 -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $2" "$1" || true
  else
    curl -s -m 4 -o /dev/null -w '%{http_code}' "$1" || true
  fi
}

dinlenen() { ss -tlnH "sport = :$PORT" 2>/dev/null | awk '{print $4}' | head -1; }

# ---------------------------------------------------------------- --kontrol
if [ "$KIP" = "kontrol" ]; then
  sorun=0
  satir() { if [ "$1" = 1 ]; then printf '✓ %-30s %s\n' "$2" "$3"; else printf '✗ %-30s %s\n' "$2" "$3"; sorun=$((sorun+1)); fi; }

  etkin="$(cfg_get API_SERVER_ENABLED)"
  [ "${etkin,,}" = "true" ] && satir 1 "API sunucusu açık" "true" || satir 0 "API sunucusu açık" "${etkin:-ayarsız}"

  anahtar_oku
  [ "${#ANAHTAR}" -ge 32 ] && satir 1 "anahtar ≥ 32 karakter" "${#ANAHTAR}" \
    || satir 0 "anahtar ≥ 32 karakter" "${#ANAHTAR} (16'dan kısa anahtarla Hermes sunucuyu BAŞLATMAZ)"

  host="$(cfg_get API_SERVER_HOST)"; host="${host:-127.0.0.1}"
  case "$host" in
    0.0.0.0) satir 0 "LAN'a kapalı (dinleme adresi)" "$host → tüm ağlara açık" ;;
    *)       satir 1 "LAN'a kapalı (dinleme adresi)" "$host" ;;
  esac

  adres="$(dinlenen)"
  [ -n "$adres" ] && satir 1 "port $PORT dinleniyor" "$adres" || satir 0 "port $PORT dinleniyor" "hayır"

  if [ -n "$adres" ]; then
    kod="$(kod_al "http://$DINLE:$PORT/v1/models" "$ANAHTAR")"
    [ "$kod" = "200" ] && satir 1 "anahtarlı istek" "HTTP 200" || satir 0 "anahtarlı istek" "HTTP $kod"
    kod="$(kod_al "http://$DINLE:$PORT/v1/models")"
    [ "$kod" = "401" ] && satir 1 "anahtarsız istek reddediliyor" "HTTP 401" || satir 0 "anahtarsız istek reddediliyor" "HTTP $kod"
  fi

  if command -v nft >/dev/null 2>&1; then
    nft_cikti="$(nft list table inet hermes_api 2>&1 >/dev/null)"
    if [ -z "$nft_cikti" ]; then
      satir 0 "eski nftables kuralı" "inet hermes_api HÂLÂ VAR → api-sunucu-geri-al.sh"
    elif printf '%s' "$nft_cikti" | grep -qi "no such file\|not found"; then
      satir 1 "eski nftables kuralı" "yok (temiz)"
    else
      printf '· %-30s %s\n' "eski nftables kuralı" "okunamadı (root gerekir): sudo nft list ruleset"
    fi
  fi

  echo
  [ "$sorun" -eq 0 ] && echo "✓ kontrol noktaları temiz" || echo "✗ $sorun kontrol noktası sorunlu"
  exit $([ "$sorun" -eq 0 ] && echo 0 || echo 1)
fi

# ---------------------------------------------------------------- uygula
echo "== 1/3 anahtar =="
mkdir -p "$SIR_DIR"; chmod 700 "$SIR_DIR"
anahtar_oku
if [ "$YENILE" -eq 1 ] || [ "${#ANAHTAR}" -lt 32 ]; then
  if [ "$KURU" -eq 1 ]; then
    echo "  [KURU] 64 karakterlik yeni anahtar üretilecek → $ANAHTAR_DOSYA (+ .env)"
  else
    yeni="$(openssl rand -hex 32)"
    (umask 077; printf '%s\n' "$yeni" > "$ANAHTAR_DOSYA"); chmod 600 "$ANAHTAR_DOSYA"
    cfg_set API_SERVER_KEY "$yeni"
    ANAHTAR="$yeni"
    echo "  yeni anahtar üretildi → $ANAHTAR_DOSYA (0600) ve .env"
  fi
else
  echo "  mevcut anahtar yeterli (${#ANAHTAR} karakter) — korunuyor"
fi

echo "== 2/3 dinleme adresi =="
cfg_set API_SERVER_ENABLED true
cfg_set API_SERVER_HOST "$DINLE"
cfg_set API_SERVER_PORT "$PORT"
echo "  ENABLED=true · HOST=$DINLE · PORT=$PORT"
case "$DINLE" in
  172.17.0.1|172.18.0.1) echo "  → yalnız Docker köprüsünden erişilebilir; LAN'dan görünmez, güvenlik duvarı gerekmez." ;;
  127.0.0.1)             echo "  → yalnız bu makineden (konteynerden erişilemez)." ;;
  0.0.0.0)               echo "  ⚠ 0.0.0.0 = tüm ağlara açık. Bu uç terminal yetkili ajandır; konteyner için 172.17.0.1 kullanın." ;;
  *)                     echo "  → yalnız $DINLE adresinden erişilebilir." ;;
esac

echo "== 3/3 doğrulama =="
if [ "$KURU" -eq 1 ]; then
  echo "  [KURU] atlandı"
else
  adres="$(dinlenen)"
  if [ -z "$adres" ]; then
    echo "  port henüz dinlenmiyor — ayar yeni yazıldı; gateway yeniden başlatılmalı (aşağıdaki 1. adım)."
  elif [ "$adres" != "$DINLE:$PORT" ]; then
    echo "  ⚠ dinlenen adres $adres — beklenen $DINLE:$PORT (yeniden başlatmadan sonra düzelir)"
  else
    echo "  anahtarlı : HTTP $(kod_al "http://$DINLE:$PORT/v1/models" "$ANAHTAR")   (200 beklenir)"
    echo "  anahtarsız: HTTP $(kod_al "http://$DINLE:$PORT/v1/models")   (401 beklenir)"
  fi
fi

GW="hermes gateway"
KENDI="$(printf '%s' "$0")"
cat <<NOT

──── sonraki adım ────
1) Ayarın etkinleşmesi için AYRI bir kabukta:
     $GW restart

2) Open WebUI'yi konteynerde çalıştır (köprüden 172.17.0.1'e erişir) — tek satır:
     docker run -d --name open-webui --restart unless-stopped -p 3000:8080 -v open-webui:/app/backend/data -e ENABLE_SIGNUP=false ghcr.io/open-webui/open-webui:main

3) Open WebUI → Ayarlar → Bağlantılar → OpenAI API:
     Base URL : http://172.17.0.1:$PORT/v1
     API Key  : dosyadan oku →  less $ANAHTAR_DOSYA

4) Kontrol:
     $KENDI --kontrol
NOT
