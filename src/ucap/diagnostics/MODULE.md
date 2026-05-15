# diagnostics

**Purpose**
Owns the chat-mediated debugging vocabulary for ucap: error-code registry, three compact report types (RPT / MET / QC), and the fixed-field QC template machinery. Every other module imports from here; this imports nothing else from ucap. Serves FR-10, FR-11, NFR-4, NFR-5, NFR-7. Concrete implementation of `[D-011]`; downstream contract for `[D-009]` (error-code + report shape), `[D-010]` (CLI emit boundary), `[D-012]` (redaction wrap), `[D-013]` (output discipline).

**Public surface**

```python
__all__ = [
    "ErrorSeverity", "ErrorCode",
    "ReportType", "ReportRecord", "ReportWriter",
    "QCField", "QCTemplate",
    "Redactor", "REDACTION_CATEGORIES",
    "get_code", "format_code",
    "PREFIX_REGISTRY", "ERROR_CODES", "QC_REGISTRY",
]

class ErrorSeverity(str, Enum):
    ERROR = "E"
    WARNING = "W"

@dataclass(frozen=True)
class ErrorCode:
    code: str           # "{PREFIX}-{E|W}{NNN}"
    message: str        # template; may contain {placeholders}
    severity: ErrorSeverity
    deprecated: bool = False

PREFIX_REGISTRY: dict[str, str]    # 3-letter prefix -> module name; 5 entries at v1
ERROR_CODES: dict[str, ErrorCode]  # code -> ErrorCode; pre-populated at module load

def get_code(code: str) -> ErrorCode: ...
def format_code(code: str, **kwargs: str) -> str: ...

class ReportType(str, Enum):
    RPT = "RPT"   # run / parse activity
    MET = "MET"   # timing + counts
    QC  = "QC"    # fixed-field quality check

@dataclass(frozen=True)
class ReportRecord:
    report_type: ReportType
    module_prefix: str            # must be in PREFIX_REGISTRY
    run_id: str                   # UUIDv4 default; CLI-overridable
    timestamp: datetime           # UTC, ISO-8601 serialized
    fields: dict[str, int | float | bool | str]
    def to_line(self) -> str: ...
    @classmethod
    def from_line(cls, line: str) -> "ReportRecord": ...

class ReportWriter:
    def __init__(
        self,
        module_prefix: str,
        run_id: str,
        redactor: "Redactor" = Redactor.empty(),
        template: "QCTemplate | None" = None,
    ) -> None: ...
    @property
    def buffer_length(self) -> int: ...
    def emit(self, record: ReportRecord) -> None: ...
    def flush(self, dest: TextIO | None = None) -> None: ...   # late-binds sys.stdout
    def __enter__(self) -> "ReportWriter": ...
    def __exit__(self, exc_type, exc_val, exc_tb) -> None: ...

REDACTION_CATEGORIES: tuple[str, ...] = ("DEV", "FW", "OP", "ID", "PATH", "SESS")

@dataclass(frozen=True)
class Redactor:
    mappings: tuple[tuple[str, str], ...]   # (real, placeholder) pairs, longest-first
    def apply(self, text: str) -> str: ...
    @classmethod
    def from_file(cls, path: Path) -> "Redactor": ...
    @classmethod
    def empty(cls) -> "Redactor": ...

@dataclass
class QCField:
    name: str
    field_type: Literal["int", "float", "bool", "enum"]
    enum_values: tuple[str, ...] | None = None   # required when field_type == "enum"

class QCTemplate:
    module_prefix: str
    artifact_type: str
    fields: tuple[QCField, ...]
    def validate_record(self, record: ReportRecord) -> list[str]: ...
    @classmethod
    def register(cls, template: "QCTemplate") -> None: ...

QC_REGISTRY: dict[str, QCTemplate]  # key: "{prefix-lower}:{artifact-type}"
```

**Invariants**

- **Leaf-node — no ucap imports.** `src/ucap/diagnostics/__init__.py` imports only stdlib (`dataclasses`, `enum`, `datetime`, `typing`, `sys`, `uuid`, `io`). Any `from ucap.*` import is a cycle and a hard error; enforced by `tests/test_diagnostics.py::test_no_ucap_imports` via AST scan.
- **No free-text in report fields by construction.** `str`-typed entries in `ReportRecord.fields` accept only registered error codes or bounded-enum tokens registered for the record's `(module_prefix, artifact_type)` via `QCTemplate`. `ReportWriter.emit` rejects unregistered strings at validation time. This is the constructive guarantee behind `NFR-4` and the load-bearing property of `NFR-7`.
- **`format_code(...)` is a thin wrapper around `str.format`** — no runtime rejection of placeholder values. The bounded-token discipline applies at the compact-report boundary (`ReportRecord.fields` → `ReportWriter.emit` → `QCTemplate.validate_record`), not at `format_code`. `format_code`'s primary callers emit human-readable error messages to stderr / log (where `{path}` in `CLI-E001` and `{field}` in `QCT-W001` legitimately carry unbounded values for debuggability); what reaches compact reports is governed by separate, more rigorous machinery. *Note 2026-05-14*: this refines D-011 #5's stricter wording — the load-bearing invariant ("no free-text in report fields") is unchanged, but the implementation detail about *how* it is enforced is corrected to the actual mechanism.
- **Defense-in-depth: redaction applied at line emit.** Every line produced by `record.to_line()` is passed through the configured `Redactor` before reaching the writer's buffer (no-op if `Redactor.empty()`). Substitution is longest-match-first over the JSON map's `(real → placeholder)` pairs. Placeholders match `<(DEV|FW|OP|ID|PATH|SESS)\d+>`. The redactor is loaded from `.ucap/state/<map>.json` via `--redact-with` (gitignored on-prem location per `NFR-6` and `[D-012]`).
- **Error codes are immutable.** Once `ERROR_CODES["XXX-EYYY"]` is registered with a `message` template, neither the code identifier nor the message template changes. Deprecation flips `deprecated: True`; codes are never renumbered, reused, or deleted.
- **All prefixes pre-registered at module load.** Loading `src/ucap/diagnostics/__init__.py` populates `PREFIX_REGISTRY` and `ERROR_CODES` to their full v1 content. A code's prefix not in `PREFIX_REGISTRY` raises `DGN-E002` at registry-load time. Collision (a prefix registered twice) raises `DGN-E001`.
- **`QCTemplate.register` is import-time only.** Templates land in `QC_REGISTRY` during module load; no runtime registration. This keeps the validation surface auditable from a single grep.

**Key choices**

- `[D-009]` — error-code format, report types, `ReportRecord` shape, pipe-delimited single-line serialization, prefix set.
- `[D-010]` — CLI flag mapping (`--diagnostic` / `--validate`) and the two pre-registered `QCTemplate`s for QCAT.
- `[D-011]` — this module's existence, sub-package-with-single-`__init__.py` layout, leaf-node invariant, registry pre-population, `QCT-E002`'s `{validation_failure}` bucketing rule.
- `[D-012]` — `Redactor` class, six placeholder categories, longest-match-first substitution at `emit()` over the serialized line, `--redact-with` CLI flag, map-is-read-only invariant. Adds `DGN-E004 Invalid redaction category in mapping: '{value}'` to `ERROR_CODES` (12 codes total).
- `[D-013]` — formal line grammar (TYPE|PREFIX|RUN_ID|TIMESTAMP|FIELD*), reserved characters (`|` and `\n` rejected at emit), 30-line-per-session cap (target 15) enforced at flush, lowercase snake_case field-name convention, timestamp format `YYYY-MM-DDTHH:MM:SSZ` (no microseconds, no offset). Defines emit-boundary enforcement order: validate → to_line → redact → buffer.
- `[D-008]` — platform-tier placement; future per-operator codes register via `customizations/`. Redaction maps explicitly do NOT live in `customizations/` — they stay on-prem under `.ucap/state/`.

**Non-goals**

- **Not a logging framework.** Modules use stdlib `logging` for verbose / debug-level diagnostics; `diagnostics` provides the compact pasteable schema for the chat-mediated debugging surface, not runtime log management.
- **Not a metrics store.** Prometheus / OpenTelemetry handle time-series metrics in projects that need them; `diagnostics` defines what to measure (`MET` records), not where to store it. ucap v1 doesn't need a metrics store at all.
- **Not a tracing system.** `run_id` in `ReportRecord` is a correlation handle for grouping records from one CLI invocation; it is not a span.
- **Not extensible at runtime.** No plugin loading, no late-registration. All registries are populated at import time; new content arrives via source changes, not configuration.

<!-- BEGIN:STRUCTURE -->
<!-- Regenerated by regen-map. Do not hand-edit. -->
<!-- END:STRUCTURE -->

**Depends on**
*(none — leaf node; stdlib only)*

**Depended on by**
- `src/ucap/MODULE.md` — `cli.py` uses `ReportWriter` / `ReportRecord` / `ReportType` for `--diagnostic` and `--validate` modes; `cli.py` raises prefixed `CLI-E???` errors via `format_code`.
- `src/ucap/adapters/MODULE.md` — each adapter raises prefixed errors (`QCT-E???`, `SHN-E???`, `ELT-E???`) and contributes counts / timings to `RPT` records; in `--validate` mode adapters surface invariants as `QC` field values.
- *(future)* `audit` / `diff` / `query` modules when those land.
