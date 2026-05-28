"""
L1 (AST) integration tests.

Tests all five L1 commands against stable, always-present project source:
  tree        — directory tree structure
  structure   — file structure (functions, classes, imports, definitions)
  extract     — complete module info from a single file
  imports     — import statements from a single file
  importers   — files that import a given module

All L1 commands are purely AST-based: no daemon, no call-graph cache,
no fixture prep required — they just parse source on disk.

Test targets (stable, always present):
  directory : tests/integration/   (5 Python files with classes and methods)
  file      : tests/conftest.py    (imports, functions, constants, docstring)
  module    : pytest               (imported by every test file)
"""

import dataclasses
import json
from pathlib import Path

import pytest
import sh

from tests.conftest import msg, requires_tldr

pytestmark = [pytest.mark.integration, requires_tldr]

PROJECT_ROOT = Path(__file__).parent.parent.parent
INTEGRATION_DIR = PROJECT_ROOT / "tests" / "integration"
CONFTEST_FILE = PROJECT_ROOT / "tests" / "conftest.py"

_tldr = sh.Command("tldr")


# ── data models ───────────────────────────────────────────────────────────


@dataclasses.dataclass(frozen=True)
class TreeNode:
    name: str
    type: str                  # "dir" | "file"
    children: list[dict]       # raw child dicts; empty for file nodes
    path: str | None           # relative path; only set for file nodes


@dataclasses.dataclass(frozen=True)
class StructureResult:
    root:     str
    language: str
    files:    list[dict]       # list of {path, classes, method_infos, imports, definitions}


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
    return StructureResult(
        root=data["root"],
        language=data["language"],
        files=data["files"],
    )


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
    return ImportsResult(
        file=data["file"],
        language=data["language"],
        imports=data["imports"],
    )


def parse_importers(raw: str) -> ImportersResult:
    data = json.loads(raw)
    return ImportersResult(
        module=data["module"],
        importers=data["importers"],
        total=data["total"],
    )


# ── fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(scope="class")
def tree_result() -> TreeNode:
    raw = _tldr("tree", "--format", "json", str(INTEGRATION_DIR))
    return parse_tree(str(raw))


@pytest.fixture(scope="class")
def structure_result() -> StructureResult:
    raw = _tldr("structure", "--format", "json", str(INTEGRATION_DIR))
    return parse_structure(str(raw))


@pytest.fixture(scope="class")
def extract_result() -> ExtractResult:
    raw = _tldr("extract", "--format", "json", str(CONFTEST_FILE))
    return parse_extract(str(raw))


@pytest.fixture(scope="class")
def imports_result() -> ImportsResult:
    raw = _tldr("imports", "--format", "json", str(CONFTEST_FILE))
    return parse_imports(str(raw))


@pytest.fixture(scope="class")
def importers_result() -> ImportersResult:
    raw = _tldr("importers", "--format", "json", "pytest", str(INTEGRATION_DIR))
    return parse_importers(str(raw))


# ── tests ─────────────────────────────────────────────────────────────────


class TestTree:
    """tldr tree — directory tree structure."""

    def test_root_type_is_dir(self, tree_result):
        assert tree_result.type == "dir", msg(
            "Root node is not a directory",
            type=tree_result.type,
            name=tree_result.name,
        )

    def test_root_name(self, tree_result):
        assert tree_result.name == "integration", msg(
            "Root name does not match scanned directory",
            actual=tree_result.name,
            expected="integration",
        )

    def test_children_present(self, tree_result):
        assert tree_result.children, msg(
            "Tree root has no children",
            path=INTEGRATION_DIR,
        )

    def test_known_file_in_children(self, tree_result):
        names = [c["name"] for c in tree_result.children]
        assert "test_daemon.py" in names, msg(
            "Expected file not found in tree",
            expected="test_daemon.py",
            found=names,
        )

    def test_each_child_has_name_and_type(self, tree_result):
        bad = [c for c in tree_result.children if "name" not in c or "type" not in c]
        assert not bad, msg(
            "Some tree children are missing 'name' or 'type'",
            bad_nodes=bad,
        )

    def test_captured_values(self, tree_result, capsys):
        with capsys.disabled():
            print(f"\n  name     : {tree_result.name}")
            print(f"  type     : {tree_result.type}")
            print(f"  children : {[c['name'] for c in tree_result.children]}")


class TestStructure:
    """tldr structure — file structure across a directory."""

    def test_language_is_python(self, structure_result):
        assert structure_result.language == "python", msg(
            "Language auto-detection failed",
            actual=structure_result.language,
            expected="python",
        )

    def test_files_non_empty(self, structure_result):
        assert structure_result.files, msg(
            "structure returned no files",
            root=structure_result.root,
        )

    def test_each_file_has_required_fields(self, structure_result):
        required = {"path", "classes", "method_infos", "imports", "definitions"}
        bad = [f for f in structure_result.files if not required.issubset(f)]
        assert not bad, msg(
            "Some files are missing required fields",
            missing_fields=[required - set(f) for f in bad],
            files=[f.get("path") for f in bad],
        )

    def test_classes_detected(self, structure_result):
        files_with_classes = [f for f in structure_result.files if f["classes"]]
        assert files_with_classes, msg(
            "No classes detected in any file — expected test classes",
            root=structure_result.root,
        )

    def test_methods_detected(self, structure_result):
        files_with_methods = [f for f in structure_result.files if f["method_infos"]]
        assert files_with_methods, msg(
            "No methods detected in any file — expected test methods",
            root=structure_result.root,
        )

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

    def test_language_is_python(self, extract_result):
        assert extract_result.language == "python", msg(
            "Language not detected correctly",
            actual=extract_result.language,
        )

    def test_file_path_matches_target(self, extract_result):
        assert Path(extract_result.file_path).name == CONFTEST_FILE.name, msg(
            "Returned file_path does not match input file",
            actual=extract_result.file_path,
            expected=CONFTEST_FILE.name,
        )

    def test_docstring_present(self, extract_result):
        assert extract_result.docstring.strip(), msg(
            "Module docstring is empty — conftest.py has a module docstring",
            file_path=extract_result.file_path,
        )

    def test_functions_detected(self, extract_result):
        names = [f["name"] for f in extract_result.functions]
        assert "msg" in names, msg(
            "'msg' function not found in extract output",
            found=names,
        )

    def test_imports_include_pytest(self, extract_result):
        modules = [i["module"] for i in extract_result.imports]
        assert "pytest" in modules, msg(
            "'pytest' not found in imports",
            found=modules,
        )

    def test_constants_detected(self, extract_result):
        names = [c["name"] for c in extract_result.constants]
        assert "PROJECT_ROOT" in names, msg(
            "'PROJECT_ROOT' constant not found",
            found=names,
        )

    def test_captured_values(self, extract_result, capsys):
        with capsys.disabled():
            print(f"\n  file_path  : {extract_result.file_path}")
            print(f"  language   : {extract_result.language}")
            print(f"  functions  : {[f['name'] for f in extract_result.functions]}")
            print(f"  imports    : {[i['module'] for i in extract_result.imports]}")
            print(f"  constants  : {[c['name'] for c in extract_result.constants]}")


class TestImports:
    """tldr imports — import statements from a single file."""

    def test_language_is_python(self, imports_result):
        assert imports_result.language == "python", msg(
            "Language not detected correctly",
            actual=imports_result.language,
        )

    def test_file_field_present(self, imports_result):
        assert imports_result.file, msg(
            "imports response 'file' field is empty",
        )

    def test_imports_non_empty(self, imports_result):
        assert imports_result.imports, msg(
            "imports returned empty list for conftest.py",
            file=imports_result.file,
        )

    def test_known_module_present(self, imports_result):
        modules = [i["module"] for i in imports_result.imports]
        assert "pytest" in modules, msg(
            "'pytest' not found in imports list",
            found=modules,
        )

    def test_response_is_envelope_not_legacy_array(self, imports_result):
        # Verify the envelope shape was returned (not --legacy-array bare list)
        assert isinstance(imports_result.imports, list), msg(
            "imports field is not a list",
            type=type(imports_result.imports).__name__,
        )
        assert imports_result.file, msg(
            "Envelope 'file' field missing — may have received legacy-array shape",
        )

    def test_captured_values(self, imports_result, capsys):
        with capsys.disabled():
            print(f"\n  file     : {imports_result.file}")
            print(f"  language : {imports_result.language}")
            print(f"  imports  : {[i['module'] for i in imports_result.imports]}")


class TestImporters:
    """tldr importers — find all files that import a given module."""

    def test_module_field(self, importers_result):
        assert importers_result.module == "pytest", msg(
            "Response 'module' field does not match query",
            actual=importers_result.module,
            expected="pytest",
        )

    def test_importers_non_empty(self, importers_result):
        assert importers_result.total > 0, msg(
            "No importers found for 'pytest' in integration dir",
            path=INTEGRATION_DIR,
        )

    def test_total_matches_list_length(self, importers_result):
        assert importers_result.total == len(importers_result.importers), msg(
            "total field does not match length of importers list",
            total=importers_result.total,
            list_len=len(importers_result.importers),
        )

    def test_known_importer_present(self, importers_result):
        files = [Path(i["file"]).name for i in importers_result.importers]
        assert "test_daemon.py" in files, msg(
            "test_daemon.py not found in importers of pytest",
            found=files,
        )

    def test_import_statement_present(self, importers_result):
        missing_stmt = [i for i in importers_result.importers if not i.get("import_statement")]
        assert not missing_stmt, msg(
            "Some importers are missing the import_statement field",
            bad=missing_stmt,
        )

    def test_line_numbers_positive(self, importers_result):
        bad = [i for i in importers_result.importers if i.get("line", 0) <= 0]
        assert not bad, msg(
            "Some importers have non-positive line numbers",
            bad=bad,
        )

    def test_captured_values(self, importers_result, capsys):
        with capsys.disabled():
            print(f"\n  module     : {importers_result.module}")
            print(f"  total      : {importers_result.total}")
            for i in importers_result.importers:
                print(f"    line {i['line']:3d}  {i['file']}")
