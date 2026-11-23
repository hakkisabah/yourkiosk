#!/usr/bin/env bash
# Üretilmiş kurulum betiği — toshibai5 / reviewer
set -euo pipefail
REPO="${AGENTS_REPO:-$(pwd)}"
[ -x "$REPO/agents/bin/agents" ] || { echo "✗ repo bulunamadı: $REPO (AGENTS_REPO ile ver)" >&2; exit 2; }
CFG="$HOME/.config/agents/gelistirici.toml"
TOKEN="$HOME/.config/gelistirici/inceleme.token"
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
  echo "instance = \"gelistirici\""
  echo "repo = \"hakkisabah/yourkiosk\""
  echo "base_branch = \"main\""
  echo "gorev_etiketi = \"agents/gorev\""
  if [ "reviewer" != "decision" ]; then
    echo "dsh_profile = \"headless\""
    echo "dsh_checkout = \"$HOME/deepseek-harness\""
    echo "dsh_home = \"$HOME/.dsh\""
    echo "dsh_patch = \"$HOME/.dsh/agents-overlay-lite.yml\""
  fi
  echo "state_dir = \"$HOME/.local/state/agents/gelistirici\""
  echo "workdir = \"$HOME/.local/state/agents/gelistirici/work\""
  echo "skills_root = \"$HOME/.local/share/agents/gelistirici/skills\""
  echo ""
  echo "[[agents]]"
  echo "name = \"toshibai5\""
  echo "role = \"reviewer\""
  echo "machine = \"toshibai5\""
  echo "token_file = \"$TOKEN\""
} > "$CFG"
chmod 600 "$CFG"
cd "$REPO"
./agents/bin/agents --config "$CFG" doctor
./agents/bin/agents --config "$CFG" install
systemctl --user daemon-reload
systemctl --user enable --now "agents@gelistirici-reviewer.service"
systemctl --user list-units 'agents@*' --no-pager
echo "✓ toshibai5 / reviewer kuruldu: $CFG"
