"""QCAT adapter — auto-dispatches between indented tree and ASN.1 value notation formats.

Per D-018, the qcat adapter is a sub-package with two internal implementation files:

- ``_indented.py`` — existing parser for the indented tree format (D-004).
- ``_asn1.py`` — new ASN.1 value notation parser with PER decoding (D-015 + D-018).
  Lands during D-015 development; not present in this commit.

The dispatcher (this file) reads the first ~50 lines of input and routes to
``_indented.parse_qcat_text`` or ``_asn1.parse_qcat_text`` per the format
discriminator in FR-21 (presence of ``message c1 : ueCapabilityInformation``).
Until ``_asn1.py`` is implemented, dispatch falls back to ``_indented`` for
every input — ASN.1 inputs will produce a parse failure with the existing
error path (and, post-D-015 development, ``QCT-E001`` / ``QCT-E003``).

Public API re-exports from ``_indented`` for now; once ``_asn1`` lands, the
re-export set stays the same — both internal modules contribute to the same
public surface, distinguished only by dispatch.
"""

from __future__ import annotations

from ucap.adapters.qcat._indented import (
    Message,
    TreeNode,
    map_message_to_canonical,
    parse_qcat_file,
    parse_qcat_text,
)

__all__ = [
    "TreeNode",
    "Message",
    "parse_qcat_text",
    "parse_qcat_file",
    "map_message_to_canonical",
]
