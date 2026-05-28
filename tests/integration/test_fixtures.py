"""
Fixture management tests.

TestFixturePresence  — fast pre-flight: is the fixture ready right now?
TestPrepareScript    — lifecycle: does the script correctly create, clean, and restore?

Methods inside TestPrepareScript run in definition order and are intentionally
stateful — each phase sets up the condition the next phase asserts against.
"""

import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

PROJECT_ROOT = Path(__file__).parent.parent.parent
FSNOTIFIER_DIR = PROJECT_ROOT / "tests" / "fixtures" / "fsnotifier"
PREPARE_SCRIPT = PROJECT_ROOT / "scripts" / "prepare-test-case.sh"

# git sparse-clone can be slow on a cold network; 5 min is generous
SCRIPT_TIMEOUT = 300


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        timeout=SCRIPT_TIMEOUT,
    )


class TestFixturePresence:
    """Pre-flight check: fixture must exist before integration tests run."""

    def test_fsnotifier_fixture_exists(self):
        assert FSNOTIFIER_DIR.exists(), (
            f"Fixture directory not found: {FSNOTIFIER_DIR}\n"
            f"Run: ./scripts/prepare-test-case.sh"
        )


class TestPrepareScript:
    """
    Validates the full lifecycle of prepare-test-case.sh.

    Phase 1 — prepare  : script creates the fixture and it is non-empty.
    Phase 2 — clean    : --clean removes the fixture entirely.
    Phase 3 — restore  : re-running the script brings the fixture back.

    If any phase fails, the assertion message tells you exactly what went wrong
    and which script invocation caused it.
    """

    def test_01_prepare_creates_nonempty_fixture(self):
        result = _run([str(PREPARE_SCRIPT)])

        assert result.returncode == 0, (
            f"prepare-test-case.sh exited {result.returncode}\n{result.stderr}"
        )
        assert FSNOTIFIER_DIR.exists(), (
            f"Script exited 0 but fixture directory was not created: {FSNOTIFIER_DIR}"
        )
        assert any(FSNOTIFIER_DIR.iterdir()), (
            f"Fixture directory exists but is empty: {FSNOTIFIER_DIR}"
        )

    def test_02_clean_removes_fixture(self):
        result = _run([str(PREPARE_SCRIPT), "--clean"])

        assert result.returncode == 0, (
            f"prepare-test-case.sh --clean exited {result.returncode}\n{result.stderr}"
        )
        assert not FSNOTIFIER_DIR.exists(), (
            f"Fixture directory still present after --clean: {FSNOTIFIER_DIR}"
        )

    def test_03_reprepare_restores_fixture(self):
        result = _run([str(PREPARE_SCRIPT)])

        assert result.returncode == 0, (
            f"prepare-test-case.sh (restore) exited {result.returncode}\n{result.stderr}"
        )
        assert FSNOTIFIER_DIR.exists(), (
            f"Script exited 0 but fixture directory was not restored: {FSNOTIFIER_DIR}"
        )
        assert any(FSNOTIFIER_DIR.iterdir()), (
            f"Restored fixture directory is empty: {FSNOTIFIER_DIR}"
        )
