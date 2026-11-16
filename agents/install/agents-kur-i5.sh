#!/usr/bin/env bash
# Üretilmiş kurulum betiği — i5 / reviewer
set -euo pipefail
REPO="${AGENTS_REPO:-$(pwd)}"
[ -x "$REPO/agents/bin/agents" ] || { echo "✗ repo bulunamadı: $REPO (AGENTS_REPO ile ver)" >&2; exit 2; }
CFG="$HOME/.config/agents/agents-test.toml"
TOKEN="$HOME/.config/yourkiosk-secrets/agents-test/inceleme.token"
OVERLAY="$HOME/.dsh/agents-overlay-lite.yml"
mkdir -p "$(dirname "$CFG")" "$HOME/.dsh"
chmod 700 "$HOME/.config/yourkiosk-secrets/agents-test" 2>/dev/null || true
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
  echo "instance = \"agents-test\""
  echo "repo = \"hakkisabah/agents-test\""
  echo "base_branch = \"main\""
  echo "gorev_etiketi = \"agents/gorev\""
  if [ "reviewer" != "decision" ]; then
    echo "dsh_profile = \"headless\""
    echo "dsh_home = \"$HOME/.dsh\""
    echo "dsh_patch = \"$HOME/.dsh/agents-overlay-lite.yml\""
  fi
  echo "state_dir = \"$HOME/.local/state/agents/agents-test\""
  echo "workdir = \"$HOME/.local/state/agents/agents-test/work\""
  echo "skills_root = \"$HOME/.local/share/agents/agents-test/skills\""
  echo ""
  echo "[[agents]]"
  echo "name = \"i5\""
  echo "role = \"reviewer\""
  echo "machine = \"i5\""
  echo "token_file = \"$TOKEN\""
} > "$CFG"
chmod 600 "$CFG"
cd "$REPO"
./agents/bin/agents --config "$CFG" doctor
./agents/bin/agents --config "$CFG" install
systemctl --user daemon-reload
systemctl --user enable --now "agents@agents-test-reviewer.service"
systemctl --user list-units 'agents@*' --no-pager
echo "✓ i5 / reviewer kuruldu: $CFG"
