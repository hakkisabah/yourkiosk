#!/usr/bin/env bash
# MAKİNE KİMLİĞİNİ KUR — yalnız OPERATÖR (root) çalıştırır; ajan çalıştıramaz.
#
# Neden: kapı akışında hangi makinenin `i5` (güvenlik incelemesi) hangisinin `i3` (karar/birleştirme)
# olduğu, `yaz.py` tarafından ROOT sahipli bir dosyadan okunur. Karar JSON'undaki `makine` alanı
# ajanın kendi beyanıdır ve tek başına iki zorunlu kontrolü açabiliyordu (AGENTS.md §3.3).
# Dosya root sahipli olduğu için ajan onu yazamaz → rolü kendisi seçemez.
#
#   sudo ./makine-kimligi-kur.sh i5          # bu makine i5
#   sudo ./makine-kimligi-kur.sh i3          # bu makine i3
#   sudo ./makine-kimligi-kur.sh --kontrol   # yalnız denetle (hiçbir şey yazmaz)
#
# Çıkış: 0 kuruldu/uygun · 2 kullanım hatası · 3 root değil · 4 doğrulama/GÜVEN reddi
#
# GÜVEN MODELİ (26 Ekim i5 bulgusu): bu betik ROOT olarak DEPO KODU ÇALIŞTIRMAZ. Önceki sürüm
# `python3 - yaz.py` ile çalışma ağacındaki yaz.py'yi import ediyordu; yani ajanın yazabildiği bir
# dosya root ayrıcalığıyla çalışıyordu ve kimlik mekanizmasının dayandığı ayrıcalık sınırı o adımda
# çöküyordu. Kural artık BETİĞİN İÇİNDE ve betik kendi güvenilirliğini de denetler: betiğin kendisi
# root sahipli değilse ya da grup/dünya-yazılabilirse "GÜVENİLMEYEN AĞAÇ" diyerek durur — root
# sahipli kopyaya alma komutu hata metninde yazılıdır.
set -euo pipefail

#: `yaz.py` içindeki MAKINE_AYARI ile AYNI olmalı — test_makine_kimligi_kur.py karşılaştırır.
ROLE_IZINLI="i5 i3"
VARSAYILAN_YOL="/etc/yourkiosk-makine-kimligi"

kullanim() {
  cat >&2 <<'METIN'
kullanım: sudo ./makine-kimligi-kur.sh <i5|i3> [yol]
          sudo ./makine-kimligi-kur.sh --kontrol [yol]
METIN
}

if [ "$#" -lt 1 ]; then kullanim; exit 2; fi
KIP="kur"; ROL=""; YOL="$VARSAYILAN_YOL"
case "$1" in
  --kontrol) KIP="kontrol" ;;
  i5|i3)     ROL="$1" ;;
  *)         echo "✗ geçersiz rol: '$1' (beklenen: $ROLE_IZINLI)" >&2; kullanim; exit 2 ;;
esac
[ "$#" -ge 2 ] && YOL="$2"

root_mu() { [ "$(id -u)" -eq 0 ]; }

# ── kendi güvenilirliğim ────────────────────────────────────────────────────────────────────
agac_guvenilir() {
  local kendi sahip mod
  kendi="$(readlink -f "${BASH_SOURCE[0]}")"
  sahip="$(stat -c '%u' "$kendi")"
  mod="$(stat -c '%a' "$kendi")"
  if [ "$sahip" != "0" ] || [ $(( 0$mod & 022 )) -ne 0 ]; then
    {
      echo "✗ GÜVENİLMEYEN AĞAÇ: betik root sahipli değil ya da grup/dünya-yazılabilir"
      echo "  betik: $kendi · uid $sahip · mod $mod"
      echo "  Ajan bu dosyayı değiştirebildiği için root olarak çalıştırılmaz."
      echo "  Önce root sahipli kopyaya alın, sonra KOPYAYI çalıştırın:"
      echo "    sudo install -o root -g root -m 0755 \"$kendi\" /usr/local/lib/yourkiosk/makine-kimligi-kur.sh"
      echo "    sudo /usr/local/lib/yourkiosk/makine-kimligi-kur.sh ${ROL:-i5}"
    } >&2
    return 4
  fi
  return 0
}

# ── kimlik kuralı (betiğin içinde; depo kodu çalıştırılmaz) ─────────────────────────────────
denetle() {
  local sahip mod dsahip dmod icerik
  if [ -L "$YOL" ]; then echo "✗ kimlik sembolik bağ ($YOL) — normal dosya olmalı" >&2; return 4; fi
  if [ ! -e "$YOL" ]; then echo "  dosya yok: $YOL" >&2; return 4; fi
  if [ ! -f "$YOL" ]; then echo "✗ kimlik normal dosya değil ($YOL)" >&2; return 4; fi
  ls -l "$YOL" >&2 || true
  sahip="$(stat -c '%u' "$YOL")"; mod="$(stat -c '%a' "$YOL")"
  if [ "$sahip" != "0" ]; then
    echo "✗ kimlik root sahipli değil (uid $sahip, yol $YOL) — yalnız operatör kurabilir" >&2
    return 4
  fi
  if [ $(( 0$mod & 022 )) -ne 0 ]; then
    echo "✗ kimlik grup/dünya-yazılabilir (mod $mod, yol $YOL)" >&2
    return 4
  fi
  dsahip="$(stat -c '%u' "$(dirname "$YOL")")"; dmod="$(stat -c '%a' "$(dirname "$YOL")")"
  if [ "$dsahip" != "0" ] || [ $(( 0$dmod & 022 )) -ne 0 ]; then
    echo "✗ kimlik dizini güvenli değil (uid $dsahip, mod $dmod, dizin $(dirname "$YOL"))" >&2
    return 4
  fi
  icerik="$(tr -d '\r\n' <"$YOL")"
  case "$icerik" in
    i5|i3) ;;
    *) echo "✗ kimlik içeriği geçersiz: '$icerik' (beklenen: $ROLE_IZINLI)" >&2; return 4 ;;
  esac
  echo "  içerik: $icerik" >&2
  echo "✓ kimlik geçerli: $icerik ($YOL)"
  return 0
}

if [ "$KIP" = "kontrol" ]; then
  # --kontrol SALT OKUR ve ayrıcalık kullanmaz: betiğin hangi ağaçtan çağrıldığı önemli değil.
  denetle
  exit $?
fi

root_mu || { echo "✗ root gerekli (sudo ile çalıştırın). Ajan bu dosyayı yazamaz." >&2; exit 3; }

# YAZMA yolu root ayrıcalığı kullanır → bu yolda ağaç güvenilirliği ZORUNLU (fail-closed).
agac_guvenilir || exit 4

# Atomik yazım: aynı dizinde geçici dosya + mv (yarım kalan dosya kimliği bozmasın).
GECICI="$(mktemp "$(dirname "$YOL")/.kimlik.XXXXXX")"
trap 'rm -f "$GECICI"' EXIT
printf '%s\n' "$ROL" >"$GECICI"
chown root:root "$GECICI"
chmod 0644 "$GECICI"
mv -f "$GECICI" "$YOL"
trap - EXIT

echo "✓ yazıldı: $YOL → $ROL" >&2
denetle
