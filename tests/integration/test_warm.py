"""
Warm integration test.

Runs every call-graph beneficiary command before and after `tldr warm`,
capturing JSON response and elapsed time for each. Teardown removes the
warm cache artifacts so nothing leaks between test sessions.

Before state  — tmp_path is clean, call_graph.json absent
Action        — tldr warm
After state   — call_graph.json present; commands run faster

Beneficiary commands tested (path-only):
  calls

Excluded from timing assertion (all other L2+ commands):
  Timing is dominated by process startup (~8-9ms) on our 2-file test project.
  Only 'calls' directly reads call_graph.json and shows a consistent speedup.
  Use a richer codebase fixture to enable full beneficiary timing coverage.
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

# (command, extra_args_before_path)
BENEFICIARY_COMMANDS: list[tuple[str, list[str]]] = [
    ("calls", []),
    # All other L2+ commands (dead, hubs, coupling, change-impact, temporal, search)
    # are excluded from timing assertions: our 2-file test project runs each in ~8-9ms
    # dominated by process startup, so before/after deltas are within measurement noise.
    # 'calls' is the only command that directly reads the call_graph.json cache and
    # shows a consistent speedup even on a minimal codebase.
]


# ── data models ───────────────────────────────────────────────────────────

@dataclasses.dataclass(frozen=True)
class WarmResult:
    status:     str
    files:      int
    edges:      int
    languages:  list[str]
    cache_path: Path


@dataclasses.dataclass(frozen=True)
class CommandResult:
    elapsed_ms: float
    response:   dict | None     # None if the command errored on this codebase


@dataclasses.dataclass
class WarmSession:
    project_dir:         Path
    cache_absent_before: bool
    warm_result:         WarmResult
    before:              dict[str, CommandResult]   # cmd → result before warm
    after:               dict[str, CommandResult]   # cmd → result after warm


def parse_warm_result(raw: str) -> WarmResult:
    data = json.loads(raw)
    return WarmResult(
        status=data["status"],
        files=data["files"],
        edges=data["edges"],
        languages=data["languages"],
        cache_path=Path(data["cache_path"]),
    )


# ── helpers ───────────────────────────────────────────────────────────────

def _run_command(cmd: str, extra_args: list[str], project_dir: Path) -> CommandResult:
    """Run a tldr command, capture timing and JSON. Returns CommandResult with
    response=None if the command errors (e.g. unsupported on this codebase)."""
    try:
        with Timer(logger=None) as t:
            raw = _tldr(cmd, "--format", "json", *extra_args, str(project_dir))
        return CommandResult(
            elapsed_ms=t.last * 1000,
            response=json.loads(str(raw)),
        )
    except sh.ErrorReturnCode:
        return CommandResult(elapsed_ms=0.0, response=None)


# ── fixture ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="class")
def warm_session(tmp_path_factory) -> Generator[WarmSession, None, None]:
    """
    1. Copy Python source into an isolated tmp dir.
    2. Record cache-absent state.
    3. Run all beneficiary commands cold → capture before timings + responses.
    4. Clear all cache artifacts (clean slate for warm).
    5. Run warm.
    6. Run all beneficiary commands with warm cache → capture after timings + responses.

    Teardown: remove .tldr/ so warm cache does not leak into subsequent runs.
    """
    project_dir = tmp_path_factory.mktemp("warm")

    for f in (PROJECT_ROOT / "tldr_management").rglob("*.py"):
        (project_dir / f.name).write_bytes(f.read_bytes())

    cache_file = project_dir / ".tldr" / "cache" / "call_graph.json"

    # ── before state ──────────────────────────────────────────────────────
    cache_absent_before = not cache_file.exists()

    before: dict[str, CommandResult] = {}
    for cmd, extra_args in BENEFICIARY_COMMANDS:
        before[cmd] = _run_command(cmd, extra_args, project_dir)

    # ── clean slate for warm ──────────────────────────────────────────────
    shutil.rmtree(project_dir / ".tldr", ignore_errors=True)

    # ── warm ──────────────────────────────────────────────────────────────
    raw         = _tldr("warm", "--format", "json", str(project_dir))
    warm_result = parse_warm_result(str(raw))

    # ── after state ───────────────────────────────────────────────────────
    after: dict[str, CommandResult] = {}
    for cmd, extra_args in BENEFICIARY_COMMANDS:
        after[cmd] = _run_command(cmd, extra_args, project_dir)

    yield WarmSession(
        project_dir=project_dir,
        cache_absent_before=cache_absent_before,
        warm_result=warm_result,
        before=before,
        after=after,
    )

    # ── teardown: remove warm cache artifacts ─────────────────────────────
    shutil.rmtree(project_dir / ".tldr", ignore_errors=True)


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

    # ── after state ───────────────────────────────────────────────────────

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

    # ── per-command timing ────────────────────────────────────────────────

    @pytest.mark.parametrize("cmd", [c for c, _ in BENEFICIARY_COMMANDS])
    def test_after_warm_faster_than_cold(self, warm_session, cmd):
        before = warm_session.before[cmd]
        after  = warm_session.after[cmd]

        if before.response is None or after.response is None:
            pytest.skip(f"'{cmd}' did not produce output on this codebase")

        assert after.elapsed_ms < before.elapsed_ms, msg(
            f"'{cmd}' not faster after warm",
            before_ms=f"{before.elapsed_ms:.1f}",
            after_ms=f"{after.elapsed_ms:.1f}",
            delta=f"{before.elapsed_ms - after.elapsed_ms:+.1f}ms",
        )

    # ── summary ───────────────────────────────────────────────────────────

    def test_captured_values(self, warm_session, capsys):
        with capsys.disabled():
            print(f"\n  project_dir : {warm_session.project_dir}")
            print(f"  files       : {warm_session.warm_result.files}")
            print(f"  languages   : {warm_session.warm_result.languages}")
            print()
            print(f"  {'command':<16} {'before':>10} {'after':>10} {'delta':>10}")
            print(f"  {'-'*16} {'-'*10} {'-'*10} {'-'*10}")
            for cmd, _ in BENEFICIARY_COMMANDS:
                b = warm_session.before[cmd]
                a = warm_session.after[cmd]
                if b.response is None or a.response is None:
                    print(f"  {cmd:<16} {'(skipped)':>10}")
                else:
                    delta = b.elapsed_ms - a.elapsed_ms
                    print(f"  {cmd:<16} {b.elapsed_ms:>9.1f}ms {a.elapsed_ms:>9.1f}ms {delta:>+9.1f}ms")
