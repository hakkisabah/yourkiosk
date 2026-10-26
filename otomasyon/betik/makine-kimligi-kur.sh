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
# Çıkış: 0 kuruldu/uygun · 2 kullanım hatası · 3 root değil · 4 doğrulama başarısız
set -euo pipefail

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
if [ "$KIP" = "kontrol" ]; then
  [ "$#" -ge 2 ] && YOL="$2"
else
  [ "$#" -ge 2 ] && YOL="$2"
fi

root_mu() { [ "$(id -u)" -eq 0 ]; }

denetle() {
  # Kural TEK yerde: yaz.py. Betik kendi kopyasını yazmaz (denetim ile yazım ayrışmasın).
  local yaz_py
  yaz_py="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/yaz.py"
  [ -f "$yaz_py" ] || { echo "✗ yaz.py bulunamadı: $yaz_py" >&2; return 4; }
  if [ -f "$YOL" ]; then
    ls -l "$YOL"
    echo "  içerik: $(tr -d '\n' <"$YOL")"
  else
    echo "  dosya yok: $YOL"
  fi
  python3 - "$yaz_py" "$YOL" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("yourkiosk_yaz", sys.argv[1])
modul = importlib.util.module_from_spec(spec)
spec.loader.exec_module(modul)
kimlik, neden = modul.makine_kimligi_denetle(sys.argv[2])
if not kimlik:
    print(f"✗ kimlik geçersiz: {neden}")
    sys.exit(4)
print(f"✓ kimlik geçerli: {kimlik} ({sys.argv[2]})")
PY
}

if [ "$KIP" = "kontrol" ]; then
  denetle
  exit $?
fi

root_mu || { echo "✗ root gerekli (sudo ile çalıştırın). Ajan bu dosyayı yazamaz." >&2; exit 3; }

# Atomik yazım: aynı dizinde geçici dosya + mv (yarım kalan dosya kimliği bozmasın).
GECICI="$(mktemp "$(dirname "$YOL")/.kimlik.XXXXXX")"
trap 'rm -f "$GECICI"' EXIT
printf '%s\n' "$ROL" >"$GECICI"
chown root:root "$GECICI"
chmod 0644 "$GECICI"
mv -f "$GECICI" "$YOL"
trap - EXIT

echo "✓ yazıldı: $YOL → $ROL"
denetle
