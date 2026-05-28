"""
Warm integration test.

Proves that `tldr warm` transitions the project from a cold (no cache) state
to a warm (cache populated) state, and records timing of a structural query
both before and after warm using codetiming.

Before state  — tmp_path is clean, call_graph.json absent
Action        — tldr warm
After state   — call_graph.json present, valid, covers source files

Warm response (JSON):
  { "status": "ok", "files": N, "edges": N,
    "languages": [...], "cache_path": ".tldr/cache/call_graph.json" }
"""

import dataclasses
import json
import shutil
from collections.abc import Generator
from pathlib import Path

import pytest
import sh
from codetiming import Timer

from tests.conftest import msg, requires_tldr

pytestmark = [pytest.mark.integration, requires_tldr]

PROJECT_ROOT = Path(__file__).parent.parent.parent
_tldr = sh.Command("tldr")


# ── data models ───────────────────────────────────────────────────────────

@dataclasses.dataclass(frozen=True)
class WarmResult:
    status:     str
    files:      int
    edges:      int
    languages:  list[str]
    cache_path: Path        # relative, as returned by tldr


@dataclasses.dataclass
class WarmSession:
    project_dir:         Path
    cache_absent_before: bool           # was .tldr/cache/ absent before warm?
    result:              WarmResult     # parsed warm response
    timings:             dict[str, float]  # keys: before_warm_ms, after_warm_ms


def parse_warm_result(raw: str) -> WarmResult:
    """Parse `tldr warm --format json` output into a typed WarmResult."""
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
    1. Copy Python source into an isolated tmp dir (clean slate).
    2. Record whether the call_graph cache is absent.
    3. Time a cold structural query (no warm cache).
    4. Clear any cache the cold query created.
    5. Run warm — builds the call_graph cache.
    6. Time the same structural query with warm cache in place.

    pytest auto-deletes the tmp dir — no teardown needed.
    """
    project_dir = tmp_path_factory.mktemp("warm")
    timings: dict[str, float] = {}

    # Copy Python source files — richer call graph than C for this project
    for f in (PROJECT_ROOT / "tldr_management").rglob("*.py"):
        (project_dir / f.name).write_bytes(f.read_bytes())

    cache_file = project_dir / ".tldr" / "cache" / "call_graph.json"

    # ── before state ──────────────────────────────────────────────────────
    cache_absent_before = not cache_file.exists()

    with Timer(logger=None) as t:
        _tldr("calls", "--format", "json", str(project_dir))
    timings["before_warm_ms"] = t.last * 1000

    # Clear whatever the cold query created — warm gets a clean slate
    shutil.rmtree(project_dir / ".tldr", ignore_errors=True)

    # ── warm ──────────────────────────────────────────────────────────────
    raw    = _tldr("warm", "--format", "json", str(project_dir))
    result = parse_warm_result(str(raw))

    # ── after state ───────────────────────────────────────────────────────
    with Timer(logger=None) as t:
        _tldr("calls", "--format", "json", str(project_dir))
    timings["after_warm_ms"] = t.last * 1000

    yield WarmSession(
        project_dir=project_dir,
        cache_absent_before=cache_absent_before,
        result=result,
        timings=timings,
    )


# ── tests ─────────────────────────────────────────────────────────────────

class TestWarm:

    # ── before state ──────────────────────────────────────────────────────

    def test_cache_was_absent_before_warm(self, warm_session):
        assert warm_session.cache_absent_before, msg(
            "Cache already existed before warm — tmp_path was not clean",
            project_dir=warm_session.project_dir,
        )

    # ── warm response ─────────────────────────────────────────────────────

    def test_status_is_ok(self, warm_session):
        assert warm_session.result.status == "ok", msg(
            "warm did not return ok",
            status=warm_session.result.status,
        )

    def test_files_indexed_is_positive(self, warm_session):
        assert warm_session.result.files > 0, msg(
            "warm indexed 0 files",
            files=warm_session.result.files,
            project_dir=warm_session.project_dir,
        )

    def test_python_detected_in_languages(self, warm_session):
        assert "python" in warm_session.result.languages, msg(
            "Python not detected in warm output",
            languages=warm_session.result.languages,
        )

    # ── after state ───────────────────────────────────────────────────────

    def test_cache_file_present_after_warm(self, warm_session):
        cache = warm_session.project_dir / warm_session.result.cache_path
        assert cache.exists(), msg(
            "call_graph.json not created after warm",
            expected=cache,
        )

    def test_cache_contains_valid_json(self, warm_session):
        cache   = warm_session.project_dir / warm_session.result.cache_path
        content = json.loads(cache.read_text())
        assert isinstance(content, dict), msg(
            "call_graph.json is not a JSON object",
            actual_type=type(content).__name__,
        )

    # ── timing ────────────────────────────────────────────────────────────

    def test_timings_captured(self, warm_session):
        assert warm_session.timings["before_warm_ms"] > 0, msg(
            "Before-warm timing was not captured",
            timings=warm_session.timings,
        )
        assert warm_session.timings["after_warm_ms"] > 0, msg(
            "After-warm timing was not captured",
            timings=warm_session.timings,
        )

    def test_captured_values(self, warm_session, capsys):
        before = warm_session.timings["before_warm_ms"]
        after  = warm_session.timings["after_warm_ms"]
        with capsys.disabled():
            print(f"\n  project_dir  : {warm_session.project_dir}")
            print(f"  files        : {warm_session.result.files}")
            print(f"  edges        : {warm_session.result.edges}")
            print(f"  languages    : {warm_session.result.languages}")
            print(f"  before_warm  : {before:.1f}ms")
            print(f"  after_warm   : {after:.1f}ms")
            print(f"  delta        : {before - after:+.1f}ms")
