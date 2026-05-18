"""Tests for ``infer_release()`` — the version-suffix scanner that derives
the highest 3GPP release seen in a decoded UE Capability dict.

The scanner is purely lexical: it looks at field-name suffixes (``-rN``,
``-vMMmm``) anywhere in a pycrate-shape value tree. It complements
``accessStratumRelease``, which for NR is always ``"rel15"`` and for LTE
reflects only baseline AS support.
"""

from __future__ import annotations

from ucap.adapters.qcat._asn1 import infer_release


# ─── Empty / baseline cases ─────────────────────────────────────────


def test_empty_dict_returns_none():
    assert infer_release({}) is None


def test_baseline_fields_only_returns_none():
    """No version-suffixed names → no inference."""
    decoded = {
        "accessStratumRelease": "rel15",
        "rf-Parameters": {
            "supportedBandListNR": [{"bandNR": 78}],
        },
        "pdcp-Parameters": {
            "supportedROHC-Profiles": {"profile0x0001": True},
        },
    }
    assert infer_release(decoded) is None


def test_primitive_value_returns_none():
    assert infer_release(0) is None
    assert infer_release("rel15") is None
    assert infer_release(b"deadbeef") is None
    assert infer_release(None) is None


# ─── -rN suffix detection ───────────────────────────────────────────


def test_single_r16_suffix():
    decoded = {"someField-r16": 1}
    assert infer_release(decoded) == "rel16"


def test_single_r17_suffix():
    decoded = {"mac-Parameters-r17": {"x": 1}}
    assert infer_release(decoded) == "rel17"


def test_r9_lower_bound():
    """Single-digit release numbers parse correctly."""
    decoded = {"old-field-r9": True}
    assert infer_release(decoded) == "rel9"


def test_max_wins_across_r_suffixes():
    decoded = {
        "a-r10": 1,
        "b-r16": 1,
        "c-r12": 1,
    }
    assert infer_release(decoded) == "rel16"


def test_r_suffix_must_be_at_token_boundary():
    """``-r170`` is not ``r17`` followed by 0 — release 170 isn't a thing,
    but more importantly, ``r9_more`` shouldn't be parsed as r9."""
    # No false positive: digit followed by alphanumeric → no match.
    assert infer_release({"foo-r9_x": 1}) is None
    assert infer_release({"foo-r9abc": 1}) is None
    # Correct match when followed by `-`:
    assert infer_release({"foo-r17-bar": 1}) == "rel17"
    # Correct match at end of string:
    assert infer_release({"foo-r18": 1}) == "rel18"


# ─── -vMMmm suffix detection ────────────────────────────────────────


def test_single_v_suffix_rel16():
    decoded = {"rf-Parameters-v1610": {"x": 1}}
    assert infer_release(decoded) == "rel16"


def test_single_v_suffix_rel17():
    decoded = {"featureSets-v1700": {"x": 1}}
    assert infer_release(decoded) == "rel17"


def test_v_suffix_rel15_sub_minor():
    """``-v1530`` is rel15.3.0 — release component is 15."""
    decoded = {"rf-Parameters-v1530": {"x": 1}}
    assert infer_release(decoded) == "rel15"


def test_v_suffix_rel18():
    decoded = {"foo-v1810": {"x": 1}}
    assert infer_release(decoded) == "rel18"


def test_v_suffix_does_not_match_three_digits():
    """``-v160`` would be too short to be a valid 3GPP version suffix."""
    assert infer_release({"foo-v160": 1}) is None


# ─── Recursive walk ─────────────────────────────────────────────────


def test_nested_dict_deep_suffix():
    decoded = {
        "outer": {
            "middle": {
                "inner-r17": True,
            },
        },
    }
    assert infer_release(decoded) == "rel17"


def test_list_of_dicts():
    decoded = {
        "bands": [
            {"bandNR": 78},
            {"bandNR-r16": 79},
        ],
    }
    assert infer_release(decoded) == "rel16"


def test_pycrate_choice_tuple():
    """pycrate CHOICE form ``(tag, sub-value)`` — the scanner walks ``sub``."""
    decoded = {
        "bandList": [
            ("nr", {"bandNR": 78}),
            ("nr", {"bandNR-r16": 79}),
        ],
    }
    assert infer_release(decoded) == "rel16"


def test_nonCriticalExtension_chain():
    """A typical chain: rel15 base → v1530-IEs → v1610-IEs → v1700-IEs."""
    decoded = {
        "accessStratumRelease": "rel15",
        "pdcp-Parameters": {},
        "nonCriticalExtension": {
            "rf-Parameters-v1530": {},
            "nonCriticalExtension": {
                "rf-Parameters-v1610": {},
                "nonCriticalExtension": {
                    "featureSets-v1700": {},
                },
            },
        },
    }
    assert infer_release(decoded) == "rel17"


def test_mixed_r_and_v_suffixes_max_wins():
    decoded = {
        "a-r17": 1,
        "b-v1610": 1,
        "nested": {
            "c-r18": 1,
        },
    }
    assert infer_release(decoded) == "rel18"


# ─── Integration with section mappers ───────────────────────────────


def test_nr_section_inferred_release_populates_in_mapper():
    """``_map_nr_from_dict`` calls ``infer_release`` and sets the field."""
    from ucap.adapters.qcat._asn1 import _map_nr_from_dict

    decoded = {
        "accessStratumRelease": "rel15",
        "rf-Parameters": {
            "supportedBandListNR": [{"bandNR": 78}],
            "supportedBandCombinationList-v1610": [],
        },
    }
    section = _map_nr_from_dict(decoded)
    assert section.accessStratumRelease == "rel15"
    assert section.inferredRelease == "rel16"


def test_eutra_section_inferred_release_populates_in_mapper():
    from ucap.adapters.qcat._asn1 import _map_eutra_from_dict

    decoded = {
        "accessStratumRelease": "rel10",
        "rf-Parameters": {
            "supportedBandListEUTRA": [{"bandEUTRA": 1, "halfDuplex": False}],
        },
        "nonCriticalExtension": {
            "rf-Parameters-v1020": {},
            "nonCriticalExtension": {
                "rf-Parameters-v1090": {},
            },
        },
    }
    section = _map_eutra_from_dict(decoded)
    assert section.accessStratumRelease == "rel10"
    assert section.inferredRelease == "rel10"  # -v10NN suffixes → release 10


def test_baseline_nr_section_no_inference():
    """A pure baseline UE-NR-Capability (no -rN, no -vMMmm) → inferredRelease=None."""
    from ucap.adapters.qcat._asn1 import _map_nr_from_dict

    decoded = {
        "accessStratumRelease": "rel15",
        "rf-Parameters": {
            "supportedBandListNR": [{"bandNR": 78}],
        },
    }
    section = _map_nr_from_dict(decoded)
    assert section.accessStratumRelease == "rel15"
    assert section.inferredRelease is None
