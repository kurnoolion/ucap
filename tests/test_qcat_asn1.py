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
