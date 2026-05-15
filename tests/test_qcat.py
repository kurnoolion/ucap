"""Tests for the QCAT adapter against vendored sample fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from ucap.adapters.qcat import map_message_to_canonical, parse_qcat_file
from ucap.schema import CanonicalUeCapability

FIXTURES = Path(__file__).parent / "fixtures" / "qcat"


def _canonical(name: str) -> CanonicalUeCapability:
    msgs = parse_qcat_file(FIXTURES / name)
    assert len(msgs) == 1, f"{name}: expected exactly one UE Cap message, got {len(msgs)}"
    return map_message_to_canonical(msgs[0], vendor="qcat", release="rel17", source_file=name)


# ─── Parser-level smoke tests ─────────────────────────────────────────


@pytest.mark.parametrize(
    "fixture",
    ["G960W_LTE.txt", "OnePlus9_LTE.txt", "OnePlus9_NR.txt", "S22_LTE.txt", "S22_NR.txt"],
)
def test_fixtures_parse(fixture: str):
    msgs = parse_qcat_file(FIXTURES / fixture)
    assert len(msgs) == 1
    m = msgs[0]
    assert "UE Capability Information" in m.title
    assert m.direction == "UL-DCCH"
    assert m.root.children, "tree should have at least one top-level child"


# ─── LTE side ────────────────────────────────────────────────────────


def test_oneplus9_lte_band_combinations():
    doc = _canonical("OnePlus9_LTE.txt")
    assert "eutra" in doc.ratsPresent
    eu = doc.eutra
    assert eu is not None

    assert eu.accessStratumRelease == "rel15"
    assert len(eu.supportedBands) == 26
    assert eu.supportedBands[0].band == 7  # first reported band
    assert all(combo.source == "main" for combo in eu.caCombinations)
    assert len(eu.caCombinations) == 29

    first = eu.caCombinations[0]
    assert first.label == "7A"
    assert first.bands[0].band == 7
    assert first.bands[0].caBandwidthClassDL == "A"
    assert first.bands[0].caBandwidthClassUL == "A"
    assert first.bands[0].maxLayersDL == 4

    # The intra-band 2x CA combo "7A-7A" should be present with BCS [0,1,2,3]
    intra = [c for c in eu.caCombinations if c.label == "7A-7A"]
    assert intra, "expected at least one 7A-7A combo"
    assert any(c.bcs == [0, 1, 2, 3] for c in intra)


def test_s22_lte_merges_main_and_add_r11():
    doc = _canonical("S22_LTE.txt")
    eu = doc.eutra
    assert eu is not None
    sources = {c.source for c in eu.caCombinations}
    assert sources == {"main", "addR11"}, sources
    main = [c for c in eu.caCombinations if c.source == "main"]
    add = [c for c in eu.caCombinations if c.source == "addR11"]
    assert len(main) == 128
    assert len(add) == 132
    # combinationId is contiguous across sources
    ids = [c.combinationId for c in eu.caCombinations]
    assert ids == list(range(len(eu.caCombinations)))


# ─── NR / MRDC side ──────────────────────────────────────────────────


def test_oneplus9_nr_endc_combinations_resolved():
    doc = _canonical("OnePlus9_NR.txt")
    assert doc.ratsPresent == ["nr", "mrdc"]
    assert doc.mrdc is not None
    assert len(doc.mrdc.bandCombinations) == 23
    assert all(c.kind == "endc" for c in doc.mrdc.bandCombinations)

    # First combo: LTE B2 + B66 + B71 + NR n71
    combo0 = doc.mrdc.bandCombinations[0]
    assert combo0.label == "2A-66C-71A-n71A"
    nr_entries = [b for b in combo0.bands if b.bandNR is not None]
    assert len(nr_entries) == 1
    nr_entry = nr_entries[0]
    # Feature-set resolution should have populated per-CC NR capabilities
    assert nr_entry.bandNR == 71
    assert nr_entry.scs == 15
    assert nr_entry.channelBWDL == "mhz20"
    assert nr_entry.maxLayersDL == 2
    assert nr_entry.modulationDL == "qam256"

    # A power-class-pc2 combo should exist somewhere in the list
    assert any(c.powerClassNR == "pc2" for c in doc.mrdc.bandCombinations)


def test_oneplus9_nr_pure_nr_section_empty():
    """OnePlus9 doesn't report pure NR CA in its UE-NR-Capability — only EN-DC."""
    doc = _canonical("OnePlus9_NR.txt")
    assert doc.nr is not None
    assert doc.nr.bandCombinations == []
    assert len(doc.nr.supportedBands) > 0


def test_s22_nr_endc():
    doc = _canonical("S22_NR.txt")
    assert doc.mrdc is not None
    assert len(doc.mrdc.bandCombinations) == 26


# ─── Schema invariants ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "fixture",
    ["G960W_LTE.txt", "OnePlus9_LTE.txt", "OnePlus9_NR.txt", "S22_LTE.txt", "S22_NR.txt"],
)
def test_canonical_roundtrips_through_json(fixture: str):
    doc = _canonical(fixture)
    payload = doc.model_dump(mode="json", by_alias=True, exclude_none=True)
    roundtripped = CanonicalUeCapability.model_validate(payload)
    assert roundtripped == doc
