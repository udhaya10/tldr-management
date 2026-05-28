"""
Warm integration test.

Validates that `tldr warm` transitions the project from a cold (no cache)
state to a warm (cache populated) state.

Before state  — tmp_path is clean, call_graph.json absent
Action        — tldr warm
After state   — call_graph.json present and contains valid JSON

Timing assertions are intentionally absent: on a small test project (2 files)
all beneficiary commands run in ~8-10ms dominated by process startup, making
before/after deltas indistinguishable from OS scheduling noise.
"""

import dataclasses
import json
import shutil
from collections.abc import Generator
from pathlib import Path

import pytest
import sh

from tests.conftest import msg, requires_tldr

pytestmark = [pytest.mark.integration, requires_tldr]

PROJECT_ROOT = Path(__file__).parent.parent.parent
_tldr = sh.Command("tldr")


# ── data model ────────────────────────────────────────────────────────────

@dataclasses.dataclass(frozen=True)
class WarmResult:
    status:     str
    files:      int
    edges:      int
    languages:  list[str]
    cache_path: Path


@dataclasses.dataclass
class WarmSession:
    project_dir:         Path
    cache_absent_before: bool
    warm_result:         WarmResult


def parse_warm_result(raw: str) -> WarmResult:
    data = json.loads(raw)
    return WarmResult(
        status=data["status"],
        files=data["files"],
        edges=data["edges"],
        languages=data["languages"],
        cache_path=Path(data["cache_path"]),
    )


# ── fixture ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="class")
def warm_session(tmp_path_factory) -> Generator[WarmSession, None, None]:
    """
    1. Copy Python source into an isolated tmp dir.
    2. Record that the call_graph cache is absent.
    3. Run warm.
    4. Yield WarmSession for assertions.

    Teardown: remove .tldr/ so the cache does not leak between test sessions.
    """
    project_dir = tmp_path_factory.mktemp("warm")

    for f in (PROJECT_ROOT / "tldr_management").rglob("*.py"):
        (project_dir / f.name).write_bytes(f.read_bytes())

    cache_file = project_dir / ".tldr" / "cache" / "call_graph.json"
    cache_absent_before = not cache_file.exists()

    raw         = _tldr("warm", "--format", "json", str(project_dir))
    warm_result = parse_warm_result(str(raw))

    yield WarmSession(
        project_dir=project_dir,
        cache_absent_before=cache_absent_before,
        warm_result=warm_result,
    )

    shutil.rmtree(project_dir / ".tldr", ignore_errors=True)


# ── tests ─────────────────────────────────────────────────────────────────

class TestWarm:

    def test_cache_was_absent_before_warm(self, warm_session):
        assert warm_session.cache_absent_before, msg(
            "Cache already existed before warm — tmp_path was not clean",
            project_dir=warm_session.project_dir,
        )

    def test_status_is_ok(self, warm_session):
        assert warm_session.warm_result.status == "ok", msg(
            "warm did not return ok",
            status=warm_session.warm_result.status,
        )

    def test_files_indexed_is_positive(self, warm_session):
        assert warm_session.warm_result.files > 0, msg(
            "warm indexed 0 files",
            files=warm_session.warm_result.files,
        )

    def test_python_detected_in_languages(self, warm_session):
        assert "python" in warm_session.warm_result.languages, msg(
            "Python not detected in warm output",
            languages=warm_session.warm_result.languages,
        )

    def test_cache_file_present_after_warm(self, warm_session):
        cache = warm_session.project_dir / warm_session.warm_result.cache_path
        assert cache.exists(), msg(
            "call_graph.json not created after warm",
            expected=cache,
        )

    def test_cache_contains_valid_json(self, warm_session):
        cache   = warm_session.project_dir / warm_session.warm_result.cache_path
        content = json.loads(cache.read_text())
        assert isinstance(content, dict), msg(
            "call_graph.json is not a JSON object",
            actual_type=type(content).__name__,
        )

    def _dump_captured_values(self, warm_session, capsys):
        with capsys.disabled():
            print(f"\n  project_dir : {warm_session.project_dir}")
            print(f"  status      : {warm_session.warm_result.status}")
            print(f"  files       : {warm_session.warm_result.files}")
            print(f"  edges       : {warm_session.warm_result.edges}")
            print(f"  languages   : {warm_session.warm_result.languages}")
            print(f"  cache_path  : {warm_session.warm_result.cache_path}")
