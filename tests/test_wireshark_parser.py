"""Tests for the Wireshark L1 parser (text → indented tree)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ucap.adapters.wireshark._parser import (
    WsTreeNode,
    parse_wireshark_text,
    parse_wireshark_file,
)

SCAN_DIR = Path.home() / "work" / "scan"


# ─── Synthetic-input tests ──────────────────────────────────────────


def _find(node: WsTreeNode, name: str) -> WsTreeNode | None:
    """DFS search for the first child node with a matching name."""
    if node.name == name:
        return node
    for c in node.children:
        r = _find(c, name)
        if r is not None:
            return r
    return None


def test_root_has_synthetic_root_node():
    """Top-level input lines become children of a synthetic ``<root>`` node."""
    tree = parse_wireshark_text("Radio Resource Control (RRC) protocol\n")
    assert tree.name == "<root>"
    assert len(tree.children) == 1
    assert tree.children[0].name == "Radio Resource Control (RRC) protocol"
    assert tree.children[0].value is None


def test_summary_node_has_no_value():
    """Lines with no ``: `` are summary nodes (SEQUENCE / CHOICE label)."""
    tree = parse_wireshark_text("UL-DCCH-Message\n")
    assert tree.children[0].name == "UL-DCCH-Message"
    assert tree.children[0].value is None


def test_field_with_simple_value():
    tree = parse_wireshark_text("rrc-TransactionIdentifier: 0\n")
    n = tree.children[0]
    assert n.name == "rrc-TransactionIdentifier"
    assert n.value == "0"
    assert n.bit_info is None


def test_enum_value_preserved_with_index():
    """ENUMERATED values keep the ``name (N)`` shape; L2 strips the index."""
    tree = parse_wireshark_text("rat-Type: nr (0)\n")
    n = tree.children[0]
    assert n.name == "rat-Type"
    assert n.value == "nr (0)"


def test_boolean_value():
    tree = parse_wireshark_text("halfDuplex: True\n")
    assert tree.children[0].value == "True"


def test_indented_hierarchy_two_spaces_per_level():
    """Children at indent+2 nest under their parent."""
    text = (
        "parent\n"
        "  child-a: 1\n"
        "  child-b: 2\n"
        "    grandchild: 3\n"
    )
    tree = parse_wireshark_text(text)
    parent = tree.children[0]
    assert parent.name == "parent"
    assert [c.name for c in parent.children] == ["child-a", "child-b"]
    assert parent.children[1].children[0].name == "grandchild"
    assert parent.children[1].children[0].value == "3"


def test_dedent_pops_back_to_correct_level():
    """A line dedented to an outer level becomes a sibling of an ancestor."""
    text = (
        "alpha\n"
        "  beta: 1\n"
        "    gamma: 2\n"
        "  delta: 3\n"  # back to siblings of beta
    )
    tree = parse_wireshark_text(text)
    alpha = tree.children[0]
    assert [c.name for c in alpha.children] == ["beta", "delta"]


def test_fc_marker_is_stripped_from_name():
    """``ue-CapabilityRAT-Container [FC*]: <hex>`` keeps just the field name."""
    tree = parse_wireshark_text("ue-CapabilityRAT-Container [FC*]: deadbeef\n")
    n = tree.children[0]
    assert n.name == "ue-CapabilityRAT-Container"
    assert n.value == "deadbeef"


def test_any_bracketed_annotation_is_stripped_from_name():
    """Wireshark display annotations vary: ``[FC*]``, ``[truncated]``, or
    Unicode/non-ASCII glyphs. Any bracketed content at the end of the name
    is stripped — the field name is what precedes the bracket.
    """
    cases = [
        "ue-CapabilityRAT-Container [truncated]: deadbeef\n",
        "ue-CapabilityRAT-Container [→]: deadbeef\n",  # arrow glyph
        "ue-CapabilityRAT-Container [▶ expert]: deadbeef\n",  # play-icon
        "ue-CapabilityRAT-Container [FC *]: deadbeef\n",  # NBSP in marker
        "ue-CapabilityRAT-Container [0x1234]: deadbeef\n",
    ]
    for text in cases:
        tree = parse_wireshark_text(text)
        n = tree.children[0]
        assert n.name == "ue-CapabilityRAT-Container", (
            f"failed to strip bracket annotation from: {text!r} "
            f"(got name={n.name!r})"
        )
        assert n.value == "deadbeef"


def test_bit_length_annotation_extracted():
    """A ``[bit length N, ..., decimal value V]`` annotation populates bit_info."""
    text = (
        "twoFL-DMRS: c0 "
        "[bit length 2, 6 LSB pad bits, 11.. .... decimal value 3]\n"
    )
    tree = parse_wireshark_text(text)
    n = tree.children[0]
    assert n.name == "twoFL-DMRS"
    assert n.value == "c0"
    assert n.bit_info == (3, 2)


def test_bit_length_annotation_without_decimal_value():
    """Tolerate annotations that omit ``decimal value`` — store length, value=0."""
    text = "field: 00 [bit length 1, 7 LSB pad bits]\n"
    tree = parse_wireshark_text(text)
    n = tree.children[0]
    assert n.bit_info == (0, 1)


def test_per_bit_child_line_strips_bit_pattern_prefix():
    """``.... ...1 profile0x0001: True`` — the bit-pattern prefix is dropped."""
    text = (
        "supportedROHC-Profiles\n"
        "  .... ...1 profile0x0001: True\n"
        "  .... ..1. profile0x0002: True\n"
        "  .... .0.. profile0x0003: False\n"
    )
    tree = parse_wireshark_text(text)
    parent = tree.children[0]
    assert parent.name == "supportedROHC-Profiles"
    assert [c.name for c in parent.children] == [
        "profile0x0001", "profile0x0002", "profile0x0003",
    ]
    assert [c.value for c in parent.children] == ["True", "True", "False"]


def test_sequence_of_with_item_n_children():
    """SEQUENCE OF appears as ``field: N item(s)`` with ``Item N`` children."""
    text = (
        "ue-CapabilityRAT-ContainerList: 2 items\n"
        "  Item 0\n"
        "    UE-CapabilityRAT-Container\n"
        "      rat-Type: eutra (1)\n"
        "  Item 1\n"
        "    UE-CapabilityRAT-Container\n"
        "      rat-Type: nr (0)\n"
    )
    tree = parse_wireshark_text(text)
    container_list = tree.children[0]
    assert container_list.value == "2 items"
    assert [c.name for c in container_list.children] == ["Item 0", "Item 1"]
    rat_types = [
        _find(item, "rat-Type").value
        for item in container_list.children
    ]
    assert rat_types == ["eutra (1)", "nr (0)"]


def test_blank_lines_ignored():
    text = (
        "alpha\n"
        "\n"
        "  beta: 1\n"
        "\n"
        "\n"
        "  gamma: 2\n"
    )
    tree = parse_wireshark_text(text)
    assert [c.name for c in tree.children[0].children] == ["beta", "gamma"]


def test_empty_input():
    tree = parse_wireshark_text("")
    assert tree.name == "<root>"
    assert tree.children == ()


def test_line_numbers_preserved_for_diagnostics():
    text = (
        "alpha\n"
        "  beta: 1\n"
        "  gamma: 2\n"
    )
    tree = parse_wireshark_text(text)
    assert tree.children[0].line == 1
    assert tree.children[0].children[0].line == 2
    assert tree.children[0].children[1].line == 3


def test_long_hex_value_preserved():
    """OCTET STRING with a long inline hex doesn't get truncated."""
    hex_str = "f9a073a047c0" + "00" * 64 + "deadbeef"
    text = f"ue-CapabilityRAT-Container [FC*]: {hex_str}\n"
    tree = parse_wireshark_text(text)
    assert tree.children[0].value == hex_str


# ─── Real-sample smoke test ─────────────────────────────────────────


# ─── Preamble stripping (outer-protocol nesting) ────────────────────


def test_preamble_with_outer_protocol_layers_stripped():
    """Wireshark export from S1AP-carried RRC nests the PDU inside outer
    layers. Preamble lines must be skipped; the RRC tree re-baselined.
    """
    text = (
        "Frame 12: 234 bytes on wire\n"
        "    Encapsulation type: Ethernet (1)\n"
        "Ethernet II, Src: aa:bb, Dst: cc:dd\n"
        "    Destination: cc:dd\n"
        "Internet Protocol Version 4, Src: 10.0.0.1, Dst: 10.0.0.2\n"
        "    Version: 4\n"
        "Stream Control Transmission Protocol\n"
        "S1 Application Protocol\n"
        "    initiatingMessage\n"
        "        procedureCode: id-uplinkNASTransport (13)\n"
        "        Radio Resource Control (RRC) protocol\n"
        "            UL-DCCH-Message\n"
        "                message: c1 (0)\n"
        "                    c1: ueCapabilityInformation (9)\n"
    )
    tree = parse_wireshark_text(text)
    # After stripping, the RRC root is the only top-level child.
    rrc_subtrees = [
        c for c in tree.children
        if c.name == "Radio Resource Control (RRC) protocol"
    ]
    assert len(rrc_subtrees) == 1
    ul = rrc_subtrees[0].children[0]
    assert ul.name == "UL-DCCH-Message"
    message = ul.children[0]
    assert message.name == "message"
    assert message.value == "c1 (0)"


def test_preamble_falls_back_to_ul_dcch_when_rrc_root_missing():
    """Some exports drop the ``Radio Resource Control (RRC) protocol`` summary
    line. The skipper still finds ``UL-DCCH-Message`` as a fallback entry.
    """
    text = (
        "Frame 1\n"
        "    Encapsulation: x\n"
        "Outer Protocol\n"
        "    UL-DCCH-Message\n"
        "        message: c1 (0)\n"
    )
    tree = parse_wireshark_text(text)
    ul_subtrees = [c for c in tree.children if c.name == "UL-DCCH-Message"]
    assert len(ul_subtrees) == 1
    assert ul_subtrees[0].children[0].name == "message"


def test_preamble_skipper_preserves_original_line_numbers():
    """Line numbers in the resulting tree must point at the user's original
    file lines — important for diagnostic error messages.
    """
    text = (
        "Frame 12\n"            # line 1
        "    Encap: x\n"        # line 2
        "Outer\n"               # line 3
        "    Radio Resource Control (RRC) protocol\n"  # line 4
        "        UL-DCCH-Message\n"                     # line 5
        "            message: c1 (0)\n"                 # line 6
    )
    tree = parse_wireshark_text(text)
    rrc = tree.children[0]
    assert rrc.name == "Radio Resource Control (RRC) protocol"
    assert rrc.line == 4  # original line number, not 1
    ul = rrc.children[0]
    assert ul.line == 5
    msg = ul.children[0]
    assert msg.line == 6


def test_preamble_skipper_no_op_when_rrc_at_top():
    """File that already starts with the RRC root: behavior unchanged."""
    text = (
        "Radio Resource Control (RRC) protocol\n"
        "  UL-DCCH-Message\n"
        "    message: c1 (0)\n"
    )
    tree = parse_wireshark_text(text)
    assert tree.children[0].name == "Radio Resource Control (RRC) protocol"
    assert tree.children[0].line == 1


def test_preamble_skipper_stops_at_outer_protocol_return():
    """If a later line dedents below the RRC baseline, we stop processing
    the RRC body — that line is a return to the outer protocol.
    """
    text = (
        "Frame 12\n"
        "    Radio Resource Control (RRC) protocol\n"
        "        UL-DCCH-Message\n"
        "            message: c1 (0)\n"
        # Back to outer protocol — sibling of "Radio Resource Control..."
        "    [Frame is complete]\n"
        "Frame 13\n"
        "    Some other content\n"
    )
    tree = parse_wireshark_text(text)
    rrc_subtrees = [
        c for c in tree.children
        if c.name == "Radio Resource Control (RRC) protocol"
    ]
    assert len(rrc_subtrees) == 1
    # The "[Frame is complete]" line and Frame 13 should not appear as
    # children of the RRC tree.
    rrc = rrc_subtrees[0]
    names_in_tree = []
    def _collect(n):
        names_in_tree.append(n.name)
        for c in n.children:
            _collect(c)
    _collect(rrc)
    assert "[Frame is complete]" not in names_in_tree
    assert "Frame 13" not in names_in_tree


def test_preamble_skipper_with_no_rrc_returns_unchanged():
    """A file with no RRC entry-point at all is left as-is for the existing
    error path to surface.
    """
    text = (
        "Frame 12\n"
        "    Encapsulation: x\n"
        "Some Other Protocol\n"
        "    fieldA: 1\n"
    )
    tree = parse_wireshark_text(text)
    # Whatever the existing parser did before the skipper was added, it
    # still does — no Radio Resource Control or UL-DCCH-Message subtree.
    names = [c.name for c in tree.children]
    assert "Frame 12" in names
    assert "Some Other Protocol" in names


@pytest.mark.skipif(
    not (SCAN_DIR / "uecap-modem-2.txt").exists(),
    reason="real Wireshark sample (~/work/scan/uecap-modem-2.txt) not present",
)
def test_real_sample_partial_nr():
    """Parse the user's real (partial) NR sample and assert key tree shape.

    The file is truncated mid-``phy-ParametersXDD-Diff`` — we can still verify
    the outer envelope, the RAT container, and that pycrate-equivalent
    descent reaches into ``UE-NR-Capability``.
    """
    tree = parse_wireshark_file(SCAN_DIR / "uecap-modem-2.txt")

    rrc = tree.children[0]
    assert rrc.name == "Radio Resource Control (RRC) protocol"

    # Walk the envelope.
    ul_dcch = rrc.children[0]
    assert ul_dcch.name == "UL-DCCH-Message"

    # Find the rat-Type and confirm it's NR.
    rat_type = _find(tree, "rat-Type")
    assert rat_type is not None
    assert rat_type.value == "nr (0)"

    # The OCTET STRING line should carry the hex; its child is the
    # decoded UE-NR-Capability.
    container = _find(tree, "ue-CapabilityRAT-Container")
    assert container is not None
    assert container.value is not None
    assert container.value.startswith("f9a073a0")
    nr_cap = _find(container, "UE-NR-Capability")
    assert nr_cap is not None

    # accessStratumRelease is the first NR field.
    asr = _find(nr_cap, "accessStratumRelease")
    assert asr is not None
    assert asr.value == "rel15 (0)"

    # supportedROHC-Profiles has named-bit children.
    rohc = _find(nr_cap, "supportedROHC-Profiles")
    assert rohc is not None
    names = [c.name for c in rohc.children]
    assert "profile0x0001" in names
    assert "profile0x0102" in names

    # twoFL-DMRS has a bit-length annotation.
    two_fl = _find(nr_cap, "twoFL-DMRS")
    assert two_fl is not None
    assert two_fl.bit_info == (3, 2)
