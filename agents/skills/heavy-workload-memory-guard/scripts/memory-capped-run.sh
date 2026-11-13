#!/usr/bin/env bash
# memory-capped-run.sh — run a heavy command inside a memory cap, serialized.
#
# Why: V8/JVM set their heap ceiling from their own defaults, not from physical RAM. A heavy Node
# command on a small host grows into swap until it aborts (FatalProcessOutOfMemory) or the kernel
# OOM-kills the machine. This wrapper refuses when headroom is gone, gives Node a ceiling that fits,
# isolates the command in a cgroup, and serializes heavy jobs so two builds never overlap.
#
#   ./memory-capped-run.sh --kuru -- npm test        # plan only
#   ./memory-capped-run.sh -- npm run tip            # capped run
#   ./memory-capped-run.sh --max-mb 1800 -- npm test
#   ./memory-capped-run.sh --zorla -- <cmd>          # operator override of the headroom gate
#
# Exit: 0 ok · 2 usage · 7 headroom below threshold · 8 another heavy job holds the lock
#       124 wall-clock timeout · otherwise the command's own code.
#
# Tests can feed a fake /proc/meminfo with MEMINFO=<path>.
set -euo pipefail

KULLANIM="kullanım: $0 [--max-mb N] [--zaman-asimi S] [--esik-mb N] [--zorla] [--kuru] -- <komut...>"
MAX_MB=""; ZAMAN_S=900; ESIK_MB="${MEM_ESIK_MB:-700}"; ZORLA=0; KURU=0

while [ $# -gt 0 ]; do
  case "$1" in
    --max-mb) MAX_MB="${2:-}"; shift 2 ;;
    --max-mb=*) MAX_MB="${1#*=}"; shift ;;
    --zaman-asimi) ZAMAN_S="${2:-}"; shift 2 ;;
    --zaman-asimi=*) ZAMAN_S="${1#*=}"; shift ;;
    --esik-mb) ESIK_MB="${2:-}"; shift 2 ;;
    --esik-mb=*) ESIK_MB="${1#*=}"; shift ;;
    --zorla) ZORLA=1; shift ;;
    --kuru) KURU=1; shift ;;
    --) shift; break ;;
    -h|--help) echo "$KULLANIM"; exit 0 ;;
    *) break ;;
  esac
done
[ $# -gt 0 ] || { echo "✗ komut verilmedi" >&2; echo "$KULLANIM" >&2; exit 2; }

sayi_mi() { case "${1:-}" in ''|*[!0-9]*) return 1 ;; *) return 0 ;; esac; }
sayi_mi "$ESIK_MB" || { echo "✗ --esik-mb sayı olmalı: '$ESIK_MB'" >&2; exit 2; }
sayi_mi "$ZAMAN_S" || { echo "✗ --zaman-asimi sayı olmalı: '$ZAMAN_S'" >&2; exit 2; }
if [ -n "$MAX_MB" ] && ! sayi_mi "$MAX_MB"; then echo "✗ --max-mb sayı olmalı" >&2; exit 2; fi

MEMINFO="${MEMINFO:-/proc/meminfo}"
alan_mb() { [ -r "$MEMINFO" ] || return 0; awk -v a="$1" '$1==a {printf "%d", $2/1024}' "$MEMINFO" 2>/dev/null || true; }
TOPLAM_MB="$(alan_mb MemTotal:)"; MUSAIT_MB="$(alan_mb MemAvailable:)"
TAKAS_MB="$(alan_mb SwapTotal:)"; TAKAS_BOS_MB="$(alan_mb SwapFree:)"
if ! sayi_mi "$TOPLAM_MB" || [ "$TOPLAM_MB" -le 0 ]; then
  echo "UYARI: $MEMINFO okunamadı → tavan hesaplanamıyor, komut yalnız V8 tavanıyla koşacak" >&2
  TOPLAM_MB=0; MUSAIT_MB=0
fi

sinirla() { local d="$1" a="$2" u="$3"; [ "$d" -lt "$a" ] && d="$a"; [ "$d" -gt "$u" ] && d="$u"; printf '%s' "$d"; }

if [ "$TOPLAM_MB" -gt 0 ]; then
  if [ "$MUSAIT_MB" -lt "$ESIK_MB" ] && [ "$ZORLA" -eq 0 ]; then
    echo "✗ REDDEDİLDİ: boş RAM ${MUSAIT_MB} MB < eşik ${ESIK_MB} MB (toplam ${TOPLAM_MB} MB, takas $(( TAKAS_MB - TAKAS_BOS_MB )) MB dolu)." >&2
    echo "  Ağır komut şimdi koşarsa süreç tavanında abort eder. Yükü azalt, sonra tekrar dene;" >&2
    echo "  gerçekten gerekiyorsa operatör olarak --zorla." >&2
    exit 7
  fi
  if [ -z "$MAX_MB" ]; then
    ust=$(( TOPLAM_MB * 75 / 100 )); [ "$ust" -gt 4096 ] && ust=4096
    MAX_MB="$(sinirla $(( MUSAIT_MB - 400 )) 800 "$ust")"
  fi
else
  [ -n "$MAX_MB" ] || MAX_MB=1024
fi
NODE_HEAP_MB="$(sinirla $(( MAX_MB * 60 / 100 )) 384 2048)"

KILIT_DIZIN="${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}}"; KILIT="$KILIT_DIZIN/memory-capped-run.lock"
GUNLUK_DIZIN="$HOME/.local/state/memory-capped-run"; GUNLUK="$GUNLUK_DIZIN/run.log"

# systemd-run existing is not systemd-run working: probe it once.
SCOPE=0
if command -v systemd-run >/dev/null 2>&1; then
  if [ "$KURU" -eq 1 ] || systemd-run --user --scope --quiet --collect -p MemoryAccounting=yes -- /bin/true >/dev/null 2>&1; then
    SCOPE=1
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
  echo "  yalıtım        : $([ "$SCOPE" -eq 1 ] && echo 'systemd-run --user --scope' || echo 'YOK (yalnız V8 tavanı)')"
  exit 0
fi

exec 9>"$KILIT"
if ! flock -n 9; then
  echo "✗ başka bir ağır komut sürüyor (kilit: $KILIT) → sıraya gir." >&2
  exit 8
fi

case " ${NODE_OPTIONS:-} " in
  *" --max-old-space-size="*) : ;;
  *) export NODE_OPTIONS="${NODE_OPTIONS:+$NODE_OPTIONS }--max-old-space-size=${NODE_HEAP_MB}" ;;
esac
export MEMORY_CAPPED_RUN=1

mkdir -p "$GUNLUK_DIZIN" 2>/dev/null || true
[ -w "$GUNLUK_DIZIN" ] && printf '[%s] tavan=%sMB heap=%sMB bos=%sMB komut=%s\n' "$(date -Iseconds)" \
  "$MAX_MB" "$NODE_HEAP_MB" "$MUSAIT_MB" "$*" >> "$GUNLUK" 2>/dev/null || true

kod=0
if [ "$SCOPE" -eq 1 ]; then
  systemd-run --user --scope --quiet --collect -p MemoryAccounting=yes \
    -p "MemoryMax=${MAX_MB}M" -p "MemoryHigh=$(( MAX_MB * 85 / 100 ))M" \
    -- timeout "$ZAMAN_S" "$@" || kod=$?
else
  echo "UYARI: systemd-run --user çalışmıyor → cgroup tavanı YOK, yalnız V8 tavanı (${NODE_HEAP_MB} MB)" >&2
  timeout "$ZAMAN_S" "$@" || kod=$?
fi

printf '[%s] çıkış=%s tavan=%sMB heap=%sMB\n' "$(date -Iseconds)" "$kod" "$MAX_MB" "$NODE_HEAP_MB" \
  >> "$GUNLUK" 2>/dev/null || true
if [ "$kod" -eq 137 ] || [ "$kod" -eq 9 ]; then
  echo "✗ komut bellek tavanında öldürüldü (${MAX_MB} MB) → işi böl ya da --max-mb yükselt" >&2
fi
exit "$kod"
