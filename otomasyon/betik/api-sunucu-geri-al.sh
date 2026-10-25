#!/usr/bin/env bash
# API sunucusu değişikliklerini ve nftables kuralını GERİ AL (i5 / aceri5 / i3).
#
# Ne yapar (sırayla):
#   1. `inet hermes_api` nftables tablosunu siler (varsa) — port 8642 üzerindeki drop kalkar,
#   2. `/etc/nftables.d/60-hermes-api.nft` dosyasını siler (kalıcı kural dosyası),
#   3. yalnızca BİZİM açtığımız nftables servisini kapatır (kapatmadan önce sorar),
#   4. `API_SERVER_HOST`'u geri alır (varsayılan: 127.0.0.1 — yalnız yerel),
#   5. son durumu yazdırır.
#
# Kullanım:
#   ./otomasyon/betik/api-sunucu-geri-al.sh --kontrol     # hiçbir şeyi değiştirme, durumu göster
#   ./otomasyon/betik/api-sunucu-geri-al.sh               # geri al (sudo parolası ister)
#   ./otomasyon/betik/api-sunucu-geri-al.sh --dinle 172.17.0.1   # geri al + docker köprüsüne bağla
#
# NEDEN: nftables kuralı yanlış kaynak IP ile uygulandığında erişim tamamen kesilebiliyor ve
# uzaktan teşhis imkânsız hâle geliyor. Docker köprüsü (172.17.0.1) yöntemi güvenlik duvarı
# gerektirmez: port yalnız konteyner ağından görünür, LAN'dan görünmez.

set -uo pipefail

HERMES="$(command -v hermes || true)"
[ -n "$HERMES" ] || HERMES="$HOME/.local/bin/hermes"
TABLO="inet hermes_api"
KURAL_DOSYA="/etc/nftables.d/60-hermes-api.nft"
KIP="geri-al"
DINLE="127.0.0.1"

while [ $# -gt 0 ]; do
  case "$1" in
    --kontrol) KIP="kontrol"; shift ;;
    --dinle)   DINLE="${2:?--dinle IP ister}"; shift 2 ;;
    -h|--help) sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "bilinmeyen argüman: $1" >&2; exit 2 ;;
  esac
done

# sudo: yalnız gerektiğinde ve kullanıcıdan parola isteyerek
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  if command -v sudo >/dev/null 2>&1; then SUDO="sudo"; else
    echo "✗ root değilsiniz ve sudo yok — bu betiği root olarak çalıştırın." >&2; exit 2
  fi
fi

tablo_var() { $SUDO nft list table $TABLO >/dev/null 2>&1; }

durum() {
  echo "──── durum ────"
  printf 'nftables servisi : %s / %s\n' "$(systemctl is-enabled nftables 2>&1)" "$(systemctl is-active nftables 2>&1)"
  if tablo_var; then echo "hermes_api tablosu: VAR (port 8642 kaynak IP ile sınırlı)"; else echo "hermes_api tablosu: yok"; fi
  printf 'kural dosyası    : %s\n' "$([ -e "$KURAL_DOSYA" ] && echo "VAR: $KURAL_DOSYA" || echo "yok")"
  printf 'API_SERVER_HOST  : %s\n' "$("$HERMES" config get API_SERVER_HOST 2>/dev/null | tail -1 || echo '(ayarsız → 127.0.0.1)')"
  printf 'API_SERVER_ENABLED: %s\n' "$("$HERMES" config get API_SERVER_ENABLED 2>/dev/null | tail -1 || echo '(ayarsız)')"
  printf '8642 dinleyen    : %s\n' "$(ss -tlnH 'sport = :8642' 2>/dev/null | awk '{print $4}' | paste -sd' ' - || true)"
  echo "──── /etc/nftables.conf (varsa, ilk 20 satır) ────"
  $SUDO sh -c 'head -20 /etc/nftables.conf 2>/dev/null' || true
}

if [ "$KIP" = "kontrol" ]; then
  durum
  exit 0
fi

echo "== 1/5 hermes_api tablosu =="
if tablo_var; then
  $SUDO nft delete table $TABLO && echo "  silindi: $TABLO"
else
  echo "  zaten yok (kural yüklü değil)"
fi

echo "== 2/5 kalıcı kural dosyası =="
if [ -e "$KURAL_DOSYA" ]; then
  $SUDO rm -f "$KURAL_DOSYA" && echo "  silindi: $KURAL_DOSYA"
else
  echo "  zaten yok"
fi
# boş kalmışsa dizini de kaldır
$SUDO rmdir /etc/nftables.d 2>/dev/null || true

echo "== 3/5 nftables servisi =="
# 08 Ekim'de kurulmuş, bizden önce kapalıydı → biz açtıysak kapatıyoruz.
etkin="$(systemctl is-enabled nftables 2>&1)"
aktif="$(systemctl is-active nftables 2>&1)"
if [ "$aktif" = "active" ] || [ "$etkin" = "enabled" ]; then
  echo "  DİKKAT: nftables şu an $etkin / $aktif."
  echo "  Bu servis açılışta /etc/nftables.conf dosyasını yükler ve o dosya varsayılan RED içerebilir."
  echo "  Kapatmak için:  sudo systemctl disable --now nftables"
  echo "  (Bu betik kendiliğinden KAPATMAZ: başka bir amaçla açılmış olabilir. Gerekmiyorsa yukarıdaki komutu çalıştırın.)"
else
  echo "  kapalı (değişiklik gerekmedi)"
fi

echo "== 4/5 API_SERVER_HOST =="
"$HERMES" config set API_SERVER_HOST "$DINLE" >/dev/null 2>&1 \
  && echo "  API_SERVER_HOST=$DINLE" \
  || echo "  ✗ ayarlanamadı (elle: hermes config set API_SERVER_HOST $DINLE)"

echo "== 5/5 son durum =="
durum

NOT2="hermes gateway"
cat <<NOT

──── sonraki adım ────
Ayar değişikliği gateway yeniden başlayınca etkin olur. Bu betik gateway'e DOKUNMAZ
(ajan süreci içinden yeniden başlatma güvenli değil). Ayrı bir kabukta:

  $NOT2 restart

Sonra doğrula:

  ss -tlnH 'sport = :8642'                          # beklenen: 127.0.0.1:8642 (ya da 172.17.0.1:8642)
  sudo nft list ruleset | head -20                  # beklenen: hermes_api tablosu YOK
NOT
