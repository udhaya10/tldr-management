"""
Pydantic models for tldr CLI JSON responses.

Each model mirrors one command's output shape exactly.
model_validate(json.loads(raw)) both parses and validates in a single call —
a ValidationError means the response shape changed or is malformed.

extra="ignore" on every model: new fields added by future tldr versions
are silently ignored so tests don't break on upgrades.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

_cfg = ConfigDict(extra="ignore")

# Reusable constraint — all source line numbers must be >= 1
LineNumber = Annotated[int, Field(ge=1)]


# ── Shared ────────────────────────────────────────────────────────────────

class ImportItem(BaseModel):
    """One import statement — shared by structure, extract, and imports."""
    model_config = _cfg

    module:  str
    is_from: bool
    names:   list[str] = []   # populated only for "from x import a, b"


# ── tree ──────────────────────────────────────────────────────────────────

class TreeNode(BaseModel):
    """Recursive node returned by `tldr tree`."""
    model_config = _cfg

    name:     str
    type:     str                    # "dir" | "file"
    children: list["TreeNode"] = []  # present on dir nodes
    path:     str | None = None      # present on file nodes

TreeNode.model_rebuild()             # required for self-referential model


# ── structure ─────────────────────────────────────────────────────────────

class MethodInfo(BaseModel):
    model_config = _cfg

    name:      str
    signature: str
    line:      LineNumber
    line_end:  LineNumber


class Definition(BaseModel):
    model_config = _cfg

    name:      str
    kind:      str
    line_start: LineNumber
    line_end:  LineNumber
    signature: str


class StructureFile(BaseModel):
    model_config = _cfg

    path:         str
    classes:      list[str]
    method_infos: list[MethodInfo]
    imports:      list[ImportItem]
    definitions:  list[Definition]


class StructureResult(BaseModel):
    model_config = _cfg

    root:     str
    language: str
    files:    list[StructureFile]


# ── extract ───────────────────────────────────────────────────────────────

class FunctionInfo(BaseModel):
    model_config = _cfg

    name:        str
    params:      list[str]
    is_method:   bool
    is_async:    bool
    line:        LineNumber
    line_end:    LineNumber
    return_type: str | None = None
    docstring:   str | None = None
    decorators:  list[str] = []


class ClassField(BaseModel):
    model_config = _cfg

    name:        str
    field_type:  str
    is_static:   bool
    is_constant: bool
    visibility:  str
    line:        LineNumber
    line_end:    LineNumber


class ClassInfo(BaseModel):
    model_config = _cfg

    name:       str
    fields:     list[ClassField] = []
    decorators: list[str] = []
    line:       LineNumber
    line_end:   LineNumber


class ConstantInfo(BaseModel):
    model_config = _cfg

    name:          str
    line:          LineNumber
    line_end:      LineNumber
    default_value: str | None = None
    is_static:     bool = False
    is_constant:   bool = False


class ExtractResult(BaseModel):
    model_config = _cfg

    file_path: str
    language:  str
    docstring: str = ""
    imports:   list[ImportItem]
    functions: list[FunctionInfo]
    classes:   list[ClassInfo]
    constants: list[ConstantInfo]


# ── imports ───────────────────────────────────────────────────────────────

class ImportsResult(BaseModel):
    model_config = _cfg

    file:     str
    language: str
    imports:  list[ImportItem]


# ── importers ─────────────────────────────────────────────────────────────

class Importer(BaseModel):
    model_config = _cfg

    file:             str
    line:             LineNumber
    import_statement: str


class ImportersResult(BaseModel):
    model_config = _cfg

    module:    str
    importers: list[Importer]
    total:     int

    @model_validator(mode="after")
    def total_matches_list(self) -> "ImportersResult":
        if self.total != len(self.importers):
            raise ValueError(
                f"total={self.total} does not match len(importers)={len(self.importers)}"
            )
        return self


# ── search ────────────────────────────────────────────────────────────────

class SearchResult(BaseModel):
    model_config = _cfg

    name:          str
    kind:          str
    file:          str
    line_range:    Annotated[list[int], Field(min_length=2, max_length=2)]
    signature:     str
    callers:       list[str] = []
    callees:       list[str] = []
    score:         float
    matched_terms: list[str] = []
    preview:       str = ""


class SearchResponse(BaseModel):
    model_config = _cfg

    query:   str
    results: list[SearchResult]


# ── context ───────────────────────────────────────────────────────────────

class ContextFunction(BaseModel):
    model_config = _cfg

    name:       str
    file:       str
    line:       LineNumber
    signature:  str
    calls:      list[str] = []
    blocks:     int
    cyclomatic: int


class ContextResult(BaseModel):
    model_config = _cfg

    entry_point: str
    depth:       int
    functions:   list[ContextFunction]


# ── semantic ──────────────────────────────────────────────────────────────

class SemanticResult(BaseModel):
    model_config = _cfg

    file_path:     str
    function_name: str | None = None
    class_name:    str | None = None
    score:         float
    line_start:    LineNumber
    line_end:      LineNumber
    snippet:       str


class SemanticResponse(BaseModel):
    model_config = _cfg

    query:         str
    results:       list[SemanticResult]
    total_results: int

    @model_validator(mode="after")
    def total_matches_list(self) -> "SemanticResponse":
        if self.total_results != len(self.results):
            raise ValueError(
                f"total_results={self.total_results} does not match len(results)={len(self.results)}"
            )
        return self


# ── similar ───────────────────────────────────────────────────────────────

class SimilarFile(BaseModel):
    model_config = _cfg

    file_path:      str
    total_score:    float
    matched_chunks: int
    avg_score:      float


class SimilarResult(BaseModel):
    model_config = _cfg

    source_file:   str
    source_chunks: int
    model:         str
    similar_files: list[SimilarFile]
