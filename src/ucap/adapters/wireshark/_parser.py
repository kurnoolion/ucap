"""L1 parser for Wireshark RRC-dissection text exports.

Wireshark's *File → Export Packet Dissections → As Plain Text* output for an
RRC PDU is an indented hierarchy with one field per line. The grammar this
module recognises:

- **Root / summary node** — content with no ``:`` separator
  (e.g. ``Radio Resource Control (RRC) protocol``, ``UL-DCCH-Message``,
  ``Item 0``, ``UE-NR-Capability``). It opens a sub-tree.
- **Field with value** — ``<name>: <value>`` (e.g. ``rrc-TransactionIdentifier: 0``).
  May carry a ``[FC*]`` filter-context marker between name and ``:``.
- **BIT STRING with annotation** — ``<name>: <hex> [bit length N, ... decimal value V]``.
  The annotation is parsed out and surfaced as ``(value, length)`` metadata so
  the L2 converter can build a pycrate-equivalent ``(int, int)`` tuple.
- **OCTET STRING with inner dissection** — line carries hex; children one
  level deeper are the dissected inner content. Wireshark does this for the
  inner ``ue-CapabilityRAT-Container`` blob, which is why we can skip the
  pycrate PER decode altogether.
- **Per-bit child line** — ``.... ...1 fieldname: True|False``. The leading
  bit-pattern is presentation noise; the bit's named identifier + boolean
  value is what we keep.

Indent is 2 spaces per level. Blank lines and lines that don't match any
shape are dropped (Wireshark sometimes emits empty separator lines between
top-level frames).

The output is a :class:`WsTreeNode` tree rooted at a synthetic ``"<root>"``
node whose children are the top-level lines (typically one
``"Radio Resource Control (RRC) protocol"`` node per dissected PDU).

This module is L1 only — it does not interpret ASN.1 types or build canonical
records. Type semantics live in ``_dict.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


# ─── Data class ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class WsTreeNode:
    """One node of the Wireshark dissection tree.

    Attributes:
        name: Field name as it appears in the dissection. For ``Item N``
            entries this is literally ``"Item N"``. For per-bit children of a
            BIT STRING this is the named-bit identifier (e.g.
            ``"profile0x0001"``); the bit-pattern prefix is stripped.
        value: Raw value text after the ``:`` separator, with any ``[FC*]``
            marker and any ``[bit length ...]`` annotation already stripped.
            ``None`` for summary nodes that have no inline value.
        bit_info: For BIT STRING fields that came with a ``[bit length N, ...
            decimal value V]`` annotation, a ``(value, length)`` tuple parsed
            from that annotation. ``None`` otherwise.
        children: Tuple of children, indented one level deeper in the source.
        line: 1-based line number in the source file (for diagnostics).
    """

    name: str
    value: str | None
    bit_info: tuple[int, int] | None
    children: tuple["WsTreeNode", ...]
    line: int


# ─── Internal mutable builder ───────────────────────────────────────


@dataclass
class _NodeBuilder:
    name: str
    value: str | None
    bit_info: tuple[int, int] | None
    line: int
    indent: int
    children: list["_NodeBuilder"] = field(default_factory=list)

    def freeze(self) -> WsTreeNode:
        return WsTreeNode(
            name=self.name,
            value=self.value,
            bit_info=self.bit_info,
            children=tuple(c.freeze() for c in self.children),
            line=self.line,
        )


# ─── Line-level regexes ─────────────────────────────────────────────


# A bit-pattern prefix used by Wireshark for BIT STRING bit decompositions
# inside an octet: groups of 4 binary digits / dots separated by spaces.
# Example: ".... ...1 " or "...0 .... ".
_BIT_PATTERN_PREFIX = re.compile(r"^(?:[01.]{4} ){1,}[01.]{4} ")

# Optional filter-context marker that appears between name and colon, e.g.
# "ue-CapabilityRAT-Container [FC*]:". The marker is stripped; the field
# name is what precedes the bracket.
_FC_MARKER = re.compile(r"\s*\[FC[^\]]*\]\s*$")

# Trailing bit-length annotation, e.g. "[bit length 2, 6 LSB pad bits, 11..
# .... decimal value 3]". Extract length and decimal value.
_BIT_ANNOTATION = re.compile(
    r"\s*\[bit length (\d+)(?:[^]]*?decimal value (\d+))?[^\]]*\]\s*$"
)


# ─── Public entry points ────────────────────────────────────────────


def parse_wireshark_text(text: str) -> WsTreeNode:
    """Parse Wireshark text-export content into a :class:`WsTreeNode` tree.

    Returns a synthetic ``"<root>"`` node whose children are the top-level
    lines from the input. For a typical single-PDU export this means one
    child: the ``"Radio Resource Control (RRC) protocol"`` node.
    """
    root = _NodeBuilder(
        name="<root>", value=None, bit_info=None, line=0, indent=-1
    )
    # Stack of open builders, ordered by indent. Always has root at the
    # bottom; the top is the deepest currently-open node.
    stack: list[_NodeBuilder] = [root]

    for lineno, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        indent, content = _split_indent(raw)
        # Wireshark uses 2 spaces per level; treat odd indents as the same
        # level as the floor (defensive against trailing whitespace edits).
        level = indent // 2

        node = _parse_content(content, lineno)
        # An empty content line after indent stripping (shouldn't happen,
        # but be defensive).
        if node is None:
            continue
        node.indent = level

        # Pop until the top of stack is one shallower than this node.
        while stack and stack[-1].indent >= level:
            stack.pop()
        # Root sentinel has indent -1 so the stack never empties for level >= 0.
        if not stack:
            # Defensive: re-seed root if somehow drained.
            stack.append(root)
        stack[-1].children.append(node)
        stack.append(node)

    return root.freeze()


def parse_wireshark_file(path: str | Path) -> WsTreeNode:
    """Read a file from disk and parse it via :func:`parse_wireshark_text`."""
    return parse_wireshark_text(Path(path).read_text())


# ─── Line-level helpers ─────────────────────────────────────────────


def _split_indent(raw: str) -> tuple[int, str]:
    """Return ``(leading_space_count, stripped_content)``."""
    stripped = raw.lstrip(" ")
    return len(raw) - len(stripped), stripped.rstrip()


def _parse_content(content: str, lineno: int) -> _NodeBuilder | None:
    """Convert one Wireshark text line's content into a :class:`_NodeBuilder`.

    Handles the four line shapes (summary node, field-with-value,
    field-with-value-and-bit-annotation, per-bit child line). Returns
    ``None`` if content is unparseable.
    """
    # Strip a leading bit-pattern prefix (per-bit child line). The rest of
    # the line is a regular field-with-value.
    m = _BIT_PATTERN_PREFIX.match(content)
    if m:
        content = content[m.end():]

    # Split on the first ": " that isn't inside a "[FC*]" marker. Easiest:
    # find the first occurrence of ": " not preceded by "[FC*]" by first
    # canonicalising the FC marker out of the name side. We do this by
    # detecting whether the colon is preceded by "]"; if so, walk past it.
    colon = _find_separator_colon(content)
    if colon < 0:
        # Summary node: no value.
        return _NodeBuilder(
            name=content.strip(),
            value=None,
            bit_info=None,
            line=lineno,
            indent=0,
        )

    name = content[:colon].rstrip()
    value = content[colon + 2 :].strip()

    # Strip "[FC*]" / "[FC<anything>]" off the end of the name.
    name = _FC_MARKER.sub("", name).strip()

    # Strip trailing "[bit length N, ..., decimal value V]" off the value
    # and capture it as bit_info if present.
    bit_info: tuple[int, int] | None = None
    bm = _BIT_ANNOTATION.search(value)
    if bm:
        length = int(bm.group(1))
        decimal = int(bm.group(2)) if bm.group(2) is not None else 0
        bit_info = (decimal, length)
        value = value[: bm.start()].rstrip()

    return _NodeBuilder(
        name=name,
        value=value,
        bit_info=bit_info,
        line=lineno,
        indent=0,
    )


def _find_separator_colon(content: str) -> int:
    """Find the index of the first ``": "`` that acts as the field/value
    separator.

    Wireshark fields with filter-context markers look like
    ``ue-CapabilityRAT-Container [FC*]: <hex>``. The ``: `` we want is the
    one *after* the closing ``]``. There's no ``: `` inside the marker
    itself in any Wireshark version observed, so the simplest correct rule
    is: take the first ``": "`` whose preceding character isn't a digit
    that's part of a bit-position. In practice the only confounder is the
    bit-pattern children, which were already stripped upstream.
    """
    return content.find(": ")
