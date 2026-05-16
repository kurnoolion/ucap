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
from pathlib import Path
from typing import Iterator


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
