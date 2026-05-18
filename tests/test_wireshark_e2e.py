"""End-to-end tests for the Wireshark adapter pipeline.

Covers the full Wireshark text → CanonicalUeCapability path including:
- Format detection-less explicit dispatch (``--vendor wireshark``).
- L3 mapper reuse from qcat._asn1 (the same EUTRA / NR / MRDC mappers handle
  the Wireshark-sourced dicts).
- CLI integration through ``_parse_log``.

Real-sample tests against ``~/work/scan/uecap-modem-2.txt`` are limited
because that file is truncated mid-message; we exercise the parser shape
and the dict-bridge envelope walk against synthetic full envelopes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ucap.adapters.wireshark import parse_wireshark_to_canonical
from ucap.cli import _parse_log
from ucap.schema import CanonicalUeCapability


# ─── Synthetic full envelopes ───────────────────────────────────────


_NR_ONLY_ENVELOPE = """\
Radio Resource Control (RRC) protocol
  UL-DCCH-Message
    message: c1 (0)
      c1: ueCapabilityInformation (9)
        ueCapabilityInformation
          rrc-TransactionIdentifier: 0
          criticalExtensions: ueCapabilityInformation (0)
            ueCapabilityInformation
              ue-CapabilityRAT-ContainerList: 1 item
                Item 0
                  UE-CapabilityRAT-Container
                    rat-Type: nr (0)
                    ue-CapabilityRAT-Container [FC*]: deadbeef
                      UE-NR-Capability
                        accessStratumRelease: rel15 (0)
                        rf-Parameters
                          supportedBandListNR
                            Item 0
                              SupportedBandNR
                                bandNR: 78
                            Item 1
                              SupportedBandNR
                                bandNR: 41
"""


_EUTRA_ONLY_ENVELOPE = """\
Radio Resource Control (RRC) protocol
  UL-DCCH-Message
    message: c1 (0)
      c1: ueCapabilityInformation (9)
        ueCapabilityInformation
          rrc-TransactionIdentifier: 0
          criticalExtensions: ueCapabilityInformation (0)
            ueCapabilityInformation
              ue-CapabilityRAT-ContainerList: 1 item
                Item 0
                  UE-CapabilityRAT-Container
                    rat-Type: eutra (1)
                    ue-CapabilityRAT-Container [FC*]: aa
                      UE-EUTRA-Capability
                        accessStratumRelease: rel8 (0)
                        ue-Category: 4
                        rf-Parameters
                          supportedBandListEUTRA
                            Item 0
                              SupportedBandEUTRA
                                bandEUTRA: 1
                                halfDuplex: False
                            Item 1
                              SupportedBandEUTRA
                                bandEUTRA: 7
                                halfDuplex: False
                            Item 2
                              SupportedBandEUTRA
                                bandEUTRA: 38
                                halfDuplex: True
"""


def test_nr_only_envelope_end_to_end(tmp_path):
    """NR-only Wireshark envelope produces an NrSection with bands."""
    log = tmp_path / "nr.txt"
    log.write_text(_NR_ONLY_ENVELOPE)

    docs = parse_wireshark_to_canonical(log, vendor="wireshark", release="rel17")
    assert len(docs) == 1
    doc = docs[0]
    assert isinstance(doc, CanonicalUeCapability)
    assert doc.meta.vendor == "wireshark"
    assert doc.meta.release == "rel17"
    assert doc.meta.sourceFile == "nr.txt"
    assert doc.ratsPresent == ["nr"]
    assert doc.nr is not None
    assert doc.eutra is None
    assert doc.mrdc is None
    assert doc.nr.accessStratumRelease == "rel15"
    bands = sorted(b.band for b in doc.nr.supportedBands)
    assert bands == [41, 78]


def test_eutra_only_envelope_end_to_end(tmp_path):
    """EUTRA-only Wireshark envelope produces an EutraSection with bands."""
    log = tmp_path / "eutra.txt"
    log.write_text(_EUTRA_ONLY_ENVELOPE)

    docs = parse_wireshark_to_canonical(log, vendor="wireshark", release="rel17")
    assert len(docs) == 1
    doc = docs[0]
    assert doc.ratsPresent == ["eutra"]
    assert doc.eutra is not None
    assert doc.eutra.accessStratumRelease == "rel8"
    bands = sorted(b.band for b in doc.eutra.supportedBands)
    assert bands == [1, 7, 38]
    # halfDuplex was True only for band 38.
    by_band = {b.band: b.halfDuplex for b in doc.eutra.supportedBands}
    assert by_band[1] is False
    assert by_band[38] is True


def test_two_containers_eutra_and_nr(tmp_path):
    """A message with both EUTRA and NR containers produces both sections."""
    text = (
        "Radio Resource Control (RRC) protocol\n"
        "  UL-DCCH-Message\n"
        "    message: c1 (0)\n"
        "      c1: ueCapabilityInformation (9)\n"
        "        ueCapabilityInformation\n"
        "          rrc-TransactionIdentifier: 1\n"
        "          criticalExtensions: ueCapabilityInformation (0)\n"
        "            ueCapabilityInformation\n"
        "              ue-CapabilityRAT-ContainerList: 2 items\n"
        "                Item 0\n"
        "                  UE-CapabilityRAT-Container\n"
        "                    rat-Type: eutra (1)\n"
        "                    ue-CapabilityRAT-Container [FC*]: aa\n"
        "                      UE-EUTRA-Capability\n"
        "                        accessStratumRelease: rel15 (8)\n"
        "                        rf-Parameters\n"
        "                          supportedBandListEUTRA\n"
        "                            Item 0\n"
        "                              SupportedBandEUTRA\n"
        "                                bandEUTRA: 7\n"
        "                                halfDuplex: False\n"
        "                Item 1\n"
        "                  UE-CapabilityRAT-Container\n"
        "                    rat-Type: nr (0)\n"
        "                    ue-CapabilityRAT-Container [FC*]: bb\n"
        "                      UE-NR-Capability\n"
        "                        accessStratumRelease: rel15 (0)\n"
        "                        rf-Parameters\n"
        "                          supportedBandListNR\n"
        "                            Item 0\n"
        "                              SupportedBandNR\n"
        "                                bandNR: 78\n"
    )
    log = tmp_path / "mixed.txt"
    log.write_text(text)
    docs = parse_wireshark_to_canonical(log, vendor="wireshark", release="rel17")
    assert len(docs) == 1
    doc = docs[0]
    assert sorted(doc.ratsPresent) == ["eutra", "nr"]
    assert doc.eutra is not None
    assert doc.eutra.supportedBands[0].band == 7
    assert doc.nr is not None
    assert doc.nr.supportedBands[0].band == 78


def test_explicit_source_file_overrides_basename(tmp_path):
    log = tmp_path / "weird-name.txt"
    log.write_text(_NR_ONLY_ENVELOPE)
    docs = parse_wireshark_to_canonical(
        log, vendor="wireshark", release="rel17", source_file="frame-42.pcap"
    )
    assert docs[0].meta.sourceFile == "frame-42.pcap"


def test_canonical_json_serialises(tmp_path):
    """The canonical record produced from a Wireshark log dumps to JSON cleanly
    via the same Pydantic alias paths the CLI uses (``_meta`` alias, etc.)."""
    log = tmp_path / "nr.txt"
    log.write_text(_NR_ONLY_ENVELOPE)
    docs = parse_wireshark_to_canonical(log, vendor="wireshark", release="rel17")

    payload = [d.model_dump(mode="json", by_alias=True, exclude_none=True) for d in docs]
    text = json.dumps(payload, indent=2)
    parsed = json.loads(text)
    assert parsed[0]["_meta"]["vendor"] == "wireshark"
    assert parsed[0]["ratsPresent"] == ["nr"]
    assert parsed[0]["nr"]["accessStratumRelease"] == "rel15"


def test_cli_parse_log_dispatches_to_wireshark(tmp_path):
    """The CLI ``_parse_log(vendor="wireshark")`` branch wires to the adapter."""
    log = tmp_path / "nr.txt"
    log.write_text(_NR_ONLY_ENVELOPE)
    docs = _parse_log(log, vendor="wireshark", release="rel17")
    assert len(docs) == 1
    assert docs[0].meta.vendor == "wireshark"
    assert docs[0].ratsPresent == ["nr"]


# ─── Partial real sample ───────────────────────────────────────────


@pytest.mark.skipif(
    not (Path.home() / "work" / "scan" / "uecap-modem-2.txt").exists(),
    reason="real Wireshark sample (~/work/scan/uecap-modem-2.txt) not present",
)
def test_real_sample_partial_nr_extracts_pair():
    """The real (partial) NR sample yields one ``(nr, decoded_dict)`` pair.

    The sample is truncated mid-message — there's no closing structure — but
    the envelope and the first few NR fields parse cleanly. We assert just
    the envelope-walker output here; the end-to-end mapping is exercised by
    the synthetic envelopes above (where we know the full shape).
    """
    from ucap.adapters.wireshark._dict import extract_rat_containers
    from ucap.adapters.wireshark._parser import parse_wireshark_file

    tree = parse_wireshark_file(Path.home() / "work" / "scan" / "uecap-modem-2.txt")
    pairs = extract_rat_containers(tree)
    assert len(pairs) == 1
    rat, decoded = pairs[0]
    assert rat == "nr"
    assert decoded["accessStratumRelease"] == "rel15"
