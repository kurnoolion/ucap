"""Tests for the diagnostics module (D-009 / D-011 / D-012 / D-013)."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_DIAGNOSTICS_INIT = (
    Path(__file__).resolve().parents[1] / "src" / "ucap" / "diagnostics" / "__init__.py"
)


# ─── Leaf-node invariant (D-011) ────────────────────────────────────


def test_no_ucap_imports() -> None:
    """diagnostics is a leaf node — no imports from anywhere in ucap.

    Enforced via AST scan rather than runtime introspection so the failure
    surfaces with the offending import path, not a cycle traceback.
    """
    tree = ast.parse(_DIAGNOSTICS_INIT.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert not module.startswith("ucap"), (
                f"diagnostics imports from '{module}' — violates the leaf-node "
                f"invariant (see D-011). Only stdlib imports are allowed."
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("ucap"), (
                    f"diagnostics imports '{alias.name}' — violates the leaf-node "
                    f"invariant (see D-011)."
                )


# ─── Prefix + error-code registries (D-009 + D-011) ─────────────────


def test_prefix_registry_shape() -> None:
    """PREFIX_REGISTRY entries are 3 uppercase ASCII letters → module names."""
    from ucap.diagnostics import PREFIX_REGISTRY

    for prefix in PREFIX_REGISTRY:
        assert len(prefix) == 3, f"Prefix '{prefix}' is not 3 characters"
        assert prefix.isupper() and prefix.isalpha(), (
            f"Prefix '{prefix}' must be uppercase ASCII letters"
        )
    # Module names are unique — no two prefixes for the same module.
    assert len(set(PREFIX_REGISTRY.values())) == len(PREFIX_REGISTRY), (
        f"Duplicate module name in PREFIX_REGISTRY: {PREFIX_REGISTRY}"
    )


def test_prefix_registry_v1_content() -> None:
    """v1 PREFIX_REGISTRY: original five from D-009 A2 plus WSH (D-020)."""
    from ucap.diagnostics import PREFIX_REGISTRY

    assert PREFIX_REGISTRY == {
        "QCT": "qcat",
        "SHN": "shannon",
        "ELT": "elt",
        "WSH": "wireshark",
        "DGN": "diagnostics",
        "CLI": "cli",
    }


def test_error_codes_format_shape() -> None:
    """Every ERROR_CODES key matches the canonical ``{PREFIX}-{E|W}{NNN}`` shape."""
    from ucap.diagnostics import ERROR_CODES

    pattern = re.compile(r"^[A-Z]{3}-[EW]\d{3}$")
    for code in ERROR_CODES:
        assert pattern.match(code), (
            f"Error code '{code}' does not match {{PREFIX}}-{{E|W}}{{NNN}}"
        )


def test_error_codes_prefix_foreign_key() -> None:
    """Every ERROR_CODES key's prefix is registered in PREFIX_REGISTRY (D-011)."""
    from ucap.diagnostics import ERROR_CODES, PREFIX_REGISTRY

    for code in ERROR_CODES:
        prefix = code.split("-", 1)[0]
        assert prefix in PREFIX_REGISTRY, (
            f"Error code '{code}' references unregistered prefix '{prefix}'"
        )


def test_error_codes_severity_matches_letter() -> None:
    """An E-coded entry has severity ErrorSeverity.ERROR; W → WARNING."""
    from ucap.diagnostics import ERROR_CODES, ErrorSeverity

    for code, ec in ERROR_CODES.items():
        letter = code.split("-", 1)[1][0]  # the E or W after the hyphen
        expected = ErrorSeverity.ERROR if letter == "E" else ErrorSeverity.WARNING
        assert ec.severity == expected, (
            f"{code}: severity mismatch — letter '{letter}' vs {ec.severity}"
        )


def test_error_codes_v1_count() -> None:
    """v1 ERROR_CODES: 14 from D-011+D-012+D-019, plus WSH-E001 from D-020."""
    from ucap.diagnostics import ERROR_CODES

    assert len(ERROR_CODES) == 15, (
        f"Expected 15 codes (D-011's initial 11 + DGN-E004 from D-012 + "
        f"QCT-E003 + QCT-E004 from D-019 + WSH-E001 from D-020); "
        f"got {len(ERROR_CODES)}"
    )


# ─── Registry accessors ─────────────────────────────────────────────


def test_get_code_returns_registered() -> None:
    """get_code returns the ErrorCode for a registered code."""
    from ucap.diagnostics import ErrorSeverity, get_code

    qct_e001 = get_code("QCT-E001")
    assert qct_e001.code == "QCT-E001"
    assert qct_e001.severity == ErrorSeverity.ERROR
    assert "{line}" in qct_e001.message


def test_get_code_raises_on_unknown() -> None:
    """get_code raises KeyError with the DGN-E002 template for an unknown code."""
    from ucap.diagnostics import get_code

    with pytest.raises(KeyError, match="QCT-E999"):
        get_code("QCT-E999")


def test_format_code_substitutes_placeholders() -> None:
    """format_code substitutes placeholders into the message template."""
    from ucap.diagnostics import format_code

    msg = format_code("CLI-E001", path="/tmp/missing.txt")
    assert msg == "Input file not found: /tmp/missing.txt"


def test_format_code_accepts_unbounded_str() -> None:
    """format_code is a thin str.format wrapper — unbounded strings pass through.

    Bounded-token discipline lives at the compact-report boundary, not at
    format_code (MODULE.md Invariants, 2026-05-14 refinement of D-011 #5).
    """
    from ucap.diagnostics import format_code

    # Path with slashes — would fail under a strict bounded-token rule, but
    # format_code is intentionally unrestricted; reports get their discipline
    # elsewhere.
    msg = format_code("CLI-E001", path="/customer/site/dump.txt")
    assert "/customer/site/dump.txt" in msg


def test_format_code_unknown_code_raises() -> None:
    """format_code propagates get_code's KeyError on an unknown code."""
    from ucap.diagnostics import format_code

    with pytest.raises(KeyError, match="ZZZ-E999"):
        format_code("ZZZ-E999", placeholder="value")


def test_registries_validated_at_module_load() -> None:
    """Module imports without RuntimeError — no orphan prefix in ERROR_CODES."""
    # If _validate_registries() raised at module load, this import would fail
    # before reaching the test body, so simply reaching here is the assertion.
    import ucap.diagnostics  # noqa: F401


# ─── ReportType + ReportRecord (D-009 + D-013) ──────────────────────


def _make_record(**overrides: object) -> "object":
    """Helper: build a ReportRecord with sensible defaults; apply overrides."""
    from datetime import datetime, timezone

    from ucap.diagnostics import ReportRecord, ReportType

    defaults: dict[str, object] = {
        "report_type": ReportType.RPT,
        "module_prefix": "QCT",
        "run_id": "run-test-001",
        "timestamp": datetime(2026, 5, 14, 22, 1, 31, tzinfo=timezone.utc),
        "fields": {"combos_eutra": 260, "result": "OK"},
    }
    defaults.update(overrides)
    return ReportRecord(**defaults)  # type: ignore[arg-type]


def test_report_type_values() -> None:
    """ReportType has exactly the three v1 values: RPT, MET, QC."""
    from ucap.diagnostics import ReportType

    assert {r.value for r in ReportType} == {"RPT", "MET", "QC"}


def test_report_record_to_line_basic() -> None:
    """to_line produces the canonical pipe-delimited form."""
    line = _make_record().to_line()
    assert line == (
        "RPT|QCT|run-test-001|2026-05-14T22:01:31Z|combos_eutra=260|result=OK"
    )


def test_report_record_round_trip_basic() -> None:
    """from_line(to_line(r)) reproduces r exactly."""
    from ucap.diagnostics import ReportRecord

    r = _make_record()
    r2 = ReportRecord.from_line(r.to_line())
    assert r2 == r


def test_report_record_round_trip_all_value_types() -> None:
    """Round-trip preserves int / float / bool / str field values."""
    from ucap.diagnostics import ReportRecord

    r = _make_record(
        fields={
            "an_int": 42,
            "a_float": 3.14,
            "a_true": True,
            "a_false": False,
            "a_str": "OK",
        }
    )
    r2 = ReportRecord.from_line(r.to_line())
    assert r2 == r


def test_report_record_round_trip_with_redaction_placeholder() -> None:
    """from_line accepts <DEV0>-style placeholders as plain str field values."""
    from ucap.diagnostics import ReportRecord

    r = _make_record(fields={"device": "<DEV0>"})
    r2 = ReportRecord.from_line(r.to_line())
    assert r2 == r
    assert r2.fields["device"] == "<DEV0>"


def test_report_record_empty_fields() -> None:
    """A record with zero fields serializes to just the four leading parts."""
    from ucap.diagnostics import ReportRecord

    r = _make_record(fields={})
    assert r.to_line() == "RPT|QCT|run-test-001|2026-05-14T22:01:31Z"
    assert ReportRecord.from_line(r.to_line()) == r


def test_report_record_timestamp_format_no_microseconds() -> None:
    """Sub-second precision is dropped during serialization (D-013 timestamp format)."""
    from datetime import datetime, timezone

    r = _make_record(
        timestamp=datetime(2026, 5, 14, 22, 1, 31, 123456, tzinfo=timezone.utc)
    )
    assert "2026-05-14T22:01:31Z" in r.to_line()
    assert ".123456" not in r.to_line()


def test_report_record_timestamp_normalized_to_utc() -> None:
    """Non-UTC tz-aware timestamps are converted to UTC for serialization."""
    from datetime import datetime, timedelta, timezone

    eastern = timezone(timedelta(hours=-5))
    r = _make_record(timestamp=datetime(2026, 5, 14, 17, 1, 31, tzinfo=eastern))
    assert "2026-05-14T22:01:31Z" in r.to_line()


def test_report_record_rejects_naive_timestamp() -> None:
    """Naive (tz-unaware) datetime is rejected at construction."""
    from datetime import datetime

    with pytest.raises(ValueError, match="timezone-aware"):
        _make_record(timestamp=datetime(2026, 5, 14, 22, 1, 31))


def test_report_record_rejects_unregistered_prefix() -> None:
    """module_prefix not in PREFIX_REGISTRY is rejected at construction (D-011)."""
    with pytest.raises(ValueError, match="not in PREFIX_REGISTRY"):
        _make_record(module_prefix="XYZ")


def test_report_record_rejects_bad_prefix_shape() -> None:
    """Non-3-letter / non-uppercase prefix rejected with a different message."""
    with pytest.raises(ValueError, match="3 uppercase ASCII"):
        _make_record(module_prefix="qct")


def test_report_record_rejects_empty_run_id() -> None:
    """run_id must be non-empty."""
    with pytest.raises(ValueError, match="non-empty"):
        _make_record(run_id="")


def test_report_record_rejects_pipe_in_run_id() -> None:
    """Reserved character '|' in run_id is rejected (D-013)."""
    with pytest.raises(ValueError, match="'|'"):
        _make_record(run_id="bad|id")


def test_report_record_rejects_newline_in_run_id() -> None:
    """Reserved character '\\n' in run_id is rejected (D-013)."""
    with pytest.raises(ValueError, match="newline"):
        _make_record(run_id="bad\nid")


def test_report_record_rejects_uppercase_field_name() -> None:
    """Field names must be lowercase snake_case (D-013)."""
    with pytest.raises(ValueError, match=r"\[a-z\]\[a-z0-9_\]\*"):
        _make_record(fields={"NotSnakeCase": 1})


def test_report_record_rejects_hyphen_field_name() -> None:
    """Field names with hyphens are rejected."""
    with pytest.raises(ValueError, match=r"\[a-z\]\[a-z0-9_\]\*"):
        _make_record(fields={"combos-eutra": 1})


def test_report_record_rejects_pipe_in_str_field() -> None:
    """Reserved character '|' in a string field value is rejected (D-013)."""
    with pytest.raises(ValueError, match="reserved chars"):
        _make_record(fields={"note": "a|b"})


def test_report_record_rejects_unsupported_value_type() -> None:
    """Field values outside int/float/bool/str are rejected at construction."""
    with pytest.raises(TypeError, match="not supported"):
        _make_record(fields={"data": [1, 2, 3]})  # type: ignore[dict-item]


def test_report_record_from_line_rejects_bad_timestamp() -> None:
    """from_line rejects timestamps that don't match the canonical format."""
    from ucap.diagnostics import ReportRecord

    bad = "RPT|QCT|run-test|2026-05-14T22:01:31.999Z|result=OK"
    with pytest.raises(ValueError, match="YYYY-MM-DDTHH"):
        ReportRecord.from_line(bad)


def test_report_record_from_line_rejects_bad_type() -> None:
    """from_line rejects unknown report types (only RPT/MET/QC valid)."""
    from ucap.diagnostics import ReportRecord

    bad = "FOO|QCT|run-test|2026-05-14T22:01:31Z|result=OK"
    with pytest.raises(ValueError, match="Unknown report type"):
        ReportRecord.from_line(bad)


def test_report_record_from_line_rejects_short_line() -> None:
    """from_line rejects lines with fewer than 4 leading parts."""
    from ucap.diagnostics import ReportRecord

    with pytest.raises(ValueError, match="fewer than 4"):
        ReportRecord.from_line("RPT|QCT|run-test")


def test_report_record_from_line_rejects_unfielded_segment() -> None:
    """A trailing segment without '=' is a parse error."""
    from ucap.diagnostics import ReportRecord

    bad = "RPT|QCT|run-test|2026-05-14T22:01:31Z|missing_equals_sign"
    with pytest.raises(ValueError, match="no '=' separator"):
        ReportRecord.from_line(bad)


def test_report_record_qc_type() -> None:
    """A QC record serializes with leading 'QC'."""
    from ucap.diagnostics import ReportType

    r = _make_record(report_type=ReportType.QC, fields={"schema_valid": True})
    assert r.to_line().startswith("QC|QCT|")


# ─── Redactor (D-012) ───────────────────────────────────────────────


def test_redaction_categories_v1() -> None:
    """REDACTION_CATEGORIES pins the six v1 categories per D-012 #2."""
    from ucap.diagnostics import REDACTION_CATEGORIES

    assert REDACTION_CATEGORIES == ("DEV", "FW", "OP", "ID", "PATH", "SESS")


def test_redactor_empty_is_identity() -> None:
    """Redactor.empty().apply(text) returns text unchanged."""
    from ucap.diagnostics import Redactor

    r = Redactor.empty()
    assert r.apply("any text |with| punctuation") == "any text |with| punctuation"


def test_redactor_substitutes_single_mapping() -> None:
    """apply substitutes a single real → placeholder pair."""
    from ucap.diagnostics import Redactor

    r = Redactor(mappings=(("S908UXXU3CWA1", "<FW0>"),))
    assert r.apply("firmware=S908UXXU3CWA1") == "firmware=<FW0>"


def test_redactor_substitutes_multiple_mappings() -> None:
    """apply substitutes multiple distinct pairs in one pass."""
    from ucap.diagnostics import Redactor

    r = Redactor(
        mappings=(
            ("CodenameX", "<DEV0>"),
            ("S908UXXU3CWA1", "<FW0>"),
        )
    )
    out = r.apply("device=CodenameX firmware=S908UXXU3CWA1")
    assert out == "device=<DEV0> firmware=<FW0>"


def test_redactor_longest_match_first() -> None:
    """Multi-word reals match before substrings (longest-first ordering)."""
    from ucap.diagnostics import Redactor

    # Pairs given in arbitrary order; from_file would sort them, but for
    # direct construction we pass them already-sorted (longest-first).
    r = Redactor(
        mappings=(
            ("AT&T Mobility", "<OP0>"),
            ("AT&T", "<OP1>"),
        )
    )
    # 'AT&T Mobility' should win over 'AT&T' when both could match.
    assert r.apply("op=AT&T Mobility") == "op=<OP0>"
    # Bare 'AT&T' still substitutes correctly when 'Mobility' isn't there.
    assert r.apply("op=AT&T inc") == "op=<OP1> inc"


def test_redactor_no_double_substitution() -> None:
    """A single re.sub pass means substituted segments are not re-scanned."""
    from ucap.diagnostics import Redactor

    # If apply re-scanned, '<DEV0>' (containing 'DEV') could re-substitute.
    r = Redactor(mappings=(("DEV", "<DEV0>"),))
    assert r.apply("just one DEV") == "just one <DEV0>"
    # Critically: NOT '<<DEV0>0>' or similar nested form.


def test_redactor_from_file_valid(tmp_path: Path) -> None:
    """from_file loads a well-formed map and sorts longest-first."""
    import json

    from ucap.diagnostics import Redactor

    p = tmp_path / "map.json"
    p.write_text(
        json.dumps(
            {
                "version": 1,
                "mappings": {
                    "AT&T": "<OP1>",
                    "AT&T Mobility": "<OP0>",  # longer; must come first
                },
            }
        )
    )
    r = Redactor.from_file(p)
    # Longest-real-first ordering — 'AT&T Mobility' before 'AT&T'.
    assert r.mappings[0][0] == "AT&T Mobility"
    assert r.mappings[1][0] == "AT&T"


def test_redactor_from_file_rejects_bad_version(tmp_path: Path) -> None:
    """from_file rejects version != 1."""
    import json

    from ucap.diagnostics import Redactor

    p = tmp_path / "map.json"
    p.write_text(json.dumps({"version": 2, "mappings": {}}))
    with pytest.raises(ValueError, match="version must be 1"):
        Redactor.from_file(p)


def test_redactor_from_file_rejects_bad_category(tmp_path: Path) -> None:
    """from_file rejects placeholders outside DEV/FW/OP/ID/PATH/SESS (raises DGN-E004)."""
    import json

    from ucap.diagnostics import Redactor

    p = tmp_path / "map.json"
    p.write_text(
        json.dumps({"version": 1, "mappings": {"SomeValue": "<UNKNOWN0>"}})
    )
    with pytest.raises(ValueError, match="Invalid redaction category"):
        Redactor.from_file(p)


def test_redactor_from_file_rejects_malformed_placeholder(tmp_path: Path) -> None:
    """Placeholder without angle brackets or digits is rejected."""
    import json

    from ucap.diagnostics import Redactor

    p = tmp_path / "map.json"
    p.write_text(
        json.dumps({"version": 1, "mappings": {"x": "DEV0"}})  # missing < >
    )
    with pytest.raises(ValueError, match="Invalid redaction category"):
        Redactor.from_file(p)


def test_redactor_from_file_rejects_duplicate_placeholder(tmp_path: Path) -> None:
    """Two distinct reals mapping to the same placeholder is a config error."""
    import json

    from ucap.diagnostics import Redactor

    p = tmp_path / "map.json"
    p.write_text(
        json.dumps(
            {
                "version": 1,
                "mappings": {"alpha": "<DEV0>", "beta": "<DEV0>"},
            }
        )
    )
    with pytest.raises(ValueError, match="Duplicate placeholder"):
        Redactor.from_file(p)


def test_redactor_from_file_rejects_extra_top_keys(tmp_path: Path) -> None:
    """Top-level keys must be exactly version + mappings."""
    import json

    from ucap.diagnostics import Redactor

    p = tmp_path / "map.json"
    p.write_text(
        json.dumps({"version": 1, "mappings": {}, "extra": "nope"})
    )
    with pytest.raises(ValueError, match="exactly"):
        Redactor.from_file(p)


def test_redactor_from_file_rejects_non_dict_root(tmp_path: Path) -> None:
    """A JSON file with a non-object root is rejected."""
    import json

    from ucap.diagnostics import Redactor

    p = tmp_path / "map.json"
    p.write_text(json.dumps(["not", "an", "object"]))
    with pytest.raises(ValueError, match="must be a JSON object"):
        Redactor.from_file(p)


# ─── QCField + QCTemplate + QC_REGISTRY (D-011) ─────────────────────


def test_qcfield_valid_int() -> None:
    """QCField with field_type='int' constructs cleanly."""
    from ucap.diagnostics import QCField

    f = QCField("count", "int")
    assert f.name == "count"
    assert f.field_type == "int"
    assert f.enum_values is None


def test_qcfield_invalid_type_raises_dgn_e003() -> None:
    """QCField with an unknown field_type raises (DGN-E003 message template)."""
    from ucap.diagnostics import QCField

    with pytest.raises(TypeError, match="Invalid QCField type"):
        QCField("x", "string")  # 'string' not in {int, float, bool, enum}


def test_qcfield_enum_requires_values() -> None:
    """QCField with field_type='enum' must supply enum_values."""
    from ucap.diagnostics import QCField

    with pytest.raises(TypeError, match="enum_values"):
        QCField("x", "enum")


def test_qcfield_non_enum_rejects_values() -> None:
    """QCField with non-enum type cannot carry enum_values."""
    from ucap.diagnostics import QCField

    with pytest.raises(TypeError, match="cannot carry enum_values"):
        QCField("x", "int", enum_values=("a", "b"))


def test_qcfield_name_must_be_snake_case() -> None:
    """QCField name must match [a-z][a-z0-9_]*."""
    from ucap.diagnostics import QCField

    with pytest.raises(ValueError, match=r"\[a-z\]\[a-z0-9_\]\*"):
        QCField("NotSnakeCase", "int")


def test_qc_registry_has_v1_templates() -> None:
    """The two v1 pre-registered templates are in QC_REGISTRY."""
    from ucap.diagnostics import QC_REGISTRY

    assert "qcat:parse_diagnostic" in QC_REGISTRY
    assert "qcat:parse_validation" in QC_REGISTRY


def test_qc_template_parse_diagnostic_field_count() -> None:
    """parse_diagnostic has the 22 fields from D-010 B4."""
    from ucap.diagnostics import QC_REGISTRY

    t = QC_REGISTRY["qcat:parse_diagnostic"]
    assert len(t.fields) == 22


def test_qc_template_parse_validation_field_count() -> None:
    """parse_validation has the 9 fields from D-010 B5."""
    from ucap.diagnostics import QC_REGISTRY

    t = QC_REGISTRY["qcat:parse_validation"]
    assert len(t.fields) == 9


def test_qc_template_register_rejects_duplicate() -> None:
    """Registering the same key twice raises."""
    from ucap.diagnostics import QC_REGISTRY, QCField, QCTemplate

    # The fixture: try to re-register parse_diagnostic.
    dup = QCTemplate(
        module_prefix="QCT",
        artifact_type="parse_diagnostic",
        fields=(QCField("dummy", "int"),),
    )
    with pytest.raises(ValueError, match="already registered"):
        QCTemplate.register(dup)
    # Sanity: the original template wasn't clobbered.
    assert len(QC_REGISTRY["qcat:parse_diagnostic"].fields) == 22


def test_qc_template_validate_valid_record() -> None:
    """A record matching the template's fields validates clean (empty errors)."""
    from datetime import datetime, timezone

    from ucap.diagnostics import QC_REGISTRY, ReportRecord, ReportType

    t = QC_REGISTRY["qcat:parse_validation"]
    rec = ReportRecord(
        report_type=ReportType.QC,
        module_prefix="QCT",
        run_id="run-x",
        timestamp=datetime(2026, 5, 14, 22, 0, 0, tzinfo=timezone.utc),
        fields={
            "vendor": "qcat",
            "release": "rel17",
            "schema_valid": True,
            "unknown_field_count": 0,
            "index_out_of_range_count": 0,
            "off_by_one_count": 0,
            "mrdc_rel16_handled": True,
            "bcs_parsed": True,
            "result": "OK",
        },
    )
    assert t.validate_record(rec) == []


def test_qc_template_validate_missing_field() -> None:
    """A record missing a declared field is flagged."""
    from datetime import datetime, timezone

    from ucap.diagnostics import QC_REGISTRY, ReportRecord, ReportType

    t = QC_REGISTRY["qcat:parse_validation"]
    rec = ReportRecord(
        report_type=ReportType.QC,
        module_prefix="QCT",
        run_id="run-x",
        timestamp=datetime(2026, 5, 14, 22, 0, 0, tzinfo=timezone.utc),
        fields={"vendor": "qcat"},  # all other declared fields missing
    )
    errors = t.validate_record(rec)
    assert any("missing field" in e for e in errors)


def test_qc_template_validate_extra_field() -> None:
    """A record with an undeclared field is flagged."""
    from datetime import datetime, timezone

    from ucap.diagnostics import QC_REGISTRY, ReportRecord, ReportType

    t = QC_REGISTRY["qcat:parse_validation"]
    rec = ReportRecord(
        report_type=ReportType.QC,
        module_prefix="QCT",
        run_id="run-x",
        timestamp=datetime(2026, 5, 14, 22, 0, 0, tzinfo=timezone.utc),
        fields={
            "vendor": "qcat",
            "release": "rel17",
            "schema_valid": True,
            "unknown_field_count": 0,
            "index_out_of_range_count": 0,
            "off_by_one_count": 0,
            "mrdc_rel16_handled": True,
            "bcs_parsed": True,
            "result": "OK",
            "snuck_in": "free text here",  # undeclared
        },
    )
    errors = t.validate_record(rec)
    assert any("unexpected field" in e and "snuck_in" in e for e in errors)


def test_qc_template_validate_wrong_type() -> None:
    """A record with the wrong type for a declared field is flagged."""
    from datetime import datetime, timezone

    from ucap.diagnostics import QC_REGISTRY, ReportRecord, ReportType

    t = QC_REGISTRY["qcat:parse_validation"]
    rec = ReportRecord(
        report_type=ReportType.QC,
        module_prefix="QCT",
        run_id="run-x",
        timestamp=datetime(2026, 5, 14, 22, 0, 0, tzinfo=timezone.utc),
        fields={
            "vendor": "qcat",
            "release": "rel17",
            "schema_valid": "true",  # str, should be bool
            "unknown_field_count": 0,
            "index_out_of_range_count": 0,
            "off_by_one_count": 0,
            "mrdc_rel16_handled": True,
            "bcs_parsed": True,
            "result": "OK",
        },
    )
    errors = t.validate_record(rec)
    assert any("schema_valid" in e and "must be bool" in e for e in errors)


def test_qc_template_validate_enum_out_of_set() -> None:
    """An enum value not in the declared set is flagged."""
    from datetime import datetime, timezone

    from ucap.diagnostics import QC_REGISTRY, ReportRecord, ReportType

    t = QC_REGISTRY["qcat:parse_validation"]
    rec = ReportRecord(
        report_type=ReportType.QC,
        module_prefix="QCT",
        run_id="run-x",
        timestamp=datetime(2026, 5, 14, 22, 0, 0, tzinfo=timezone.utc),
        fields={
            "vendor": "qcat",
            "release": "rel17",
            "schema_valid": True,
            "unknown_field_count": 0,
            "index_out_of_range_count": 0,
            "off_by_one_count": 0,
            "mrdc_rel16_handled": True,
            "bcs_parsed": True,
            "result": "MAYBE",  # not in {OK, WARN, FAIL}
        },
    )
    errors = t.validate_record(rec)
    assert any("result" in e and "MAYBE" in e for e in errors)


# ─── ReportWriter (D-011 + D-013) ───────────────────────────────────


def _make_qct_record(**overrides: object) -> "object":
    """Helper: build a minimal valid RPT-style record for QCT."""
    from datetime import datetime, timezone

    from ucap.diagnostics import ReportRecord, ReportType

    defaults: dict[str, object] = {
        "report_type": ReportType.RPT,
        "module_prefix": "QCT",
        "run_id": "run-001",
        "timestamp": datetime(2026, 5, 14, 22, 0, 0, tzinfo=timezone.utc),
        "fields": {"messages_parsed": 1, "result": "OK"},
    }
    defaults.update(overrides)
    return ReportRecord(**defaults)  # type: ignore[arg-type]


def test_writer_emit_and_flush(capsys: pytest.CaptureFixture[str]) -> None:
    """Emit a record, flush to stdout, verify it appeared on a single line."""
    from ucap.diagnostics import ReportWriter

    w = ReportWriter(module_prefix="QCT", run_id="run-001")
    w.emit(_make_qct_record())
    w.flush()
    out = capsys.readouterr().out
    assert out.startswith("RPT|QCT|run-001|2026-05-14T22:00:00Z|")
    assert out.endswith("\n")
    assert out.count("\n") == 1  # exactly one line


def test_writer_emit_multiple(capsys: pytest.CaptureFixture[str]) -> None:
    """Multiple emits accumulate; flush emits each on its own line."""
    from ucap.diagnostics import ReportWriter, ReportType

    w = ReportWriter(module_prefix="QCT", run_id="run-001")
    w.emit(_make_qct_record(report_type=ReportType.RPT))
    w.emit(_make_qct_record(report_type=ReportType.QC))
    w.flush()
    out = capsys.readouterr().out
    lines = out.strip().split("\n")
    assert len(lines) == 2
    assert lines[0].startswith("RPT|QCT|")
    assert lines[1].startswith("QC|QCT|")


def test_writer_context_manager_auto_flushes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Exiting the with-block flushes buffered records."""
    from ucap.diagnostics import ReportWriter

    with ReportWriter(module_prefix="QCT", run_id="run-001") as w:
        w.emit(_make_qct_record())
    out = capsys.readouterr().out
    assert "RPT|QCT|run-001" in out


def test_writer_context_manager_drops_on_exception(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Exception inside the with-block drops the buffer (no partial output)."""
    from ucap.diagnostics import ReportWriter

    with pytest.raises(RuntimeError, match="boom"):
        with ReportWriter(module_prefix="QCT", run_id="run-001") as w:
            w.emit(_make_qct_record())
            raise RuntimeError("boom")
    out = capsys.readouterr().out
    assert out == ""


def test_writer_rejects_mismatched_prefix() -> None:
    """Emitting a record whose module_prefix doesn't match the writer raises."""
    from datetime import datetime, timezone

    from ucap.diagnostics import ReportRecord, ReportType, ReportWriter

    w = ReportWriter(module_prefix="QCT", run_id="run-001")
    rec = ReportRecord(
        report_type=ReportType.RPT,
        module_prefix="CLI",  # mismatched
        run_id="run-001",
        timestamp=datetime(2026, 5, 14, 22, 0, 0, tzinfo=timezone.utc),
        fields={},
    )
    with pytest.raises(ValueError, match="module_prefix"):
        w.emit(rec)


def test_writer_rejects_mismatched_run_id() -> None:
    """Emitting a record whose run_id doesn't match the writer raises."""
    from ucap.diagnostics import ReportWriter

    w = ReportWriter(module_prefix="QCT", run_id="run-001")
    rec = _make_qct_record(run_id="other-run")
    with pytest.raises(ValueError, match="run_id"):
        w.emit(rec)


def test_writer_with_template_validates(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A writer constructed with a template runs validate_record at emit."""
    from datetime import datetime, timezone

    from ucap.diagnostics import (
        QC_REGISTRY,
        ReportRecord,
        ReportType,
        ReportWriter,
    )

    template = QC_REGISTRY["qcat:parse_validation"]
    valid_rec = ReportRecord(
        report_type=ReportType.QC,
        module_prefix="QCT",
        run_id="run-001",
        timestamp=datetime(2026, 5, 14, 22, 0, 0, tzinfo=timezone.utc),
        fields={
            "vendor": "qcat",
            "release": "rel17",
            "schema_valid": True,
            "unknown_field_count": 0,
            "index_out_of_range_count": 0,
            "off_by_one_count": 0,
            "mrdc_rel16_handled": True,
            "bcs_parsed": True,
            "result": "OK",
        },
    )
    with ReportWriter(
        module_prefix="QCT", run_id="run-001", template=template
    ) as w:
        w.emit(valid_rec)
    out = capsys.readouterr().out
    assert out.startswith("QC|QCT|run-001|")


def test_writer_with_template_rejects_invalid_record() -> None:
    """A record that fails template.validate_record raises ValueError at emit."""
    from datetime import datetime, timezone

    from ucap.diagnostics import (
        QC_REGISTRY,
        ReportRecord,
        ReportType,
        ReportWriter,
    )

    template = QC_REGISTRY["qcat:parse_validation"]
    invalid_rec = ReportRecord(
        report_type=ReportType.QC,
        module_prefix="QCT",
        run_id="run-001",
        timestamp=datetime(2026, 5, 14, 22, 0, 0, tzinfo=timezone.utc),
        fields={"vendor": "qcat"},  # missing many declared fields
    )
    w = ReportWriter(
        module_prefix="QCT", run_id="run-001", template=template
    )
    with pytest.raises(ValueError, match="validation failed"):
        w.emit(invalid_rec)


def test_writer_template_prefix_must_match() -> None:
    """ReportWriter rejects a template whose module_prefix differs from the writer's."""
    from ucap.diagnostics import QC_REGISTRY, ReportWriter

    template = QC_REGISTRY["qcat:parse_validation"]
    with pytest.raises(ValueError, match="does not match"):
        ReportWriter(module_prefix="CLI", run_id="run-001", template=template)


def test_writer_30_line_cap_raises_at_flush() -> None:
    """Buffering more than 30 records raises at flush (D-013 #4)."""
    from ucap.diagnostics import ReportWriter

    w = ReportWriter(module_prefix="QCT", run_id="run-001")
    for _ in range(31):
        w.emit(_make_qct_record())
    with pytest.raises(ValueError, match="exceeds the 30-line"):
        w.flush()


def test_writer_under_cap_flushes_cleanly(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """30 records exactly is at the cap — flush succeeds."""
    from ucap.diagnostics import ReportWriter

    with ReportWriter(module_prefix="QCT", run_id="run-001") as w:
        for _ in range(30):
            w.emit(_make_qct_record())
    out = capsys.readouterr().out
    assert out.count("\n") == 30


def test_writer_applies_redaction(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A non-empty Redactor substitutes values in emitted lines."""
    from ucap.diagnostics import Redactor, ReportRecord, ReportType, ReportWriter
    from datetime import datetime, timezone

    redactor = Redactor(mappings=(("S908UXXU3CWA1", "<FW0>"),))
    rec = ReportRecord(
        report_type=ReportType.RPT,
        module_prefix="QCT",
        run_id="run-001",
        timestamp=datetime(2026, 5, 14, 22, 0, 0, tzinfo=timezone.utc),
        fields={"firmware": "S908UXXU3CWA1", "result": "OK"},
    )
    with ReportWriter(
        module_prefix="QCT", run_id="run-001", redactor=redactor
    ) as w:
        w.emit(rec)
    out = capsys.readouterr().out
    assert "S908UXXU3CWA1" not in out
    assert "<FW0>" in out


def test_writer_buffer_length_property() -> None:
    """The buffer_length property reflects pending records."""
    from ucap.diagnostics import ReportWriter

    w = ReportWriter(module_prefix="QCT", run_id="run-001")
    assert w.buffer_length == 0
    w.emit(_make_qct_record())
    w.emit(_make_qct_record())
    assert w.buffer_length == 2
    w.flush()
    assert w.buffer_length == 0


def test_writer_rejects_unregistered_prefix() -> None:
    """ReportWriter constructor rejects a prefix not in PREFIX_REGISTRY."""
    from ucap.diagnostics import ReportWriter

    with pytest.raises(ValueError, match="not in PREFIX_REGISTRY"):
        ReportWriter(module_prefix="XYZ", run_id="run-001")


def test_writer_rejects_empty_run_id() -> None:
    """ReportWriter constructor rejects an empty run_id."""
    from ucap.diagnostics import ReportWriter

    with pytest.raises(ValueError, match="non-empty"):
        ReportWriter(module_prefix="QCT", run_id="")
