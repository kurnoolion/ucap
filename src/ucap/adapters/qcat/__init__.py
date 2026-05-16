"""QCAT adapter — auto-dispatches between indented tree and ASN.1 value notation formats.

Per ``D-018``, the qcat adapter is a sub-package with two internal implementation
files:

- ``_indented.py`` — parser + mapper for the indented tree format (``D-004``).
- ``_asn1.py`` — parser + pycrate-based PER decoder + canonical mapper for the
  ASN.1 value notation format (``D-015`` + ``D-019``).

The dispatcher in this module reads the first portion of input and routes to
``_indented`` or ``_asn1`` per ``FR-21``: presence of
``message c1 : ueCapabilityInformation`` (or the no-space variant) → ASN.1
adapter; otherwise (with ``UE Capability Information (...)`` title present)
→ indented tree adapter.

Two layers of public API are exposed:

1. **Low-level**: ``parse_qcat_text`` / ``parse_qcat_file`` / ``Message`` /
   ``TreeNode`` / ``map_message_to_canonical`` — re-exported from ``_indented``
   for backward compatibility and for callers that want the parse-then-map
   two-step against the indented format.

2. **High-level**: ``parse_qcat_to_canonical(path, *, vendor, release,
   source_file=None)`` — the one-step pipeline the CLI uses. Auto-detects
   format, decodes (PER if ASN.1), maps to ``CanonicalUeCapability``, returns
   a list of canonical records. This is the path callers should prefer.
"""

from __future__ import annotations

from pathlib import Path

from ucap.schema import CanonicalUeCapability, Release, Vendor

from ucap.adapters.qcat._asn1 import (
    Asn1Message,
    Asn1RatContainer,
    map_asn1_message_to_canonical,
    parse_asn1_text,
)
from ucap.adapters.qcat._indented import (
    Message,
    TreeNode,
    map_message_to_canonical,
    parse_qcat_file,
    parse_qcat_text,
)


__all__ = [
    # Low-level — indented format
    "TreeNode",
    "Message",
    "parse_qcat_text",
    "parse_qcat_file",
    "map_message_to_canonical",
    # Low-level — ASN.1 format
    "Asn1Message",
    "Asn1RatContainer",
    "parse_asn1_text",
    "map_asn1_message_to_canonical",
    # High-level pipeline
    "parse_qcat_to_canonical",
    "detect_format",
]


def detect_format(text: str) -> str:
    """Detect QCAT export format from the input text per ``FR-21``.

    Returns ``"asn1"`` if the ASN.1 value-notation entry marker
    (``message c1 : ueCapabilityInformation`` with optional whitespace before
    the first colon) is present anywhere in the text, otherwise ``"indented"``.

    This is a fast first-pass scan — both formats may occur in the same input
    if it's a multi-message log, but in practice a single QCAT install emits
    one or the other, not both. The dispatcher routes the whole file by its
    discriminator; mixed-format files are not supported in v1.
    """
    import re
    if re.search(r"message\s+c1\s*:\s*ueCapabilityInformation\s*:", text):
        return "asn1"
    return "indented"


def parse_qcat_to_canonical(
    path: str | Path,
    *,
    vendor: Vendor = "qcat",
    release: Release,
    source_file: str | None = None,
) -> list[CanonicalUeCapability]:
    """One-step pipeline: parse a QCAT export file and return canonical records.

    Auto-detects format per ``FR-21``. For ASN.1 inputs, the inner per-RAT
    OCTET STRINGs are PER-decoded via pycrate against TS 36.331 / TS 38.331
    v17.4.0 schemas (``D-019``).

    ``source_file`` defaults to the basename of ``path`` (recorded in
    ``Meta.sourceFile`` of each emitted ``CanonicalUeCapability``).
    """
    p = Path(path)
    text = p.read_text()
    source_file = source_file if source_file is not None else p.name

    if detect_format(text) == "asn1":
        return [
            map_asn1_message_to_canonical(
                m, vendor=vendor, release=release, source_file=source_file
            )
            for m in parse_asn1_text(text)
        ]
    # Indented tree format.
    return [
        map_message_to_canonical(
            m, vendor=vendor, release=release, source_file=source_file
        )
        for m in parse_qcat_text(text)
    ]
