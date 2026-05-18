"""Tests for the Wireshark L2 converter (tree → pycrate-equivalent dict)."""

from __future__ import annotations

import pytest

from ucap.adapters.wireshark._dict import (
    WiresharkEnvelopeError,
    convert_node,
    extract_rat_containers,
)
from ucap.adapters.wireshark._parser import parse_wireshark_text


def _parse_root(text: str):
    """Helper: parse text, return the first real (non-``<root>``) child."""
    return parse_wireshark_text(text).children[0]


# ─── Leaf conversions ───────────────────────────────────────────────


def test_leaf_integer():
    n = _parse_root("rrc-TransactionIdentifier: 0\n")
    assert convert_node(n) == 0


def test_leaf_negative_integer():
    n = _parse_root("offset: -5\n")
    assert convert_node(n) == -5


def test_leaf_boolean_true():
    n = _parse_root("halfDuplex: True\n")
    assert convert_node(n) is True


def test_leaf_boolean_false():
    n = _parse_root("halfDuplex: False\n")
    assert convert_node(n) is False


def test_leaf_enumerated_to_string():
    """ENUMERATED ``name (N)`` → string ``"name"`` (the index drops)."""
    n = _parse_root("accessStratumRelease: rel15 (0)\n")
    assert convert_node(n) == "rel15"


def test_leaf_hex_to_bytes():
    n = _parse_root("ue-CapabilityRAT-Container [FC*]: deadbeef\n")
    assert convert_node(n) == bytes.fromhex("deadbeef")


def test_leaf_bit_string_annotation_to_tuple():
    """``[bit length N, decimal value V]`` → ``(V, N)`` tuple."""
    text = "twoFL-DMRS: c0 [bit length 2, 6 LSB pad bits, 11.. .... decimal value 3]\n"
    n = _parse_root(text)
    assert convert_node(n) == (3, 2)


# ─── SEQUENCE conversions ───────────────────────────────────────────


def test_summary_node_becomes_dict():
    text = (
        "rf-Parameters\n"
        "  supportedBandListNR\n"
        "    Item 0\n"
        "      SupportedBandNR\n"
        "        bandNR: 78\n"
    )
    n = _parse_root(text)
    d = convert_node(n)
    assert d == {
        "supportedBandListNR": [{"bandNR": 78}],
    }


def test_nested_sequence_dict():
    text = (
        "pdcp-Parameters\n"
        "  supportedROHC-Profiles\n"
        "    .... ...1 profile0x0001: True\n"
        "    .... ..1. profile0x0002: True\n"
        "    .... .0.. profile0x0003: False\n"
        "  maxNumberROHC-ContextSessions: cs16 (4)\n"
    )
    n = _parse_root(text)
    d = convert_node(n)
    assert d == {
        "supportedROHC-Profiles": {
            "profile0x0001": True,
            "profile0x0002": True,
            "profile0x0003": False,
        },
        "maxNumberROHC-ContextSessions": "cs16",
    }


# ─── SEQUENCE OF conversions ────────────────────────────────────────


def test_sequence_of_items_become_list():
    """``ue-CapabilityRAT-ContainerList: 2 items`` → a list of dicts."""
    text = (
        "ue-CapabilityRAT-ContainerList: 2 items\n"
        "  Item 0\n"
        "    UE-CapabilityRAT-Container\n"
        "      rat-Type: eutra (1)\n"
        "  Item 1\n"
        "    UE-CapabilityRAT-Container\n"
        "      rat-Type: nr (0)\n"
    )
    n = _parse_root(text)
    result = convert_node(n)
    assert result == [
        {"rat-Type": "eutra"},
        {"rat-Type": "nr"},
    ]


def test_sequence_of_single_item():
    text = (
        "supportedBandListNR\n"
        "  Item 0\n"
        "    SupportedBandNR\n"
        "      bandNR: 78\n"
    )
    n = _parse_root(text)
    assert convert_node(n) == [{"bandNR": 78}]


# ─── CHOICE conversions ─────────────────────────────────────────────


def test_choice_with_named_child_becomes_tuple():
    """A field whose value names a child becomes a pycrate ``(tag, sub)`` tuple."""
    text = (
        "bandParameters: nr (0)\n"
        "  nr\n"
        "    bandNR: 78\n"
        "    ca-BandwidthClassDL: a (0)\n"
    )
    n = _parse_root(text)
    result = convert_node(n)
    assert result == ("nr", {"bandNR": 78, "ca-BandwidthClassDL": "a"})


def test_choice_with_eutra_band():
    text = (
        "bandParameters: eutra (1)\n"
        "  eutra\n"
        "    bandEUTRA: 7\n"
    )
    n = _parse_root(text)
    assert convert_node(n) == ("eutra", {"bandEUTRA": 7})


# ─── OCTET STRING with dissected child ──────────────────────────────


def test_octet_string_with_dissected_child_returns_inner():
    """Wireshark dissects inner ``ue-CapabilityRAT-Container``; prefer the
    decoded dict over the raw bytes."""
    text = (
        "ue-CapabilityRAT-Container [FC*]: deadbeef\n"
        "  UE-NR-Capability\n"
        "    accessStratumRelease: rel15 (0)\n"
    )
    n = _parse_root(text)
    assert convert_node(n) == {"accessStratumRelease": "rel15"}


# ─── extract_rat_containers ─────────────────────────────────────────


def _build_minimal_envelope(rat: str, inner_lines: str) -> str:
    """Build a minimal valid Wireshark envelope around an inner UE-*-Capability
    SEQUENCE body."""
    return (
        "Radio Resource Control (RRC) protocol\n"
        "  UL-DCCH-Message\n"
        "    message: c1 (0)\n"
        "      c1: ueCapabilityInformation (9)\n"
        "        ueCapabilityInformation\n"
        "          rrc-TransactionIdentifier: 0\n"
        "          criticalExtensions: ueCapabilityInformation (0)\n"
        "            ueCapabilityInformation\n"
        "              ue-CapabilityRAT-ContainerList: 1 item\n"
        "                Item 0\n"
        "                  UE-CapabilityRAT-Container\n"
        f"                    rat-Type: {rat}\n"
        "                    ue-CapabilityRAT-Container [FC*]: deadbeef\n"
        f"{inner_lines}"
    )


def test_extract_single_nr_container():
    text = _build_minimal_envelope(
        rat="nr (0)",
        inner_lines=(
            "                      UE-NR-Capability\n"
            "                        accessStratumRelease: rel15 (0)\n"
        ),
    )
    tree = parse_wireshark_text(text)
    pairs = extract_rat_containers(tree)
    assert pairs == [("nr", {"accessStratumRelease": "rel15"})]


def test_extract_eutra_container_with_bands():
    text = _build_minimal_envelope(
        rat="eutra (1)",
        inner_lines=(
            "                      UE-EUTRA-Capability\n"
            "                        accessStratumRelease: rel15 (8)\n"
            "                        rf-Parameters\n"
            "                          supportedBandListEUTRA\n"
            "                            Item 0\n"
            "                              SupportedBandEUTRA\n"
            "                                bandEUTRA: 1\n"
            "                                halfDuplex: False\n"
            "                            Item 1\n"
            "                              SupportedBandEUTRA\n"
            "                                bandEUTRA: 3\n"
            "                                halfDuplex: True\n"
        ),
    )
    tree = parse_wireshark_text(text)
    pairs = extract_rat_containers(tree)
    assert len(pairs) == 1
    rat, decoded = pairs[0]
    assert rat == "eutra"
    assert decoded["accessStratumRelease"] == "rel15"
    assert decoded["rf-Parameters"]["supportedBandListEUTRA"] == [
        {"bandEUTRA": 1, "halfDuplex": False},
        {"bandEUTRA": 3, "halfDuplex": True},
    ]


def test_extract_two_containers_eutra_then_nr():
    text = (
        "Radio Resource Control (RRC) protocol\n"
        "  UL-DCCH-Message\n"
        "    message: c1 (0)\n"
        "      c1: ueCapabilityInformation (9)\n"
        "        ueCapabilityInformation\n"
        "          rrc-TransactionIdentifier: 0\n"
        "          criticalExtensions: ueCapabilityInformation (0)\n"
        "            ueCapabilityInformation\n"
        "              ue-CapabilityRAT-ContainerList: 2 items\n"
        "                Item 0\n"
        "                  UE-CapabilityRAT-Container\n"
        "                    rat-Type: eutra (1)\n"
        "                    ue-CapabilityRAT-Container [FC*]: aa\n"
        "                      UE-EUTRA-Capability\n"
        "                        accessStratumRelease: rel15 (8)\n"
        "                Item 1\n"
        "                  UE-CapabilityRAT-Container\n"
        "                    rat-Type: nr (0)\n"
        "                    ue-CapabilityRAT-Container [FC*]: bb\n"
        "                      UE-NR-Capability\n"
        "                        accessStratumRelease: rel15 (0)\n"
    )
    pairs = extract_rat_containers(parse_wireshark_text(text))
    assert [p[0] for p in pairs] == ["eutra", "nr"]


def test_extract_raises_when_container_list_missing():
    text = (
        "Radio Resource Control (RRC) protocol\n"
        "  UL-DCCH-Message\n"
        "    something-else: 0\n"
    )
    tree = parse_wireshark_text(text)
    with pytest.raises(WiresharkEnvelopeError):
        extract_rat_containers(tree)


def test_extract_raises_when_inner_not_dissected():
    """If Wireshark didn't have the schema for that RAT, the container line
    carries hex but has no decoded child — surface a useful error."""
    text = _build_minimal_envelope(
        rat="nr (0)",
        # Note: no UE-NR-Capability child.
        inner_lines="",
    )
    tree = parse_wireshark_text(text)
    with pytest.raises(WiresharkEnvelopeError, match="no dissected inner content"):
        extract_rat_containers(tree)


def test_extract_handles_item_without_sequence_wrapper():
    """Some Wireshark versions omit the ``UE-CapabilityRAT-Container``
    SEQUENCE-type summary wrapper between ``Item N`` and the fields. The
    walker must accept both shapes.
    """
    text = (
        "Radio Resource Control (RRC) protocol\n"
        "  UL-DCCH-Message\n"
        "    message: c1 (0)\n"
        "      c1: ueCapabilityInformation (9)\n"
        "        ueCapabilityInformation\n"
        "          rrc-TransactionIdentifier: 0\n"
        "          criticalExtensions: ueCapabilityInformation (0)\n"
        "            ueCapabilityInformation\n"
        "              ue-CapabilityRAT-ContainerList: 1 item\n"
        "                Item 0\n"
        # No "UE-CapabilityRAT-Container" wrapper — fields are direct
        # children of Item 0.
        "                  rat-Type: nr (0)\n"
        "                  ue-CapabilityRAT-Container [FC*]: deadbeef\n"
        "                    UE-NR-Capability\n"
        "                      accessStratumRelease: rel15 (0)\n"
    )
    pairs = extract_rat_containers(parse_wireshark_text(text))
    assert pairs == [("nr", {"accessStratumRelease": "rel15"})]


def test_extract_error_message_shows_actual_children():
    """A missing inner field's error message must list the children Wireshark
    *did* emit, so the user can diagnose the shape mismatch without re-reading
    the file."""
    text = (
        "Radio Resource Control (RRC) protocol\n"
        "  UL-DCCH-Message\n"
        "    message: c1 (0)\n"
        "      c1: ueCapabilityInformation (9)\n"
        "        ueCapabilityInformation\n"
        "          rrc-TransactionIdentifier: 0\n"
        "          criticalExtensions: ueCapabilityInformation (0)\n"
        "            ueCapabilityInformation\n"
        "              ue-CapabilityRAT-ContainerList: 1 item\n"
        "                Item 0\n"
        # rat-Type present but no ue-CapabilityRAT-Container at all.
        "                  rat-Type: nr (0)\n"
        "                  some-other-field: 42\n"
    )
    tree = parse_wireshark_text(text)
    with pytest.raises(WiresharkEnvelopeError) as exc_info:
        extract_rat_containers(tree)
    msg = str(exc_info.value)
    # The error mentions the item by its actual node name (not just a line
    # number that reads ambiguously) and shows what was actually present.
    assert "Item 0" in msg
    assert "source line" in msg
    assert "rat-Type" in msg or "some-other-field" in msg


def test_extract_does_not_descend_into_inner_for_field_lookup():
    """The walker must not pick up ``rat-Type`` or ``ue-CapabilityRAT-Container``
    that appears *inside* the decoded UE-*-Capability content. Stops at any
    node whose name starts with ``UE-``.
    """
    # Pathological case: a UE-NR-Capability containing a (made-up) field
    # named "rat-Type" — the walker must use the outer rat-Type, not this
    # inner accidental match.
    text = (
        "Radio Resource Control (RRC) protocol\n"
        "  UL-DCCH-Message\n"
        "    message: c1 (0)\n"
        "      c1: ueCapabilityInformation (9)\n"
        "        ueCapabilityInformation\n"
        "          rrc-TransactionIdentifier: 0\n"
        "          criticalExtensions: ueCapabilityInformation (0)\n"
        "            ueCapabilityInformation\n"
        "              ue-CapabilityRAT-ContainerList: 1 item\n"
        "                Item 0\n"
        "                  rat-Type: nr (0)\n"
        "                  ue-CapabilityRAT-Container [FC*]: aa\n"
        "                    UE-NR-Capability\n"
        "                      accessStratumRelease: rel15 (0)\n"
        # Fake nested field that would confuse a naive recursive walker:
        "                      rat-Type: eutra (1)\n"
    )
    pairs = extract_rat_containers(parse_wireshark_text(text))
    # We get the outer rat-Type (nr), not the accidental inner one (eutra).
    assert pairs[0][0] == "nr"
