"""L2: convert a Wireshark :class:`WsTreeNode` tree into pycrate-equivalent
Python values.

Wireshark exports text per the ASN.1 field structure; pycrate's PER decoder
emits Python values per the same structure. The mapping is one-to-one for the
field shapes we care about in UE Capability messages:

==================== =================================== =========================
ASN.1 type           Wireshark text shape                pycrate value
==================== =================================== =========================
SEQUENCE             summary node with named children    ``dict[str, Any]``
SEQUENCE OF          ``field: N item(s)`` + ``Item N``s  ``list[Any]``
ENUMERATED           ``field: name (N)``                 ``"name"``  (string)
INTEGER              ``field: 42``                       ``int``
BOOLEAN              ``field: True`` / ``False``         ``bool``
BIT STRING (annot.)  ``field: c0 [bit length 2, ...]``   ``(value, length)`` tuple
BIT STRING (decomp.) parent with named-bit children      dict of named booleans*
OCTET STRING (hex)   ``field: deadbeef``                 ``bytes``
CHOICE               ``field: alt (N)`` + 1 child ``alt`` ``(alt, sub-dict)`` tuple
==================== =================================== =========================

\\*For BIT STRING with decomposed children, the canonical schema only surfaces
``supportedBandwidthCombinationSet`` (BCS bitmap) into the JSON output, and
that one is always emitted with a ``[bit length N, decimal value V]``
annotation by Wireshark. Other BIT STRINGs (PDCP profile flags etc.) get the
dict-of-booleans shape, which the L3 mappers tolerate via their ``.get()``
guards — they only look at the keys they care about.

Public API:

- :func:`convert_node` — convert any subtree to its pycrate-equivalent value.
- :func:`extract_rat_containers` — walk a parsed Wireshark tree's UL-DCCH
  envelope down to ``ue-CapabilityRAT-ContainerList`` and emit
  ``(rat_type, decoded_dict)`` pairs ready for the L3 dispatcher.
"""

from __future__ import annotations

import re
from typing import Any

from ucap.adapters.wireshark._parser import WsTreeNode


# ─── Value-shape recognisers ────────────────────────────────────────


# "name (N)" — ENUMERATED display: optional underscore/dash in names, digits
# in parentheses at end. Wireshark always pairs the identifier with its
# integer index for ENUMERATED, CHOICE, and "Item N"-style fields.
_ENUM_VALUE = re.compile(r"^([A-Za-z][A-Za-z0-9_\-]*)\s*\(\s*\d+\s*\)$")

# "N item" or "N items" — SEQUENCE OF item-count marker on the parent line.
_SEQOF_COUNT = re.compile(r"^(\d+)\s+items?$")

# Pure hex octets (no spaces, even length). Used to recognise OCTET STRING
# values. We *don't* greedily classify any short value as hex — "0" / "1" /
# "42" are integers; "True" / "False" are booleans; those are checked first.
_HEX_VALUE = re.compile(r"^[0-9a-fA-F]+$")


# ─── Conversion ─────────────────────────────────────────────────────


def convert_node(node: WsTreeNode) -> Any:
    """Convert a :class:`WsTreeNode` subtree to its pycrate-equivalent value.

    See module docstring for the full mapping table. The function is recursive
    and pure (no I/O, no global state).
    """
    # 1. BIT STRING with annotation — explicit (value, length) tuple.
    if node.bit_info is not None:
        return node.bit_info

    has_children = bool(node.children)
    value = node.value

    # 2. Leaf with no children: dispatch by value shape.
    if value is not None and not has_children:
        return _convert_leaf_value(value)

    # 3. Summary node (no value): could be SEQUENCE OF (children all "Item N"),
    #    or a plain SEQUENCE / record. Or a BIT STRING decomposed as named
    #    booleans (children all carry True/False values).
    if value is None and has_children:
        if _children_all_item_entries(node.children):
            return [_convert_item_entry(item) for item in node.children]
        return _convert_sequence(node.children)

    # 4. Field with value AND children:
    #    a) "N item(s)" — SEQUENCE OF parent. The list is the children.
    #    b) "name (N)" with one child named "name" — CHOICE; emit a tuple.
    #    c) Hex value with a single decoded child — Wireshark's inner-
    #       dissection of an OCTET STRING; prefer the decoded dict over the
    #       raw bytes (this is exactly the ue-CapabilityRAT-Container case).
    #    d) Otherwise — treat as SEQUENCE built from children (the inline
    #       value is supplementary and dropped).
    if value is not None and has_children:
        if _SEQOF_COUNT.match(value):
            if _children_all_item_entries(node.children):
                return [_convert_item_entry(item) for item in node.children]
            # Some Wireshark exports use other wrappers; fall through.
        em = _ENUM_VALUE.match(value)
        if em and len(node.children) == 1 and node.children[0].name == em.group(1):
            return (em.group(1), convert_node(node.children[0]))
        if _HEX_VALUE.match(value) and len(node.children) == 1:
            # OCTET STRING that Wireshark dissected; return the inner dict.
            return convert_node(node.children[0])
        # Fall-through: ignore inline value, build a SEQUENCE from children.
        return _convert_sequence(node.children)

    # 5. Empty node (no value, no children) — empty SEQUENCE.
    return {}


def _convert_leaf_value(value: str) -> Any:
    """Convert a leaf node's raw value string to a typed Python value."""
    if value == "True":
        return True
    if value == "False":
        return False
    if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
        return int(value)
    em = _ENUM_VALUE.match(value)
    if em:
        return em.group(1)
    if _HEX_VALUE.match(value) and len(value) % 2 == 0:
        try:
            return bytes.fromhex(value)
        except ValueError:
            return value
    return value


def _convert_sequence(children: tuple[WsTreeNode, ...]) -> dict[str, Any]:
    """Convert children of a SEQUENCE / record node into a dict.

    Duplicate field names (which shouldn't happen in valid Wireshark output)
    are resolved last-wins.
    """
    result: dict[str, Any] = {}
    for c in children:
        result[c.name] = convert_node(c)
    return result


def _children_all_item_entries(children: tuple[WsTreeNode, ...]) -> bool:
    """True iff every child's name looks like ``Item <N>`` — SEQUENCE OF marker."""
    if not children:
        return False
    return all(re.match(r"^Item \d+$", c.name) for c in children)


def _convert_item_entry(item: WsTreeNode) -> Any:
    """Convert one ``Item N`` wrapper to its content.

    Wireshark wraps each SEQUENCE OF element in a synthetic ``Item N`` node
    whose single child is the actual element. We unwrap that here so the list
    contains the elements directly.

    A defensive note: if an ``Item N`` has multiple children (shouldn't happen
    in valid Wireshark output for SEQUENCE OF), we treat the whole thing as a
    record dict.
    """
    if len(item.children) == 1:
        return convert_node(item.children[0])
    return _convert_sequence(item.children)


# ─── Envelope walker ────────────────────────────────────────────────


def extract_rat_containers(tree: WsTreeNode) -> list[tuple[str, dict]]:
    """Walk a Wireshark RRC tree to its ``ue-CapabilityRAT-ContainerList``
    and emit ``(rat_type, inner_decoded_dict)`` pairs.

    The expected envelope is::

        Radio Resource Control (RRC) protocol
          UL-DCCH-Message
            message: c1 (0)
              c1: ueCapabilityInformation (9)
                ueCapabilityInformation
                  rrc-TransactionIdentifier: <N>
                  criticalExtensions: ueCapabilityInformation (0)
                    ueCapabilityInformation
                      ue-CapabilityRAT-ContainerList: <N> item(s)
                        Item 0
                          UE-CapabilityRAT-Container
                            rat-Type: <rat> (N)
                            ue-CapabilityRAT-Container [FC*]: <hex>
                              UE-{NR|EUTRA|MRDC}-Capability
                                ...

    The walker is tolerant of intermediate summary nodes and the inner
    ``ue-CapabilityRAT-Container`` may have its dissected child under any
    name starting with ``UE-`` (since EUTRA / NR / MRDC all use different
    inner types).
    """
    container_list = _find_first(tree, "ue-CapabilityRAT-ContainerList")
    if container_list is None:
        raise WiresharkEnvelopeError(
            "no ue-CapabilityRAT-ContainerList in Wireshark tree", line=tree.line,
        )

    pairs: list[tuple[str, dict]] = []
    for item in container_list.children:
        if not re.match(r"^Item \d+$", item.name):
            continue
        if not item.children:
            continue

        # Wireshark's tree shape inside an Item varies between versions and
        # between LTE-RRC / NR-RRC dissectors. The two we've observed are:
        #
        #   (a) Item N
        #         UE-CapabilityRAT-Container       ← SEQUENCE-type wrapper
        #           rat-Type: <rat> (N)
        #           ue-CapabilityRAT-Container [FC*]: <hex>
        #             UE-{NR|EUTRA|MRDC}-Capability
        #
        #   (b) Item N
        #         rat-Type: <rat> (N)              ← no wrapper
        #         ue-CapabilityRAT-Container [FC*]: <hex>
        #           UE-{NR|EUTRA|MRDC}-Capability
        #
        # Both are handled by searching the Item subtree for the two fields
        # but stopping the descent when we hit a node whose name starts with
        # ``UE-`` — that's the decoded inner content, which we want to find
        # and convert separately, not search through.
        rat_type_node = _find_descendant_outside_inner(item, "rat-Type")
        if rat_type_node is None or rat_type_node.value is None:
            raise WiresharkEnvelopeError(
                f"{item.name} at source line {item.line}: missing rat-Type "
                f"field. Direct children seen: {_child_names_summary(item)}",
                line=item.line,
            )
        rat_type = _strip_enum_index(rat_type_node.value)

        inner = _find_descendant_outside_inner(item, "ue-CapabilityRAT-Container")
        if inner is None:
            raise WiresharkEnvelopeError(
                f"{item.name} at source line {item.line}: missing inner "
                f"ue-CapabilityRAT-Container OCTET STRING field. Subtree "
                f"shape:\n{_dump_subtree(item, max_depth=3)}\n"
                f"(Expected Wireshark to emit `ue-CapabilityRAT-Container "
                f"[FC*]: <hex>` with a dissected `UE-*-Capability` child "
                f"beneath it. A bracketed Wireshark annotation in the field "
                f"name is now stripped regardless of content.)",
                line=item.line,
            )
        if not inner.children:
            raise WiresharkEnvelopeError(
                f"{item.name} at source line {item.line}: "
                f"ue-CapabilityRAT-Container at source line {inner.line} has "
                f"no dissected inner content. Wireshark probably didn't have "
                f"the schema for rat-Type={rat_type!r}, or the message was "
                f"truncated before the inner dissection started.",
                line=inner.line,
            )
        decoded = convert_node(inner.children[0])
        if not isinstance(decoded, dict):
            raise WiresharkEnvelopeError(
                f"{item.name} at source line {item.line}: inner decoded "
                f"content (line {inner.children[0].line}) is not a SEQUENCE "
                f"(got {type(decoded).__name__}).",
                line=inner.line,
            )
        pairs.append((rat_type, decoded))

    return pairs


# ─── Errors ────────────────────────────────────────────────────────


class WiresharkEnvelopeError(Exception):
    """Raised when the Wireshark tree doesn't carry the expected RRC envelope."""

    def __init__(self, msg: str, *, line: int) -> None:
        super().__init__(f"line {line}: {msg}")
        self.line = line


# ─── Walk helpers ───────────────────────────────────────────────────


def _find_first(node: WsTreeNode, name: str) -> WsTreeNode | None:
    """DFS search for the first node whose ``name`` matches exactly."""
    if node.name == name:
        return node
    for c in node.children:
        r = _find_first(c, name)
        if r is not None:
            return r
    return None


def _find_child(node: WsTreeNode, name: str) -> WsTreeNode | None:
    """Find a direct child of ``node`` matching ``name`` (no recursion)."""
    for c in node.children:
        if c.name == name:
            return c
    return None


_INNER_BLOB_NAME = re.compile(r"^UE-[A-Za-z0-9]+-Capability$")


def _find_descendant_outside_inner(
    node: WsTreeNode, name: str
) -> WsTreeNode | None:
    """DFS within ``node``'s subtree for a node matching ``name``, but stop
    descending into the decoded inner ``UE-*-Capability`` blobs — we must not
    find the same field name *inside* the decoded content.

    Used by :func:`extract_rat_containers` to tolerate Wireshark trees that
    do or do not include a ``UE-CapabilityRAT-Container`` SEQUENCE wrapper
    between the ``Item N`` node and the ``rat-Type`` / inner field lines.

    The stop boundary is the regex ``^UE-[A-Za-z0-9]+-Capability$`` —
    matching ``UE-NR-Capability``, ``UE-EUTRA-Capability``,
    ``UE-MRDC-Capability``, and any future RAT inner type. The legitimate
    SEQUENCE-type wrapper ``UE-CapabilityRAT-Container`` does NOT match
    (it doesn't end in ``-Capability``), so the walker descends through it.
    """
    for c in node.children:
        if c.name == name:
            return c
        if _INNER_BLOB_NAME.match(c.name):
            # Decoded inner content — don't descend.
            continue
        r = _find_descendant_outside_inner(c, name)
        if r is not None:
            return r
    return None


def _child_names_summary(node: WsTreeNode) -> str:
    """Return a compact representation of a node's direct children for use in
    diagnostic error messages. Truncates long lists to first 6 names + count.
    """
    names = [c.name for c in node.children]
    if len(names) > 6:
        names = names[:6] + [f"... ({len(node.children) - 6} more)"]
    return "[" + ", ".join(names) + "]" if names else "[<no children>]"


def _dump_subtree(node: WsTreeNode, *, max_depth: int, _depth: int = 0) -> str:
    """Render a subtree as indented text for diagnostic error messages.

    Truncates each level's children to a small cap and stops at ``max_depth``
    so even pathological subtrees produce a bounded, readable message.
    """
    indent = "  " * _depth
    label = f"{node.name}"
    if node.value is not None:
        v = node.value
        if len(v) > 40:
            v = v[:40] + "..."
        label += f": {v}"
    lines = [f"{indent}{label}"]
    if _depth >= max_depth or not node.children:
        return "\n".join(lines)
    shown = node.children[:6]
    for c in shown:
        lines.append(_dump_subtree(c, max_depth=max_depth, _depth=_depth + 1))
    if len(node.children) > len(shown):
        lines.append(
            f"{indent}  ... ({len(node.children) - len(shown)} more children)"
        )
    return "\n".join(lines)


def _strip_enum_index(value: str) -> str:
    """Convert ``"nr (0)"`` to ``"nr"``. Returns the input unchanged if it
    doesn't match the ENUMERATED display shape."""
    m = _ENUM_VALUE.match(value)
    return m.group(1) if m else value
