<!-- retrofit: skeleton -->
# ucap

**Purpose**
TODO — retrofit skeleton; please fill in. This is the top-level Python package: CLI entry point (`cli.py`), canonical schema (`schema.py`), package metadata (`__init__.py`). Submodules (`adapters/`, future `diagnostics/`) get their own MODULE.md.

**Public surface**
<!-- Candidates observed in code (curate; don't copy verbatim): -->
<!-- From src/ucap/__init__.py: -->
<!-- - __version__: str -->
<!-- From src/ucap/cli.py: -->
<!-- - def main(argv: list[str] | None = None) -> int  # registered as `ucap` console script in pyproject.toml -->
<!-- From src/ucap/schema.py — type aliases: -->
<!-- - Vendor: Literal["qcat", "shannon", "elt"] -->
<!-- - Release: Literal["rel15", "rel16", "rel17", "rel18"] -->
<!-- - RatName: Literal["eutra", "nr", "mrdc"] -->
<!-- - CaBandwidthClass, Modulation, FrequencyRange, PowerClassNR -->
<!-- - EutraComboSource, NrComboSource, MrdcComboSource, NrComboKind, MrdcComboKind -->
<!-- From src/ucap/schema.py — Pydantic models: -->
<!-- - Meta, EutraBand, EutraComboBandEntry, EutraCaCombination, EutraSection -->
<!-- - NrBand, NrComboBandEntry, NrBandCombination, NrSection -->
<!-- - MrdcBandCombination, MrdcSection -->
<!-- - CanonicalUeCapability  # top-level canonical output type -->
TODO

**Invariants**
TODO — likely candidates worth committing to:
- `extra="forbid"` on every Pydantic model — emitting an undeclared field is a schema-discipline failure.
- `_meta` / `_unmapped` JSON aliases must round-trip through Pydantic validation unchanged.
- `CanonicalUeCapability` is the single canonical output type — all adapters map into it.

**Key choices**
TODO — link to DECISIONS entries once architecture phase formalizes them. Candidates: Pydantic v2 over hand-rolled dicts; flat canonical shape focused on band combinations; per-vendor adapter pattern under `adapters/`.

**Non-goals**
TODO — likely:
- Not a 3GPP ASN.1 decoder (we parse vendor text exports, not raw ASN.1 BER/PER).
- Not a runtime / service — CLI batch tool only.
- Per-band `mimo-ParametersPerBand` and `scsSupported` deferred to a later release.

<!-- BEGIN:STRUCTURE -->
_Regenerated 2026-05-14 by regen-map. Do not hand-edit._

### `__init__.py`

- `__version__` — value — pub — Package version string.

### `cli.py`

- `_build_parser` — function — internal — Build the argparse parser for the `ucap` CLI.
- `_cmd_parse` — function — internal — Handler for the `parse` subcommand.
- `_parse_log` — function — internal — Dispatch to the per-vendor adapter.
- `main` — function — pub — CLI entry point; registered as the `ucap` console script.

### `schema.py`

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
TODO — link peer MODULE.md files.
- `src/ucap/adapters/MODULE.md` (the package consumes adapter outputs via the CLI dispatcher in `cli.py`).
- Future `src/ucap/diagnostics/MODULE.md` once drafted (Pillar C).

**Depended on by**
TODO — top-level package; depended on by `tests/` and (externally) any consumer of the canonical JSON output.
