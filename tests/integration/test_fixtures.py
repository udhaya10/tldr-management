"""
Fixture management tests.

TestFixturePresence  — fast pre-flight: is the fixture ready right now?
TestPrepareScript    — lifecycle: does the script correctly create, clean, and restore?

Methods inside TestPrepareScript run in definition order and are intentionally
stateful — each phase sets up the condition the next phase asserts against.
"""

from pathlib import Path

import pytest
from sh import ErrorReturnCode, bash

from tests.conftest import msg

pytestmark = pytest.mark.integration

PROJECT_ROOT = Path(__file__).parent.parent.parent
FSNOTIFIER_DIR = PROJECT_ROOT / "tests" / "fixtures" / "fsnotifier"
FSNOTIFIER_SRC = FSNOTIFIER_DIR / "native" / "fsNotifier"
PREPARE_SCRIPT = PROJECT_ROOT / "scripts" / "prepare-test-case.sh"


def _prepare(*flags: str) -> None:
    """Run prepare-test-case.sh; calls pytest.fail on non-zero exit."""
    try:
        bash(str(PREPARE_SCRIPT), *flags, _cwd=str(PROJECT_ROOT), _timeout=300)
    except ErrorReturnCode as exc:
        invocation = ("prepare-test-case.sh " + " ".join(flags)).strip()
        pytest.fail(msg(
            "Script failed",
            command=invocation,
            exit_code=exc.exit_code,
            stderr=exc.stderr.decode(errors="replace").strip() or "(empty)",
        ))


# ── tests ──────────────────────────────────────────────────────────────────

class TestFixturePresence:
    """Pre-flight check: fixture must exist and contain real C source."""

    def test_fsnotifier_dir_exists(self):
        assert FSNOTIFIER_DIR.exists(), msg(
            "Fixture directory missing",
            path=FSNOTIFIER_DIR,
            fix="Run: ./scripts/prepare-test-case.sh",
        )

    def test_sparse_checkout_materialised(self):
        assert FSNOTIFIER_SRC.exists(), msg(
            "Sparse checkout did not materialise source directory",
            expected=FSNOTIFIER_SRC,
            hint="Clone exists but sparse path is wrong — check prepare-test-case.sh",
        )

    def test_c_source_files_present(self):
        c_files = list(FSNOTIFIER_SRC.rglob("*.c"))
        assert c_files, msg(
            "No C source files found",
            searched=FSNOTIFIER_SRC,
            hint="Sparse clone completed but *.c files were not checked out",
        )


class TestPrepareScript:
    """
    Validates the full lifecycle of prepare-test-case.sh so it never goes stale.

    Phase 1 — prepare  : script creates the fixture; real C source is present.
    Phase 2 — clean    : --clean removes the fixture root entirely.
    Phase 3 — restore  : re-running the script brings the fixture back.
    """

    def test_01_prepare_creates_fixture(self):
        _prepare()
        assert FSNOTIFIER_SRC.exists(), msg(
            "Prepare did not materialise source directory",
            expected=FSNOTIFIER_SRC,
        )
        assert any(FSNOTIFIER_SRC.rglob("*.c")), msg(
            "Prepare produced no C source files",
            searched=FSNOTIFIER_SRC,
        )

    def test_02_clean_removes_fixture(self):
        _prepare("--clean")
        assert not FSNOTIFIER_DIR.exists(), msg(
            "Fixture directory still present after --clean",
            path=FSNOTIFIER_DIR,
            hint="--clean may not be removing the directory",
        )

    def test_03_reprepare_restores_fixture(self):
        _prepare()
        assert FSNOTIFIER_SRC.exists(), msg(
            "Restore did not materialise source directory",
            expected=FSNOTIFIER_SRC,
        )
        assert any(FSNOTIFIER_SRC.rglob("*.c")), msg(
            "Restored fixture has no C source files",
            searched=FSNOTIFIER_SRC,
        )
