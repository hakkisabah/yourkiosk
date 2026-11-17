#!/usr/bin/env bash
# Makineye özel kurulum betiği üretir: agents/install/agents-kur-<makine>.sh
# Kullanım: agents/install/uret.sh <instance> <makine> <rol> [repo] [cikti] [token_ad] [token_dir]
set -euo pipefail
INSTANCE="${1:-}"; MAKINE="${2:-}"; ROL="${3:-}"; REPO="${4:-hakkisabah/agents-test}"; CIKTI="${5:-}"; TOKEN_AD="${6:-}"; TOKEN_DIR="${7:-}"
[ -n "$INSTANCE" ] && [ -n "$MAKINE" ] && [ -n "$ROL" ] || { echo "kullanım: $0 <instance> <makine> <developer|reviewer|decision> [repo] [cikti]" >&2; exit 2; }
case "$ROL" in developer) TOKEN="gelistirici.token";; reviewer) TOKEN="inceleme.token";; decision) TOKEN="karar.token";; *) echo "geçersiz rol: $ROL" >&2; exit 2;; esac
KOK="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
[ -n "$TOKEN_AD" ] || TOKEN_AD="$TOKEN"
if [ -n "$TOKEN_DIR" ]; then TOKEN_PATH="$TOKEN_DIR/$TOKEN_AD"; else TOKEN_PATH='$HOME/.config/'"$INSTANCE"'/'"$TOKEN_AD"; fi
[ -n "$CIKTI" ] || CIKTI="$KOK/agents/install/agents-kur-$MAKINE.sh"
cat > "$CIKTI" <<'BETIK'
#!/usr/bin/env bash
# Üretilmiş kurulum betiği — @MAKINE@ / @ROL@
set -euo pipefail
REPO="${AGENTS_REPO:-$(pwd)}"
[ -x "$REPO/agents/bin/agents" ] || { echo "✗ repo bulunamadı: $REPO (AGENTS_REPO ile ver)" >&2; exit 2; }
CFG="$HOME/.config/agents/@INSTANCE@.toml"
TOKEN="@TOKEN_PATH@"
OVERLAY="$HOME/.dsh/agents-overlay-lite.yml"
mkdir -p "$(dirname "$CFG")" "$HOME/.dsh"
chmod 700 "$(dirname "$TOKEN")" 2>/dev/null || true
if [ ! -f "$TOKEN" ]; then
  echo "✗ token yok: $TOKEN" >&2
  echo "  Bu dosyayı 0600 ile koyun (aceri5'ten kopyalayın)." >&2
  exit 3
fi
chmod 600 "$TOKEN"
if [ ! -f "$OVERLAY" ]; then
  cp "$REPO/agents/install/dsh-overlay-lite.example.yml" "$OVERLAY"
fi
{
  echo "instance = \"@INSTANCE@\""
  echo "repo = \"@REPO@\""
  echo "base_branch = \"main\""
  echo "gorev_etiketi = \"agents/gorev\""
  if [ "@ROL@" != "decision" ]; then
    echo "dsh_profile = \"headless\""
    echo "dsh_home = \"$HOME/.dsh\""
    echo "dsh_patch = \"$HOME/.dsh/agents-overlay-lite.yml\""
  fi
  echo "state_dir = \"$HOME/.local/state/agents/@INSTANCE@\""
  echo "workdir = \"$HOME/.local/state/agents/@INSTANCE@/work\""
  echo "skills_root = \"$HOME/.local/share/agents/@INSTANCE@/skills\""
  echo ""
  echo "[[agents]]"
  echo "name = \"@MAKINE@\""
  echo "role = \"@ROL@\""
  echo "machine = \"@MAKINE@\""
  echo "token_file = \"$TOKEN\""
} > "$CFG"
chmod 600 "$CFG"
cd "$REPO"
./agents/bin/agents --config "$CFG" doctor
./agents/bin/agents --config "$CFG" install
systemctl --user daemon-reload
systemctl --user enable --now "agents@@INSTANCE@-@ROL@.service"
systemctl --user list-units 'agents@*' --no-pager
echo "✓ @MAKINE@ / @ROL@ kuruldu: $CFG"
BETIK
sed -i "s|@INSTANCE@|$INSTANCE|g; s|@MAKINE@|$MAKINE|g; s|@ROL@|$ROL|g; s|@TOKEN_PATH@|$TOKEN_PATH|g; s|@REPO@|$REPO|g" "$CIKTI"
chmod 755 "$CIKTI"
echo "yazıldı: $CIKTI"
