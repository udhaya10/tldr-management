"""
Search layer integration tests — structural validation only.

Tests four search/context commands:
  search    — BM25 keyword search enriched with AST context cards
  context   — LLM-ready call graph context from an entry-point function
  semantic  — vector embedding similarity search (natural language)
  similar   — find files with similar embedding fingerprints

Structural validation is handled by Pydantic model_validate() in each
fixture. Test methods assert only behavioural invariants.

Test targets:
  search   : tests/integration/  query="test"  --no-callgraph (pure BM25, fast)
  context  : tests/integration/  entry="parse_daemon_filename" (known function)
  semantic : tests/fixtures/fsnotifier/  query="file watching"  --quiet
             (requires_fixture — needs a real C corpus with embedded chunks)
  similar  : tests/integration/test_l1.py  --path PROJECT_ROOT  --quiet
             (uses Python test files; path must include the source file)
"""

import json
from pathlib import Path

import pytest
import sh

from tests.conftest import msg, requires_fixture, requires_tldr
from tests.tldr_models import (
    ContextResult,
    SearchResponse,
    SemanticResponse,
    SimilarResult,
)

pytestmark = [pytest.mark.integration, requires_tldr]

PROJECT_ROOT    = Path(__file__).parent.parent.parent
INTEGRATION_DIR = PROJECT_ROOT / "tests" / "integration"
FSNOTIFIER_SRC  = PROJECT_ROOT / "tests" / "fixtures" / "fsnotifier" / "native" / "fsNotifier"

_tldr = sh.Command("tldr")


# ── fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="class")
def search_response() -> SearchResponse:
    raw = _tldr(
        "search", "--format", "json", "--no-callgraph",
        "test", str(INTEGRATION_DIR),
    )
    return SearchResponse.model_validate(json.loads(str(raw)))


@pytest.fixture(scope="class")
def context_result() -> ContextResult:
    raw = _tldr(
        "context", "--format", "json",
        "parse_daemon_filename", str(INTEGRATION_DIR),
    )
    return ContextResult.model_validate(json.loads(str(raw)))


@pytest.fixture(scope="class")
def semantic_response(fsnotifier_fixture) -> SemanticResponse:
    # --no-cache: don't write to ~/.cache/tldr/ — avoids pre-caching files that
    # other tests (TestEmbedCaching) need to embed as "fresh" for the first time
    raw = _tldr(
        "semantic", "--format", "json", "--quiet", "--no-cache",
        "file watching", str(FSNOTIFIER_SRC),
    )
    return SemanticResponse.model_validate(json.loads(str(raw)))


@pytest.fixture(scope="class")
def similar_result() -> SimilarResult:
    # --no-cache: don't write to ~/.cache/tldr/ — same isolation reason as
    # semantic_response. Without this, all project Python files get cached on
    # first run and any future test wanting a "fresh" embed would find them pre-cached.
    source = INTEGRATION_DIR / "test_l1.py"
    raw = _tldr(
        "similar", "--format", "json", "--quiet", "--no-cache",
        "--path", str(PROJECT_ROOT),
        str(source),
    )
    return SimilarResult.model_validate(json.loads(str(raw)))


# ── tests ─────────────────────────────────────────────────────────────────

class TestSearch:
    """tldr search — BM25 enriched keyword search."""

    def test_results_non_empty(self, search_response):
        assert search_response.results, msg(
            "search returned no results for query 'test' in integration dir",
            path=INTEGRATION_DIR,
        )

    def test_scores_non_negative(self, search_response):
        bad = [r for r in search_response.results if r.score < 0]
        assert not bad, msg(
            "Some search results have negative scores",
            bad=[(r.name, r.score) for r in bad],
        )

    def test_captured_values(self, search_response, capsys):
        with capsys.disabled():
            print(f"\n  query   : {search_response.query}")
            print(f"  results : {len(search_response.results)}")
            for r in search_response.results[:3]:
                print(f"    [{r.kind:8s}] {r.name:30s}  score={r.score:.1f}  {r.file}")


class TestContext:
    """tldr context — LLM-ready call graph context from an entry point."""

    def test_entry_point_resolved(self, context_result):
        assert context_result.functions, msg(
            "context returned no functions for known entry point",
            entry_point=context_result.entry_point,
            hint="parse_daemon_filename must be parseable in tests/integration/",
        )

    def test_depth_is_positive(self, context_result):
        assert context_result.depth > 0, msg(
            "context depth is not positive",
            depth=context_result.depth,
        )

    def test_captured_values(self, context_result, capsys):
        with capsys.disabled():
            print(f"\n  entry_point : {context_result.entry_point}")
            print(f"  depth       : {context_result.depth}")
            print(f"  functions   : {len(context_result.functions)}")
            for f in context_result.functions:
                print(f"    {f.name:30s}  line={f.line}  cyclomatic={f.cyclomatic}")


@requires_fixture
class TestSemantic:
    """tldr semantic — vector similarity search (requires fsnotifier fixture)."""

    def test_results_non_empty(self, semantic_response):
        assert semantic_response.results, msg(
            "semantic returned no results",
            query=semantic_response.query,
            path=FSNOTIFIER_SRC,
        )

    def test_scores_in_valid_range(self, semantic_response):
        bad = [r for r in semantic_response.results if not (0.0 <= r.score <= 1.0)]
        assert not bad, msg(
            "Semantic scores outside [0, 1] range",
            bad=[(r.file_path, r.score) for r in bad],
        )

    def test_captured_values(self, semantic_response, capsys):
        with capsys.disabled():
            print(f"\n  query         : {semantic_response.query}")
            print(f"  total_results : {semantic_response.total_results}")
            for r in semantic_response.results[:3]:
                print(f"    score={r.score:.4f}  {Path(r.file_path).name}"
                      f"  lines {r.line_start}-{r.line_end}")


class TestSimilar:
    """tldr similar — find files with similar embedding fingerprints."""

    def test_source_chunks_positive(self, similar_result):
        assert similar_result.source_chunks > 0, msg(
            "Source file produced no chunks — may not be embeddable",
            source_file=similar_result.source_file,
        )

    def test_similar_files_non_empty(self, similar_result):
        assert similar_result.similar_files, msg(
            "similar returned no matching files",
            source=similar_result.source_file,
            hint="--path must cover the source file (use project root)",
        )

    def test_captured_values(self, similar_result, capsys):
        with capsys.disabled():
            print(f"\n  source_file   : {Path(similar_result.source_file).name}")
            print(f"  source_chunks : {similar_result.source_chunks}")
            print(f"  model         : {similar_result.model}")
            print(f"  similar_files : {len(similar_result.similar_files)}")
            for f in similar_result.similar_files[:3]:
                print(f"    avg={f.avg_score:.4f}  {Path(f.file_path).name}")
