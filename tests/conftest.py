"""
Shared pytest fixtures and skip conditions for the tldr-management test suite.

Skip hierarchy (outermost to innermost):
  unit        — no external deps; always runnable
  integration — requires tldr binary on PATH and/or a prepared fixture
  e2e         — requires all of the above plus a running daemon
"""

import os
import shutil
from pathlib import Path

import pytest
from rich.console import Console
from rich.panel import Panel

# ── shared helpers ────────────────────────────────────────────────────────

def msg(title: str, **fields) -> str:
    """Render a Rich panel to plain text for use in assertion messages."""
    console = Console(record=True, width=72, highlight=False)
    body = "\n".join(f"  [bold]{k}:[/bold] {v}" for k, v in fields.items())
    console.print(Panel(body, title=f"[red]{title}[/red]", expand=False))
    return "\n" + console.export_text()


# ── project paths ──────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "fsnotifier"
FSNOTIFIER_SRC = FIXTURE_DIR / "native" / "fsNotifier"
WATCHER_BINARY = PROJECT_ROOT / ".tldr-svc" / "watcher"


# ── reusable skip markers ──────────────────────────────────────────────────

def _missing(name: str) -> str:
    return f"{name!r} not found — run: ./scripts/prepare-test-case.sh"


requires_tldr = pytest.mark.skipif(
    not shutil.which("tldr"),
    reason="tldr binary not on PATH — install tldr-code first",
)

requires_clang = pytest.mark.skipif(
    not shutil.which("clang"),
    reason="clang not installed — see README § Installing clang",
)

requires_watcher = pytest.mark.skipif(
    not WATCHER_BINARY.exists(),
    reason=f"watcher binary not built — run: ./scripts/build-watcher.sh",
)

requires_daemon = pytest.mark.skipif(
    not os.environ.get("TLDR_DAEMON_URL"),
    reason="TLDR_DAEMON_URL not set — daemon not running",
)

requires_fixture = pytest.mark.skipif(
    not FSNOTIFIER_SRC.exists(),
    reason=_missing("tests/fixtures/fsnotifier/native/fsNotifier"),
)


# ── pytest fixtures ────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def fsnotifier_fixture(tmp_path_factory):
    """
    Path to the sparse-cloned fsNotifier C source used as a real-world corpus.

    Skips the test (not fails) if the fixture hasn't been prepared yet.
    Run: ./scripts/prepare-test-case.sh
    """
    if not FSNOTIFIER_SRC.exists():
        pytest.skip(_missing("tests/fixtures/fsnotifier/native/fsNotifier"))
    return FSNOTIFIER_SRC


@pytest.fixture(scope="session")
def tldr_binary():
    """Path to the tldr binary. Skips if not on PATH."""
    binary = shutil.which("tldr")
    if not binary:
        pytest.skip("tldr binary not on PATH — install tldr-code first")
    return binary


@pytest.fixture(scope="session")
def watcher_binary():
    """Path to the compiled file-watcher helper. Skips if not built."""
    if not WATCHER_BINARY.exists():
        pytest.skip("watcher binary not built — run: ./scripts/build-watcher.sh")
    return WATCHER_BINARY
