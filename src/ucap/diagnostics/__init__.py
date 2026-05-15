"""Diagnostics: error codes and compact report types for chat-mediated debugging.

Leaf-node module. Imports only stdlib; never imports from anywhere else in ucap.
This invariant is enforced by ``tests/test_diagnostics.py::test_no_ucap_imports``
via AST scan. See ``docs/compact/DECISIONS.md`` D-009, D-011, D-012, D-013.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TextIO


# ─── Severity + error-code model ────────────────────────────────────


class ErrorSeverity(str, Enum):
    """Severity of a registered error code (D-009).

    ``E`` = error (operation failed or produced invalid output).
    ``W`` = warning (operation succeeded but observed something noteworthy).
    No ``I`` (info) — info events use stdlib ``logging``, outside the
    chat-mediated debugging surface.
    """

    ERROR = "E"
    WARNING = "W"


@dataclass(frozen=True)
class ErrorCode:
    """A stable, registered error code per D-009.

    Format ``{PREFIX}-{E|W}{NNN}``: three-letter prefix from
    :data:`PREFIX_REGISTRY`, severity letter, three-digit number. Once
    registered, neither the code nor the message template changes. Deprecation
    flips ``deprecated=True``; codes are never renumbered, reused, or deleted.
    """

    code: str
    message: str
    severity: ErrorSeverity
    deprecated: bool = False


# ─── Prefix + code registries ───────────────────────────────────────


PREFIX_REGISTRY: dict[str, str] = {
    "QCT": "qcat",
    "SHN": "shannon",
    "ELT": "elt",
    "DGN": "diagnostics",
    "CLI": "cli",
}


ERROR_CODES: dict[str, ErrorCode] = {
    # diagnostics self-checks
    "DGN-E001": ErrorCode(
        "DGN-E001",
        "Duplicate prefix '{prefix}' registered",
        ErrorSeverity.ERROR,
    ),
    "DGN-E002": ErrorCode(
        "DGN-E002",
        "Unknown error code '{code}' referenced",
        ErrorSeverity.ERROR,
    ),
    "DGN-E003": ErrorCode(
        "DGN-E003",
        "Invalid QCField type '{ft}' (allowed: int, float, bool, enum)",
        ErrorSeverity.ERROR,
    ),
    "DGN-E004": ErrorCode(
        "DGN-E004",
        "Invalid redaction category in mapping: '{value}'",
        ErrorSeverity.ERROR,
    ),
    "DGN-W001": ErrorCode(
        "DGN-W001",
        "Module '{module}' has no QCTemplate registered",
        ErrorSeverity.WARNING,
    ),
    # QCAT adapter
    "QCT-E001": ErrorCode(
        "QCT-E001",
        "Failed to parse QCAT message at line {line}",
        ErrorSeverity.ERROR,
    ),
    "QCT-E002": ErrorCode(
        "QCT-E002",
        "Canonical-output validation failed for message at line {line}: {validation_failure}",
        ErrorSeverity.ERROR,
    ),
    "QCT-W001": ErrorCode(
        "QCT-W001",
        "Unmapped top-level field '{field}' in container '{container}'",
        ErrorSeverity.WARNING,
    ),
    # Shannon DM adapter
    "SHN-E001": ErrorCode(
        "SHN-E001",
        "Shannon DM adapter not implemented — sample log needed",
        ErrorSeverity.ERROR,
    ),
    # ELT adapter
    "ELT-E001": ErrorCode(
        "ELT-E001",
        "ELT adapter not implemented — sample log needed",
        ErrorSeverity.ERROR,
    ),
    # CLI dispatcher
    "CLI-E001": ErrorCode(
        "CLI-E001",
        "Input file not found: {path}",
        ErrorSeverity.ERROR,
    ),
    "CLI-E002": ErrorCode(
        "CLI-E002",
        "Unsupported vendor '{vendor}' (valid: qcat, shannon, elt)",
        ErrorSeverity.ERROR,
    ),
}


def _validate_registries() -> None:
    """Foreign-key check at module load: every ERROR_CODES prefix is in PREFIX_REGISTRY."""
    for code in ERROR_CODES:
        prefix = code.split("-", 1)[0]
        if prefix not in PREFIX_REGISTRY:
            raise RuntimeError(
                f"Error code '{code}' has prefix '{prefix}' not in PREFIX_REGISTRY. "
                f"Register the prefix before adding codes that use it (D-011)."
            )


_validate_registries()


# ─── Registry accessors ─────────────────────────────────────────────


def get_code(code: str) -> ErrorCode:
    """Look up a registered error code.

    Raises ``KeyError`` carrying the DGN-E002 message template if ``code`` is
    not registered.
    """
    if code not in ERROR_CODES:
        raise KeyError(ERROR_CODES["DGN-E002"].message.format(code=code))
    return ERROR_CODES[code]


def format_code(code: str, **kwargs: object) -> str:
    """Format a registered code's message template with the given placeholders.

    Thin wrapper around :meth:`str.format`. No runtime rejection of placeholder
    values — bounded-token discipline lives at the compact-report boundary
    (:class:`ReportWriter.emit` + :class:`QCTemplate.validate_record`), not
    here. Primary callers emit human-readable messages to stderr / log where
    unbounded placeholders (paths, field names) are legitimate. See MODULE.md
    Invariants (2026-05-14 refinement of D-011 #5).
    """
    return get_code(code).message.format(**kwargs)


# ─── Report types + record (D-009 + D-013) ──────────────────────────


class ReportType(str, Enum):
    """Type tag for compact records (D-009).

    ``RPT`` — run / parse activity report. What happened, pass / fail, counts.
    ``MET`` — metrics: timing, rates, queue depths.
    ``QC``  — quality check: fixed-field, int / float / bool / bounded-enum only.
    """

    RPT = "RPT"
    MET = "MET"
    QC = "QC"


_TIMESTAMP_FMT = "%Y-%m-%dT%H:%M:%SZ"
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_PREFIX_RE = re.compile(r"^[A-Z]{3}$")
_FIELD_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _format_value(value: object) -> str:
    """Serialize a field value to its on-the-wire form per D-013 grammar."""
    if isinstance(value, bool):
        # bool BEFORE int — Python's bool is a subclass of int.
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    raise TypeError(
        f"Field value of type {type(value).__name__} not supported "
        f"(allowed: int, float, bool, str — D-013 grammar)"
    )


def _parse_value(s: str) -> int | float | bool | str:
    """Parse a field value from its on-the-wire form into Python type."""
    if s == "true":
        return True
    if s == "false":
        return False
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


@dataclass(frozen=True)
class ReportRecord:
    """One compact report record — RPT, MET, or QC (D-009).

    Validates its shape at construction time so :meth:`to_line` never has to
    error-handle. The on-the-wire form is a single pipe-delimited line per the
    D-013 grammar; :meth:`to_line` and :meth:`from_line` are exact inverses.
    """

    report_type: ReportType
    module_prefix: str
    run_id: str
    timestamp: datetime
    fields: dict[str, int | float | bool | str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.report_type, ReportType):
            raise TypeError(
                f"report_type must be ReportType, got {type(self.report_type).__name__}"
            )
        if not _PREFIX_RE.match(self.module_prefix):
            raise ValueError(
                f"module_prefix '{self.module_prefix}' must be 3 uppercase ASCII letters"
            )
        if self.module_prefix not in PREFIX_REGISTRY:
            raise ValueError(
                f"module_prefix '{self.module_prefix}' not in PREFIX_REGISTRY "
                f"(register it before emitting records under that prefix — D-011)"
            )
        if not self.run_id:
            raise ValueError("run_id must be non-empty")
        if "|" in self.run_id or "\n" in self.run_id:
            raise ValueError(
                f"run_id must not contain '|' or newline (got {self.run_id!r}) — D-013"
            )
        if self.timestamp.tzinfo is None:
            raise ValueError(
                "timestamp must be timezone-aware (use datetime.now(tz=timezone.utc))"
            )
        for name, value in self.fields.items():
            if not _FIELD_NAME_RE.match(name):
                raise ValueError(
                    f"Field name '{name}' must match [a-z][a-z0-9_]* (D-013 grammar)"
                )
            if not isinstance(value, (int, float, bool, str)):
                raise TypeError(
                    f"Field '{name}': type {type(value).__name__} not supported "
                    f"(allowed: int, float, bool, str — D-013)"
                )
            if isinstance(value, str) and ("|" in value or "\n" in value):
                raise ValueError(
                    f"Field '{name}' value contains '|' or newline — D-013 reserved chars"
                )

    def to_line(self) -> str:
        """Serialize to a single pipe-delimited line per D-013 grammar."""
        ts = self.timestamp.astimezone(timezone.utc).strftime(_TIMESTAMP_FMT)
        parts = [
            self.report_type.value,
            self.module_prefix,
            self.run_id,
            ts,
        ]
        for name, value in self.fields.items():
            parts.append(f"{name}={_format_value(value)}")
        return "|".join(parts)

    @classmethod
    def from_line(cls, line: str) -> "ReportRecord":
        """Parse a pipe-delimited line back into a :class:`ReportRecord`.

        Accepts redacted lines (placeholders like ``<DEV0>`` in string field
        values) — the parse layer doesn't validate bounded-enum tokens; that
        is :class:`QCTemplate`'s job.
        """
        if "\n" in line:
            raise ValueError("Line must not contain newline characters")
        parts = line.split("|")
        if len(parts) < 4:
            raise ValueError(
                f"Line has fewer than 4 leading fields (TYPE|PREFIX|RUN_ID|TIMESTAMP): "
                f"{line!r}"
            )
        type_str, prefix, run_id, ts_str = parts[:4]
        try:
            report_type = ReportType(type_str)
        except ValueError as exc:
            raise ValueError(
                f"Unknown report type '{type_str}' (expected RPT, MET, or QC)"
            ) from exc
        if not _TIMESTAMP_RE.match(ts_str):
            raise ValueError(
                f"Timestamp '{ts_str}' does not match YYYY-MM-DDTHH:MM:SSZ"
            )
        timestamp = datetime.strptime(ts_str, _TIMESTAMP_FMT).replace(
            tzinfo=timezone.utc
        )
        fields: dict[str, int | float | bool | str] = {}
        for field_str in parts[4:]:
            if "=" not in field_str:
                raise ValueError(f"Field '{field_str}' has no '=' separator")
            name, _, value_str = field_str.partition("=")
            fields[name] = _parse_value(value_str)
        return cls(
            report_type=report_type,
            module_prefix=prefix,
            run_id=run_id,
            timestamp=timestamp,
            fields=fields,
        )


# ─── Redaction (D-012) ──────────────────────────────────────────────


REDACTION_CATEGORIES: tuple[str, ...] = ("DEV", "FW", "OP", "ID", "PATH", "SESS")

_PLACEHOLDER_RE = re.compile(
    r"^<(" + "|".join(REDACTION_CATEGORIES) + r")\d+>$"
)


@dataclass(frozen=True)
class Redactor:
    """Forward-substitution layer applied at report-emit time (D-012).

    The `mappings` tuple is sorted longest-real-first so multi-word reals
    match before their substrings. Loaded from an on-prem JSON file via
    :meth:`from_file`; gitignored under ``.ucap/state/`` per NFR-6.
    """

    mappings: tuple[tuple[str, str], ...] = ()

    def apply(self, text: str) -> str:
        """Apply forward substitution (real → placeholder) over `text`.

        Longest-match-first is preserved by ordering ``mappings`` longest-first;
        the regex alternation respects that order so a multi-word real matches
        before any substring it contains. A single ``re.sub`` pass ensures
        substituted segments are not re-scanned (no double-substitution risk).
        """
        if not self.mappings:
            return text
        pattern = "|".join(re.escape(real) for real, _ in self.mappings)
        replace_map = dict(self.mappings)
        return re.sub(pattern, lambda m: replace_map[m.group(0)], text)

    @classmethod
    def from_file(cls, path: Path) -> "Redactor":
        """Load a redaction map from `path`. Validates shape per D-012."""
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            raise ValueError(
                f"Redaction map must be a JSON object, got {type(data).__name__}"
            )
        if set(data.keys()) != {"version", "mappings"}:
            raise ValueError(
                f"Redaction map top-level keys must be exactly "
                f"'version' and 'mappings'; got {sorted(data.keys())}"
            )
        if data["version"] != 1:
            raise ValueError(
                f"Redaction map version must be 1; got {data['version']!r}"
            )
        mappings_dict = data["mappings"]
        if not isinstance(mappings_dict, dict):
            raise ValueError(
                f"'mappings' must be a JSON object; got {type(mappings_dict).__name__}"
            )
        seen_placeholders: set[str] = set()
        for real, placeholder in mappings_dict.items():
            if not isinstance(real, str) or not isinstance(placeholder, str):
                raise ValueError(
                    "Mapping pairs must be string → string; got "
                    f"{type(real).__name__} → {type(placeholder).__name__}"
                )
            if not _PLACEHOLDER_RE.match(placeholder):
                raise ValueError(format_code("DGN-E004", value=placeholder))
            if placeholder in seen_placeholders:
                raise ValueError(
                    f"Duplicate placeholder '{placeholder}' in redaction map "
                    f"(two real strings map to the same placeholder)"
                )
            seen_placeholders.add(placeholder)
        # Longest-real-first ordering so the regex alternation respects the
        # longest-match semantic.
        pairs = sorted(mappings_dict.items(), key=lambda p: -len(p[0]))
        return cls(mappings=tuple(pairs))

    @classmethod
    def empty(cls) -> "Redactor":
        """Identity redactor — `apply(text) == text`."""
        return cls(mappings=())


# ─── QC machinery (D-011) ───────────────────────────────────────────


_ALLOWED_FIELD_TYPES = ("int", "float", "bool", "enum")


@dataclass(frozen=True)
class QCField:
    """One field declaration in a :class:`QCTemplate` (D-011).

    The runtime check at construction is the compile-time-equivalent
    no-free-text enforcement: any ``field_type`` outside
    ``{int, float, bool, enum}`` raises ``DGN-E003`` at instantiation.
    """

    name: str
    field_type: str  # one of _ALLOWED_FIELD_TYPES
    enum_values: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if self.field_type not in _ALLOWED_FIELD_TYPES:
            raise TypeError(format_code("DGN-E003", ft=self.field_type))
        if self.field_type == "enum":
            if self.enum_values is None or len(self.enum_values) == 0:
                raise TypeError(
                    f"QCField '{self.name}' has field_type='enum' but no enum_values"
                )
        elif self.enum_values is not None:
            raise TypeError(
                f"QCField '{self.name}' (field_type='{self.field_type}') "
                f"cannot carry enum_values"
            )
        if not _FIELD_NAME_RE.match(self.name):
            raise ValueError(
                f"QCField name '{self.name}' must match [a-z][a-z0-9_]* (D-013)"
            )


@dataclass(frozen=True)
class QCTemplate:
    """Fixed-field schema for ReportRecord validation per ``(module_prefix, artifact_type)``.

    Registered globally in :data:`QC_REGISTRY`; :class:`ReportWriter` looks up the
    template for the writer's prefix + artifact_type and runs
    :meth:`validate_record` at emit time. See D-011.
    """

    module_prefix: str
    artifact_type: str
    fields: tuple[QCField, ...]

    def __post_init__(self) -> None:
        if self.module_prefix not in PREFIX_REGISTRY:
            raise ValueError(
                f"QCTemplate module_prefix '{self.module_prefix}' not in PREFIX_REGISTRY"
            )
        names = [f.name for f in self.fields]
        if len(set(names)) != len(names):
            raise ValueError(f"QCTemplate has duplicate field names: {names}")

    @classmethod
    def register(cls, template: "QCTemplate") -> None:
        """Add ``template`` to :data:`QC_REGISTRY` under ``'<module-name>:<artifact-type>'``.

        The module-name comes from :data:`PREFIX_REGISTRY` (e.g. ``QCT`` → ``qcat``),
        matching hilda's convention and the MODULE.md examples.

        Raises ``ValueError`` if the key is already registered — templates are
        registered at module-import time only; runtime re-registration is a bug.
        """
        key = f"{PREFIX_REGISTRY[template.module_prefix]}:{template.artifact_type}"
        if key in QC_REGISTRY:
            raise ValueError(f"QCTemplate '{key}' already registered")
        QC_REGISTRY[key] = template

    def validate_record(self, record: "ReportRecord") -> list[str]:
        """Return a list of validation errors against this template; empty = valid."""
        errors: list[str] = []
        declared = {f.name: f for f in self.fields}
        for declared_name in declared:
            if declared_name not in record.fields:
                errors.append(f"missing field: '{declared_name}'")
        for name, value in record.fields.items():
            if name not in declared:
                errors.append(f"unexpected field: '{name}'")
                continue
            qf = declared[name]
            if qf.field_type == "int":
                # bool is a subclass of int — reject explicitly.
                if isinstance(value, bool) or not isinstance(value, int):
                    errors.append(
                        f"field '{name}' must be int, got {type(value).__name__}"
                    )
            elif qf.field_type == "float":
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    errors.append(
                        f"field '{name}' must be float, got {type(value).__name__}"
                    )
            elif qf.field_type == "bool":
                if not isinstance(value, bool):
                    errors.append(
                        f"field '{name}' must be bool, got {type(value).__name__}"
                    )
            elif qf.field_type == "enum":
                if not isinstance(value, str):
                    errors.append(
                        f"field '{name}' enum value must be str, got {type(value).__name__}"
                    )
                elif qf.enum_values is None or value not in qf.enum_values:
                    errors.append(
                        f"field '{name}' value '{value}' not in enum {qf.enum_values}"
                    )
        return errors


QC_REGISTRY: dict[str, QCTemplate] = {}


# ─── Pre-registered v1 templates (D-010 B4 + B5) ────────────────────


_VENDOR_ENUM: tuple[str, ...] = ("qcat", "shannon", "elt")
_RELEASE_ENUM: tuple[str, ...] = ("rel15", "rel16", "rel17", "rel18")
_RESULT_ENUM: tuple[str, ...] = ("OK", "WARN", "FAIL")


QCTemplate.register(
    QCTemplate(
        module_prefix="QCT",
        artifact_type="parse_diagnostic",
        fields=(
            QCField("vendor", "enum", _VENDOR_ENUM),
            QCField("release", "enum", _RELEASE_ENUM),
            QCField("messages_parsed", "int"),
            QCField("combos_eutra", "int"),
            QCField("combos_nr", "int"),
            QCField("combos_mrdc", "int"),
            QCField("source_eutra_main", "int"),
            QCField("source_eutra_addr11", "int"),
            QCField("source_mrdc_main", "int"),
            QCField("source_mrdc_nedconly", "int"),
            QCField("source_mrdc_nrdc", "int"),
            QCField("kind_endc", "int"),
            QCField("kind_canr", "int"),
            QCField("kind_nedc", "int"),
            QCField("kind_nrdc", "int"),
            QCField("unmapped_top_level_count", "int"),
            QCField("hex_dump_stripped", "bool"),
            QCField("parse_ms_tokenize", "int"),
            QCField("parse_ms_tree", "int"),
            QCField("parse_ms_map", "int"),
            QCField("parse_ms_total", "int"),
            QCField("result", "enum", _RESULT_ENUM),
        ),
    )
)


QCTemplate.register(
    QCTemplate(
        module_prefix="QCT",
        artifact_type="parse_validation",
        fields=(
            QCField("vendor", "enum", _VENDOR_ENUM),
            QCField("release", "enum", _RELEASE_ENUM),
            QCField("schema_valid", "bool"),
            QCField("unknown_field_count", "int"),
            QCField("index_out_of_range_count", "int"),
            QCField("off_by_one_count", "int"),
            QCField("mrdc_rel16_handled", "bool"),
            QCField("bcs_parsed", "bool"),
            QCField("result", "enum", _RESULT_ENUM),
        ),
    )
)


# ─── Report writer (D-011 + D-013) ──────────────────────────────────


_MAX_RECORDS_PER_SESSION = 30  # D-013 #4


class ReportWriter:
    """Buffers :class:`ReportRecord` instances and flushes serialized lines.

    Emit pipeline (D-013): validate (against ``template`` if provided) → to_line
    → redact → buffer. The per-session cap (30 records, target 15 per D-013 #4)
    is checked at :meth:`flush`. Use as a context manager to auto-flush on
    successful exit; on exception, the buffer is dropped to avoid emitting
    partial output.
    """

    def __init__(
        self,
        module_prefix: str,
        run_id: str,
        redactor: Redactor = Redactor.empty(),
        template: QCTemplate | None = None,
    ) -> None:
        if module_prefix not in PREFIX_REGISTRY:
            raise ValueError(
                f"module_prefix '{module_prefix}' not in PREFIX_REGISTRY (D-011)"
            )
        if not run_id:
            raise ValueError("run_id must be non-empty")
        if template is not None and template.module_prefix != module_prefix:
            raise ValueError(
                f"template module_prefix '{template.module_prefix}' does not "
                f"match writer module_prefix '{module_prefix}'"
            )
        self._module_prefix = module_prefix
        self._run_id = run_id
        self._redactor = redactor
        self._template = template
        self._buffer: list[str] = []

    @property
    def buffer_length(self) -> int:
        """Number of records currently buffered (mostly for tests / introspection)."""
        return len(self._buffer)

    def emit(self, record: ReportRecord) -> None:
        """Validate, serialize, redact, and buffer one record."""
        if record.module_prefix != self._module_prefix:
            raise ValueError(
                f"emit: record module_prefix '{record.module_prefix}' "
                f"does not match writer's '{self._module_prefix}'"
            )
        if record.run_id != self._run_id:
            raise ValueError(
                f"emit: record run_id '{record.run_id}' "
                f"does not match writer's '{self._run_id}'"
            )
        if self._template is not None:
            errors = self._template.validate_record(record)
            if errors:
                module_name = PREFIX_REGISTRY[self._template.module_prefix]
                raise ValueError(
                    f"QCTemplate '{module_name}:{self._template.artifact_type}' "
                    f"validation failed: " + "; ".join(errors)
                )
        line = record.to_line()
        line = self._redactor.apply(line)
        self._buffer.append(line)

    def flush(self, dest: TextIO | None = None) -> None:
        """Write buffered records to ``dest`` (default: current ``sys.stdout``).

        Late-binds ``sys.stdout`` at call time rather than function-def time so
        test fixtures like pytest's ``capsys`` capture correctly.

        Raises ``ValueError`` if the buffer exceeds the 30-line per-session cap
        from D-013 #4.
        """
        if len(self._buffer) > _MAX_RECORDS_PER_SESSION:
            raise ValueError(
                f"ReportWriter buffer has {len(self._buffer)} records, "
                f"exceeds the {_MAX_RECORDS_PER_SESSION}-line per-session cap (D-013 #4)"
            )
        if dest is None:
            dest = sys.stdout
        for line in self._buffer:
            dest.write(line + "\n")
        self._buffer.clear()

    def __enter__(self) -> "ReportWriter":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        if exc_type is None:
            self.flush()
        else:
            # Drop buffered output on exception so partial reports don't reach
            # stdout. Caller's exception propagates.
            self._buffer.clear()


__all__ = [
    "ErrorSeverity",
    "ErrorCode",
    "PREFIX_REGISTRY",
    "ERROR_CODES",
    "get_code",
    "format_code",
    "ReportType",
    "ReportRecord",
    "REDACTION_CATEGORIES",
    "Redactor",
    "QCField",
    "QCTemplate",
    "QC_REGISTRY",
    "ReportWriter",
]
