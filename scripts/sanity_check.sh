#!/usr/bin/env bash
# Sanity check: verify git repo and TLDR setup
set -uo pipefail
PROJECT="$1"

echo "=== Sanity Check: $PROJECT ==="
echo ""

# Git repo check
if git -C "$PROJECT" rev-parse --git-dir &>/dev/null; then
  echo "[PASS] Git repo"
  echo "##CHECK Git repo PASS"
else
  echo "[FAIL] Not a git repo"
  echo "##CHECK Git repo FAIL"
fi

# TLDR repo check
if [ -d "$PROJECT/.tldr" ] || [ -f "$PROJECT/.tldrignore" ]; then
  echo "[PASS] TLDR repo (.tldr/ or .tldrignore found)"
  echo "##CHECK TLDR repo PASS"
else
  echo "[FAIL] Not a TLDR repo (no .tldr/ or .tldrignore)"
  echo "##CHECK TLDR repo FAIL"
fi

echo ""
echo "Done."
