#!/usr/bin/env bash
# agir-komut.sh — BELLEK TAVANLI ağır komut koşucusu.
#
# NEDEN (26 Ekim, casperi5 günlüğü): `yourkiosk-nobetci` biriminin cgroup'unda `node-MainThread`
# V8 `FatalProcessOutOfMemory` ile core dump aldı (`Heap::CollectGarbage` → abort). Bu makinelerde
# ~3,8 GB RAM var; V8 kendi tavanını makine RAM'inden bağımsız kurar (Hermes TUI 8 GB ister, Node
# varsayılanı ~2 GB) → tavan makinenin taşıyamayacağı yere ayarlanır, takas dolar, süreç abort eder
# ve makine kullanılamaz hâle gelir. Kabahatlisi tek tek komutlar değil, **tavansız** koşmaları:
# aynı anda iki `npm test` + `vue-tsc` + sohbet gateway'i 4 GB'a sığmaz.
#
# Ne yapar:
#   1. Boş RAM'i ölçer, eşiğin altındaysa komutu REDDEDER (makineyi kilitlemektense erken dur),
#   2. Node çocuklarına ÖLÇÜLÜ `--max-old-space-size` verir (V8 tavanı = tavanın %60'ı),
#   3. Komutu cgroup bellek tavanı içinde koşar (`systemd-run --user --scope -p MemoryMax`),
#      böylece taşma olursa OOM yalnız bu komutu öldürür, oturumu/makineyi değil,
#   4. `flock` ile ağır işleri SIRAYA sokar (iki derleme aynı anda = 4 GB'ta kesin OOM),
#   5. Duvar saati tavanı (`timeout`) ve tek satır günlük (`~/.local/state/yourkiosk-otomasyon/agir-komut.log`).
#
# Kullanım:
#   ./otomasyon/betik/agir-komut.sh --kuru -- npm test                    # planı yazdır, koşma
#   ./otomasyon/betik/agir-komut.sh -- npm test                           # ölçülü koş
#   ./otomasyon/betik/agir-komut.sh --max-mb 1800 -- npm run tip
#   ./otomasyon/betik/agir-komut.sh --zorla -- <komut>                    # eşiği yok say (operatör)
#
# Çıkış kodları: 0 komut başarılı · 2 kullanım · 7 boş RAM eşiğin altında · 8 başka ağır iş
#                sürüyor · 124 zaman aşımı · diğerleri komutun kendi kodu.
set -euo pipefail

KULLANIM="kullanım: $0 [--max-mb N] [--zaman-asimi S] [--esik-mb N] [--zorla] [--kuru] -- <komut...>"

MAX_MB=""
ZAMAN_S=900
ESIK_MB="${AGIR_ESIK_MB:-700}"
ZORLA=0
KURU=0

while [ $# -gt 0 ]; do
  case "$1" in
    --max-mb)        MAX_MB="${2:-}"; shift 2 ;;
    --max-mb=*)      MAX_MB="${1#*=}"; shift ;;
    --zaman-asimi)   ZAMAN_S="${2:-}"; shift 2 ;;
    --zaman-asimi=*) ZAMAN_S="${1#*=}"; shift ;;
    --esik-mb)       ESIK_MB="${2:-}"; shift 2 ;;
    --esik-mb=*)     ESIK_MB="${1#*=}"; shift ;;
    --zorla)         ZORLA=1; shift ;;
    --kuru)          KURU=1; shift ;;
    --)              shift; break ;;
    -h|--help)       echo "$KULLANIM"; exit 0 ;;
    *)               break ;;
  esac
done

if [ $# -eq 0 ]; then
  echo "✗ komut verilmedi" >&2
  echo "$KULLANIM" >&2
  exit 2
fi

sayi_mi() { case "${1:-}" in ''|*[!0-9]*) return 1 ;; *) return 0 ;; esac; }
sayi_mi "$ESIK_MB" || { echo "✗ --esik-mb sayı olmalı: '$ESIK_MB'" >&2; exit 2; }
sayi_mi "$ZAMAN_S" || { echo "✗ --zaman-asimi sayı olmalı: '$ZAMAN_S'" >&2; exit 2; }
if [ -n "$MAX_MB" ] && ! sayi_mi "$MAX_MB"; then
  echo "✗ --max-mb sayı olmalı: '$MAX_MB'" >&2; exit 2
fi

# ── ölçüm ────────────────────────────────────────────────────────────────────────────────────────
# AGIR_MEMINFO yalnız testler için: /proc/meminfo biçiminde sahte dosya.
MEMINFO="${AGIR_MEMINFO:-/proc/meminfo}"
alan_mb() {  # $1 = MemTotal: gibi alan adı → MB (bulunamazsa boş)
  [ -r "$MEMINFO" ] || return 0
  awk -v ad="$1" '$1==ad { printf "%d", $2/1024 }' "$MEMINFO" 2>/dev/null || true
}

TOPLAM_MB="$(alan_mb MemTotal:)"
MUSAIT_MB="$(alan_mb MemAvailable:)"
TAKAS_MB="$(alan_mb SwapTotal:)"
TAKAS_BOS_MB="$(alan_mb SwapFree:)"

# Okunamazsa ölçüm yok: fail-closed DAVRANMIYORUZ (komut çalışsın) ama görünür uyarı veriyoruz.
if ! sayi_mi "$TOPLAM_MB" || [ "$TOPLAM_MB" -le 0 ]; then
  echo "UYARI: /proc/meminfo okunamadı → bellek tavanı hesaplanamıyor, komut tavansız koşacak" >&2
  TOPLAM_MB=0
  MUSAIT_MB=0
fi

sinirla() {  # $1 değer, $2 alt, $3 üst → [alt, üst]
  local d="$1" alt="$2" ust="$3"
  [ "$d" -lt "$alt" ] && d="$alt"
  [ "$d" -gt "$ust" ] && d="$ust"
  printf '%s' "$d"
}

if [ "$TOPLAM_MB" -gt 0 ]; then
  # Eşik: boş RAM eşiğin altındaysa ağır iş başlatmak makineyi takasa gömer.
  if [ "$MUSAIT_MB" -lt "$ESIK_MB" ] && [ "$ZORLA" -eq 0 ]; then
    echo "✗ REDDEDİLDİ: boş RAM ${MUSAIT_MB} MB < eşik ${ESIK_MB} MB (toplam ${TOPLAM_MB} MB," \
         "takas $(( TAKAS_MB - TAKAS_BOS_MB )) MB dolu)." >&2
    echo "  Ağır komut şimdi koşarsa V8 'FatalProcessOutOfMemory' ile abort eder (26 Ekim dersi)." >&2
    echo "  Yapılacaklar: (1) sohbet/derleme yükünü kapat, (2) birkaç saniye sonra tekrar dene," >&2
    echo "  (3) gerçekten gerekiyorsa operatör olarak --zorla." >&2
    exit 7
  fi
  if [ -z "$MAX_MB" ]; then
    # Tavan: boş RAM'in 400 MB altı. Üst sınır = makine RAM'inin %75'i VE 4096 MB
    # (büyük makinede "boş RAM kadar" tavan vermek anlamsız: tek komut 4 GB'ı geçmemeli).
    ust=$(( TOPLAM_MB * 75 / 100 ))
    [ "$ust" -gt 4096 ] && ust=4096
    MAX_MB="$(sinirla $(( MUSAIT_MB - 400 )) 800 "$ust")"
  fi
else
  [ -n "$MAX_MB" ] || MAX_MB=1024
fi

# V8 tavanı: cgroup tavanının %60'ı (kalan %40 yığın/diğer RSS + ebeveyn süreçler için).
NODE_HEAP_MB="$(sinirla $(( MAX_MB * 60 / 100 )) 384 2048)"

# ── kilit: ağır işler sırayla ────────────────────────────────────────────────────────────────────
KILIT_DIZIN="${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}}"
KILIT="$KILIT_DIZIN/yourkiosk-agir-komut.lock"
GUNLUK_DIZIN="$HOME/.local/state/yourkiosk-otomasyon"
GUNLUK="$GUNLUK_DIZIN/agir-komut.log"

SCOPE_VAR=0
if command -v systemd-run >/dev/null 2>&1; then
  # Gerçek bir yoklama: kullanıcı systemd bus'ı yoksa (konteyner, XDG_RUNTIME_DIR taşınmış)
  # `systemd-run` komutu HİÇ çalıştırmadan hata verir → sessizce "komut koşmadı" olurdu.
  # Bu yüzden bir kez /bin/true ile denenir; başarısızsa yalıtımsız yola düşülür.
  if [ "$KURU" -eq 1 ] || systemd-run --user --scope --quiet --collect \
       -p MemoryAccounting=yes -- /bin/true >/dev/null 2>&1; then
    SCOPE_VAR=1
  fi
fi

if [ "$KURU" -eq 1 ]; then
  echo "plan (kuru):"
  echo "  komut          : $*"
  echo "  toplam/boş RAM : ${TOPLAM_MB} MB / ${MUSAIT_MB} MB"
  echo "  cgroup tavanı  : ${MAX_MB} MB (MemoryHigh $(( MAX_MB * 85 / 100 )) MB)"
  echo "  NODE_OPTIONS   : --max-old-space-size=${NODE_HEAP_MB}"
  echo "  zaman aşımı    : ${ZAMAN_S} sn"
  echo "  kilit          : $KILIT"
  echo "  yalıtım        : $([ "$SCOPE_VAR" -eq 1 ] && echo 'systemd-run --user --scope' || echo 'ulimit -v (systemd-run yok)')"
  exit 0
fi

exec 9>"$KILIT"
if ! flock -n 9; then
  echo "✗ başka bir ağır komut sürüyor (kilit: $KILIT)." >&2
  echo "  Aynı anda iki derleme/test bu makinelerde bellek tavanını aşar → sıraya gir." >&2
  exit 8
fi

# ── NODE_OPTIONS: var olanı koru, tavanı ekle ────────────────────────────────────────────────────
mevcut="${NODE_OPTIONS:-}"
case " $mevcut " in
  *" --max-old-space-size="*) : ;;  # çağıran bilinçli bir tavan verdiyse ona dokunma
  *) export NODE_OPTIONS="${mevcut:+$mevcut }--max-old-space-size=${NODE_HEAP_MB}" ;;
esac
# Vite/vitest iş parçacıkları da aynı tavanı görsün (tinypool çocukları NODE_OPTIONS'ı devralır).
export AGIR_KOMUT=1

mkdir -p "$GUNLUK_DIZIN" 2>/dev/null || true
satir="[$(date -Iseconds)] tavan=${MAX_MB}MB heap=${NODE_HEAP_MB}MB bos=${MUSAIT_MB}MB komut=$*"
[ -w "$GUNLUK_DIZIN" ] && printf '%s\n' "$satir" >> "$GUNLUK" 2>/dev/null || true

kod=0
if [ "$SCOPE_VAR" -eq 1 ]; then
  # --scope: komut bizim cgroup'umuzda ama AYRI bir kapsamda koşar → tavan yalnız onu bağlar.
  # --collect: kapsam bitince artık birim kalmasın (systemctl list-units kirlenmesin).
  systemd-run --user --scope --quiet --collect \
    -p MemoryAccounting=yes \
    -p "MemoryMax=${MAX_MB}M" \
    -p "MemoryHigh=$(( MAX_MB * 85 / 100 ))M" \
    -- timeout "$ZAMAN_S" "$@" || kod=$?
else
  # Geri düşüş: cgroup yalıtımı yok → yalnız V8 tavanı + duvar saati. Adres alanı (`ulimit -v`)
  # BİLİNÇLİ olarak kullanılmıyor: V8/JVM büyük sanal alan ayırır, ulimit onları sebepsiz düşürür.
  echo "UYARI: systemd-run --user çalışmıyor → cgroup bellek tavanı YOK, yalnız V8 tavanı (${NODE_HEAP_MB} MB) uygulanıyor" >&2
  timeout "$ZAMAN_S" "$@" || kod=$?
fi

printf '[%s] çıkış=%s tavan=%sMB heap=%sMB\n' "$(date -Iseconds)" "$kod" "$MAX_MB" "$NODE_HEAP_MB" \
  >> "$GUNLUK" 2>/dev/null || true

if [ "$kod" -eq 137 ] || [ "$kod" -eq 9 ]; then
  echo "✗ komut bellek tavanında öldürüldü (${MAX_MB} MB). Daha küçük parçalara böl" \
       "(örn. tek dosya testi) ya da --max-mb yükselt." >&2
fi
exit "$kod"
