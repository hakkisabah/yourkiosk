#!/usr/bin/env bash
# agents kurulum/çalıştırma sarmalayıcısı — sabit yol yok.
set -euo pipefail

KOK="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec env PYTHONPATH="$KOK${PYTHONPATH:+:$PYTHONPATH}" python3 -m agents.driver.cli "$@"
