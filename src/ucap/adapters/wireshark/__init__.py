"""Wireshark RRC-dissection text-export adapter.

Wireshark's *File → Export Packet Dissections → As Plain Text* produces an
indented hierarchy where each ASN.1 field of an RRC PDU appears as one line.
Because Wireshark has already dissected the inner per-RAT
``ue-CapabilityRAT-Container`` OCTET STRINGs, this adapter does **not** need
to run the pycrate PER decoder — the decoded fields are right there in the
text. The path is:

    Wireshark text → indented tree (L1) → pycrate-equivalent dict (L2) →
    existing qcat._asn1 L3 mappers → CanonicalUeCapability

The L3 mappers (``_map_eutra_from_dict`` / ``_map_nr_from_dict`` /
``_map_mrdc_from_dict``) and the two-pass MRDC dispatcher are reused from the
QCAT ASN.1 adapter so the canonical JSON is identical regardless of source.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ucap import __version__ as _PARSER_VERSION
from ucap.adapters.qcat._asn1 import _dispatch_decoded_pairs
from ucap.adapters.wireshark._dict import (
    WiresharkEnvelopeError,
    extract_rat_containers,
)
from ucap.adapters.wireshark._parser import (
    WsTreeNode,
    parse_wireshark_file,
    parse_wireshark_text,
)
from ucap.schema import CanonicalUeCapability, Meta, Release, Vendor

__all__ = [
    "WsTreeNode",
    "WiresharkEnvelopeError",
    "parse_wireshark_text",
    "parse_wireshark_file",
    "parse_wireshark_to_canonical",
]


def parse_wireshark_to_canonical(
    path: str | Path,
    *,
    vendor: Vendor = "wireshark",
    release: Release,
    source_file: str | None = None,
) -> list[CanonicalUeCapability]:
    """One-step pipeline: parse a Wireshark text export → canonical records.

    Reads ``path``, parses the indented dissection tree, extracts each
    ``ue-CapabilityRAT-Container`` (already PER-decoded by Wireshark itself),
    converts each to a pycrate-equivalent dict, and runs the same L3 dispatch
    as the QCAT ASN.1 adapter — yielding ``CanonicalUeCapability`` records
    indistinguishable from the QCAT path (per ``NFR-9``).

    ``source_file`` defaults to the basename of ``path`` (recorded in
    ``Meta.sourceFile``).

    Returns a list because a single Wireshark export *can* carry multiple
    RRC PDUs (e.g. selecting several packets in Wireshark before exporting).
    For the common single-PDU case the list has one element.
    """
    p = Path(path)
    text = p.read_text()
    source_file = source_file if source_file is not None else p.name

    tree = parse_wireshark_text(text)

    # Wireshark may carry multiple top-level "Radio Resource Control (RRC)
    # protocol" subtrees if the user selected multiple packets at export
    # time. Each one is its own message.
    rrc_subtrees = [
        c for c in tree.children if c.name == "Radio Resource Control (RRC) protocol"
    ]
    if not rrc_subtrees:
        # Tolerate inputs where the top-level "Radio Resource Control (RRC)
        # protocol" header is missing but the rest of the envelope is present
        # (e.g. a user copied just the dissection sub-tree). Use the whole
        # synthetic root as one subtree.
        rrc_subtrees = [tree]

    results: list[CanonicalUeCapability] = []
    start_line = min((s.line for s in rrc_subtrees if s.line > 0), default=1)
    end_line = max(_max_line(s) for s in rrc_subtrees)

    for subtree in rrc_subtrees:
        decoded_pairs = extract_rat_containers(subtree)
        rats_present, eutra, nr, mrdc = _dispatch_decoded_pairs(decoded_pairs)

        meta = Meta(
            vendor=vendor,
            release=release,
            sourceFile=source_file,
            sourceLineRange=(start_line, end_line),
            decodedAt=datetime.now(tz=timezone.utc),
            parserVersion=_PARSER_VERSION,
        )
        results.append(
            CanonicalUeCapability(
                _meta=meta,
                ratsPresent=rats_present,
                eutra=eutra,
                nr=nr,
                mrdc=mrdc,
            )
        )

    return results


def _max_line(node: WsTreeNode) -> int:
    """Return the largest ``line`` number in the subtree rooted at ``node``."""
    m = node.line
    for c in node.children:
        m = max(m, _max_line(c))
    return m
