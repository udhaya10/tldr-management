#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# prepare-test-case.sh
#
# Prepares the test fixture used by the tldr-management test suite.
#
# Clones a sparse subset of JetBrains/intellij-community — specifically the
# `native/fsNotifier/` directory — into ./tests/fixtures/fsnotifier/. This
# is the same C source we vendor as our file-watcher helper, so the test
# corpus and the runtime helper share an origin (dogfooding).
#
# Why this fixture?
#   - Tiny (~10 C files, ~2,000 LOC) → semantic indexing finishes in seconds
#   - Real-world, production-grade source (used by every JetBrains IDE)
#   - C language coverage for tldr's embedder
#   - Apache 2.0 licensed, freely redistributable
#
# Why a script instead of a git submodule?
#   - New contributors do not need to learn submodule mechanics.
#   - A fresh `git clone` of tldr-management stays fast and small.
#   - The test fixture is rebuildable from one command.
#   - The fixture folder is .gitignored and MUST NEVER be committed.
#
# Usage:
#   ./scripts/prepare-test-case.sh                 # clone if missing
#   ./scripts/prepare-test-case.sh --update        # pull the latest changes
#   ./scripts/prepare-test-case.sh --clean         # remove the fixture
#   ./scripts/prepare-test-case.sh --sha <commit>  # checkout a specific commit
#
# Environment:
#   TLDR_TEST_REPO     Override the source repository URL
#                      (default: https://github.com/JetBrains/intellij-community)
#   TLDR_TEST_PATH     Override the sparse-checkout subdirectory
#                      (default: native/fsNotifier)
#   TLDR_TEST_SHA      Pin to a specific commit/tag/branch
#                      (default: master)
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── configuration ───────────────────────────────────────────────────────────
REPO_URL="${TLDR_TEST_REPO:-https://github.com/JetBrains/intellij-community}"
SPARSE_PATH="${TLDR_TEST_PATH:-native/fsNotifier}"
DEFAULT_REF="${TLDR_TEST_SHA:-master}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FIXTURE_DIR="$PROJECT_ROOT/tests/fixtures"
TARGET_DIR="$FIXTURE_DIR/fsnotifier"

# ── helpers ─────────────────────────────────────────────────────────────────
log()  { printf '\033[1;34m[prepare-test-case]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[prepare-test-case]\033[0m %s\n' "$*" >&2; }
fail() { printf '\033[1;31m[prepare-test-case]\033[0m %s\n' "$*" >&2; exit 1; }

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"
}

# ── argument parsing ────────────────────────────────────────────────────────
MODE="ensure"
REF="$DEFAULT_REF"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --update)  MODE="update"; shift ;;
        --clean)   MODE="clean";  shift ;;
        --sha)     REF="$2"; shift 2 ;;
        -h|--help)
            sed -n '2,38p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) fail "unknown argument: $1 (try --help)" ;;
    esac
done

# ── preflight ───────────────────────────────────────────────────────────────
require_cmd git
mkdir -p "$FIXTURE_DIR"

# ── sparse-checkout setup helper ────────────────────────────────────────────
sparse_clone() {
    log "cloning $REPO_URL (sparse: $SPARSE_PATH) into $TARGET_DIR"
    git clone \
        --depth 1 \
        --filter=blob:none \
        --sparse \
        --no-checkout \
        --branch "$REF" \
        "$REPO_URL" "$TARGET_DIR" 2>/dev/null || \
    git clone \
        --filter=blob:none \
        --sparse \
        --no-checkout \
        "$REPO_URL" "$TARGET_DIR"
    git -C "$TARGET_DIR" sparse-checkout init --cone
    git -C "$TARGET_DIR" sparse-checkout set "$SPARSE_PATH"
    git -C "$TARGET_DIR" checkout "$REF" 2>/dev/null || \
        git -C "$TARGET_DIR" checkout
    log "sparse checkout complete — only $SPARSE_PATH materialized"
}

# ── modes ───────────────────────────────────────────────────────────────────
case "$MODE" in
    clean)
        if [[ -d "$TARGET_DIR" ]]; then
            log "removing $TARGET_DIR"
            rm -rf "$TARGET_DIR"
        else
            log "nothing to remove — $TARGET_DIR does not exist"
        fi
        ;;

    ensure)
        if [[ -d "$TARGET_DIR/.git" ]]; then
            local_ref=$(git -C "$TARGET_DIR" rev-parse --short HEAD)
            log "fsnotifier fixture already present at commit $local_ref — skipping clone"
            log "use --update to pull latest, or --sha <commit> to checkout a specific revision"
        else
            sparse_clone
            log "done — $(git -C "$TARGET_DIR" rev-parse --short HEAD)"
        fi
        ;;

    update)
        if [[ ! -d "$TARGET_DIR/.git" ]]; then
            fail "$TARGET_DIR is not a git checkout — run without --update first"
        fi
        log "fetching latest from $REPO_URL"
        git -C "$TARGET_DIR" fetch --all --tags --prune
        log "checking out $REF"
        git -C "$TARGET_DIR" checkout "$REF"
        if git -C "$TARGET_DIR" symbolic-ref -q HEAD >/dev/null; then
            git -C "$TARGET_DIR" pull --ff-only
        fi
        log "now at $(git -C "$TARGET_DIR" rev-parse --short HEAD)"
        ;;
esac

# ── final sanity check ──────────────────────────────────────────────────────
if [[ "$MODE" != "clean" ]]; then
    file_count=$(find "$TARGET_DIR/$SPARSE_PATH" -type f 2>/dev/null | wc -l | tr -d ' ')
    total_size=$(du -sh "$TARGET_DIR/$SPARSE_PATH" 2>/dev/null | cut -f1)
    log "fixture ready: $TARGET_DIR/$SPARSE_PATH"
    log "  files: $file_count   size: ${total_size:-unknown}"
    log "all tests should read from this path; never commit its contents"
fi
