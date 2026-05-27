"""EUTRA dict-mapper tests for FR-26 (v9e0 overlay), FR-27 (Reduced-r13),
and FR-2 parity (Add-r11 + BCS) in the shared ASN.1/Wireshark mapper.

These exercise ``_map_eutra_from_dict`` with hand-built pycrate-shaped decoded
dicts — no PER decoding needed — plus one indented-path v9e0 case via a
constructed ``TreeNode`` tree. BIT STRINGs use pycrate's ``(value, length)``
tuple form.
"""

from __future__ import annotations

from ucap.adapters.qcat._asn1 import _map_eutra_from_dict
from ucap.adapters.qcat._indented import TreeNode, _map_eutra


def _ncx(**layers: dict) -> dict:
    """Wrap rf-Parameters-vXXXX layers in a single nonCriticalExtension level."""
    return {"nonCriticalExtension": dict(layers)}


# ─── FR-26: v9e0 band overlay (dict path) ───────────────────────────


def test_v9e0_overlay_overrides_placeholder_bands():
    decoded = {
        "accessStratumRelease": "rel13",
        "rf-Parameters": {
            "supportedBandListEUTRA": [
                {"bandEUTRA": 2},
                {"bandEUTRA": 64},
                {"bandEUTRA": 64},
            ]
        },
        **_ncx(**{
            "rf-Parameters-v9e0": {
                "supportedBandListEUTRA-v9e0": [
                    {},
                    {"bandEUTRA-v9e0": 66},
                    {"bandEUTRA-v9e0": 71},
                ]
            }
        }),
    }
    sec = _map_eutra_from_dict(decoded)
    assert [b.band for b in sec.supportedBands] == [2, 66, 71]


def test_v9e0_absent_keeps_base_bands():
    decoded = {"rf-Parameters": {"supportedBandListEUTRA": [{"bandEUTRA": 2}, {"bandEUTRA": 7}]}}
    sec = _map_eutra_from_dict(decoded)
    assert [b.band for b in sec.supportedBands] == [2, 7]


def test_v9e0_overlay_indented_path():
    def N(name, value=None, children=None):
        return TreeNode(name, value, children or [], 0)

    rat = N("[0 ]", None, [
        N("RAT Type", "eutra"),
        N("UE EUTRA Capability", None, [
            N("accessStratumRelease", "rel13"),
            N("rf-Parameters", None, [
                N("supportedBandListEUTRA", None, [
                    N("[0 ]", None, [N("bandEUTRA", "2")]),
                    N("[1 ]", None, [N("bandEUTRA", "64")]),
                ]),
                N("supportedBandListEUTRA-v9e0", None, [
                    N("[0 ]", None, []),
                    N("[1 ]", None, [N("bandEUTRA-v9e0", "66")]),
                ]),
            ]),
        ]),
    ])
    sec = _map_eutra(rat)
    assert [b.band for b in sec.supportedBands] == [2, 66]


# ─── FR-27: Reduced-r13 combos (dict path) ──────────────────────────


def test_reduced_r13_combos_extracted():
    decoded = {
        "rf-Parameters": {"supportedBandListEUTRA": [{"bandEUTRA": 2}]},
        **_ncx(**{
            "rf-Parameters-v1310": {
                "supportedBandCombinationReduced-r13": [
                    {
                        "bandParameterList-r13": [
                            {
                                "bandEUTRA-r13": 2,
                                "bandParametersDL-r13": {
                                    "ca-BandwidthClassDL-r13": "d",
                                    "supportedMIMO-CapabilityDL-r13": "fourLayers",
                                },
                                "bandParametersUL-r13": {"ca-BandwidthClassUL-r10": "a"},
                            },
                            {
                                "bandEUTRA-r13": 66,
                                "bandParametersDL-r13": {"ca-BandwidthClassDL-r13": "a"},
                            },
                        ],
                        "supportedBandwidthCombinationSet-r13": (0b111, 3),
                    }
                ]
            }
        }),
    }
    sec = _map_eutra_from_dict(decoded)
    assert len(sec.caCombinations) == 1
    c = sec.caCombinations[0]
    assert c.source == "reducedR13"
    assert c.label == "2D-66A"
    assert c.bcs == [0, 1, 2]
    assert c.bands[0].band == 2
    assert c.bands[0].caBandwidthClassDL == "D"
    assert c.bands[0].caBandwidthClassUL == "A"
    assert c.bands[0].maxLayersDL == 4
    assert c.bands[1].band == 66
    assert c.bands[1].caBandwidthClassDL == "A"


# ─── FR-2 parity: Add-r11 + inline BCS (dict path) ──────────────────


def test_add_r11_combos_with_inline_bcs():
    decoded = {
        "rf-Parameters": {"supportedBandListEUTRA": [{"bandEUTRA": 7}]},
        **_ncx(**{
            "rf-Parameters-v1180": {
                "supportedBandCombinationAdd-r11": [
                    {
                        "bandParameterList-r11": [
                            {
                                "bandEUTRA-r11": 7,
                                "bandParametersDL-r11": [
                                    {
                                        "ca-BandwidthClassDL-r10": "c",
                                        "supportedMIMO-CapabilityDL-r10": "twoLayers",
                                    }
                                ],
                                "bandParametersUL-r11": [{"ca-BandwidthClassUL-r10": "a"}],
                            }
                        ],
                        "supportedBandwidthCombinationSet-r11": (0b1, 1),
                    }
                ]
            }
        }),
    }
    sec = _map_eutra_from_dict(decoded)
    assert len(sec.caCombinations) == 1
    c = sec.caCombinations[0]
    assert c.source == "addR11"
    assert c.label == "7C"
    assert c.bcs == [0]
    assert c.bands[0].caBandwidthClassDL == "C"
    assert c.bands[0].caBandwidthClassUL == "A"
    assert c.bands[0].maxLayersDL == 2


# ─── FR-2 parity: main r10 BCS from parallel Ext-r10 ────────────────


def test_main_r10_bcs_from_parallel_ext():
    decoded = {
        "rf-Parameters": {"supportedBandListEUTRA": [{"bandEUTRA": 2}]},
        **_ncx(**{
            "rf-Parameters-v1020": {
                "supportedBandCombination-r10": [
                    [
                        {
                            "bandEUTRA-r10": 2,
                            "bandParametersDL-r10": [
                                {
                                    "ca-BandwidthClassDL-r10": "a",
                                    "supportedMIMO-CapabilityDL-r10": "fourLayers",
                                }
                            ],
                            "bandParametersUL-r10": [{"ca-BandwidthClassUL-r10": "a"}],
                        }
                    ],
                    [{"bandEUTRA-r10": 7, "bandParametersDL-r10": [{"ca-BandwidthClassDL-r10": "a"}]}],
                ]
            },
            "rf-Parameters-v1060": {
                "supportedBandCombinationExt-r10": [
                    {"supportedBandwidthCombinationSet-r10": (0b11, 2)},
                    {},
                ]
            },
        }),
    }
    sec = _map_eutra_from_dict(decoded)
    assert len(sec.caCombinations) == 2
    assert sec.caCombinations[0].source == "main"
    assert sec.caCombinations[0].label == "2A"
    assert sec.caCombinations[0].bcs == [0, 1]
    assert sec.caCombinations[0].bands[0].maxLayersDL == 4
    assert sec.caCombinations[1].bcs is None


# ─── combinationId contiguity across all three sources ──────────────


def test_combination_ids_contiguous_across_sources():
    decoded = {
        "rf-Parameters": {"supportedBandListEUTRA": [{"bandEUTRA": 2}]},
        **_ncx(**{
            "rf-Parameters-v1020": {
                "supportedBandCombination-r10": [
                    [{"bandEUTRA-r10": 2, "bandParametersDL-r10": [{"ca-BandwidthClassDL-r10": "a"}]}]
                ]
            },
            "rf-Parameters-v1180": {
                "supportedBandCombinationAdd-r11": [
                    {"bandParameterList-r11": [{"bandEUTRA-r11": 7, "bandParametersDL-r11": [{"ca-BandwidthClassDL-r10": "a"}]}]}
                ]
            },
            "rf-Parameters-v1310": {
                "supportedBandCombinationReduced-r13": [
                    {"bandParameterList-r13": [{"bandEUTRA-r13": 66, "bandParametersDL-r13": {"ca-BandwidthClassDL-r13": "a"}}]}
                ]
            },
        }),
    }
    sec = _map_eutra_from_dict(decoded)
    assert [c.combinationId for c in sec.caCombinations] == [0, 1, 2]
    assert [c.source for c in sec.caCombinations] == ["main", "addR11", "reducedR13"]
    assert [c.label for c in sec.caCombinations] == ["2A", "7A", "66A"]
