"""
Warm integration test.

`tldr warm` builds the call graph cache inside the target directory.
Tests use tmp_path_factory for isolation — pytest auto-deletes it,
so no explicit teardown is needed.

Warm response (JSON):
  { "status": "ok", "files": N, "edges": N,
    "languages": [...], "cache_path": ".tldr/cache/call_graph.json" }

Cache artifact:
  <project_dir>/.tldr/cache/call_graph.json
"""

import dataclasses
import json
from collections.abc import Generator
from pathlib import Path

import pytest
import sh

from tests.conftest import msg, requires_tldr, requires_fixture

pytestmark = [pytest.mark.integration, requires_tldr, requires_fixture]

_tldr = sh.Command("tldr")


# ── data model ────────────────────────────────────────────────────────────

@dataclasses.dataclass(frozen=True)
class WarmResult:
    status:      str
    files:       int
    edges:       int
    languages:   list[str]
    cache_path:  Path   # relative, as returned by tldr
    project_dir: Path   # absolute tmp_path used for this test run


def parse_warm_result(raw: str, project_dir: Path) -> WarmResult:
    """Parse `tldr warm --format json` output into a typed WarmResult."""
    data = json.loads(raw)
    return WarmResult(
        status=data["status"],
        files=data["files"],
        edges=data["edges"],
        languages=data["languages"],
        cache_path=Path(data["cache_path"]),
        project_dir=project_dir,
    )


# ── fixture ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="class")
def warm_result(
    tmp_path_factory,
    fsnotifier_fixture,
) -> Generator[WarmResult, None, None]:
    """
    Copy C source into an isolated tmp dir, warm it, yield the parsed result.
    tmp_path_factory is session-scoped so it is safe to use here.
    pytest deletes the tmp dir after the session — no teardown needed.
    """
    project_dir = tmp_path_factory.mktemp("warm")

    for f in (fsnotifier_fixture / "linux").glob("*.c"):
        (project_dir / f.name).write_bytes(f.read_bytes())

    raw = _tldr("warm", "--format", "json", str(project_dir))
    yield parse_warm_result(str(raw), project_dir)


# ── tests ─────────────────────────────────────────────────────────────────

class TestWarm:
    """Validates `tldr warm` response shape and cache artifact creation."""

    def test_status_is_ok(self, warm_result):
        assert warm_result.status == "ok", msg(
            "warm did not return ok",
            status=warm_result.status,
        )

    def test_files_count_is_positive(self, warm_result):
        assert warm_result.files > 0, msg(
            "warm reported 0 files indexed",
            files=warm_result.files,
            project_dir=warm_result.project_dir,
        )

    def test_c_language_detected(self, warm_result):
        assert "c" in warm_result.languages, msg(
            "C language not detected in warm output",
            languages=warm_result.languages,
        )

    def test_cache_file_created_in_project_dir(self, warm_result):
        cache = warm_result.project_dir / warm_result.cache_path
        assert cache.exists(), msg(
            "call_graph.json not created inside project directory",
            expected=cache,
        )

    def test_captured_values(self, warm_result, capsys):
        """Print all captured values — visible with pytest -s."""
        with capsys.disabled():
            print(f"\n  status      : {warm_result.status}")
            print(f"  files       : {warm_result.files}")
            print(f"  edges       : {warm_result.edges}")
            print(f"  languages   : {warm_result.languages}")
            print(f"  cache_path  : {warm_result.cache_path}")
            print(f"  project_dir : {warm_result.project_dir}")
