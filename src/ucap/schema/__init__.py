"""Canonical schema for UE capability band combinations.

Field names mirror 3GPP ASN.1 identifiers (lowerCamelCase) so the JSON stays
greppable against TS 36.331 / TS 38.331.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Vendor = Literal["qcat", "shannon", "elt", "wireshark"]
Release = Literal["rel15", "rel16", "rel17", "rel18"]
RatName = Literal["eutra", "nr", "mrdc"]

CaBandwidthClass = Literal["A", "B", "C", "D", "E", "F"]
Modulation = Literal["qam64", "qam256", "qam1024"]
FrequencyRange = Literal["FR1", "FR2"]
PowerClassNR = Literal["pc1dot5", "pc2", "pc3", "pc5"]

EutraComboSource = Literal["main", "addR11", "reducedR13", "v1090", "v1130"]
NrComboSource = Literal["main", "v1540", "v1550", "v1560", "v1610"]
MrdcComboSource = Literal["main", "nedcOnlyR16", "nrdcR16"]

# Kind of dual-connectivity / CA arrangement, derived from the combo's contents:
#   caNR  — pure NR CA (only bandNR entries, no mrdc-Parameters)
#   endc  — LTE anchor + NR secondary (mixed entries, or sourced from MRDC main list)
#   nedc  — NR anchor + LTE secondary (sourced from NEDC list)
#   nrdc  — two NR cells in different bands (sourced from NR-DC list)
NrComboKind = Literal["caNR", "endc", "nedc", "nrdc"]
MrdcComboKind = Literal["endc", "nedc", "nrdc"]


class _M(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class Meta(_M):
    vendor: Vendor
    vendorToolVersion: str | None = None
    release: Release
    sourceFile: str
    sourceLineRange: tuple[int, int] | None = None
    timestamp: str | None = None
    decodedAt: datetime
    parserVersion: str


# ─── EUTRA ──────────────────────────────────────────────────────────


class EutraBand(_M):
    band: int
    halfDuplex: bool = False


class EutraComboBandEntry(_M):
    band: int
    caBandwidthClassDL: CaBandwidthClass | None = None
    caBandwidthClassUL: CaBandwidthClass | None = None
    maxLayersDL: int | None = None
    maxLayersUL: int | None = None


class EutraCaCombination(_M):
    combinationId: int
    label: str
    bands: list[EutraComboBandEntry]
    bcs: list[int] | None = None
    supports256QAMDL: bool | None = None
    supports64QAMUL: bool | None = None
    supports1024QAMDL: bool | None = None
    source: EutraComboSource = "main"


class EutraSection(_M):
    accessStratumRelease: str
    # Release inferred from version-suffixed field names in the decoded
    # data (e.g. ``-r16``, ``-v1610``, ``-v1700``). Distinct from
    # ``accessStratumRelease``: in NR ``accessStratumRelease`` is always
    # ``"rel15"`` (TS 38.331 hasn't populated the spare slots), and in LTE
    # it reflects baseline AS support which may lag actual feature support.
    # ``None`` when no version-suffixed fields are present (typically a
    # baseline-only message). Format: ``"relN"`` for N in 9..18+ — not
    # constrained to the ``Release`` literal because suffix scanning may
    # surface release numbers beyond v1's ``--release`` choices.
    inferredRelease: str | None = None
    supportedBands: list[EutraBand]
    caCombinations: list[EutraCaCombination]
    unmapped: dict[str, Any] | None = Field(default=None, alias="_unmapped")


# ─── NR (+ EN-DC combos that live in the NR cap container) ──────────


class NrBand(_M):
    band: int
    fr: FrequencyRange
    scsSupported: list[int]


class NrComboBandEntry(_M):
    """One component-carrier in an NR or EN-DC band combination.

    Either ``bandNR`` or ``bandEUTRA`` is set, not both. NR-specific fields
    (``scs``, ``channelBWDL`` / ``channelBWUL``) come from feature-set
    resolution and only apply when ``bandNR`` is set.
    """

    bandNR: int | None = None
    bandEUTRA: int | None = None
    # NR per-CC capabilities (feature-set-resolved):
    scs: int | None = None
    channelBWDL: str | None = None
    channelBWUL: str | None = None
    # EUTRA-style CA bandwidth class (applies to EUTRA entries):
    caBandwidthClassDL: CaBandwidthClass | None = None
    caBandwidthClassUL: CaBandwidthClass | None = None
    # MIMO / modulation (both flavors):
    maxLayersDL: int | None = None
    maxLayersUL: int | None = None
    modulationDL: Modulation | None = None
    modulationUL: Modulation | None = None
    supportsSUL: bool = False


class NrBandCombination(_M):
    combinationId: int
    label: str
    kind: NrComboKind
    bands: list[NrComboBandEntry]
    bcs: list[int] | None = None
    featureSetCombinationId: int | None = None
    powerClassNR: PowerClassNR | None = None
    source: NrComboSource = "main"


class NrSection(_M):
    accessStratumRelease: str
    # See EutraSection.inferredRelease. Important for NR specifically:
    # ``accessStratumRelease`` is always ``"rel15"`` (TS 38.331's
    # ``AccessStratumRelease ::= ENUMERATED {rel15, spare7..1}``; no spares
    # populated for rel16/17/18). ``inferredRelease`` is the practical
    # answer for "what release of features is this UE reporting?".
    inferredRelease: str | None = None
    supportedBands: list[NrBand]
    bandCombinations: list[NrBandCombination]
    unmapped: dict[str, Any] | None = Field(default=None, alias="_unmapped")


# ─── MRDC ───────────────────────────────────────────────────────────


class MrdcBandCombination(_M):
    """A combo from the dedicated UE-MRDC-Capability container.

    Uses the same per-CC entry shape as NR combos.
    """

    combinationId: int
    label: str
    kind: MrdcComboKind
    bands: list[NrComboBandEntry]
    bcs: list[int] | None = None
    featureSetCombinationId: int | None = None
    powerClassNR: PowerClassNR | None = None
    source: MrdcComboSource = "main"


class MrdcSection(_M):
    # MRDC has no ``accessStratumRelease`` field — see EutraSection.
    inferredRelease: str | None = None
    bandCombinations: list[MrdcBandCombination]
    unmapped: dict[str, Any] | None = Field(default=None, alias="_unmapped")


# ─── Root ───────────────────────────────────────────────────────────


class CanonicalUeCapability(_M):
    meta: Meta = Field(alias="_meta")
    ratsPresent: list[RatName]
    eutra: EutraSection | None = None
    nr: NrSection | None = None
    mrdc: MrdcSection | None = None
