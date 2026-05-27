"""QCAT ASN.1 value-notation parser (L1) — extracts the outer envelope.

Handles QCAT exports in ASN.1 value notation per ``D-015`` / ``D-018`` / ``D-019``.
The parser is **targeted**, not a general ASN.1 value-notation parser:

- Entry point: the ``message c1 : ueCapabilityInformation : { ... }`` block.
  The outer ``value UL-DCCH-Message ::= { ... }`` envelope is intentionally
  skipped. End-of-message is detected by brace matching from the opening ``{``
  of the entry block.
- No ``-- comment`` syntax is expected in the format.
- Per-RAT ``ue-CapabilityRAT-Container`` ``OCTET STRING`` literals (``'HEX'H``
  form, possibly multi-line) are captured as raw bytes; PER decoding against
  the 3GPP RRC schema is L2's job (uses ``pycrate``).

A file containing multiple ``UE Capability Information`` messages yields
multiple :class:`Asn1Message` records — one per ``message c1 :
ueCapabilityInformation :`` occurrence.

This module's contract for callers: ``parse_asn1_text(text)`` or
``parse_asn1_file(path)`` returns / yields :class:`Asn1Message` records.
Mapping to ``CanonicalUeCapability`` (post-L2 PER decode) lives in L3 — not
yet implemented in this commit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from ucap import __version__ as _PARSER_VERSION
from ucap.schema import (
    CaBandwidthClass,
    CanonicalUeCapability,
    EutraBand,
    EutraCaCombination,
    EutraComboBandEntry,
    EutraSection,
    Meta,
    Modulation,
    MrdcBandCombination,
    MrdcComboKind,
    MrdcComboSource,
    MrdcSection,
    NrBand,
    NrBandCombination,
    NrComboBandEntry,
    NrComboKind,
    NrSection,
    PowerClassNR,
    RatName,
    Release,
    Vendor,
)

# Shared canonical-mapping helpers from the indented adapter. Per D-018:
# helpers that operate on canonical-shape values (not TreeNode-specific)
# are imported across the qcat sub-package. When the cross-import surface
# exceeds 5 internal symbols, D-018's trigger fires a refactor into _common.py.
from ucap.adapters.qcat._indented import (  # noqa: E402
    _MIMO_LAYERS,
    _MOD_MAP,
    _POWER_CLASS_MAP,
    _SCS_MAP,
    _derive_fr,
    _make_combo_label,
    _normalize_power_class,
    _parse_bw_class,
)


# ─── Public dataclasses ─────────────────────────────────────────────


@dataclass(frozen=True)
class Asn1RatContainer:
    """One per-RAT container from an ASN.1 ``ueCapabilityInformation`` message.

    Held opaquely as PER-encoded bytes; L2 decodes via :mod:`pycrate` against
    the 3GPP RRC schema for the matched ``rat_type``.
    """

    rat_type: str  # "eutra" | "nr" | "eutra-nr" | "mrdc-XPDCP" | future
    encoded: bytes  # PER-encoded UE-{EUTRA,NR,MRDC}-Capability payload


@dataclass(frozen=True)
class Asn1Message:
    """One parsed ``UE Capability Information`` message from ASN.1 value notation.

    Mirrors the indented-format :class:`~ucap.adapters.qcat._indented.Message`
    shape conceptually, but the per-RAT payload is held as PER-encoded bytes
    rather than as a parsed ``TreeNode``. L2 / L3 turn this into a
    ``CanonicalUeCapability`` (post-pycrate-decode).
    """

    rrc_transaction_id: int
    rat_containers: tuple[Asn1RatContainer, ...]
    start_line: int  # 1-based line where `message c1 :` was found
    end_line: int  # 1-based line of the matching closing `}`


# ─── Public entry points ────────────────────────────────────────────


# Detects the start of each ueCapabilityInformation block, with both
# whitespace variants observed in real QCAT exports:
#   "message c1: ueCapabilityInformation :"
#   "message c1 : ueCapabilityInformation :"
_ENTRY_RE = re.compile(
    r"message\s+c1\s*:\s*ueCapabilityInformation\s*:",
)


def parse_asn1_file(path: str | Path) -> list[Asn1Message]:
    """Parse every ``UE Capability Information`` message in a QCAT ASN.1 export file."""
    return list(parse_asn1_text(Path(path).read_text()))


def parse_asn1_text(text: str) -> Iterator[Asn1Message]:
    """Yield each ``UE Capability Information`` message from QCAT ASN.1 text.

    Multiple messages per file are supported — the scanner advances past each
    parsed entry block and resumes from the next ``message c1 :`` occurrence.
    """
    pos = 0
    while True:
        match = _ENTRY_RE.search(text, pos)
        if match is None:
            return
        start_line = text.count("\n", 0, match.start()) + 1
        msg, advance_to = _parse_one_message(text, match.end(), start_line)
        yield msg
        pos = advance_to


# ─── Tokenizer ──────────────────────────────────────────────────────


# Token kinds.
_T_IDENT = "IDENT"  # field name or enum / value identifier
_T_INT = "INT"  # decimal integer (possibly negative)
_T_HEX_STR = "HEX_STR"  # ``'HEX...'H`` literal (multi-line tolerant)
_T_LBRACE = "{"
_T_RBRACE = "}"
_T_COMMA = ","
_T_COLON = ":"


@dataclass(frozen=True)
class _Token:
    kind: str
    value: str
    line: int


_IDENT_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
_INT_RE = re.compile(r"-?\d+")
# Multi-line hex tolerant: whitespace inside ``'...'H`` is stripped at extraction.
_HEX_STR_RE = re.compile(r"'([0-9A-Fa-f\s]*)'H", re.DOTALL)


def _tokenize(text: str, start: int, end: int | None = None) -> list[_Token]:
    """Tokenize ``text[start:end]``.

    ``end`` defaults to ``len(text)``. Callers parsing one message-of-many
    pass the EOM offset (found by :func:`_find_matching_brace`) to avoid
    choking on inter-message junk.
    """
    tokens: list[_Token] = []
    i = start
    line = text.count("\n", 0, start) + 1
    n = end if end is not None else len(text)
    while i < n:
        c = text[i]
        if c == " " or c == "\t":
            i += 1
            continue
        if c == "\n":
            line += 1
            i += 1
            continue
        if c == "\r":
            i += 1
            continue
        if c == "{":
            tokens.append(_Token(_T_LBRACE, "{", line))
            i += 1
            continue
        if c == "}":
            tokens.append(_Token(_T_RBRACE, "}", line))
            i += 1
            continue
        if c == ",":
            tokens.append(_Token(_T_COMMA, ",", line))
            i += 1
            continue
        if c == ":":
            tokens.append(_Token(_T_COLON, ":", line))
            i += 1
            continue
        if c == "'":
            m = _HEX_STR_RE.match(text, i)
            if m is None:
                raise _Asn1SyntaxError(
                    f"Unterminated or malformed hex-string literal", line
                )
            # Strip whitespace from the captured hex digits and advance line counter.
            hex_clean = re.sub(r"\s+", "", m.group(1))
            line += text.count("\n", i, m.end())
            tokens.append(_Token(_T_HEX_STR, hex_clean, line))
            i = m.end()
            continue
        # Identifier (must come before integer, since identifiers can start with letters).
        m = _IDENT_RE.match(text, i)
        if m is not None:
            tokens.append(_Token(_T_IDENT, m.group(0), line))
            i = m.end()
            continue
        # Integer.
        m = _INT_RE.match(text, i)
        if m is not None:
            tokens.append(_Token(_T_INT, m.group(0), line))
            i = m.end()
            continue
        raise _Asn1SyntaxError(f"Unexpected character {c!r}", line)
    return tokens


# ─── Parser ─────────────────────────────────────────────────────────


class _Asn1SyntaxError(Exception):
    """Internal exception raised on ASN.1-grammar mismatches.

    Carries a line number for adapter callers to surface via ``QCT-E003`` per
    ``D-019``. Callers (eventually the dispatcher in ``__init__.py``) catch
    this and wrap with the diagnostics registry's ``format_code("QCT-E003",
    line=err.line, detail=str(err))``.
    """

    def __init__(self, message: str, line: int) -> None:
        super().__init__(message)
        self.line = line


def _parse_one_message(
    text: str, start: int, start_line: int
) -> tuple[Asn1Message, int]:
    """Parse one ``ueCapabilityInformation`` block.

    ``start`` is the offset immediately after the regex-matched
    ``message c1 : ueCapabilityInformation :`` header. The text from there
    begins with optional whitespace then the opening ``{`` of the SEQUENCE
    body.

    Returns ``(Asn1Message, advance_to)`` — ``advance_to`` is the offset in
    ``text`` to resume the multi-message scan from (just past the matching
    closing ``}``).
    """
    # Find the body's opening brace and its matching close via text-level
    # brace matching. Pre-scoping the tokenizer to this range avoids choking
    # on inter-message junk (e.g. log timestamps between messages).
    brace_open = text.find("{", start)
    if brace_open == -1:
        raise _Asn1SyntaxError(
            "Expected '{' after 'message c1 : ueCapabilityInformation :'",
            start_line,
        )
    brace_close = _find_matching_brace(text, brace_open)
    if brace_close == -1:
        raise _Asn1SyntaxError(
            "Unmatched '{' for ueCapabilityInformation body", start_line
        )

    tokens = _tokenize(text, brace_open, brace_close + 1)

    pos = _expect(tokens, 0, _T_LBRACE, start_line, "after 'message c1 : ueCapabilityInformation :'")

    rrc_transaction_id: int | None = None
    rat_containers: list[Asn1RatContainer] = []
    end_line = start_line

    while pos < len(tokens):
        tok = tokens[pos]
        if tok.kind == _T_RBRACE:
            end_line = tok.line
            if rrc_transaction_id is None:
                raise _Asn1SyntaxError(
                    "Missing 'rrc-TransactionIdentifier' field", start_line
                )
            return (
                Asn1Message(
                    rrc_transaction_id=rrc_transaction_id,
                    rat_containers=tuple(rat_containers),
                    start_line=start_line,
                    end_line=end_line,
                ),
                brace_close + 1,
            )
        if tok.kind == _T_COMMA:
            pos += 1
            continue
        if tok.kind == _T_IDENT:
            field_name = tok.value
            pos += 1
            if field_name == "rrc-TransactionIdentifier":
                pos = _expect(tokens, pos, _T_INT, tok.line, "after 'rrc-TransactionIdentifier'")
                rrc_transaction_id = int(tokens[pos - 1].value)
            elif field_name == "criticalExtensions":
                # Expect: `<choice-tag> : { ... }`.
                pos, containers = _parse_critical_extensions(tokens, pos, tok.line)
                rat_containers.extend(containers)
            else:
                pos = _skip_value(tokens, pos)
            continue
        raise _Asn1SyntaxError(
            f"Unexpected token {tok.kind} {tok.value!r}", tok.line
        )

    raise _Asn1SyntaxError(
        "Unexpected EOF inside ueCapabilityInformation body", start_line
    )


def _parse_critical_extensions(
    tokens: list[_Token], pos: int, header_line: int
) -> tuple[int, list[Asn1RatContainer]]:
    """Parse ``<choice-tag> : { <UECapabilityInformation-IEs body> }``.

    Pos is positioned at the choice tag identifier. Returns ``(new_pos,
    rat_containers)``. Only the ``ueCapabilityInformation`` choice tag is
    supported; the alternative ``criticalExtensionsFuture`` raises.
    """
    if pos >= len(tokens) or tokens[pos].kind != _T_IDENT:
        raise _Asn1SyntaxError(
            "Expected '<choice-tag> :' after 'criticalExtensions'", header_line
        )
    choice_tag = tokens[pos].value
    line = tokens[pos].line
    pos += 1
    pos = _expect(tokens, pos, _T_COLON, line, "after criticalExtensions choice tag")
    if choice_tag != "ueCapabilityInformation":
        raise _Asn1SyntaxError(
            f"Unsupported criticalExtensions choice {choice_tag!r} "
            f"(expected 'ueCapabilityInformation')",
            line,
        )
    pos = _expect(
        tokens, pos, _T_LBRACE, line,
        "after 'criticalExtensions ueCapabilityInformation :'",
    )

    # Inside UECapabilityInformation-IEs.
    rat_containers: list[Asn1RatContainer] = []
    while pos < len(tokens):
        tok = tokens[pos]
        if tok.kind == _T_RBRACE:
            return pos + 1, rat_containers
        if tok.kind == _T_COMMA:
            pos += 1
            continue
        if tok.kind == _T_IDENT:
            field_name = tok.value
            pos += 1
            if field_name == "ue-CapabilityRAT-ContainerList":
                pos = _expect(
                    tokens, pos, _T_LBRACE, tok.line,
                    "after 'ue-CapabilityRAT-ContainerList'",
                )
                pos, containers = _parse_rat_container_list(tokens, pos, tok.line)
                rat_containers.extend(containers)
            else:
                pos = _skip_value(tokens, pos)
            continue
        raise _Asn1SyntaxError(
            f"Unexpected token {tok.kind} in UECapabilityInformation-IEs body",
            tok.line,
        )
    raise _Asn1SyntaxError(
        "Unexpected EOF inside UECapabilityInformation-IEs", header_line
    )


def _parse_rat_container_list(
    tokens: list[_Token], pos: int, header_line: int
) -> tuple[int, list[Asn1RatContainer]]:
    """Parse a SEQUENCE OF UE-CapabilityRAT-Container.

    Pos is just after the opening ``{`` of the SEQUENCE-OF list. Each element
    is itself a ``{ rat-Type X, ue-CapabilityRAT-Container 'HEX'H }`` block.
    """
    containers: list[Asn1RatContainer] = []
    while pos < len(tokens):
        tok = tokens[pos]
        if tok.kind == _T_RBRACE:
            return pos + 1, containers
        if tok.kind == _T_COMMA:
            pos += 1
            continue
        if tok.kind == _T_LBRACE:
            pos, container = _parse_rat_container(tokens, pos + 1, tok.line)
            containers.append(container)
            continue
        raise _Asn1SyntaxError(
            f"Unexpected token {tok.kind} in RAT-container list", tok.line
        )
    raise _Asn1SyntaxError(
        "Unexpected EOF inside ue-CapabilityRAT-ContainerList", header_line
    )


def _parse_rat_container(
    tokens: list[_Token], pos: int, header_line: int
) -> tuple[int, Asn1RatContainer]:
    """Parse one UE-CapabilityRAT-Container SEQUENCE.

    Pos is just after the opening ``{`` of this container. Expects:
    ``rat-Type <IDENT>, ue-CapabilityRAT-Container 'HEX'H`` (order tolerant).
    """
    rat_type: str | None = None
    encoded: bytes | None = None

    while pos < len(tokens):
        tok = tokens[pos]
        if tok.kind == _T_RBRACE:
            if rat_type is None or encoded is None:
                raise _Asn1SyntaxError(
                    "Incomplete UE-CapabilityRAT-Container "
                    f"(rat_type={rat_type!r}, encoded={'present' if encoded else 'missing'})",
                    header_line,
                )
            return pos + 1, Asn1RatContainer(rat_type=rat_type, encoded=encoded)
        if tok.kind == _T_COMMA:
            pos += 1
            continue
        if tok.kind == _T_IDENT:
            field_name = tok.value
            pos += 1
            if field_name == "rat-Type":
                if pos >= len(tokens) or tokens[pos].kind != _T_IDENT:
                    raise _Asn1SyntaxError(
                        "Expected rat-Type value identifier", tok.line
                    )
                rat_type = tokens[pos].value
                pos += 1
            elif field_name == "ue-CapabilityRAT-Container":
                if pos >= len(tokens) or tokens[pos].kind != _T_HEX_STR:
                    raise _Asn1SyntaxError(
                        "Expected hex OCTET STRING ('HEX'H) after "
                        "'ue-CapabilityRAT-Container'",
                        tok.line,
                    )
                encoded = bytes.fromhex(tokens[pos].value) if tokens[pos].value else b""
                pos += 1
            else:
                pos = _skip_value(tokens, pos)
            continue
        raise _Asn1SyntaxError(
            f"Unexpected token {tok.kind} inside RAT container", tok.line
        )
    raise _Asn1SyntaxError(
        "Unexpected EOF inside UE-CapabilityRAT-Container", header_line
    )


def _skip_value(tokens: list[_Token], pos: int) -> int:
    """Skip an unknown field's value: tokens until the next top-level COMMA
    or matching outer ``}``. Handles nested braces.
    """
    depth = 0
    while pos < len(tokens):
        tok = tokens[pos]
        if tok.kind == _T_LBRACE:
            depth += 1
            pos += 1
        elif tok.kind == _T_RBRACE:
            if depth == 0:
                return pos  # outer ``}`` — caller handles
            depth -= 1
            pos += 1
        elif tok.kind == _T_COMMA and depth == 0:
            return pos
        else:
            pos += 1
    return pos


def _expect(
    tokens: list[_Token], pos: int, kind: str, line_hint: int, where: str
) -> int:
    """Assert that ``tokens[pos]`` has kind ``kind``; return ``pos + 1``."""
    if pos >= len(tokens) or tokens[pos].kind != kind:
        actual = (
            f"{tokens[pos].kind} {tokens[pos].value!r}"
            if pos < len(tokens)
            else "EOF"
        )
        raise _Asn1SyntaxError(
            f"Expected {kind!r} {where}; got {actual}", line_hint
        )
    return pos + 1


# ─── L2: PER decoder (D-019) ────────────────────────────────────────


class _PerDecodeError(Exception):
    """Internal exception raised when pycrate fails to decode a per-RAT OCTET STRING.

    Carries ``rat_type`` and a bounded ``failure_reason`` enum token (currently
    always ``"per_decode_failed"``; future refinements can sub-bucket). The
    dispatcher wraps this exception as :data:`QCT-E004` via
    ``format_code("QCT-E004", rat_type=..., line=..., failure_reason=...)``
    before emitting to stderr or to a compact report.
    """

    def __init__(self, rat_type: str, failure_reason: str, original: Exception) -> None:
        super().__init__(
            f"PER decode failed for rat-Type={rat_type!r}: {failure_reason}"
        )
        self.rat_type = rat_type
        self.failure_reason = failure_reason
        self.original = original


def _get_pycrate_type(rat_type: str):
    """Look up the pycrate ASN.1 type object for a given ``rat-Type`` enum value.

    Per D-015 / D-019:

    - ``"eutra"``        → TS 36.331 ``UE_EUTRA_Capability``
    - ``"nr"``           → TS 38.331 ``UE_NR_Capability``
    - ``"eutra-nr"``     → TS 38.331 ``UE_MRDC_Capability`` (EN-DC outer container)
    - ``"mrdc-XPDCP"``   → TS 38.331 ``UE_MRDC_Capability`` (Rel-15 variant)

    Imports are lazy so ucap's startup doesn't pay the pycrate-load cost when
    only the indented-tree adapter is exercised.

    Raises ``ValueError`` on unsupported ``rat_type``.
    """
    if rat_type == "eutra":
        from pycrate_asn1dir.RRCLTE import EUTRA_RRC_Definitions
        return EUTRA_RRC_Definitions.UE_EUTRA_Capability
    if rat_type == "nr":
        from pycrate_asn1dir.RRCNR import NR_RRC_Definitions
        return NR_RRC_Definitions.UE_NR_Capability
    if rat_type in ("eutra-nr", "mrdc-XPDCP"):
        from pycrate_asn1dir.RRCNR import NR_RRC_Definitions
        return NR_RRC_Definitions.UE_MRDC_Capability
    raise ValueError(
        f"Unsupported rat-Type {rat_type!r} "
        f"(expected one of: 'eutra', 'nr', 'eutra-nr', 'mrdc-XPDCP')"
    )


def _bucket_per_decode_failure(exc: Exception) -> str:
    """Map a pycrate exception to one of the QCT-E002 ``{validation_failure}``
    bounded-enum tokens documented in :mod:`ucap.diagnostics`.

    v1 implementation is coarse — any pycrate decode failure buckets to
    ``"per_decode_failed"``. Future refinement could parse exception text to
    distinguish ``type_mismatch`` / ``value_out_of_range`` etc. but the value
    of those buckets is low until real-log experience suggests which are
    actually informative.
    """
    return "per_decode_failed"


def decode_rat_container(container: Asn1RatContainer) -> dict:
    """PER-decode a single :class:`Asn1RatContainer` via pycrate.

    Returns the decoded value as a Python dict (pycrate's natural shape for
    ASN.1 SEQUENCE values — nested dicts, tuples for CHOICE, lists for
    SEQUENCE-OF, bytes for OCTET STRING, ints / bools / strs for primitives).

    Raises :class:`_PerDecodeError` on pycrate decode failure — the
    dispatcher (or other caller) catches this and emits ``QCT-E004``.
    Raises ``ValueError`` if ``container.rat_type`` is unsupported.
    """
    pyc_type = _get_pycrate_type(container.rat_type)
    try:
        pyc_type.from_uper(container.encoded)
    except Exception as exc:  # pycrate raises various exception types
        raise _PerDecodeError(
            rat_type=container.rat_type,
            failure_reason=_bucket_per_decode_failure(exc),
            original=exc,
        ) from exc
    return pyc_type.get_val()


def decode_message_containers(msg: Asn1Message) -> tuple[dict, ...]:
    """Decode all RAT containers in an :class:`Asn1Message`.

    Returns a tuple of decoded dicts, one per container, in the same order as
    :attr:`Asn1Message.rat_containers`. Raises :class:`_PerDecodeError` on
    the first failure; the caller decides whether to wrap as ``QCT-E004`` and
    abort the message, or to attempt partial recovery (L3's policy choice).
    """
    return tuple(decode_rat_container(c) for c in msg.rat_containers)


# ─── L3: pycrate-dict → CanonicalUeCapability (D-019) ───────────────


def map_asn1_message_to_canonical(
    msg: Asn1Message,
    *,
    vendor: Vendor,
    release: Release,
    source_file: str,
) -> CanonicalUeCapability:
    """Map an :class:`Asn1Message` (post-L1 outer parser) to a fully-populated
    :class:`CanonicalUeCapability`.

    Internally calls L2 (PER decode) for each RAT container, then dispatches
    to per-RAT mappers (``_map_eutra_from_dict`` and friends). The output
    shape mirrors the indented adapter's ``map_message_to_canonical`` —
    callers see the same canonical JSON regardless of source format (per
    ``NFR-9``).

    v1 first pass implements **EUTRA only**. NR and MRDC paths raise
    ``NotImplementedError`` and are tracked as follow-on work under task #17.
    """
    decoded_pairs: list[tuple[str, dict]] = []
    for container in msg.rat_containers:
        decoded = decode_rat_container(container)  # raises _PerDecodeError
        decoded_pairs.append((container.rat_type, decoded))

    rats_present, eutra, nr, mrdc = _dispatch_decoded_pairs(decoded_pairs)

    meta = Meta(
        vendor=vendor,
        release=release,
        sourceFile=source_file,
        sourceLineRange=(msg.start_line, msg.end_line),
        decodedAt=datetime.now(tz=timezone.utc),
        parserVersion=_PARSER_VERSION,
    )

    return CanonicalUeCapability(
        _meta=meta,
        ratsPresent=rats_present,
        eutra=eutra,
        nr=nr,
        mrdc=mrdc,
    )


def _dispatch_decoded_pairs(
    decoded_pairs: list[tuple[str, dict]],
) -> tuple[list[RatName], EutraSection | None, NrSection | None, MrdcSection | None]:
    """Two-pass L3 dispatch over already-decoded ``(rat_type, dict)`` pairs.

    Shared by the QCAT ASN.1 adapter (after L2 PER decode) and the Wireshark
    adapter (which gets pre-decoded dicts from Wireshark's own dissector and
    therefore skips L2 entirely).

    Pass 1: collect NR per-CC tables from the first NR container — MRDC reuses
    them per ``D-015`` / ``D-018``.

    Pass 2: each container is mapped to its canonical section. Each RAT lane
    is populated at most once; later duplicates are silently skipped.

    Raises ``ValueError`` for an unsupported ``rat_type``.
    """
    rats_present: list[RatName] = []
    eutra: EutraSection | None = None
    nr: NrSection | None = None
    mrdc: MrdcSection | None = None

    nr_per_cc = _NrPerCcTablesDict()
    for rat_type, decoded in decoded_pairs:
        if rat_type == "nr" and not nr_per_cc.downlink and not nr_per_cc.uplink:
            nr_per_cc = _collect_nr_per_cc_tables_dict(decoded)

    for rat, decoded in decoded_pairs:
        if rat == "eutra":
            if eutra is None:
                eutra = _map_eutra_from_dict(decoded)
                rats_present.append("eutra")
        elif rat == "nr":
            if nr is None:
                nr = _map_nr_from_dict(decoded)
                rats_present.append("nr")
        elif rat in ("eutra-nr", "mrdc-XPDCP"):
            if mrdc is None:
                mrdc = _map_mrdc_from_dict(decoded, nr_per_cc=nr_per_cc)
                rats_present.append("mrdc")
        else:
            raise ValueError(f"Unsupported rat-Type {rat!r}")

    return rats_present, eutra, nr, mrdc


# ─── L3: per-RAT mappers ────────────────────────────────────────────


# Version-suffix patterns used by 3GPP RRC to indicate the release that
# introduced a field:
#   -rN / -rNN — release N (e.g. ``mac-Parameters-r17``).
#   -vMMmm     — release MM, sub-version mm (e.g. ``rf-Parameters-v1610``
#                = rel16.1.0; ``-v1700`` = rel17.0.0).
# Both patterns require a non-alphanumeric boundary after the digits so we
# don't accidentally read ``-r170`` as release 17 or ``-r9_x`` as r9.
_VSUFFIX_R = re.compile(r"-r(\d{1,2})(?!\w)")
_VSUFFIX_V = re.compile(r"-v(\d{2})\d{2}(?!\w)")


def infer_release(value: object) -> str | None:
    """Infer the 3GPP release a UE Capability container reports against.

    Walks the decoded pycrate-shape value recursively and looks at every
    dict-key encountered for a ``-rN`` or ``-vMMmm`` version suffix; takes
    the highest release seen and returns it as ``"relN"``. Returns ``None``
    if no version-suffixed field names appear, which typically means the
    container only carries rel15 base fields (or rel8 base for LTE).

    Why this exists: ``accessStratumRelease`` is **not** a reliable signal
    for the practical release coverage of an NR UE Capability message.
    TS 38.331's ``AccessStratumRelease ::= ENUMERATED {rel15, spare7..1}``
    only populates ``rel15``; rel16/17/18 features are encoded as
    version-suffixed field names and ``nonCriticalExtension`` chain layers.
    A fully rel17-capable NR UE still reports ``accessStratumRelease=rel15``.

    For LTE, ``accessStratumRelease`` *does* track baseline AS support
    (rel8..rel15+), but optional features still appear with
    ``-rN`` / ``-vMMmm`` suffixes, so this scan complements it.

    The function is robust to pycrate's CHOICE shape (``(tag, sub)`` tuples)
    and to nested lists. Field-name scanning is purely lexical — no schema
    knowledge required.
    """
    max_release = 0

    def _walk(v: object) -> None:
        nonlocal max_release
        if isinstance(v, dict):
            for k, sub in v.items():
                if isinstance(k, str):
                    m = _VSUFFIX_R.search(k)
                    if m:
                        max_release = max(max_release, int(m.group(1)))
                    m = _VSUFFIX_V.search(k)
                    if m:
                        max_release = max(max_release, int(m.group(1)))
                _walk(sub)
        elif isinstance(v, list):
            for item in v:
                _walk(item)
        elif isinstance(v, tuple) and len(v) == 2 and isinstance(v[0], str):
            # pycrate CHOICE form: (tag, sub-value).
            _walk(v[1])
        # Primitives: nothing to scan.

    _walk(value)
    return f"rel{max_release}" if max_release > 0 else None


def _flatten_extensions(decoded: dict) -> dict:
    """Walk the ``nonCriticalExtension`` chain and merge each layer's fields
    into a flat dict.

    3GPP RRC adds per-release fields under a chained ``nonCriticalExtension``
    sub-SEQUENCE: ``UE-EUTRA-Capability → V920-IEs → V940-IEs → V1020-IEs →
    …``. Each layer's fields are non-overlapping (3GPP assigns unique names
    like ``rf-Parameters-v1020``, ``rf-Parameters-v1090``, etc.), so a flat
    merge is unambiguous.

    Returns a dict with all encountered fields keyed by their original names;
    ``nonCriticalExtension`` and ``lateNonCriticalExtension`` are consumed
    during the walk and not included in the result.
    """
    result: dict = {}
    cur: dict | None = decoded
    while cur is not None:
        for k, v in cur.items():
            if k in ("nonCriticalExtension", "lateNonCriticalExtension"):
                continue
            result[k] = v
        nxt = cur.get("nonCriticalExtension")
        if not isinstance(nxt, dict):
            break
        cur = nxt
    return result


def _map_eutra_from_dict(decoded: dict) -> EutraSection:
    """Map a pycrate-decoded ``UE-EUTRA-Capability`` dict to an :class:`EutraSection`.

    Coverage:

    - ``accessStratumRelease`` from the base SEQUENCE.
    - ``supportedBands`` from ``supportedBandListEUTRA`` with the
      ``supportedBandListEUTRA-v9e0`` band-number overlay applied (``FR-26``):
      bands above 64 carry their true value from ``bandEUTRA-v9e0`` rather than
      the placeholder 64.
    - ``caCombinations`` merged from three sources, ``combinationId`` contiguous:
      ``supportedBandCombination-r10`` (``"main"``, BCS from the index-parallel
      ``supportedBandCombinationExt-r10``), ``supportedBandCombinationAdd-r11``
      (``"addR11"``, inline BCS — ``FR-2`` parity), and
      ``supportedBandCombinationReduced-r13`` (``"reducedR13"``, inline BCS —
      ``FR-27``).

    All combo lists and the v9e0 overlay are located by merging every
    ``rf-Parameters*`` extension layer into one view — 3GPP assigns unique field
    names per layer, so this is collision-free and release-structure-agnostic.

    **Still deferred (FR-15)**: per-combo extension flags (256QAM-DL / 64QAM-UL /
    1024QAM-DL) from ``-v1090`` / ``-v10i0`` / ``-v1430``.
    """
    flat = _flatten_extensions(decoded)
    access_stratum_release = flat.get("accessStratumRelease", "rel8")

    # Merge all rf-Parameters* layers (base + every -vXXXX) into one view. The
    # lists we need live across layers: supportedBandListEUTRA→rf-Parameters,
    # -v9e0→v9e0, r10→v1020, Ext-r10→v1060, Add-r11→v1180, Reduced-r13→v1310.
    rf_all: dict = {}
    for key, val in flat.items():
        if (key == "rf-Parameters" or key.startswith("rf-Parameters-")) and isinstance(val, dict):
            rf_all.update(val)

    supported_bands = _map_eutra_supported_bands(rf_all)

    ca_combinations: list[EutraCaCombination] = []

    # Main Rel-10 list; BCS comes from the index-parallel Ext-r10 list.
    main_raw = rf_all.get("supportedBandCombination-r10") or []
    ext_raw = rf_all.get("supportedBandCombinationExt-r10") or []
    for src_i, combo_entry in enumerate(main_raw):
        ext_entry = ext_raw[src_i] if src_i < len(ext_raw) and isinstance(ext_raw[src_i], dict) else None
        bcs = (
            _bcs_positions(ext_entry.get("supportedBandwidthCombinationSet-r10"))
            if ext_entry is not None
            else None
        )
        ca_combinations.append(_map_eutra_combo_r10(len(ca_combinations), combo_entry, bcs=bcs))

    # Rel-11 Add list (wrapped, inline BCS) — FR-2 parity.
    for combo in rf_all.get("supportedBandCombinationAdd-r11") or []:
        c = _map_eutra_combo_wrapped(
            len(ca_combinations), combo, source="addR11",
            band_list_key="bandParameterList-r11",
            bcs_key="supportedBandwidthCombinationSet-r11",
            band_mapper=lambda bp: _map_eutra_band_params_r10(
                bp,
                band_field="bandEUTRA-r11",
                dl_field="bandParametersDL-r11",
                ul_field="bandParametersUL-r11",
            ),
        )
        if c is not None:
            ca_combinations.append(c)

    # Rel-13 Reduced list (wrapped, inline BCS) — FR-27.
    for combo in rf_all.get("supportedBandCombinationReduced-r13") or []:
        c = _map_eutra_combo_wrapped(
            len(ca_combinations), combo, source="reducedR13",
            band_list_key="bandParameterList-r13",
            bcs_key="supportedBandwidthCombinationSet-r13",
            band_mapper=_map_eutra_band_params_r13,
        )
        if c is not None:
            ca_combinations.append(c)

    return EutraSection(
        accessStratumRelease=str(access_stratum_release),
        inferredRelease=infer_release(decoded),
        supportedBands=supported_bands,
        caCombinations=ca_combinations,
    )


def _map_eutra_combo_r10(
    idx: int, combo_entry: list | dict, *, bcs: list[int] | None = None
) -> EutraCaCombination:
    """Map one entry of ``supportedBandCombination-r10`` to :class:`EutraCaCombination`.

    The Rel-10 grammar is ``SupportedBandCombination-r10 ::= SEQUENCE (SIZE
    (..)) OF BandCombinationParameters-r10``; pycrate decodes each combo as a
    list of band-parameter dicts. ``bcs`` (set-bit positions) comes from the
    index-parallel ``supportedBandCombinationExt-r10`` list and is passed in by
    the caller so the model is constructed in one shot (no post-build mutation).
    """
    # combo_entry is a list of band-parameter dicts.
    band_list = combo_entry if isinstance(combo_entry, list) else []

    band_entries: list[EutraComboBandEntry] = []
    for bp in band_list:
        if not isinstance(bp, dict):
            continue
        band_entries.append(_map_eutra_band_params_r10(bp))

    return EutraCaCombination(
        combinationId=idx,
        label=_format_eutra_combo_label(band_entries),
        bands=band_entries,
        bcs=bcs,
        supports256QAMDL=None,
        supports64QAMUL=None,
        supports1024QAMDL=None,
        source="main",
    )


def _map_eutra_band_params_r10(
    bp: dict,
    *,
    band_field: str = "bandEUTRA-r10",
    dl_field: str = "bandParametersDL-r10",
    ul_field: str = "bandParametersUL-r10",
) -> EutraComboBandEntry:
    """Map one ``BandParameters-r10`` (or ``-r11``) dict to :class:`EutraComboBandEntry`.

    Rel-11's ``BandParameters-r11`` keeps the Rel-10 SEQUENCE-OF DL/UL shape and
    the inner ``ca-BandwidthClass*-r10`` / ``supportedMIMO-Capability*-r10`` field
    names, but renames the outer band-number and ``bandParameters{DL,UL}`` fields
    to ``-r11`` — pass ``band_field`` / ``dl_field`` / ``ul_field`` to select them.
    """
    band_eutra = bp.get(band_field)
    band = int(band_eutra) if band_eutra is not None else 0

    # DL: SEQUENCE OF { ca-BandwidthClassDL-r10, supportedMIMO-CapabilityDL-r10 OPT }
    # In TS 36.331 there's typically zero or one BW class per direction; pycrate
    # produces a list. We take the first entry's class as the canonical value.
    dl_class = None
    dl_layers = None
    dl_list = bp.get(dl_field) or []
    if dl_list and isinstance(dl_list[0], dict):
        dl0 = dl_list[0]
        dl_class_raw = dl0.get("ca-BandwidthClassDL-r10")
        if dl_class_raw is not None:
            dl_class = _normalize_ca_bw_class(dl_class_raw)
        dl_layers_raw = dl0.get("supportedMIMO-CapabilityDL-r10")
        if dl_layers_raw is not None:
            dl_layers = _normalize_mimo_capability(dl_layers_raw)

    ul_class = None
    ul_layers = None
    ul_list = bp.get(ul_field) or []
    if ul_list and isinstance(ul_list[0], dict):
        ul0 = ul_list[0]
        ul_class_raw = ul0.get("ca-BandwidthClassUL-r10")
        if ul_class_raw is not None:
            ul_class = _normalize_ca_bw_class(ul_class_raw)
        ul_layers_raw = ul0.get("supportedMIMO-CapabilityUL-r10")
        if ul_layers_raw is not None:
            ul_layers = _normalize_mimo_capability(ul_layers_raw)

    return EutraComboBandEntry(
        band=band,
        caBandwidthClassDL=dl_class,
        caBandwidthClassUL=ul_class,
        maxLayersDL=dl_layers,
        maxLayersUL=ul_layers,
    )


def _map_eutra_supported_bands(rf_all: dict) -> list[EutraBand]:
    """Build the EUTRA supported-band list, applying the v9e0 overlay (``FR-26``).

    ``supportedBandListEUTRA-v9e0`` is an index-parallel list (same length, same
    order, per TS 36.331); where an entry carries ``bandEUTRA-v9e0`` it overrides
    the base ``bandEUTRA`` (pinned to the 64 placeholder for bands above 64).
    """
    base = rf_all.get("supportedBandListEUTRA") or []
    v9e0 = rf_all.get("supportedBandListEUTRA-v9e0") or []
    bands: list[EutraBand] = []
    for i, entry in enumerate(base):
        if not isinstance(entry, dict):
            continue
        band_num = entry.get("bandEUTRA")
        if band_num is None:
            continue
        if i < len(v9e0) and isinstance(v9e0[i], dict):
            override = v9e0[i].get("bandEUTRA-v9e0")
            if override is not None:
                band_num = override
        bands.append(
            EutraBand(band=int(band_num), halfDuplex=bool(entry.get("halfDuplex", False)))
        )
    return bands


def _bcs_positions(bs: object) -> list[int] | None:
    """BCS BIT STRING → set-bit positions (e.g. ``'1111'`` → ``[0,1,2,3]``).

    Matches the indented adapter's `_parse_binary_string` convention so the two
    formats stay equivalent under ``NFR-9``.
    """
    bits = _bit_string_to_list(bs)
    if bits is None:
        return None
    return [i for i, b in enumerate(bits) if b]


def _map_eutra_combo_wrapped(
    idx: int,
    combo: object,
    *,
    source: str,
    band_list_key: str,
    bcs_key: str,
    band_mapper,
) -> EutraCaCombination | None:
    """Map a wrapped EUTRA combo (Add-r11 / Reduced-r13 shape) to a combination.

    Both wrap their per-CC entries in a ``bandParameterList-rXX`` field and carry
    an inline ``supportedBandwidthCombinationSet-rXX`` BCS bitmap, unlike the bare
    Rel-10 list. ``band_mapper`` maps one per-CC entry to an `EutraComboBandEntry`.
    """
    if not isinstance(combo, dict):
        return None
    entries: list[EutraComboBandEntry] = []
    for bp in combo.get(band_list_key) or []:
        if isinstance(bp, dict):
            entry = band_mapper(bp)
            if entry is not None:
                entries.append(entry)
    if not entries:
        return None
    return EutraCaCombination(
        combinationId=idx,
        label=_format_eutra_combo_label(entries),
        bands=entries,
        bcs=_bcs_positions(combo.get(bcs_key)),
        source=source,  # type: ignore[arg-type]
    )


def _map_eutra_band_params_r13(bp: dict) -> EutraComboBandEntry:
    """Map one ``BandParameters-r13`` dict to :class:`EutraComboBandEntry`.

    Unlike Rel-10/11, the Rel-13 ``bandParameters{DL,UL}-r13`` are single
    SEQUENCEs (not SEQUENCE-OF), and the DL inner fields carry the ``-r13``
    suffix while the UL inner fields re-use the ``-r10`` names.
    """
    band_eutra = bp.get("bandEUTRA-r13")
    band = int(band_eutra) if band_eutra is not None else 0

    dl = bp.get("bandParametersDL-r13")
    dl_class = dl_layers = None
    if isinstance(dl, dict):
        if dl.get("ca-BandwidthClassDL-r13") is not None:
            dl_class = _normalize_ca_bw_class(dl.get("ca-BandwidthClassDL-r13"))
        if dl.get("supportedMIMO-CapabilityDL-r13") is not None:
            dl_layers = _normalize_mimo_capability(dl.get("supportedMIMO-CapabilityDL-r13"))

    ul = bp.get("bandParametersUL-r13")
    ul_class = ul_layers = None
    if isinstance(ul, dict):
        if ul.get("ca-BandwidthClassUL-r10") is not None:
            ul_class = _normalize_ca_bw_class(ul.get("ca-BandwidthClassUL-r10"))
        if ul.get("supportedMIMO-CapabilityUL-r10") is not None:
            ul_layers = _normalize_mimo_capability(ul.get("supportedMIMO-CapabilityUL-r10"))

    return EutraComboBandEntry(
        band=band,
        caBandwidthClassDL=dl_class,
        caBandwidthClassUL=ul_class,
        maxLayersDL=dl_layers,
        maxLayersUL=ul_layers,
    )


def _normalize_ca_bw_class(raw: str | None) -> str | None:
    """ASN.1 ENUMERATED for CA-BandwidthClass uses lowercase tokens (``a``,
    ``b``, ...); canonical schema uses uppercase (``A``, ``B``, ...).
    """
    if raw is None:
        return None
    return str(raw).upper() if len(str(raw)) == 1 else None


def _normalize_mimo_capability(raw: str | None) -> int | None:
    """Map MIMO-CapabilityDL-r10 enum tokens (``twoLayers``, ``fourLayers``,
    ``eightLayers``) to integer layer counts.
    """
    if raw is None:
        return None
    mapping = {
        "twoLayers": 2,
        "fourLayers": 4,
        "eightLayers": 8,
        "sixteenLayers": 16,
    }
    return mapping.get(str(raw))


# ─── NR mapper (TS 38.331 → NrSection) ──────────────────────────────


@dataclass(frozen=True)
class _NrPerCcTablesDict:
    """Per-CC feature-set tables, dict-shape parallel to the indented adapter's
    :class:`_indented._NrPerCcTables` but holding pycrate-decoded dicts.

    Always sourced from ``ue-NR-Capability.featureSets`` (the NR container's
    own ``featureSets``); the MRDC container reuses these per `D-015` /
    `D-018` even when it has its own ``featureSetCombinations`` table.
    """

    downlink: tuple[dict, ...] = ()
    uplink: tuple[dict, ...] = ()
    dl_per_cc: tuple[dict, ...] = ()
    ul_per_cc: tuple[dict, ...] = ()


@dataclass(frozen=True)
class _ResolvedNrCapsDict:
    """Resolved per-CC capabilities for one band in one combo (post-feature-set walk)."""

    scs: int | None = None
    channel_bw_dl: str | None = None
    channel_bw_ul: str | None = None
    max_layers_dl: int | None = None
    max_layers_ul: int | None = None
    modulation_dl: Modulation | None = None
    modulation_ul: Modulation | None = None


def _collect_nr_per_cc_tables_dict(decoded: dict) -> _NrPerCcTablesDict:
    """Collect NR per-CC tables from ``ue-NR-Capability.featureSets``."""
    fs = decoded.get("featureSets")
    if not isinstance(fs, dict):
        return _NrPerCcTablesDict()
    return _NrPerCcTablesDict(
        downlink=tuple(fs.get("featureSetsDownlink", []) or []),
        uplink=tuple(fs.get("featureSetsUplink", []) or []),
        dl_per_cc=tuple(fs.get("featureSetsDownlinkPerCC", []) or []),
        ul_per_cc=tuple(fs.get("featureSetsUplinkPerCC", []) or []),
    )


def _map_nr_from_dict(decoded: dict) -> NrSection:
    """Map a pycrate-decoded ``UE-NR-Capability`` dict to an :class:`NrSection`.

    Coverage:

    - ``accessStratumRelease`` from the base SEQUENCE.
    - ``supportedBands`` from ``rf-Parameters.supportedBandListNR`` (one
      :class:`NrBand` per entry; FR derived from band number per `_derive_fr`).
      ``scsSupported`` left empty (`FR-17` deferred).
    - ``bandCombinations`` from ``rf-Parameters.supportedBandCombinationList``
      with feature-set indirection resolved per `D-015`.

    Pure UE-NR-Capability never carries EUTRA bands or mrdc-Parameters, so
    every combo's :attr:`NrBandCombination.kind` is ``"caNR"``.

    **Deferred** (`FR-16`): ``supportedBandCombinationList-v1540``,
    ``-v1590`` extensions.
    """
    asr = decoded.get("accessStratumRelease", "unknown")

    bands: list[NrBand] = []
    rf = decoded.get("rf-Parameters", {})
    band_list_raw = rf.get("supportedBandListNR", []) or []
    for entry in band_list_raw:
        if not isinstance(entry, dict):
            continue
        b = entry.get("bandNR")
        if b is None:
            continue
        bands.append(NrBand(band=int(b), fr=_derive_fr(int(b)), scsSupported=[]))

    per_cc = _collect_nr_per_cc_tables_dict(decoded)
    fs = decoded.get("featureSets")
    combinations = (
        tuple(fs.get("featureSetCombinations", []) or [])
        if isinstance(fs, dict)
        else ()
    )

    combos: list[NrBandCombination] = []
    main_list = rf.get("supportedBandCombinationList", []) or []
    for i, combo_entry in enumerate(main_list):
        combo = _map_nr_band_combination_dict(
            combo_entry,
            idx=i,
            source="main",
            combinations=combinations,
            per_cc=per_cc,
        )
        if combo is not None:
            combos.append(combo)

    return NrSection(
        accessStratumRelease=str(asr),
        inferredRelease=infer_release(decoded),
        supportedBands=bands,
        bandCombinations=combos,
    )


def _map_nr_band_combination_dict(
    combo: dict,
    *,
    idx: int,
    source: str,
    combinations: tuple[dict, ...] | tuple[list, ...],
    per_cc: _NrPerCcTablesDict,
) -> NrBandCombination | None:
    """Map one ``BandCombination`` dict to :class:`NrBandCombination`.

    Pulls feature-set-resolved per-CC caps for NR bands via
    :func:`_resolve_nr_caps_dict`. EUTRA bands (only possible in MRDC
    containers; pure NR shouldn't have them) carry their own BW class but
    no per-CC NR caps.
    """
    entries, has_eutra, has_nr, fsc_id = _extract_combo_band_entries_dict(
        combo, combinations, per_cc
    )
    if not entries:
        return None

    has_mrdc = "mrdc-Parameters" in combo
    if has_eutra:
        kind: NrComboKind = "endc"
    elif has_mrdc and has_nr:
        kind = "nrdc"
    else:
        kind = "caNR"

    return NrBandCombination(
        combinationId=idx,
        label=_make_combo_label(entries),
        kind=kind,
        bands=entries,
        bcs=_bit_string_to_list(combo.get("supportedBandwidthCombinationSet")),
        featureSetCombinationId=fsc_id if fsc_id >= 0 else None,
        powerClassNR=_normalize_power_class(combo.get("powerClass-v1530")),
        source=source,  # type: ignore[arg-type]
    )


def _extract_combo_band_entries_dict(
    combo: dict,
    combinations: tuple,
    per_cc: _NrPerCcTablesDict,
) -> tuple[list[NrComboBandEntry], bool, bool, int]:
    """Walk ``combo.bandList`` (a list of ``BandParameters`` CHOICE values).

    Each entry is a ``(tag, sub-dict)`` tuple in pycrate's CHOICE
    representation: tag is ``"eutra"`` or ``"nr"``; sub-dict carries the
    band number and CA bandwidth classes for that direction.

    Returns ``(entries, has_eutra, has_nr, fsc_id)``. ``fsc_id`` is the
    0-indexed ``featureSetCombination`` reference or -1 if absent.
    """
    band_list = combo.get("bandList", []) or []
    fsc_id_raw = combo.get("featureSetCombination")
    fsc_id = int(fsc_id_raw) if fsc_id_raw is not None else -1

    has_eutra = False
    has_nr = False
    entries: list[NrComboBandEntry] = []

    for band_idx, bp in enumerate(band_list):
        # bp is pycrate's CHOICE form: (tag, sub-dict).
        if not isinstance(bp, tuple) or len(bp) != 2:
            continue
        tag, sub = bp
        if not isinstance(sub, dict):
            continue
        if tag == "eutra":
            has_eutra = True
            band_e = sub.get("bandEUTRA")
            entries.append(
                NrComboBandEntry(
                    bandEUTRA=int(band_e) if band_e is not None else None,
                    caBandwidthClassDL=_normalize_bw_class(
                        sub.get("ca-BandwidthClassDL-EUTRA")
                    ),
                    caBandwidthClassUL=_normalize_bw_class(
                        sub.get("ca-BandwidthClassUL-EUTRA")
                    ),
                )
            )
        elif tag == "nr":
            has_nr = True
            caps = _resolve_nr_caps_dict(
                band_idx=band_idx,
                fsc_id=fsc_id,
                combinations=combinations,
                per_cc=per_cc,
            )
            band_n = sub.get("bandNR")
            entries.append(
                NrComboBandEntry(
                    bandNR=int(band_n) if band_n is not None else None,
                    caBandwidthClassDL=_normalize_bw_class(
                        sub.get("ca-BandwidthClassDL-NR")
                    ),
                    caBandwidthClassUL=_normalize_bw_class(
                        sub.get("ca-BandwidthClassUL-NR")
                    ),
                    scs=caps.scs,
                    channelBWDL=caps.channel_bw_dl,
                    channelBWUL=caps.channel_bw_ul,
                    maxLayersDL=caps.max_layers_dl,
                    maxLayersUL=caps.max_layers_ul,
                    modulationDL=caps.modulation_dl,
                    modulationUL=caps.modulation_ul,
                )
            )

    return entries, has_eutra, has_nr, fsc_id


def _resolve_nr_caps_dict(
    *,
    band_idx: int,
    fsc_id: int,
    combinations: tuple,
    per_cc: _NrPerCcTablesDict,
) -> _ResolvedNrCapsDict:
    """Walk the feature-set indirection chain for one band in one combo.

    ``fsc_id`` is the 0-indexed ``featureSetCombination`` index. Per 3GPP
    convention, the downstream feature-set IDs (``downlinkSetNR``,
    ``uplinkSetNR``, and the per-CC IDs inside ``featureSetListPerDownlinkCC``
    / ``UplinkCC``) are **1-indexed** with ``0`` meaning "no feature set."
    """
    if fsc_id < 0 or fsc_id >= len(combinations):
        return _ResolvedNrCapsDict()
    per_band_entries = combinations[fsc_id]
    if not isinstance(per_band_entries, list) or band_idx >= len(per_band_entries):
        return _ResolvedNrCapsDict()
    fspb_alts = per_band_entries[band_idx]
    if not isinstance(fspb_alts, list) or not fspb_alts:
        return _ResolvedNrCapsDict()
    # Take the first alternative (active feature set).
    first_alt = fspb_alts[0]
    if not isinstance(first_alt, tuple) or len(first_alt) != 2:
        return _ResolvedNrCapsDict()
    tag, fs_dict = first_alt
    if tag != "nr" or not isinstance(fs_dict, dict):
        return _ResolvedNrCapsDict()

    dl_set = int(fs_dict.get("downlinkSetNR", 0) or 0)
    ul_set = int(fs_dict.get("uplinkSetNR", 0) or 0)

    dl = _resolve_per_cc_dict(
        dl_set,
        per_cc.downlink,
        per_cc.dl_per_cc,
        cc_list_field="featureSetListPerDownlinkCC",
        scs_field="supportedSubcarrierSpacingDL",
        bw_field="supportedBandwidthDL",
        mimo_field="maxNumberMIMO-LayersPDSCH",
        mod_field="supportedModulationOrderDL",
    )
    ul = _resolve_per_cc_dict(
        ul_set,
        per_cc.uplink,
        per_cc.ul_per_cc,
        cc_list_field="featureSetListPerUplinkCC",
        scs_field="supportedSubcarrierSpacingUL",
        bw_field="supportedBandwidthUL",
        mimo_field="maxNumberMIMO-LayersPUSCH",
        mod_field="supportedModulationOrderUL",
    )

    return _ResolvedNrCapsDict(
        scs=dl["scs"] or ul["scs"],
        channel_bw_dl=dl["bw"],
        channel_bw_ul=ul["bw"],
        max_layers_dl=dl["layers"],
        max_layers_ul=ul["layers"],
        modulation_dl=dl["mod"],
        modulation_ul=ul["mod"],
    )


def _resolve_per_cc_dict(
    set_idx: int,
    fs_list: tuple[dict, ...],
    per_cc_list: tuple[dict, ...],
    *,
    cc_list_field: str,
    scs_field: str,
    bw_field: str,
    mimo_field: str,
    mod_field: str,
) -> dict:
    """Resolve a FeatureSetDownlink/Uplink → first CC → FeatureSetXPerCC entry."""
    empty: dict = {"scs": None, "bw": None, "layers": None, "mod": None}
    if set_idx <= 0 or set_idx > len(fs_list):
        return empty
    fs_entry = fs_list[set_idx - 1]
    if not isinstance(fs_entry, dict):
        return empty
    cc_id_list = fs_entry.get(cc_list_field, []) or []
    if not cc_id_list:
        return empty
    # CC list entries are FeatureSetXPerCC-Id INTEGER values (1-indexed; 0 = absent).
    cc_id_raw = cc_id_list[0]
    try:
        cc_id = int(cc_id_raw)
    except (TypeError, ValueError):
        return empty
    if cc_id <= 0 or cc_id > len(per_cc_list):
        return empty
    fspc = per_cc_list[cc_id - 1]
    if not isinstance(fspc, dict):
        return empty
    return {
        "scs": _SCS_MAP.get(str(fspc.get(scs_field)).strip())
        if fspc.get(scs_field)
        else None,
        "bw": _parse_channel_bw_dict(fspc.get(bw_field)),
        "layers": _MIMO_LAYERS.get(str(fspc.get(mimo_field)).strip())
        if fspc.get(mimo_field)
        else None,
        "mod": _MOD_MAP.get(str(fspc.get(mod_field)).strip())
        if fspc.get(mod_field)
        else None,
    }


# ─── MRDC mapper (TS 38.331 UE-MRDC-Capability → MrdcSection) ───────


def _map_mrdc_from_dict(
    decoded: dict, *, nr_per_cc: _NrPerCcTablesDict
) -> MrdcSection:
    """Map a pycrate-decoded ``UE-MRDC-Capability`` dict to :class:`MrdcSection`.

    The MRDC container carries its **own** ``featureSetCombinations`` table
    (separate from the NR container's) but **reuses the NR per-CC tables**
    for feature-set resolution per `D-015` / `D-018`. The two-pass dispatcher
    in :func:`map_asn1_message_to_canonical` collects ``nr_per_cc`` from the
    NR container before processing the MRDC container.

    Coverage:

    - ``rf-ParametersMRDC.supportedBandCombinationList`` → main EN-DC combos
      (``MrdcComboKind="endc"`` / ``MrdcComboSource="main"``).
    - ``rf-ParametersMRDC.supportedBandCombinationListNEDC-Only-r16`` →
      NEDC combos (``kind="nedc"`` / ``source="nedcOnlyR16"``).
    - ``rf-ParametersMRDC.supportedBandCombinationListNRDC-r16`` →
      NRDC combos (``kind="nrdc"`` / ``source="nrdcR16"``).

    Feature-set indirection resolves through ``decoded["featureSetCombinations"]``
    (MRDC's own table) plus ``nr_per_cc`` (NR's per-CC tables).
    """
    # MRDC's featureSetCombinations is a direct child of UE-MRDC-Capability,
    # NOT under a featureSets wrapper as in NR.
    combinations = tuple(decoded.get("featureSetCombinations", []) or [])

    rf_mrdc = decoded.get("rf-ParametersMRDC")
    if not isinstance(rf_mrdc, dict):
        return MrdcSection(
            inferredRelease=infer_release(decoded),
            bandCombinations=[],
        )

    combos: list[MrdcBandCombination] = []
    _append_mrdc_combos_dict(
        combos,
        rf_mrdc.get("supportedBandCombinationList"),
        kind="endc",
        source="main",
        combinations=combinations,
        per_cc=nr_per_cc,
    )
    _append_mrdc_combos_dict(
        combos,
        rf_mrdc.get("supportedBandCombinationListNEDC-Only-r16"),
        kind="nedc",
        source="nedcOnlyR16",
        combinations=combinations,
        per_cc=nr_per_cc,
    )
    _append_mrdc_combos_dict(
        combos,
        rf_mrdc.get("supportedBandCombinationListNRDC-r16"),
        kind="nrdc",
        source="nrdcR16",
        combinations=combinations,
        per_cc=nr_per_cc,
    )

    return MrdcSection(
        inferredRelease=infer_release(decoded),
        bandCombinations=combos,
    )


def _append_mrdc_combos_dict(
    combos: list[MrdcBandCombination],
    list_node: list | None,
    *,
    kind: MrdcComboKind,
    source: MrdcComboSource,
    combinations: tuple,
    per_cc: _NrPerCcTablesDict,
) -> None:
    """Append :class:`MrdcBandCombination` entries to ``combos`` for each
    BandCombination in ``list_node``. IDs continue sequentially from the
    current length of ``combos`` (so main + nedc + nrdc share one ID space).
    """
    if not isinstance(list_node, list):
        return
    start_idx = len(combos)
    for i, combo_entry in enumerate(list_node):
        if not isinstance(combo_entry, dict):
            continue
        combo = _map_mrdc_band_combination_dict(
            combo_entry,
            idx=start_idx + i,
            kind=kind,
            source=source,
            combinations=combinations,
            per_cc=per_cc,
        )
        if combo is not None:
            combos.append(combo)


def _map_mrdc_band_combination_dict(
    combo: dict,
    *,
    idx: int,
    kind: MrdcComboKind,
    source: MrdcComboSource,
    combinations: tuple,
    per_cc: _NrPerCcTablesDict,
) -> MrdcBandCombination | None:
    """Map one BandCombination dict from a UE-MRDC-Capability source list
    to :class:`MrdcBandCombination`. ``kind`` and ``source`` are pinned by
    the caller (main → endc, NEDC-Only-r16 → nedc, NRDC-r16 → nrdc).
    """
    entries, _has_eutra, _has_nr, fsc_id = _extract_combo_band_entries_dict(
        combo, combinations, per_cc
    )
    if not entries:
        return None
    return MrdcBandCombination(
        combinationId=idx,
        label=_make_combo_label(entries),
        kind=kind,
        bands=entries,
        bcs=_bit_string_to_list(combo.get("supportedBandwidthCombinationSet")),
        featureSetCombinationId=fsc_id if fsc_id >= 0 else None,
        powerClassNR=_normalize_power_class(combo.get("powerClass-v1530")),
        source=source,
    )


def _parse_channel_bw_dict(bw: tuple | dict | None) -> str | None:
    """Parse ``SupportedBandwidth`` CHOICE → canonical BW string (e.g. ``"mhz100"``).

    pycrate represents the CHOICE as a tuple ``(tag, value)`` where ``tag``
    is ``"fr1"`` or ``"fr2"`` and ``value`` is the ENUMERATED token string.
    """
    if bw is None:
        return None
    if isinstance(bw, tuple) and len(bw) == 2:
        tag, value = bw
        if tag in ("fr1", "fr2") and isinstance(value, str):
            return value
    return None


def _normalize_bw_class(raw: object) -> CaBandwidthClass | None:
    """Normalize pycrate's lowercase ASN.1 ENUMERATED token (``"a"``, ``"b"``, …)
    to the canonical uppercase :data:`CaBandwidthClass` (``"A"``, ``"B"``, …).
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if len(s) == 1:
        upper = s.upper()
        if upper in ("A", "B", "C", "D", "E", "F"):
            return upper  # type: ignore[return-value]
    return None


def _bit_string_to_list(bs: object) -> list[int] | None:
    """Convert pycrate's BIT STRING tuple ``(value, length)`` to a list of bits.

    Returns the bits in MSB-first order per ASN.1 convention.
    """
    if bs is None:
        return None
    if not isinstance(bs, tuple) or len(bs) != 2:
        return None
    value, length = bs
    try:
        value = int(value)
        length = int(length)
    except (TypeError, ValueError):
        return None
    return [(value >> (length - 1 - i)) & 1 for i in range(length)]


def _format_eutra_combo_label(entries: list[EutraComboBandEntry]) -> str:
    """Build the canonical combo label: ``<band><BWClass>`` joined by ``-``.

    Mirrors the indented adapter's helper (per qcat/MODULE.md Key choices →
    label-formatting logic shared between formats). NR bands are not relevant
    here (EUTRA-only adapter).
    """
    parts: list[str] = []
    for e in entries:
        bw = e.caBandwidthClassDL or e.caBandwidthClassUL or ""
        parts.append(f"{e.band}{bw}")
    return "-".join(parts)


# ─── Utility: brace matching ────────────────────────────────────────


def _find_matching_brace(text: str, open_pos: int) -> int:
    """Find the index of the ``}`` that matches ``text[open_pos]`` (a ``{``).

    Hex-string-aware: skips over ``'…'H`` literals so braces inside hex
    digits (which never actually appear, since hex is ``[0-9A-Fa-f]`` only)
    don't trip the depth count — but more importantly, single quotes inside
    hex literals don't get re-interpreted as starts of further hex literals.

    Returns ``-1`` if no matching ``}`` is found.
    """
    if text[open_pos] != "{":
        raise ValueError(f"_find_matching_brace expected '{{' at {open_pos}")
    depth = 1
    i = open_pos + 1
    n = len(text)
    in_hex = False
    while i < n:
        c = text[i]
        if in_hex:
            # End of hex string: ``'H``.
            if c == "'" and i + 1 < n and text[i + 1] == "H":
                in_hex = False
                i += 2
                continue
            i += 1
            continue
        if c == "'":
            in_hex = True
            i += 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1
