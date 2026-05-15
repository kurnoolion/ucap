# schema

**Purpose**
Canonical schema for UE capability band combinations — Pydantic v2 models with `extra="forbid"` and the Literal type aliases (`Vendor`, `Release`, `RatName`, etc.) that every adapter and the CLI share. The contract every vendor adapter maps into. Serves `FR-1` (canonical JSON output), `FR-2`–`FR-5` (canonical shape for EUTRA / NR / MRDC sections), `NFR-2` (schema strictness).

**Public surface**

Type aliases (Literal types — bounded enums used as field types and as CLI argparse choices):

```python
Vendor              = Literal["qcat", "shannon", "elt"]
Release             = Literal["rel15", "rel16", "rel17", "rel18"]
RatName             = Literal["eutra", "nr", "mrdc"]
CaBandwidthClass    = Literal["A", "B", "C", "D", "E", "F"]
Modulation          = Literal["qam64", "qam256", "qam1024"]
FrequencyRange      = Literal["FR1", "FR2"]
PowerClassNR        = Literal["pc1dot5", "pc2", "pc3", "pc5"]
EutraComboSource    = Literal["main", "addR11", "reducedR13", "v1090", "v1130"]
NrComboSource       = Literal["main", "v1540", "v1550", "v1560", "v1610"]
MrdcComboSource     = Literal["main", "nedcOnlyR16", "nrdcR16"]
NrComboKind         = Literal["caNR", "endc", "nedc", "nrdc"]
MrdcComboKind       = Literal["endc", "nedc", "nrdc"]
```

Pydantic models (all extend `_M`, which sets `populate_by_name=True, extra="forbid"`):

```python
class Meta                  # per-message provenance
class EutraBand             # supported EUTRA band entry
class EutraComboBandEntry   # band entry inside an EUTRA combo
class EutraCaCombination    # one EUTRA CA combination
class EutraSection          # EUTRA section of the canonical document

class NrBand                # supported NR band entry
class NrComboBandEntry      # component-carrier in an NR or EN-DC combo
class NrBandCombination     # one NR / dual-connectivity combo
class NrSection             # NR section of the canonical document

class MrdcBandCombination   # combo from the dedicated UE-MRDC-Capability container
class MrdcSection           # MRDC section of the canonical document

class CanonicalUeCapability # root canonical document — what every adapter emits
```

**Invariants**

- **Every model declares `extra="forbid"`** via the `_M` base. Emitting an undeclared field is a Pydantic `ValidationError`, not a silent pass-through. Anchors `[D-002]` and `NFR-2`.
- **`_meta` and `_unmapped` are JSON-key aliases.** Surfaced as `_meta` / `_unmapped` keys in JSON output via Pydantic field aliases; Python attribute names are `meta` and `unmapped` (no leading underscore). Anchors `[D-007]`.
- **Field names mirror 3GPP ASN.1 identifiers** (lowerCamelCase: `supportedBands`, `caBandwidthClassDL`, `featureSetCombinationId`, etc.) so the canonical JSON stays greppable against TS 36.331 / TS 38.331. Snake_case is reserved for ucap-internal Python identifiers; the wire-format keys use the ASN.1-native casing.
- **Type aliases are stable across the v1 major.** Adding values to `Release` / `Vendor` is additive; removing or renaming a value is a breaking change requiring a major-version bump (`NFR-9` / `NFR-10`).
- **Schema is pure Pydantic + stdlib.** No imports from `ucap.adapters`, `ucap.cli`, or `ucap.diagnostics`. This is what makes schema a leaf at the file-graph level and resolves the package-level cycle that `[D-014]` addresses by sub-packaging schema separately.

**Key choices**

- `[D-002]` — Pydantic v2 with `extra="forbid"`.
- `[D-005]` — flat canonical JSON shape oriented around band combinations; not a hierarchical mirror of the ASN.1 tree.
- `[D-007]` — `_meta` / `_unmapped` JSON aliases for provenance + forward-compatibility escape hatch.
- `[D-014]` — schema split into its own sub-package (this module) to resolve the `ucap ↔ adapters` package-level cycle.

**Non-goals**

- **Not an ASN.1 grammar definition.** ucap parses vendor *text* exports; the 3GPP ASN.1 grammar is referenced by adapter logic, not represented as a parseable artifact here.
- **Not a JSON Schema export.** Pydantic can emit JSON Schema, but ucap doesn't ship one as a published artifact in v1.
- **Not a SQL / Avro / Protobuf schema.** Pydantic + canonical JSON are the only output forms for v1.
- **Not validation infrastructure for non-canonical types.** General-purpose validators (e.g., for compliance-sheet inputs in a future `audit` module) live in their owning module, not here.

<!-- BEGIN:STRUCTURE -->
_Regenerated 2026-05-14 by regen-map. Do not hand-edit._

### `__init__.py`

- `CaBandwidthClass` — type alias — pub — Carrier-aggregation bandwidth-class enum (A–F).
- `CanonicalUeCapability` — class — pub — Root canonical UE-capability document.
- `EutraBand` — class — pub — A single supported EUTRA band entry.
- `EutraCaCombination` — class — pub — An EUTRA CA band combination.
- `EutraComboBandEntry` — class — pub — One band entry inside an EUTRA combo.
- `EutraComboSource` — type alias — pub — Source list an EUTRA combo came from.
- `EutraSection` — class — pub — EUTRA section of the canonical document.
- `FrequencyRange` — type alias — pub — NR frequency range (FR1 / FR2).
- `Meta` — class — pub — Per-message provenance metadata.
- `Modulation` — type alias — pub — Per-CC modulation order (qam64 / qam256 / qam1024).
- `MrdcBandCombination` — class — pub — A combo from the dedicated UE-MRDC-Capability container.
- `MrdcComboKind` — type alias — pub — Kind of MRDC combo (endc / nedc / nrdc).
- `MrdcComboSource` — type alias — pub — Source list an MRDC combo came from.
- `MrdcSection` — class — pub — MRDC section of the canonical document.
- `NrBand` — class — pub — A single supported NR band entry.
- `NrBandCombination` — class — pub — An NR / dual-connectivity band combination.
- `NrComboBandEntry` — class — pub — One component-carrier in an NR or EN-DC band combination.
- `NrComboKind` — type alias — pub — Kind of NR / dual-connectivity combo (caNR / endc / nedc / nrdc).
- `NrComboSource` — type alias — pub — Source list an NR combo came from.
- `NrSection` — class — pub — NR section of the canonical document.
- `PowerClassNR` — type alias — pub — NR UE power class (pc1dot5 / pc2 / pc3 / pc5).
- `RatName` — type alias — pub — Radio-Access-Technology name (eutra / nr / mrdc).
- `Release` — type alias — pub — 3GPP grammar release (rel15 / rel16 / rel17 / rel18).
- `Vendor` — type alias — pub — Chipset-vendor modem-log tool (qcat / shannon / elt).
- `_M` — class — internal — Shared Pydantic base configured `populate_by_name=True, extra="forbid"`.
<!-- END:STRUCTURE -->

**Depends on**
*(none in ucap — leaf node like `diagnostics`. External: `pydantic>=2.6`.)*

**Depended on by**
- `src/ucap/MODULE.md` — `cli.py` uses `Vendor` and `Release` literal types as argparse choices.
- `src/ucap/adapters/MODULE.md` — every adapter consumes the full type-and-model surface, producing `CanonicalUeCapability` from a vendor-specific log.
- *(future)* `audit`, `diff`, `query` modules when those land — all operate over `CanonicalUeCapability` records.
