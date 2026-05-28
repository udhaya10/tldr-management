"""
L1 (AST) integration tests.

Tests all five L1 commands:
  tree        — directory tree structure
  structure   — file structure (functions, classes, imports, definitions)
  extract     — complete module info from a single file
  imports     — import statements from a single file
  importers   — files that import a given module

Structural validation is handled entirely by Pydantic: model_validate()
in each fixture both parses and validates the response shape. A
ValidationError from a fixture means the response schema changed.

Test methods only assert invariants Pydantic cannot express:
  - non-empty lists (a model cannot know the codebase is non-trivial)
  - semantic contracts (e.g. tree on a dir → root.type == "dir")
  - cross-field consistency already enforced by @model_validator
    (ImportersResult.total == len(importers))
"""

import json
from pathlib import Path

import pytest
import sh

from tests.conftest import msg, requires_tldr
from tests.tldr_models import (
    ExtractResult,
    ImportersResult,
    ImportsResult,
    StructureResult,
    TreeNode,
)

pytestmark = [pytest.mark.integration, requires_tldr]

PROJECT_ROOT    = Path(__file__).parent.parent.parent
INTEGRATION_DIR = PROJECT_ROOT / "tests" / "integration"
CONFTEST_FILE   = PROJECT_ROOT / "tests" / "conftest.py"

_tldr = sh.Command("tldr")


# ── fixtures ──────────────────────────────────────────────────────────────
# Each fixture calls model_validate() — if the shape is wrong, Pydantic
# raises ValidationError and pytest reports a fixture error with full detail.

@pytest.fixture(scope="class")
def tree_result() -> TreeNode:
    raw = _tldr("tree", "--format", "json", str(INTEGRATION_DIR))
    return TreeNode.model_validate(json.loads(str(raw)))


@pytest.fixture(scope="class")
def structure_result() -> StructureResult:
    raw = _tldr("structure", "--format", "json", str(INTEGRATION_DIR))
    return StructureResult.model_validate(json.loads(str(raw)))


@pytest.fixture(scope="class")
def extract_result() -> ExtractResult:
    raw = _tldr("extract", "--format", "json", str(CONFTEST_FILE))
    return ExtractResult.model_validate(json.loads(str(raw)))


@pytest.fixture(scope="class")
def imports_result() -> ImportsResult:
    raw = _tldr("imports", "--format", "json", str(CONFTEST_FILE))
    return ImportsResult.model_validate(json.loads(str(raw)))


@pytest.fixture(scope="class")
def importers_result() -> ImportersResult:
    raw = _tldr("importers", "--format", "json", "pytest", str(INTEGRATION_DIR))
    return ImportersResult.model_validate(json.loads(str(raw)))


# ── tests ─────────────────────────────────────────────────────────────────


class TestTree:
    """tldr tree — Pydantic validates shape; tests assert semantic contracts."""

    def test_root_is_dir_node(self, tree_result):
        assert tree_result.type == "dir", msg(
            "tldr tree on a directory must return a dir root node",
            type=tree_result.type,
        )

    def test_children_non_empty(self, tree_result):
        assert tree_result.children, msg(
            "Tree has no children — target directory appears empty",
            path=INTEGRATION_DIR,
        )

    def test_file_nodes_have_path(self, tree_result):
        bad = [c for c in tree_result.children if c.type == "file" and c.path is None]
        assert not bad, msg(
            "File nodes must have a 'path' field",
            bad=[c.name for c in bad],
        )

    def test_captured_values(self, tree_result, capsys):
        with capsys.disabled():
            print(f"\n  name     : {tree_result.name}")
            print(f"  type     : {tree_result.type}")
            print(f"  children : {[c.name for c in tree_result.children]}")


class TestStructure:
    """tldr structure — Pydantic validates nested file/method/import/definition shapes."""

    def test_files_non_empty(self, structure_result):
        assert structure_result.files, msg(
            "structure returned no files",
            root=structure_result.root,
        )

    def test_captured_values(self, structure_result, capsys):
        with capsys.disabled():
            print(f"\n  root     : {structure_result.root}")
            print(f"  language : {structure_result.language}")
            print(f"  files    : {len(structure_result.files)}")
            for f in structure_result.files:
                print(f"    {f.path:30s}  "
                      f"classes={len(f.classes)}  "
                      f"methods={len(f.method_infos)}")


class TestExtract:
    """tldr extract — Pydantic validates functions/classes/constants/imports shapes."""

    def test_captured_values(self, extract_result, capsys):
        with capsys.disabled():
            print(f"\n  file_path : {extract_result.file_path}")
            print(f"  language  : {extract_result.language}")
            print(f"  imports   : {len(extract_result.imports)}")
            print(f"  functions : {len(extract_result.functions)}")
            print(f"  classes   : {len(extract_result.classes)}")
            print(f"  constants : {len(extract_result.constants)}")


class TestImports:
    """tldr imports — Pydantic validates import item schema."""

    def test_imports_non_empty(self, imports_result):
        assert imports_result.imports, msg(
            "imports returned empty list — target file has imports",
            file=imports_result.file,
        )

    def test_captured_values(self, imports_result, capsys):
        with capsys.disabled():
            print(f"\n  file     : {imports_result.file}")
            print(f"  language : {imports_result.language}")
            print(f"  imports  : {[i.module for i in imports_result.imports]}")


class TestImporters:
    """tldr importers — total==len(importers) enforced by @model_validator."""

    def test_importers_non_empty(self, importers_result):
        assert importers_result.importers, msg(
            "importers returned empty list",
            module=importers_result.module,
            path=INTEGRATION_DIR,
        )

    def test_captured_values(self, importers_result, capsys):
        with capsys.disabled():
            print(f"\n  module : {importers_result.module}")
            print(f"  total  : {importers_result.total}")
            for i in importers_result.importers:
                print(f"    line {i.line:3d}  {Path(i.file).name}")
