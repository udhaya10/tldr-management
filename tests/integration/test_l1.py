"""
L1 (AST) integration tests — structural validation only.

Tests all five L1 commands:
  tree        — directory tree structure
  structure   — file structure (functions, classes, imports, definitions)
  extract     — complete module info from a single file
  imports     — import statements from a single file
  importers   — files that import a given module

Philosophy: we validate response SHAPE (field presence, types, schema
consistency) — not content. No assertions about specific file names,
function names, module names, or language strings. That keeps tests
stable when source changes and avoids coupling tests to their own
implementation.
"""

import dataclasses
import json
from pathlib import Path

import pytest
import sh

from tests.conftest import msg, requires_tldr

pytestmark = [pytest.mark.integration, requires_tldr]

PROJECT_ROOT   = Path(__file__).parent.parent.parent
INTEGRATION_DIR = PROJECT_ROOT / "tests" / "integration"
CONFTEST_FILE  = PROJECT_ROOT / "tests" / "conftest.py"

_tldr = sh.Command("tldr")


# ── data models ───────────────────────────────────────────────────────────

@dataclasses.dataclass(frozen=True)
class TreeNode:
    name:     str
    type:     str            # "dir" | "file"
    children: list[dict]     # raw child dicts; empty for file nodes
    path:     str | None     # relative path; only present on file nodes


@dataclasses.dataclass(frozen=True)
class StructureResult:
    root:     str
    language: str
    files:    list[dict]     # {path, classes, method_infos, imports, definitions}


@dataclasses.dataclass(frozen=True)
class ExtractResult:
    file_path: str
    language:  str
    docstring: str
    imports:   list[dict]
    functions: list[dict]
    classes:   list[dict]
    constants: list[dict]


@dataclasses.dataclass(frozen=True)
class ImportsResult:
    file:     str
    language: str
    imports:  list[dict]


@dataclasses.dataclass(frozen=True)
class ImportersResult:
    module:    str
    importers: list[dict]
    total:     int


# ── parsers ───────────────────────────────────────────────────────────────

def parse_tree(raw: str) -> TreeNode:
    data = json.loads(raw)
    return TreeNode(
        name=data["name"],
        type=data["type"],
        children=data.get("children", []),
        path=data.get("path"),
    )


def parse_structure(raw: str) -> StructureResult:
    data = json.loads(raw)
    return StructureResult(root=data["root"], language=data["language"], files=data["files"])


def parse_extract(raw: str) -> ExtractResult:
    data = json.loads(raw)
    return ExtractResult(
        file_path=data["file_path"],
        language=data["language"],
        docstring=data.get("docstring", ""),
        imports=data.get("imports", []),
        functions=data.get("functions", []),
        classes=data.get("classes", []),
        constants=data.get("constants", []),
    )


def parse_imports(raw: str) -> ImportsResult:
    data = json.loads(raw)
    return ImportsResult(file=data["file"], language=data["language"], imports=data["imports"])


def parse_importers(raw: str) -> ImportersResult:
    data = json.loads(raw)
    return ImportersResult(module=data["module"], importers=data["importers"], total=data["total"])


# ── fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="class")
def tree_result() -> TreeNode:
    return parse_tree(str(_tldr("tree", "--format", "json", str(INTEGRATION_DIR))))


@pytest.fixture(scope="class")
def structure_result() -> StructureResult:
    return parse_structure(str(_tldr("structure", "--format", "json", str(INTEGRATION_DIR))))


@pytest.fixture(scope="class")
def extract_result() -> ExtractResult:
    return parse_extract(str(_tldr("extract", "--format", "json", str(CONFTEST_FILE))))


@pytest.fixture(scope="class")
def imports_result() -> ImportsResult:
    return parse_imports(str(_tldr("imports", "--format", "json", str(CONFTEST_FILE))))


@pytest.fixture(scope="class")
def importers_result() -> ImportersResult:
    return parse_importers(str(_tldr("importers", "--format", "json", "pytest", str(INTEGRATION_DIR))))


# ── helpers ───────────────────────────────────────────────────────────────

def _check_schema(items: list[dict], required: dict[str, type], label: str) -> None:
    """Assert every item in a list has the required fields with the right types."""
    for i, item in enumerate(items):
        for field, expected_type in required.items():
            assert field in item, msg(
                f"{label}[{i}] missing field '{field}'",
                item=item,
            )
            assert isinstance(item[field], expected_type), msg(
                f"{label}[{i}].{field} has wrong type",
                expected=expected_type.__name__,
                actual=type(item[field]).__name__,
                value=item[field],
            )


# ── tests ─────────────────────────────────────────────────────────────────

class TestTree:
    """tldr tree — directory tree structure."""

    def test_root_has_name_and_type(self, tree_result):
        assert isinstance(tree_result.name, str) and tree_result.name, msg(
            "Root 'name' is not a non-empty string", name=repr(tree_result.name),
        )
        assert tree_result.type in ("dir", "file"), msg(
            "Root 'type' is not 'dir' or 'file'", type=tree_result.type,
        )

    def test_dir_node_has_children_list(self, tree_result):
        if tree_result.type == "dir":
            assert isinstance(tree_result.children, list), msg(
                "Dir node 'children' is not a list", actual=type(tree_result.children).__name__,
            )

    def test_children_non_empty(self, tree_result):
        assert tree_result.children, msg(
            "Tree has no children — target directory appears empty",
            path=INTEGRATION_DIR,
        )

    def test_each_child_has_name_and_type(self, tree_result):
        _check_schema(tree_result.children, {"name": str, "type": str}, "child")

    def test_file_children_have_path(self, tree_result):
        file_nodes = [c for c in tree_result.children if c.get("type") == "file"]
        _check_schema(file_nodes, {"path": str}, "file-child")

    def test_captured_values(self, tree_result, capsys):
        with capsys.disabled():
            print(f"\n  name     : {tree_result.name}")
            print(f"  type     : {tree_result.type}")
            print(f"  children : {[c['name'] for c in tree_result.children]}")


class TestStructure:
    """tldr structure — file structure across a directory."""

    def test_top_level_fields(self, structure_result):
        assert isinstance(structure_result.root, str) and structure_result.root, msg(
            "'root' is not a non-empty string",
        )
        assert isinstance(structure_result.language, str) and structure_result.language, msg(
            "'language' is not a non-empty string",
        )
        assert isinstance(structure_result.files, list), msg(
            "'files' is not a list",
        )

    def test_files_non_empty(self, structure_result):
        assert structure_result.files, msg(
            "structure returned no files", root=structure_result.root,
        )

    def test_each_file_has_required_keys(self, structure_result):
        required = {"path", "classes", "method_infos", "imports", "definitions"}
        for f in structure_result.files:
            missing = required - set(f)
            assert not missing, msg(
                "File entry missing required keys",
                path=f.get("path"),
                missing=missing,
            )

    def test_method_info_schema(self, structure_result):
        all_methods = [m for f in structure_result.files for m in f.get("method_infos", [])]
        _check_schema(all_methods, {"name": str, "signature": str, "line": int, "line_end": int}, "method_info")

    def test_import_schema(self, structure_result):
        all_imports = [i for f in structure_result.files for i in f.get("imports", [])]
        _check_schema(all_imports, {"module": str, "is_from": bool}, "import")

    def test_definition_schema(self, structure_result):
        all_defs = [d for f in structure_result.files for d in f.get("definitions", [])]
        _check_schema(all_defs, {"name": str, "kind": str, "line_start": int, "line_end": int}, "definition")

    def test_captured_values(self, structure_result, capsys):
        with capsys.disabled():
            print(f"\n  root     : {structure_result.root}")
            print(f"  language : {structure_result.language}")
            print(f"  files    : {len(structure_result.files)}")
            for f in structure_result.files:
                print(f"    {f['path']:30s}  "
                      f"classes={len(f['classes'])}  "
                      f"methods={len(f['method_infos'])}")


class TestExtract:
    """tldr extract — complete module info from a single file."""

    def test_top_level_fields(self, extract_result):
        assert isinstance(extract_result.file_path, str) and extract_result.file_path, msg(
            "'file_path' is not a non-empty string",
        )
        assert isinstance(extract_result.language, str) and extract_result.language, msg(
            "'language' is not a non-empty string",
        )
        for field, val in [("imports", extract_result.imports),
                           ("functions", extract_result.functions),
                           ("classes", extract_result.classes),
                           ("constants", extract_result.constants)]:
            assert isinstance(val, list), msg(f"'{field}' is not a list", actual=type(val).__name__)

    def test_imports_schema(self, extract_result):
        _check_schema(extract_result.imports, {"module": str, "is_from": bool}, "import")

    def test_functions_schema(self, extract_result):
        _check_schema(
            extract_result.functions,
            {"name": str, "params": list, "is_method": bool, "is_async": bool, "line": int, "line_end": int},
            "function",
        )

    def test_constants_schema(self, extract_result):
        _check_schema(extract_result.constants, {"name": str, "line": int, "line_end": int}, "constant")

    def test_captured_values(self, extract_result, capsys):
        with capsys.disabled():
            print(f"\n  file_path : {extract_result.file_path}")
            print(f"  language  : {extract_result.language}")
            print(f"  imports   : {len(extract_result.imports)}")
            print(f"  functions : {len(extract_result.functions)}")
            print(f"  classes   : {len(extract_result.classes)}")
            print(f"  constants : {len(extract_result.constants)}")


class TestImports:
    """tldr imports — import statements from a single file."""

    def test_top_level_fields(self, imports_result):
        assert isinstance(imports_result.file, str) and imports_result.file, msg(
            "'file' is not a non-empty string",
        )
        assert isinstance(imports_result.language, str) and imports_result.language, msg(
            "'language' is not a non-empty string",
        )
        assert isinstance(imports_result.imports, list), msg(
            "'imports' is not a list",
        )

    def test_imports_non_empty(self, imports_result):
        assert imports_result.imports, msg(
            "imports returned empty list — target file has no imports",
            file=imports_result.file,
        )

    def test_each_import_schema(self, imports_result):
        _check_schema(imports_result.imports, {"module": str, "is_from": bool}, "import")

    def test_captured_values(self, imports_result, capsys):
        with capsys.disabled():
            print(f"\n  file     : {imports_result.file}")
            print(f"  language : {imports_result.language}")
            print(f"  imports  : {[i['module'] for i in imports_result.imports]}")


class TestImporters:
    """tldr importers — find all files that import a given module."""

    def test_top_level_fields(self, importers_result):
        assert isinstance(importers_result.module, str) and importers_result.module, msg(
            "'module' is not a non-empty string",
        )
        assert isinstance(importers_result.importers, list), msg(
            "'importers' is not a list",
        )
        assert isinstance(importers_result.total, int), msg(
            "'total' is not an int",
        )

    def test_total_equals_list_length(self, importers_result):
        assert importers_result.total == len(importers_result.importers), msg(
            "'total' does not match length of 'importers' list",
            total=importers_result.total,
            list_len=len(importers_result.importers),
        )

    def test_importers_non_empty(self, importers_result):
        assert importers_result.importers, msg(
            "importers returned empty list",
            module=importers_result.module,
            path=INTEGRATION_DIR,
        )

    def test_each_importer_schema(self, importers_result):
        _check_schema(
            importers_result.importers,
            {"file": str, "line": int, "import_statement": str},
            "importer",
        )

    def test_importer_line_numbers_positive(self, importers_result):
        bad = [i for i in importers_result.importers if i["line"] <= 0]
        assert not bad, msg(
            "Some importers have non-positive line numbers",
            bad=bad,
        )

    def test_captured_values(self, importers_result, capsys):
        with capsys.disabled():
            print(f"\n  module   : {importers_result.module}")
            print(f"  total    : {importers_result.total}")
            for i in importers_result.importers:
                print(f"    line {i['line']:3d}  {Path(i['file']).name}")
