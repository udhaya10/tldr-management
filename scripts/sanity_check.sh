#!/usr/bin/env bash
# Sanity check: verify git repo and TLDR setup
set -uo pipefail
PROJECT="$1"

pass() { echo "[PASS] $1"; }
fail() { echo "[FAIL] $1"; }

echo "=== Sanity Check: $PROJECT ==="
echo ""

# Git repo check
if git -C "$PROJECT" rev-parse --git-dir &>/dev/null; then
  pass "Git repo"
else
  fail "Not a git repo"
fi

# TLDR repo check
if [ -d "$PROJECT/.tldr" ] || [ -f "$PROJECT/.tldrignore" ]; then
  pass "TLDR repo (.tldr/ or .tldrignore found)"
else
  fail "Not a TLDR repo (no .tldr/ or .tldrignore)"
fi

echo ""
echo "Done."
