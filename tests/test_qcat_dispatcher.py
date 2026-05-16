"""Tests for the QCAT adapter dispatcher in qcat/__init__.py.

Covers ``detect_format`` and the high-level ``parse_qcat_to_canonical`` pipeline
that auto-routes between the indented-tree and ASN.1 value-notation formats.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ucap.adapters.qcat import (
    detect_format,
    parse_qcat_to_canonical,
)
from ucap.schema import CanonicalUeCapability

FIXTURES = Path(__file__).parent / "fixtures" / "qcat"


_ASN1_SAMPLE = """\
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


# ─── detect_format ──────────────────────────────────────────────────


def test_detect_format_asn1():
    assert detect_format(_ASN1_SAMPLE) == "asn1"


def test_detect_format_asn1_no_whitespace_variant():
    """Tolerates ``message c1: ueCapabilityInformation :`` (no space before colon)."""
    txt = "junk\nmessage c1: ueCapabilityInformation :\n  { rrc-TransactionIdentifier 0 }\n"
    assert detect_format(txt) == "asn1"


def test_detect_format_indented_fixture():
    text = (FIXTURES / "OnePlus9_LTE.txt").read_text()
    assert detect_format(text) == "indented"


def test_detect_format_empty():
    assert detect_format("") == "indented"


def test_detect_format_unrelated_text():
    """Anything that doesn't carry the ASN.1 entry marker defaults to indented.

    The indented adapter will then surface its own diagnostic if the input is
    actually not a UE Cap log.
    """
    assert detect_format("UE Capability Information (UL-DCCH)\n") == "indented"
    assert detect_format("random garbage\nno marker here\n") == "indented"


# ─── parse_qcat_to_canonical — indented route ───────────────────────


def test_dispatch_indented_fixture():
    """The indented-format fixture produces a canonical record end-to-end."""
    docs = parse_qcat_to_canonical(
        FIXTURES / "OnePlus9_LTE.txt",
        vendor="qcat",
        release="rel17",
    )
    assert len(docs) == 1
    doc = docs[0]
    assert isinstance(doc, CanonicalUeCapability)
    assert "eutra" in doc.ratsPresent
    assert doc.meta.sourceFile == "OnePlus9_LTE.txt"


def test_dispatch_indented_explicit_source_file():
    """An explicit ``source_file`` overrides the path basename."""
    docs = parse_qcat_to_canonical(
        FIXTURES / "OnePlus9_LTE.txt",
        vendor="qcat",
        release="rel17",
        source_file="custom_name.txt",
    )
    assert docs[0].meta.sourceFile == "custom_name.txt"


def test_dispatch_indented_string_path(tmp_path):
    """``parse_qcat_to_canonical`` accepts ``str`` paths in addition to ``Path``."""
    src = FIXTURES / "OnePlus9_LTE.txt"
    docs = parse_qcat_to_canonical(str(src), vendor="qcat", release="rel17")
    assert len(docs) == 1
    assert docs[0].meta.sourceFile == "OnePlus9_LTE.txt"


# ─── parse_qcat_to_canonical — ASN.1 route ──────────────────────────


def test_dispatch_asn1_route(tmp_path, monkeypatch):
    """An ASN.1-format input routes through the ASN.1 mapper.

    pycrate's PER decode requires real Rel-17 OCTET STRINGs which we don't have
    in the open-source fixtures, so we monkeypatch
    ``map_asn1_message_to_canonical`` to bypass the decode and confirm only
    that the dispatcher hands the parsed L1 message to the ASN.1 path.
    """
    import ucap.adapters.qcat as qcat_pkg
    from ucap.adapters.qcat._asn1 import Asn1Message
    from ucap.schema import Meta

    log = tmp_path / "rel17_asn1.txt"
    log.write_text(_ASN1_SAMPLE)

    calls: list[tuple[Asn1Message, str, str, str]] = []

    from datetime import datetime, timezone

    def fake_map(msg, *, vendor, release, source_file):
        calls.append((msg, vendor, release, source_file))
        return CanonicalUeCapability(
            meta=Meta(
                vendor=vendor,
                release=release,
                sourceFile=source_file,
                decodedAt=datetime.now(timezone.utc),
                parserVersion="test",
            ),
            ratsPresent=[],
        )

    monkeypatch.setattr(qcat_pkg, "map_asn1_message_to_canonical", fake_map)

    docs = parse_qcat_to_canonical(log, vendor="qcat", release="rel17")
    assert len(docs) == 1
    assert len(calls) == 1
    msg, vendor, release, source_file = calls[0]
    assert isinstance(msg, Asn1Message)
    assert msg.rrc_transaction_id == 2
    assert len(msg.rat_containers) == 1
    assert msg.rat_containers[0].rat_type == "nr"
    assert vendor == "qcat"
    assert release == "rel17"
    assert source_file == "rel17_asn1.txt"


def test_dispatch_missing_file_raises(tmp_path):
    """A non-existent path raises ``FileNotFoundError`` — CLI surfaces this."""
    with pytest.raises(FileNotFoundError):
        parse_qcat_to_canonical(
            tmp_path / "does_not_exist.txt", vendor="qcat", release="rel17"
        )
