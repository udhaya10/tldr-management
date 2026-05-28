"""
Embed integration test.

`tldr embed` generates vector embeddings for code chunks.
All tests use --no-cache for determinism — avoids dependency on the
shared user-level cache at ~/.cache/tldr/ between runs.

Embed response (JSON):
  { "path": "...", "model": "...", "granularity": "...",
    "chunks_embedded": N, "chunks_cached": N, "latency_ms": N }

Cache behaviour:
  TestEmbedFresh   — --no-cache: always embeds, never reads/writes cache
  TestEmbedCaching — no flag: run twice to confirm chunks_cached > 0 on hit
"""

import dataclasses
import json
from pathlib import Path

import pytest
import sh

from tests.conftest import msg, requires_tldr, requires_fixture

pytestmark = [pytest.mark.integration, requires_tldr, requires_fixture]

_tldr = sh.Command("tldr")


# ── data model ────────────────────────────────────────────────────────────

@dataclasses.dataclass(frozen=True)
class EmbedResult:
    path:            Path
    model:           str
    granularity:     str
    chunks_embedded: int
    chunks_cached:   int
    latency_ms:      float


def parse_embed_result(raw: str) -> EmbedResult:
    """Parse `tldr embed --format json` output into a typed EmbedResult."""
    data = json.loads(raw)
    return EmbedResult(
        path=Path(data["path"]),
        model=data["model"],
        granularity=data["granularity"],
        chunks_embedded=data["chunks_embedded"],
        chunks_cached=data["chunks_cached"],
        latency_ms=data["latency_ms"],
    )


# ── fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="class")
def embed_fresh(fsnotifier_fixture):
    """Embed a single C file with --no-cache. Always a cold embed, no teardown."""
    target = fsnotifier_fixture / "linux" / "main.c"
    raw    = _tldr("embed", "--no-cache", "--format", "json", str(target))
    return parse_embed_result(str(raw))


@pytest.fixture(scope="class")
def embed_cached_pair(fsnotifier_fixture):
    """
    Embed the same file twice without --no-cache.
    Returns (first_run, second_run) — second run must hit the cache.
    """
    target = fsnotifier_fixture / "linux" / "util.c"
    first  = parse_embed_result(str(_tldr("embed", "--format", "json", str(target))))
    second = parse_embed_result(str(_tldr("embed", "--format", "json", str(target))))
    return first, second


# ── tests ─────────────────────────────────────────────────────────────────

class TestEmbedFresh:
    """Validates embed response shape on a cold --no-cache run."""

    def test_filename_in_response(self, embed_fresh):
        assert embed_fresh.path.name == "main.c", msg(
            "Response path filename does not match input",
            actual=embed_fresh.path.name,
            expected="main.c",
        )

    def test_model_is_set(self, embed_fresh):
        assert embed_fresh.model, msg(
            "Embed model field is empty",
            model=repr(embed_fresh.model),
        )

    def test_default_granularity_is_function(self, embed_fresh):
        assert embed_fresh.granularity == "function", msg(
            "Default granularity is not 'function'",
            granularity=embed_fresh.granularity,
        )

    def test_chunks_embedded_is_positive(self, embed_fresh):
        assert embed_fresh.chunks_embedded > 0, msg(
            "No chunks embedded — file may be empty or unparseable",
            chunks_embedded=embed_fresh.chunks_embedded,
            path=embed_fresh.path,
        )

    def test_no_cache_hits_with_no_cache_flag(self, embed_fresh):
        assert embed_fresh.chunks_cached == 0, msg(
            "--no-cache flag still returned cache hits",
            chunks_cached=embed_fresh.chunks_cached,
        )

    def test_latency_is_positive(self, embed_fresh):
        assert embed_fresh.latency_ms > 0, msg(
            "Embed latency is zero or negative",
            latency_ms=embed_fresh.latency_ms,
        )

    def test_captured_values(self, embed_fresh, capsys):
        """Print all captured values — visible with pytest -s."""
        with capsys.disabled():
            print(f"\n  path            : {embed_fresh.path}")
            print(f"  model           : {embed_fresh.model}")
            print(f"  granularity     : {embed_fresh.granularity}")
            print(f"  chunks_embedded : {embed_fresh.chunks_embedded}")
            print(f"  chunks_cached   : {embed_fresh.chunks_cached}")
            print(f"  latency_ms      : {embed_fresh.latency_ms:.0f}ms")


class TestEmbedCaching:
    """
    Validates the embed cache lifecycle — same file embedded twice.
    Second run must report cache hits, confirming the cache was populated.
    Stateful: first run populates the cache, second run reads it.
    """

    def test_01_first_run_embeds_chunks(self, embed_cached_pair):
        first, _ = embed_cached_pair
        assert first.chunks_embedded > 0, msg(
            "First embed run produced no chunks",
            chunks_embedded=first.chunks_embedded,
            path=first.path,
        )

    def test_02_second_run_hits_cache(self, embed_cached_pair):
        _, second = embed_cached_pair
        assert second.chunks_cached > 0, msg(
            "Second embed run produced no cache hits",
            chunks_cached=second.chunks_cached,
            hint="Cache may not be persisting between calls",
        )

    def test_02_second_run_embeds_nothing_new(self, embed_cached_pair):
        _, second = embed_cached_pair
        assert second.chunks_embedded == 0, msg(
            "Second embed run re-embedded chunks that should have been cached",
            chunks_embedded=second.chunks_embedded,
        )
