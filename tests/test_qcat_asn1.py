"""Tests for the QCAT ASN.1 value-notation parser (L1) in qcat/_asn1.py."""

from __future__ import annotations

import pytest


# ─── Synthetic ASN.1 fixtures ───────────────────────────────────────


_MINIMAL_NR_MSG = """\
value UL-DCCH-Message ::=
{
  message c1 : ueCapabilityInformation :
    {
      rrc-TransactionIdentifier 2,
      criticalExtensions ueCapabilityInformation :
        {
          ue-CapabilityRAT-ContainerList
          {
            {
              rat-Type nr,
              ue-CapabilityRAT-Container 'E7E45380'H
            }
          }
        }
    }
}
"""


_MULTI_RAT_MSG = """\
message c1: ueCapabilityInformation :
  {
    rrc-TransactionIdentifier 0,
    criticalExtensions ueCapabilityInformation :
    {
      ue-CapabilityRAT-ContainerList
      {
        {
          rat-Type eutra,
          ue-CapabilityRAT-Container '0102030405'H
        },
        {
          rat-Type nr,
          ue-CapabilityRAT-Container 'AABBCCDD'H
        },
        {
          rat-Type eutra-nr,
          ue-CapabilityRAT-Container 'CAFEBABE'H
        }
      }
    }
  }
"""


_MULTI_LINE_HEX_MSG = """\
message c1 : ueCapabilityInformation :
  {
    rrc-TransactionIdentifier 7,
    criticalExtensions ueCapabilityInformation :
    {
      ue-CapabilityRAT-ContainerList
      {
        {
          rat-Type nr,
          ue-CapabilityRAT-Container
          'AA BB CC DD
           11 22 33 44
           DE AD BE EF'H
        }
      }
    }
  }
"""


_TWO_MESSAGES = _MINIMAL_NR_MSG + "\n\nSome unrelated content here.\n\n" + _MULTI_RAT_MSG


# ─── Public API ─────────────────────────────────────────────────────


def test_parse_minimal_nr_message() -> None:
    """A single-RAT NR message parses to one Asn1Message with one container."""
    from ucap.adapters.qcat._asn1 import parse_asn1_text

    msgs = list(parse_asn1_text(_MINIMAL_NR_MSG))
    assert len(msgs) == 1
    msg = msgs[0]
    assert msg.rrc_transaction_id == 2
    assert len(msg.rat_containers) == 1
    c = msg.rat_containers[0]
    assert c.rat_type == "nr"
    assert c.encoded == bytes.fromhex("E7E45380")


def test_parse_multi_rat_message() -> None:
    """Three RATs in one message — all extracted in order, with correct hex."""
    from ucap.adapters.qcat._asn1 import parse_asn1_text

    msgs = list(parse_asn1_text(_MULTI_RAT_MSG))
    assert len(msgs) == 1
    msg = msgs[0]
    assert msg.rrc_transaction_id == 0
    assert len(msg.rat_containers) == 3
    assert [c.rat_type for c in msg.rat_containers] == ["eutra", "nr", "eutra-nr"]
    assert msg.rat_containers[0].encoded == bytes.fromhex("0102030405")
    assert msg.rat_containers[1].encoded == bytes.fromhex("AABBCCDD")
    assert msg.rat_containers[2].encoded == bytes.fromhex("CAFEBABE")


def test_multi_line_hex_strings_concatenate() -> None:
    """Hex OCTET STRING literals tolerate internal whitespace and newlines."""
    from ucap.adapters.qcat._asn1 import parse_asn1_text

    msgs = list(parse_asn1_text(_MULTI_LINE_HEX_MSG))
    assert len(msgs) == 1
    c = msgs[0].rat_containers[0]
    assert c.rat_type == "nr"
    assert c.encoded == bytes.fromhex("AABBCCDD" + "11223344" + "DEADBEEF")


def test_two_messages_in_one_file() -> None:
    """The scanner advances past one parsed message and finds the next."""
    from ucap.adapters.qcat._asn1 import parse_asn1_text

    msgs = list(parse_asn1_text(_TWO_MESSAGES))
    assert len(msgs) == 2
    # First is the minimal NR message, second is the multi-RAT message.
    assert msgs[0].rrc_transaction_id == 2
    assert msgs[0].rat_containers[0].rat_type == "nr"
    assert msgs[1].rrc_transaction_id == 0
    assert len(msgs[1].rat_containers) == 3


def test_outer_envelope_is_ignored() -> None:
    """The `value UL-DCCH-Message ::= { ... }` envelope around the entry block
    doesn't trip the parser — the scanner anchors on `message c1 : ...`."""
    from ucap.adapters.qcat._asn1 import parse_asn1_text

    wrapped = (
        "Subscription ID = 1\n"
        "Pkt Version = 28\n"
        "RRC Release Number,Major,Minor = 18.2.0\n"
        "\n"
        + _MINIMAL_NR_MSG
    )
    msgs = list(parse_asn1_text(wrapped))
    assert len(msgs) == 1
    assert msgs[0].rrc_transaction_id == 2


def test_both_whitespace_variants() -> None:
    """Both `c1 : ueCapabilityInformation` and `c1: ueCapabilityInformation` detected."""
    from ucap.adapters.qcat._asn1 import parse_asn1_text

    # `_MINIMAL_NR_MSG` uses ' : ' (space-colon-space).
    msgs_v1 = list(parse_asn1_text(_MINIMAL_NR_MSG))
    assert len(msgs_v1) == 1
    # `_MULTI_RAT_MSG` uses ': ' (no leading space).
    msgs_v2 = list(parse_asn1_text(_MULTI_RAT_MSG))
    assert len(msgs_v2) == 1


def test_empty_input_yields_zero_messages() -> None:
    """No `message c1` marker → empty iterator."""
    from ucap.adapters.qcat._asn1 import parse_asn1_text

    assert list(parse_asn1_text("")) == []
    assert list(parse_asn1_text("nothing relevant here\nat all.\n")) == []


def test_start_and_end_lines() -> None:
    """Parsed message records its source line range (1-based)."""
    from ucap.adapters.qcat._asn1 import parse_asn1_text

    # The header line "message c1 : ueCapabilityInformation :" starts on line 3
    # of _MINIMAL_NR_MSG (1: value..., 2: {, 3: message c1...).
    msgs = list(parse_asn1_text(_MINIMAL_NR_MSG))
    assert msgs[0].start_line == 3
    # end_line should be the line of the matching closing `}` of the
    # ueCapabilityInformation body. It's later than start_line.
    assert msgs[0].end_line > msgs[0].start_line


# ─── File API ───────────────────────────────────────────────────────


def test_parse_asn1_file(tmp_path) -> None:
    """parse_asn1_file reads a path and returns the same records."""
    from ucap.adapters.qcat._asn1 import parse_asn1_file, parse_asn1_text

    p = tmp_path / "sample.txt"
    p.write_text(_MINIMAL_NR_MSG)
    file_msgs = parse_asn1_file(p)
    text_msgs = list(parse_asn1_text(_MINIMAL_NR_MSG))
    assert file_msgs == text_msgs


# ─── Error paths ────────────────────────────────────────────────────


def test_missing_rrc_transaction_identifier_raises() -> None:
    """A message body without rrc-TransactionIdentifier is a parse error."""
    from ucap.adapters.qcat._asn1 import parse_asn1_text

    bad = """\
message c1 : ueCapabilityInformation :
  {
    criticalExtensions ueCapabilityInformation :
      { ue-CapabilityRAT-ContainerList { } }
  }
"""
    with pytest.raises(Exception, match="rrc-TransactionIdentifier"):
        list(parse_asn1_text(bad))


def test_unsupported_critical_extensions_choice_raises() -> None:
    """Non-ueCapabilityInformation choices are not handled by the L1 parser."""
    from ucap.adapters.qcat._asn1 import parse_asn1_text

    bad = """\
message c1 : ueCapabilityInformation :
  {
    rrc-TransactionIdentifier 0,
    criticalExtensions criticalExtensionsFuture : { }
  }
"""
    with pytest.raises(Exception, match="criticalExtensionsFuture"):
        list(parse_asn1_text(bad))


def test_unterminated_hex_string_raises() -> None:
    """A `'…` literal without the closing `'H` is a parse error."""
    from ucap.adapters.qcat._asn1 import parse_asn1_text

    bad = """\
message c1 : ueCapabilityInformation :
  {
    rrc-TransactionIdentifier 0,
    criticalExtensions ueCapabilityInformation :
      { ue-CapabilityRAT-ContainerList { { rat-Type nr, ue-CapabilityRAT-Container 'AABB } } }
  }
"""
    with pytest.raises(Exception):
        list(parse_asn1_text(bad))


def test_missing_hex_value_raises() -> None:
    """ue-CapabilityRAT-Container without a hex literal is a parse error."""
    from ucap.adapters.qcat._asn1 import parse_asn1_text

    bad = """\
message c1 : ueCapabilityInformation :
  {
    rrc-TransactionIdentifier 0,
    criticalExtensions ueCapabilityInformation :
      { ue-CapabilityRAT-ContainerList { { rat-Type nr, ue-CapabilityRAT-Container } } }
  }
"""
    with pytest.raises(Exception, match="hex OCTET STRING"):
        list(parse_asn1_text(bad))


# ─── Dataclass invariants ───────────────────────────────────────────


def test_asn1_message_is_frozen() -> None:
    """Asn1Message is immutable after construction (D-009 ReportRecord-style)."""
    from ucap.adapters.qcat._asn1 import Asn1Message, Asn1RatContainer

    msg = Asn1Message(
        rrc_transaction_id=0,
        rat_containers=(Asn1RatContainer(rat_type="nr", encoded=b"\x01\x02"),),
        start_line=1,
        end_line=10,
    )
    with pytest.raises(Exception):
        msg.rrc_transaction_id = 99  # type: ignore[misc]


def test_asn1_rat_container_is_frozen() -> None:
    """Asn1RatContainer is immutable."""
    from ucap.adapters.qcat._asn1 import Asn1RatContainer

    c = Asn1RatContainer(rat_type="nr", encoded=b"\xff")
    with pytest.raises(Exception):
        c.rat_type = "eutra"  # type: ignore[misc]


def test_empty_hex_string_decodes_to_empty_bytes() -> None:
    """`''H` (no hex digits) is valid; produces an empty bytes payload."""
    from ucap.adapters.qcat._asn1 import parse_asn1_text

    empty_hex = """\
message c1 : ueCapabilityInformation :
  {
    rrc-TransactionIdentifier 0,
    criticalExtensions ueCapabilityInformation :
      { ue-CapabilityRAT-ContainerList { { rat-Type nr, ue-CapabilityRAT-Container ''H } } }
  }
"""
    msgs = list(parse_asn1_text(empty_hex))
    assert len(msgs) == 1
    assert msgs[0].rat_containers[0].encoded == b""


# ─── L2: PER decoder via pycrate ────────────────────────────────────


def test_get_pycrate_type_dispatch_nr() -> None:
    """rat_type='nr' dispatches to RRCNR.UE_NR_Capability."""
    from pycrate_asn1dir.RRCNR import NR_RRC_Definitions

    from ucap.adapters.qcat._asn1 import _get_pycrate_type

    assert _get_pycrate_type("nr") is NR_RRC_Definitions.UE_NR_Capability


def test_get_pycrate_type_dispatch_eutra() -> None:
    """rat_type='eutra' dispatches to RRCLTE.UE_EUTRA_Capability."""
    from pycrate_asn1dir.RRCLTE import EUTRA_RRC_Definitions

    from ucap.adapters.qcat._asn1 import _get_pycrate_type

    assert _get_pycrate_type("eutra") is EUTRA_RRC_Definitions.UE_EUTRA_Capability


def test_get_pycrate_type_dispatch_eutra_nr() -> None:
    """rat_type='eutra-nr' dispatches to RRCNR.UE_MRDC_Capability."""
    from pycrate_asn1dir.RRCNR import NR_RRC_Definitions

    from ucap.adapters.qcat._asn1 import _get_pycrate_type

    assert _get_pycrate_type("eutra-nr") is NR_RRC_Definitions.UE_MRDC_Capability


def test_get_pycrate_type_dispatch_mrdc_xpdcp() -> None:
    """rat_type='mrdc-XPDCP' also dispatches to UE_MRDC_Capability (Rel-15 variant)."""
    from pycrate_asn1dir.RRCNR import NR_RRC_Definitions

    from ucap.adapters.qcat._asn1 import _get_pycrate_type

    assert _get_pycrate_type("mrdc-XPDCP") is NR_RRC_Definitions.UE_MRDC_Capability


def test_get_pycrate_type_rejects_unknown() -> None:
    """Unsupported rat-Type values raise ValueError."""
    from ucap.adapters.qcat._asn1 import _get_pycrate_type

    with pytest.raises(ValueError, match="Unsupported rat-Type"):
        _get_pycrate_type("nbiot")
    with pytest.raises(ValueError, match="Unsupported rat-Type"):
        _get_pycrate_type("utra")


def test_decode_rat_container_invalid_bytes_raises_per_decode_error() -> None:
    """Random non-PER bytes raise _PerDecodeError with bucketed failure_reason."""
    from ucap.adapters.qcat._asn1 import (
        Asn1RatContainer,
        _PerDecodeError,
        decode_rat_container,
    )

    container = Asn1RatContainer(rat_type="nr", encoded=b"\xde\xad\xbe\xef" * 8)
    with pytest.raises(_PerDecodeError) as exc_info:
        decode_rat_container(container)
    err = exc_info.value
    assert err.rat_type == "nr"
    assert err.failure_reason == "per_decode_failed"
    assert err.original is not None


def test_decode_rat_container_propagates_unsupported_rat_type() -> None:
    """An Asn1RatContainer with an unsupported rat-Type raises ValueError
    (not _PerDecodeError — dispatch failure happens before pycrate).
    """
    from ucap.adapters.qcat._asn1 import Asn1RatContainer, decode_rat_container

    container = Asn1RatContainer(rat_type="utra", encoded=b"\x00")
    with pytest.raises(ValueError, match="Unsupported rat-Type"):
        decode_rat_container(container)


def test_decode_rat_container_round_trip() -> None:
    """A pycrate-encoded UE-NR-Capability round-trips through decode_rat_container.

    Build a minimal-valid UE-NR-Capability value, encode it, wrap in
    Asn1RatContainer, decode via the L2 path, and verify the dict shape.
    """
    from pycrate_asn1dir.RRCNR import NR_RRC_Definitions

    from ucap.adapters.qcat._asn1 import Asn1RatContainer, decode_rat_container

    # Build minimal-valid UE-NR-Capability per TS 38.331 mandatory fields.
    minimal = {
        "accessStratumRelease": "rel15",
        "pdcp-Parameters": {
            "supportedROHC-Profiles": {
                "profile0x0000": False,
                "profile0x0001": False,
                "profile0x0002": False,
                "profile0x0003": False,
                "profile0x0004": False,
                "profile0x0006": False,
                "profile0x0101": False,
                "profile0x0102": False,
                "profile0x0103": False,
                "profile0x0104": False,
            },
            "maxNumberROHC-ContextSessions": "cs2",
        },
        "phy-Parameters": {},
        "rf-Parameters": {
            "supportedBandListNR": [{"bandNR": 78}],
        },
    }
    ue_nr = NR_RRC_Definitions.UE_NR_Capability
    ue_nr.set_val(minimal)
    encoded = ue_nr.to_uper()
    assert isinstance(encoded, (bytes, bytearray))

    container = Asn1RatContainer(rat_type="nr", encoded=bytes(encoded))
    decoded = decode_rat_container(container)
    assert isinstance(decoded, dict)
    assert decoded.get("accessStratumRelease") == "rel15"
    assert "rf-Parameters" in decoded
    assert decoded["rf-Parameters"]["supportedBandListNR"][0]["bandNR"] == 78


def test_decode_message_containers_decodes_all() -> None:
    """decode_message_containers returns one dict per RAT in container order."""
    from pycrate_asn1dir.RRCNR import NR_RRC_Definitions

    from ucap.adapters.qcat._asn1 import (
        Asn1Message,
        Asn1RatContainer,
        decode_message_containers,
    )

    # Encode the minimal NR cap (same construction as the round-trip test).
    minimal = {
        "accessStratumRelease": "rel15",
        "pdcp-Parameters": {
            "supportedROHC-Profiles": {
                "profile0x0000": False,
                "profile0x0001": False,
                "profile0x0002": False,
                "profile0x0003": False,
                "profile0x0004": False,
                "profile0x0006": False,
                "profile0x0101": False,
                "profile0x0102": False,
                "profile0x0103": False,
                "profile0x0104": False,
            },
            "maxNumberROHC-ContextSessions": "cs2",
        },
        "phy-Parameters": {},
        "rf-Parameters": {"supportedBandListNR": [{"bandNR": 41}]},
    }
    ue_nr = NR_RRC_Definitions.UE_NR_Capability
    ue_nr.set_val(minimal)
    encoded = bytes(ue_nr.to_uper())

    # Re-encode under a different band for the second container so the two
    # decoded values are demonstrably distinct.
    minimal["rf-Parameters"]["supportedBandListNR"] = [{"bandNR": 78}]
    ue_nr.set_val(minimal)
    encoded2 = bytes(ue_nr.to_uper())

    msg = Asn1Message(
        rrc_transaction_id=0,
        rat_containers=(
            Asn1RatContainer(rat_type="nr", encoded=encoded),
            Asn1RatContainer(rat_type="nr", encoded=encoded2),
        ),
        start_line=1,
        end_line=10,
    )
    decoded = decode_message_containers(msg)
    assert len(decoded) == 2
    assert decoded[0]["rf-Parameters"]["supportedBandListNR"][0]["bandNR"] == 41
    assert decoded[1]["rf-Parameters"]["supportedBandListNR"][0]["bandNR"] == 78


def test_decode_message_containers_propagates_failure() -> None:
    """If any container fails to decode, decode_message_containers raises
    _PerDecodeError immediately (caller decides recovery policy).
    """
    from ucap.adapters.qcat._asn1 import (
        Asn1Message,
        Asn1RatContainer,
        _PerDecodeError,
        decode_message_containers,
    )

    msg = Asn1Message(
        rrc_transaction_id=0,
        rat_containers=(
            Asn1RatContainer(rat_type="nr", encoded=b"\xff" * 16),
        ),
        start_line=1,
        end_line=5,
    )
    with pytest.raises(_PerDecodeError):
        decode_message_containers(msg)


def test_per_decode_error_attributes() -> None:
    """_PerDecodeError carries rat_type, failure_reason, and the original exception."""
    from ucap.adapters.qcat._asn1 import _PerDecodeError

    inner = ValueError("test inner")
    err = _PerDecodeError(
        rat_type="nr", failure_reason="per_decode_failed", original=inner
    )
    assert err.rat_type == "nr"
    assert err.failure_reason == "per_decode_failed"
    assert err.original is inner
    assert "rat-Type='nr'" in str(err)


# ─── L3: dict → CanonicalUeCapability — EUTRA first slice ──────────


def test_flatten_extensions_one_layer() -> None:
    """A flat dict with no nonCriticalExtension comes back unchanged (sans the key)."""
    from ucap.adapters.qcat._asn1 import _flatten_extensions

    d = {"a": 1, "b": {"c": 2}}
    assert _flatten_extensions(d) == {"a": 1, "b": {"c": 2}}


def test_flatten_extensions_chain() -> None:
    """Each nonCriticalExtension layer's fields land at the top of the flat view."""
    from ucap.adapters.qcat._asn1 import _flatten_extensions

    d = {
        "accessStratumRelease": "rel8",
        "ue-Category": 4,
        "nonCriticalExtension": {
            "rf-Parameters-v920": {"foo": 1},
            "nonCriticalExtension": {
                "rf-Parameters-v1020": {"supportedBandCombination-r10": []},
                "lateNonCriticalExtension": b"some-bytes",
                "nonCriticalExtension": {
                    "rf-Parameters-v1430": {"bar": 2},
                },
            },
        },
    }
    flat = _flatten_extensions(d)
    assert flat["accessStratumRelease"] == "rel8"
    assert flat["ue-Category"] == 4
    assert flat["rf-Parameters-v920"] == {"foo": 1}
    assert flat["rf-Parameters-v1020"] == {"supportedBandCombination-r10": []}
    assert flat["rf-Parameters-v1430"] == {"bar": 2}
    # nonCriticalExtension and lateNonCriticalExtension are consumed.
    assert "nonCriticalExtension" not in flat
    assert "lateNonCriticalExtension" not in flat


def test_map_eutra_synthetic_minimal() -> None:
    """A minimal UE-EUTRA-Capability dict produces an EutraSection with one band, no combos."""
    from ucap.adapters.qcat._asn1 import _map_eutra_from_dict

    decoded = {
        "accessStratumRelease": "rel8",
        "ue-Category": 4,
        "rf-Parameters": {
            "supportedBandListEUTRA": [
                {"bandEUTRA": 1, "halfDuplex": False},
                {"bandEUTRA": 3, "halfDuplex": True},
            ],
        },
    }
    section = _map_eutra_from_dict(decoded)
    assert section.accessStratumRelease == "rel8"
    assert len(section.supportedBands) == 2
    assert section.supportedBands[0].band == 1
    assert section.supportedBands[0].halfDuplex is False
    assert section.supportedBands[1].band == 3
    assert section.supportedBands[1].halfDuplex is True
    assert section.caCombinations == []


def test_map_eutra_with_main_combo() -> None:
    """A UE-EUTRA-Capability with one supportedBandCombination-r10 entry produces
    one EutraCaCombination with the right band entries and label.
    """
    from ucap.adapters.qcat._asn1 import _map_eutra_from_dict

    decoded = {
        "accessStratumRelease": "rel10",
        "ue-Category": 4,
        "rf-Parameters": {
            "supportedBandListEUTRA": [
                {"bandEUTRA": 1, "halfDuplex": False},
                {"bandEUTRA": 3, "halfDuplex": False},
            ],
        },
        "nonCriticalExtension": {
            "nonCriticalExtension": {
                "rf-Parameters-v1020": {
                    "supportedBandCombination-r10": [
                        # One combo: band 1 + band 3 (both class A, DL)
                        [
                            {
                                "bandEUTRA-r10": 1,
                                "bandParametersDL-r10": [
                                    {
                                        "ca-BandwidthClassDL-r10": "a",
                                        "supportedMIMO-CapabilityDL-r10": "twoLayers",
                                    }
                                ],
                                "bandParametersUL-r10": [
                                    {"ca-BandwidthClassUL-r10": "a"}
                                ],
                            },
                            {
                                "bandEUTRA-r10": 3,
                                "bandParametersDL-r10": [
                                    {
                                        "ca-BandwidthClassDL-r10": "a",
                                        "supportedMIMO-CapabilityDL-r10": "twoLayers",
                                    }
                                ],
                            },
                        ],
                    ]
                },
            },
        },
    }
    section = _map_eutra_from_dict(decoded)
    assert section.accessStratumRelease == "rel10"
    assert len(section.caCombinations) == 1
    combo = section.caCombinations[0]
    assert combo.combinationId == 0
    assert combo.label == "1A-3A"
    assert combo.source == "main"
    assert combo.bcs is None
    assert combo.supports256QAMDL is None
    assert len(combo.bands) == 2
    assert combo.bands[0].band == 1
    assert combo.bands[0].caBandwidthClassDL == "A"
    assert combo.bands[0].caBandwidthClassUL == "A"
    assert combo.bands[0].maxLayersDL == 2
    assert combo.bands[1].band == 3
    assert combo.bands[1].caBandwidthClassDL == "A"
    assert combo.bands[1].caBandwidthClassUL is None  # no UL band-parameters
    assert combo.bands[1].maxLayersDL == 2


def test_map_eutra_multiple_combos_indexed() -> None:
    """Multiple combos get sequential combinationId values starting at 0."""
    from ucap.adapters.qcat._asn1 import _map_eutra_from_dict

    decoded = {
        "accessStratumRelease": "rel10",
        "nonCriticalExtension": {
            "nonCriticalExtension": {
                "rf-Parameters-v1020": {
                    "supportedBandCombination-r10": [
                        [{"bandEUTRA-r10": 1, "bandParametersDL-r10": [{"ca-BandwidthClassDL-r10": "a"}]}],
                        [{"bandEUTRA-r10": 3, "bandParametersDL-r10": [{"ca-BandwidthClassDL-r10": "b"}]}],
                        [{"bandEUTRA-r10": 7, "bandParametersDL-r10": [{"ca-BandwidthClassDL-r10": "c"}]}],
                    ]
                },
            },
        },
    }
    section = _map_eutra_from_dict(decoded)
    assert len(section.caCombinations) == 3
    assert [c.combinationId for c in section.caCombinations] == [0, 1, 2]
    assert [c.label for c in section.caCombinations] == ["1A", "3B", "7C"]


def test_map_asn1_message_to_canonical_eutra(monkeypatch) -> None:
    """End-to-end: an Asn1Message routes through L2 (mocked) + L3 EUTRA mapper
    and produces a CanonicalUeCapability with the right shape.

    Mocks ``decode_rat_container`` to return a synthetic UE-EUTRA-Capability
    dict, bypassing pycrate's encoder-side mandatory-fields complexity. The
    L3 logic (``_map_eutra_from_dict``) is independently covered by the
    synthetic-dict unit tests above. The full pycrate round-trip will exercise
    here once a paired ASN.1 fixture lands (D-017).
    """
    from ucap.adapters.qcat import _asn1
    from ucap.adapters.qcat._asn1 import (
        Asn1Message,
        Asn1RatContainer,
        map_asn1_message_to_canonical,
    )

    synthetic_decoded = {
        "accessStratumRelease": "rel10",
        "ue-Category": 4,
        "rf-Parameters": {
            "supportedBandListEUTRA": [
                {"bandEUTRA": 1, "halfDuplex": False},
                {"bandEUTRA": 3, "halfDuplex": False},
            ],
        },
        "nonCriticalExtension": {
            "nonCriticalExtension": {
                "rf-Parameters-v1020": {
                    "supportedBandCombination-r10": [
                        [
                            {
                                "bandEUTRA-r10": 1,
                                "bandParametersDL-r10": [
                                    {"ca-BandwidthClassDL-r10": "a"}
                                ],
                            },
                            {
                                "bandEUTRA-r10": 3,
                                "bandParametersDL-r10": [
                                    {"ca-BandwidthClassDL-r10": "a"}
                                ],
                            },
                        ]
                    ]
                }
            }
        },
    }

    monkeypatch.setattr(_asn1, "decode_rat_container", lambda _c: synthetic_decoded)

    msg = Asn1Message(
        rrc_transaction_id=2,
        rat_containers=(Asn1RatContainer(rat_type="eutra", encoded=b"\x00" * 4),),
        start_line=10,
        end_line=20,
    )
    canonical = map_asn1_message_to_canonical(
        msg, vendor="qcat", release="rel17", source_file="test.txt"
    )

    assert canonical.ratsPresent == ["eutra"]
    assert canonical.nr is None
    assert canonical.mrdc is None
    assert canonical.eutra is not None
    assert canonical.eutra.accessStratumRelease == "rel10"
    assert len(canonical.eutra.supportedBands) == 2
    assert canonical.eutra.supportedBands[0].band == 1
    assert canonical.eutra.supportedBands[1].band == 3
    assert len(canonical.eutra.caCombinations) == 1
    assert canonical.eutra.caCombinations[0].label == "1A-3A"

    # Meta provenance preserved.
    assert canonical.meta.vendor == "qcat"
    assert canonical.meta.release == "rel17"
    assert canonical.meta.sourceFile == "test.txt"
    assert canonical.meta.sourceLineRange == (10, 20)


def test_map_asn1_message_nr_via_monkeypatch(monkeypatch) -> None:
    """An NR message routes through L2 (mocked) + L3 NR mapper and produces
    a CanonicalUeCapability with an NrSection.
    """
    from ucap.adapters.qcat import _asn1
    from ucap.adapters.qcat._asn1 import (
        Asn1Message,
        Asn1RatContainer,
        map_asn1_message_to_canonical,
    )

    synthetic_decoded = {
        "accessStratumRelease": "rel17",
        "rf-Parameters": {
            "supportedBandListNR": [
                {"bandNR": 41},
                {"bandNR": 78},
            ],
            "supportedBandCombinationList": [
                {
                    "bandList": [
                        ("nr", {"bandNR": 78, "ca-BandwidthClassDL-NR": "a"}),
                    ],
                    "featureSetCombination": 0,
                },
            ],
        },
        "featureSets": {
            "featureSetCombinations": [
                # FeatureSetCombination 0: one per-band entry, one alt each.
                [[("nr", {"downlinkSetNR": 0, "uplinkSetNR": 0})]],
            ],
            "featureSetsDownlink": [],
            "featureSetsUplink": [],
            "featureSetsDownlinkPerCC": [],
            "featureSetsUplinkPerCC": [],
        },
    }

    monkeypatch.setattr(_asn1, "decode_rat_container", lambda _c: synthetic_decoded)

    msg = Asn1Message(
        rrc_transaction_id=0,
        rat_containers=(Asn1RatContainer(rat_type="nr", encoded=b"\x00"),),
        start_line=1,
        end_line=5,
    )
    canonical = map_asn1_message_to_canonical(
        msg, vendor="qcat", release="rel17", source_file="test.txt"
    )
    assert canonical.ratsPresent == ["nr"]
    assert canonical.eutra is None
    assert canonical.mrdc is None
    assert canonical.nr is not None
    assert canonical.nr.accessStratumRelease == "rel17"
    assert [b.band for b in canonical.nr.supportedBands] == [41, 78]
    assert [b.fr for b in canonical.nr.supportedBands] == ["FR1", "FR1"]
    assert len(canonical.nr.bandCombinations) == 1
    combo = canonical.nr.bandCombinations[0]
    assert combo.combinationId == 0
    assert combo.label == "n78A"
    assert combo.kind == "caNR"
    assert combo.source == "main"
    assert combo.featureSetCombinationId == 0
    assert combo.bcs is None
    assert combo.bands[0].bandNR == 78
    assert combo.bands[0].caBandwidthClassDL == "A"


def test_map_nr_resolves_feature_set_indirection() -> None:
    """A full feature-set chain (combo → fsc → fs → cc → per-cc) populates
    SCS / BW / MIMO / modulation on the combo band entry.
    """
    from ucap.adapters.qcat._asn1 import _map_nr_from_dict

    decoded = {
        "accessStratumRelease": "rel17",
        "rf-Parameters": {
            "supportedBandListNR": [{"bandNR": 78}],
            "supportedBandCombinationList": [
                {
                    "bandList": [
                        ("nr", {"bandNR": 78, "ca-BandwidthClassDL-NR": "a"}),
                    ],
                    "featureSetCombination": 0,
                },
            ],
        },
        "featureSets": {
            "featureSetCombinations": [
                # fsc 0: one band, one alt — references DL set 1, UL set 1.
                [[("nr", {"downlinkSetNR": 1, "uplinkSetNR": 1})]],
            ],
            # featureSetsDownlink[0] = the FeatureSetDownlink referenced by
            # downlinkSetNR=1. Its featureSetListPerDownlinkCC[0] = 1 → CC table
            # entry 0.
            "featureSetsDownlink": [
                {"featureSetListPerDownlinkCC": [1]},
            ],
            "featureSetsUplink": [
                {"featureSetListPerUplinkCC": [1]},
            ],
            "featureSetsDownlinkPerCC": [
                {
                    "supportedSubcarrierSpacingDL": "kHz30",
                    "supportedBandwidthDL": ("fr1", "mhz100"),
                    "maxNumberMIMO-LayersPDSCH": "fourLayers",
                    "supportedModulationOrderDL": "qam256",
                },
            ],
            "featureSetsUplinkPerCC": [
                {
                    "supportedSubcarrierSpacingUL": "kHz30",
                    "supportedBandwidthUL": ("fr1", "mhz100"),
                    "maxNumberMIMO-LayersPUSCH": "twoLayers",
                    "supportedModulationOrderUL": "qam256",
                },
            ],
        },
    }
    section = _map_nr_from_dict(decoded)
    assert len(section.bandCombinations) == 1
    entry = section.bandCombinations[0].bands[0]
    assert entry.bandNR == 78
    assert entry.scs == 30
    assert entry.channelBWDL == "mhz100"
    assert entry.channelBWUL == "mhz100"
    assert entry.maxLayersDL == 4
    assert entry.maxLayersUL == 2
    assert entry.modulationDL == "qam256"
    assert entry.modulationUL == "qam256"


def test_map_nr_with_bcs_bitmap() -> None:
    """BIT STRING ``(value, length)`` tuple converts to MSB-first list[int]."""
    from ucap.adapters.qcat._asn1 import _map_nr_from_dict

    decoded = {
        "accessStratumRelease": "rel17",
        "rf-Parameters": {
            "supportedBandListNR": [{"bandNR": 41}],
            "supportedBandCombinationList": [
                {
                    "bandList": [("nr", {"bandNR": 41, "ca-BandwidthClassDL-NR": "a"})],
                    "featureSetCombination": 0,
                    # value=0b10100000 (160), length=8 → bits [1,0,1,0,0,0,0,0]
                    "supportedBandwidthCombinationSet": (0b10100000, 8),
                },
            ],
        },
        "featureSets": {"featureSetCombinations": [[[("nr", {"downlinkSetNR": 0, "uplinkSetNR": 0})]]]},
    }
    section = _map_nr_from_dict(decoded)
    assert section.bandCombinations[0].bcs == [1, 0, 1, 0, 0, 0, 0, 0]


def test_map_nr_kind_caNR_when_no_mrdc_no_eutra() -> None:
    """A combo with only NR band entries and no mrdc-Parameters → kind=caNR."""
    from ucap.adapters.qcat._asn1 import _map_nr_from_dict

    decoded = {
        "accessStratumRelease": "rel17",
        "rf-Parameters": {
            "supportedBandListNR": [{"bandNR": 41}, {"bandNR": 78}],
            "supportedBandCombinationList": [
                {
                    "bandList": [
                        ("nr", {"bandNR": 41, "ca-BandwidthClassDL-NR": "a"}),
                        ("nr", {"bandNR": 78, "ca-BandwidthClassDL-NR": "a"}),
                    ],
                    "featureSetCombination": 0,
                },
            ],
        },
        "featureSets": {
            "featureSetCombinations": [
                [
                    [("nr", {"downlinkSetNR": 0, "uplinkSetNR": 0})],
                    [("nr", {"downlinkSetNR": 0, "uplinkSetNR": 0})],
                ],
            ],
        },
    }
    section = _map_nr_from_dict(decoded)
    assert len(section.bandCombinations) == 1
    combo = section.bandCombinations[0]
    assert combo.kind == "caNR"
    assert combo.label == "n41A-n78A"


def test_map_nr_powerclass_normalization() -> None:
    """powerClass-v1530 enum tokens map through _normalize_power_class."""
    from ucap.adapters.qcat._asn1 import _map_nr_from_dict

    decoded = {
        "accessStratumRelease": "rel17",
        "rf-Parameters": {
            "supportedBandListNR": [{"bandNR": 41}],
            "supportedBandCombinationList": [
                {
                    "bandList": [("nr", {"bandNR": 41, "ca-BandwidthClassDL-NR": "a"})],
                    "featureSetCombination": 0,
                    "powerClass-v1530": "pc2",
                },
            ],
        },
        "featureSets": {"featureSetCombinations": [[[("nr", {"downlinkSetNR": 0, "uplinkSetNR": 0})]]]},
    }
    section = _map_nr_from_dict(decoded)
    assert section.bandCombinations[0].powerClassNR == "pc2"


def test_map_nr_empty_band_list() -> None:
    """A UE-NR-Capability with no supportedBandListNR yields an empty section."""
    from ucap.adapters.qcat._asn1 import _map_nr_from_dict

    decoded = {"accessStratumRelease": "rel15", "rf-Parameters": {}}
    section = _map_nr_from_dict(decoded)
    assert section.accessStratumRelease == "rel15"
    assert section.supportedBands == []
    assert section.bandCombinations == []


def test_map_mrdc_endc_combo() -> None:
    """A UE-MRDC-Capability with one main supportedBandCombination (EN-DC)
    yields an MrdcSection with kind=endc, source=main, label combining the
    LTE anchor + NR secondary.
    """
    from ucap.adapters.qcat._asn1 import _map_mrdc_from_dict, _NrPerCcTablesDict

    decoded = {
        "rf-ParametersMRDC": {
            "supportedBandCombinationList": [
                {
                    "bandList": [
                        ("eutra", {"bandEUTRA": 3, "ca-BandwidthClassDL-EUTRA": "a"}),
                        ("nr", {"bandNR": 78, "ca-BandwidthClassDL-NR": "a"}),
                    ],
                    "featureSetCombination": 0,
                },
            ],
        },
        "featureSetCombinations": [
            [  # FSC 0: two per-band entries
                [("eutra", {})],  # band 0: EUTRA — no NR caps to resolve
                [("nr", {"downlinkSetNR": 0, "uplinkSetNR": 0})],  # band 1: NR
            ],
        ],
    }
    section = _map_mrdc_from_dict(decoded, nr_per_cc=_NrPerCcTablesDict())
    assert len(section.bandCombinations) == 1
    combo = section.bandCombinations[0]
    assert combo.combinationId == 0
    assert combo.kind == "endc"
    assert combo.source == "main"
    assert combo.label == "3A-n78A"
    assert combo.featureSetCombinationId == 0
    assert len(combo.bands) == 2
    assert combo.bands[0].bandEUTRA == 3
    assert combo.bands[0].bandNR is None
    assert combo.bands[0].caBandwidthClassDL == "A"
    assert combo.bands[1].bandNR == 78
    assert combo.bands[1].bandEUTRA is None


def test_map_mrdc_three_source_lists() -> None:
    """Main + NEDC-Only-r16 + NRDC-r16 source lists each map with the right
    kind/source. combinationId is shared across the three lists (continues
    sequentially).
    """
    from ucap.adapters.qcat._asn1 import _map_mrdc_from_dict, _NrPerCcTablesDict

    decoded = {
        "rf-ParametersMRDC": {
            "supportedBandCombinationList": [
                {
                    "bandList": [
                        ("eutra", {"bandEUTRA": 3, "ca-BandwidthClassDL-EUTRA": "a"}),
                        ("nr", {"bandNR": 78, "ca-BandwidthClassDL-NR": "a"}),
                    ],
                    "featureSetCombination": 0,
                },
            ],
            "supportedBandCombinationListNEDC-Only-r16": [
                {
                    "bandList": [
                        ("nr", {"bandNR": 41, "ca-BandwidthClassDL-NR": "a"}),
                    ],
                    "featureSetCombination": 0,
                },
            ],
            "supportedBandCombinationListNRDC-r16": [
                {
                    "bandList": [
                        ("nr", {"bandNR": 78, "ca-BandwidthClassDL-NR": "a"}),
                        ("nr", {"bandNR": 41, "ca-BandwidthClassDL-NR": "a"}),
                    ],
                    "featureSetCombination": 0,
                },
            ],
        },
        "featureSetCombinations": [
            [[("nr", {"downlinkSetNR": 0, "uplinkSetNR": 0})] for _ in range(2)],
        ],
    }
    section = _map_mrdc_from_dict(decoded, nr_per_cc=_NrPerCcTablesDict())
    assert len(section.bandCombinations) == 3
    assert section.bandCombinations[0].kind == "endc"
    assert section.bandCombinations[0].source == "main"
    assert section.bandCombinations[0].combinationId == 0
    assert section.bandCombinations[1].kind == "nedc"
    assert section.bandCombinations[1].source == "nedcOnlyR16"
    assert section.bandCombinations[1].combinationId == 1
    assert section.bandCombinations[2].kind == "nrdc"
    assert section.bandCombinations[2].source == "nrdcR16"
    assert section.bandCombinations[2].combinationId == 2


def test_map_mrdc_empty() -> None:
    """A UE-MRDC-Capability without rf-ParametersMRDC yields empty MrdcSection."""
    from ucap.adapters.qcat._asn1 import _map_mrdc_from_dict, _NrPerCcTablesDict

    section = _map_mrdc_from_dict({}, nr_per_cc=_NrPerCcTablesDict())
    assert section.bandCombinations == []


def test_map_mrdc_reuses_nr_per_cc_tables() -> None:
    """When MRDC's combo references an NR feature-set, per-CC capabilities
    pull from the supplied nr_per_cc tables. Caps populate on the NR band entry.
    """
    from ucap.adapters.qcat._asn1 import _map_mrdc_from_dict, _NrPerCcTablesDict

    nr_per_cc = _NrPerCcTablesDict(
        downlink=({"featureSetListPerDownlinkCC": [1]},),
        uplink=({"featureSetListPerUplinkCC": [1]},),
        dl_per_cc=(
            {
                "supportedSubcarrierSpacingDL": "kHz30",
                "supportedBandwidthDL": ("fr1", "mhz100"),
                "maxNumberMIMO-LayersPDSCH": "fourLayers",
                "supportedModulationOrderDL": "qam256",
            },
        ),
        ul_per_cc=(
            {
                "supportedSubcarrierSpacingUL": "kHz30",
                "supportedBandwidthUL": ("fr1", "mhz100"),
                "maxNumberMIMO-LayersPUSCH": "twoLayers",
                "supportedModulationOrderUL": "qam256",
            },
        ),
    )
    decoded = {
        "rf-ParametersMRDC": {
            "supportedBandCombinationList": [
                {
                    "bandList": [
                        ("eutra", {"bandEUTRA": 3, "ca-BandwidthClassDL-EUTRA": "a"}),
                        ("nr", {"bandNR": 78, "ca-BandwidthClassDL-NR": "a"}),
                    ],
                    "featureSetCombination": 0,
                },
            ],
        },
        "featureSetCombinations": [
            [
                [("eutra", {})],  # band 0
                [("nr", {"downlinkSetNR": 1, "uplinkSetNR": 1})],  # band 1: NR
            ],
        ],
    }
    section = _map_mrdc_from_dict(decoded, nr_per_cc=nr_per_cc)
    nr_band = section.bandCombinations[0].bands[1]
    assert nr_band.bandNR == 78
    assert nr_band.scs == 30
    assert nr_band.channelBWDL == "mhz100"
    assert nr_band.maxLayersDL == 4
    assert nr_band.maxLayersUL == 2
    assert nr_band.modulationDL == "qam256"


def test_map_asn1_message_two_containers_nr_and_mrdc(monkeypatch) -> None:
    """A message with both an NR container and an EN-DC MRDC container
    produces both NrSection and MrdcSection populated; MRDC's mapper reuses
    NR's per-CC tables.
    """
    from ucap.adapters.qcat import _asn1
    from ucap.adapters.qcat._asn1 import (
        Asn1Message,
        Asn1RatContainer,
        map_asn1_message_to_canonical,
    )

    nr_decoded = {
        "accessStratumRelease": "rel17",
        "rf-Parameters": {
            "supportedBandListNR": [{"bandNR": 78}],
            "supportedBandCombinationList": [
                {
                    "bandList": [("nr", {"bandNR": 78, "ca-BandwidthClassDL-NR": "a"})],
                    "featureSetCombination": 0,
                },
            ],
        },
        "featureSets": {
            "featureSetCombinations": [[[("nr", {"downlinkSetNR": 1, "uplinkSetNR": 1})]]],
            "featureSetsDownlink": [{"featureSetListPerDownlinkCC": [1]}],
            "featureSetsUplink": [{"featureSetListPerUplinkCC": [1]}],
            "featureSetsDownlinkPerCC": [
                {
                    "supportedSubcarrierSpacingDL": "kHz30",
                    "supportedBandwidthDL": ("fr1", "mhz100"),
                    "maxNumberMIMO-LayersPDSCH": "fourLayers",
                    "supportedModulationOrderDL": "qam256",
                },
            ],
            "featureSetsUplinkPerCC": [
                {
                    "supportedSubcarrierSpacingUL": "kHz30",
                    "supportedBandwidthUL": ("fr1", "mhz100"),
                    "maxNumberMIMO-LayersPUSCH": "twoLayers",
                    "supportedModulationOrderUL": "qam256",
                },
            ],
        },
    }
    mrdc_decoded = {
        "rf-ParametersMRDC": {
            "supportedBandCombinationList": [
                {
                    "bandList": [
                        ("eutra", {"bandEUTRA": 3, "ca-BandwidthClassDL-EUTRA": "a"}),
                        ("nr", {"bandNR": 78, "ca-BandwidthClassDL-NR": "a"}),
                    ],
                    "featureSetCombination": 0,
                },
            ],
        },
        "featureSetCombinations": [
            [
                [("eutra", {})],
                [("nr", {"downlinkSetNR": 1, "uplinkSetNR": 1})],
            ],
        ],
    }

    # Route decode_rat_container to the right synthetic dict by rat-Type.
    def fake_decode(container):
        if container.rat_type == "nr":
            return nr_decoded
        return mrdc_decoded

    monkeypatch.setattr(_asn1, "decode_rat_container", fake_decode)

    msg = Asn1Message(
        rrc_transaction_id=2,
        rat_containers=(
            Asn1RatContainer(rat_type="nr", encoded=b"\x00"),
            Asn1RatContainer(rat_type="eutra-nr", encoded=b"\x00"),
        ),
        start_line=10,
        end_line=20,
    )
    canonical = map_asn1_message_to_canonical(
        msg, vendor="qcat", release="rel17", source_file="test.txt"
    )

    assert set(canonical.ratsPresent) == {"nr", "mrdc"}
    assert canonical.eutra is None
    assert canonical.nr is not None
    assert canonical.mrdc is not None

    # NR section: one supported band, one combo with full per-CC caps.
    assert canonical.nr.supportedBands[0].band == 78
    assert canonical.nr.bandCombinations[0].label == "n78A"
    assert canonical.nr.bandCombinations[0].bands[0].scs == 30
    assert canonical.nr.bandCombinations[0].bands[0].modulationDL == "qam256"

    # MRDC section: EN-DC combo with per-CC caps populated FROM NR's tables.
    assert len(canonical.mrdc.bandCombinations) == 1
    mrdc_combo = canonical.mrdc.bandCombinations[0]
    assert mrdc_combo.kind == "endc"
    assert mrdc_combo.label == "3A-n78A"
    nr_band_in_mrdc = mrdc_combo.bands[1]
    assert nr_band_in_mrdc.bandNR == 78
    assert nr_band_in_mrdc.scs == 30  # Came from NR per-CC tables.
    assert nr_band_in_mrdc.maxLayersDL == 4
    assert nr_band_in_mrdc.modulationDL == "qam256"
