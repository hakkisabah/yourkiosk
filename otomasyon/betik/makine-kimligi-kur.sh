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
# SUDO GEREKTİRMEYEN YOL (27 Ekim — asıl kullanılan):
#   bash makine-kimligi-kur.sh --kaydet i5        # bu makinenin eşleme satırını YAZDIRIR
#   bash makine-kimligi-kur.sh --kaydet i5 --yaz  # depodaki eşlemeye ekler (PR ile birleşir)
#   Neden: i5'te sudo parolası yok → `/etc/yourkiosk-makine-kimligi` hiç kurulamadı → karar kapısı
#   13 kez reddetti ve inceleme kuyruğu 39 saat kilitlendi. `/etc/machine-id` root sahipli ve
#   makineye özgüdür; rol eşlemesi depoda (`otomasyon/makine-kimlikleri.json`) tutulur. Ajan bu
#   dosyayı ancak PR ile değiştirebilir (yaz.py dosyanın git'te TEMİZ olmasını şart koşar).
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
          bash ./makine-kimligi-kur.sh --kaydet <i5|i3> [--yaz]   (sudo GEREKMEZ)
METIN
}

if [ "$#" -lt 1 ]; then kullanim; exit 2; fi
KIP="kur"; ROL=""; YOL="$VARSAYILAN_YOL"; KAYDET_YAZ=0
case "$1" in
  --kontrol) KIP="kontrol" ;;
  --kaydet)  KIP="kaydet"; shift
             case "${1:-}" in
               i5|i3) ROL="$1"; shift ;;
               *) echo "✗ --kaydet için rol gerekli (beklenen: $ROLE_IZINLI)" >&2; kullanim; exit 2 ;;
             esac
             case "${1:-}" in
               --yaz) KAYDET_YAZ=1 ;;
               "")    ;;
               *)     echo "✗ bilinmeyen seçenek: '$1'" >&2; kullanim; exit 2 ;;
             esac
             set -- ;;
  i5|i3)     ROL="$1" ;;
  *)         echo "✗ geçersiz rol: '$1' (beklenen: $ROLE_IZINLI)" >&2; kullanim; exit 2 ;;
esac
if [ "$KIP" != "kaydet" ] && [ "$#" -ge 2 ]; then YOL="$2"; fi

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

# ── --kaydet: SUDO YOK ────────────────────────────────────────────────────────────────────────
# `/etc/machine-id` root sahipli ve makineye özgüdür; ajan yazamaz. Rol eşlemesi depoda tutulur.
kaydet() {
  local rol="$1" yaz="$2" mid host kok hedef
  # Bu yol ROOT GEREKTİRMEZ ve root olarak ÇALIŞMAZ: root ayrıcalığıyla yalnız `denetle`/yazım
  # yolu (dosya kurulumu) çalışır. Böylece "root sahipli betik depo kodu çalıştırmaz" kuralı korunur.
  if [ "$(id -u)" -eq 0 ]; then
    echo "✗ --kaydet root olarak çalıştırılmaz (sudo'suz, kullanıcı olarak çalıştırın)" >&2
    return 3
  fi
  if [ -L /etc/machine-id ] || [ ! -f /etc/machine-id ]; then
    echo "✗ /etc/machine-id normal dosya değil — kimlik kurulamaz" >&2; return 4
  fi
  case "$(stat -c '%u' /etc/machine-id)" in 0) ;; *)
    echo "✗ /etc/machine-id root sahipli değil — kimlik kurulamaz" >&2; return 4 ;;
  esac
  mid="$(tr -d '[:space:]' < /etc/machine-id | tr 'A-F' 'a-f')"
  case "$mid" in
    ""|*[!0-9a-f]*) echo "✗ /etc/machine-id biçimi beklenmedik: '$mid'" >&2; return 4 ;;
  esac
  host="$(cat /etc/hostname 2>/dev/null || hostname 2>/dev/null || echo '?')"
  # HAM machine-id DEPOYA YAZILMAZ (depo herkese açık; machine-id kalıcı cihaz tanımlayıcısıdır).
  # Depoda yalnız ayrımlı sha256 özeti tutulur (yaz.py KIMLIK_OZET_AYRACI ile AYNI olmalı).
  ozet="$(printf '%s%s' 'yourkiosk-makine-kimligi-v1|' "$mid" | sha256sum | cut -d' ' -f1)"
  echo "  rol         : $rol"
  echo "  machine-id  : $mid (yalnız YERELDE gösterilir, depoya yazılmaz)"
  echo "  kimlik_ozet : $ozet"
  echo "  hostname    : $host"
  echo "  eşleme satırı (otomasyon/makine-kimlikleri.json):"
  printf '    "%s": {"hostname": "%s", "kimlik_ozet": "%s"}\n' "$rol" "$host" "$ozet"

  if [ "$yaz" != "1" ]; then
    echo
    echo "  Yazmak için: $0 --kaydet $rol --yaz   (depo içinde çalıştırın; değişiklik PR ister)"
    return 0
  fi

  kok="$(git -C "$(dirname "$0")/../.." rev-parse --show-toplevel 2>/dev/null || true)"
  [ -n "$kok" ] || { echo "✗ depo bulunamadı — --yaz yalnız depo içinde çalışır" >&2; return 4; }
  hedef="$kok/otomasyon/makine-kimlikleri.json"
  python3 - "$hedef" "$rol" "$host" "$ozet" <<'PYEOF'
import json, os, sys, tempfile
hedef, rol, host, ozet = sys.argv[1:5]
veri = {}
if os.path.exists(hedef):
    with open(hedef, encoding="utf-8") as f:
        veri = json.load(f) or {}
if not isinstance(veri, dict):
    sys.exit("var olan eşleme sözlük değil")
veri[rol] = {"hostname": host, "kimlik_ozet": ozet}
dizin = os.path.dirname(hedef)
fd, gecici = tempfile.mkstemp(dir=dizin, prefix=".makine-kimlikleri.")
with os.fdopen(fd, "w", encoding="utf-8") as f:
    json.dump(veri, f, ensure_ascii=False, indent=2, sort_keys=True)
    f.write("\n")
os.replace(gecici, hedef)
PYEOF
  rc=$?
  [ "$rc" -eq 0 ] || { echo "✗ eşleme yazılamadı" >&2; return 4; }
  echo "✓ yazıldı: $hedef — şimdi commit + PR (ajan kendi rolünü doğrudan yazamaz)"
  return 0
}

if [ "$KIP" = "kaydet" ]; then
  kaydet "$ROL" "$KAYDET_YAZ"
  exit $?
fi

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
