#!/usr/bin/env bash
# Check basic git status of the project
set -euo pipefail
PROJECT="$1"

echo "=== Git Status: $PROJECT ==="
echo ""
git -C "$PROJECT" status
echo ""
echo "=== Recent commits ==="
git -C "$PROJECT" log --oneline -10
