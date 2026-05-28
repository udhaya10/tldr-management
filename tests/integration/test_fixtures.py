"""
Fixture presence tests.

These fail (not skip) when required fixtures are missing — the fixture
must be prepared before any integration tests can run.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

PROJECT_ROOT = Path(__file__).parent.parent.parent
FSNOTIFIER_DIR = PROJECT_ROOT / "tests" / "fixtures" / "fsnotifier"


class TestFixturePresence:

    def test_fsnotifier_fixture_exists(self):
        assert FSNOTIFIER_DIR.exists(), (
            f"Fixture directory not found: {FSNOTIFIER_DIR}\n"
            f"Run: ./scripts/prepare-test-case.sh"
        )
