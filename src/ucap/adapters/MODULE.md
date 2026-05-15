# adapters

**Purpose**
Per-vendor parsers that map chipset-vendor modem-log text exports to `CanonicalUeCapability` records — one record per `UE Capability Information` message in the input. v1 ships the QCAT adapter (Qualcomm); Shannon DM and ELT adapters are stubs awaiting sample logs. Serves `FR-1` (parse-to-canonical pipeline), `FR-2`–`FR-5` (EUTRA / NR / MRDC mapping), `FR-9` (BIT STRING dual-style parsing), `FR-8` (stub-adapter NotImplementedError messages).

**Public surface**

`src/ucap/adapters/qcat.py` (file declares `__all__`; that list is authoritative):

```python
class TreeNode               # node in the indent-driven parse tree (name, value, children, line_no)
class Message                # parsed QCAT message: title, direction, timestamp, line range, root TreeNode

def parse_qcat_file(path: str | Path) -> list[Message]
def parse_qcat_text(text: str) -> Iterator[Message]
def map_message_to_canonical(
    msg: Message, *, vendor: Vendor, release: Release, source_file: str,
) -> CanonicalUeCapability
```

`src/ucap/adapters/shannon.py`:

```python
def parse_shannon_log(path: str | Path, *, release: str) -> list[CanonicalUeCapability]
# v1: stub. Raises NotImplementedError with a message naming the sample-log artifact needed
# (Shannon DM right-click "Copy Details" path: LTE RRC → ULDCCH → ueCapabilityInformation).
# Under --diagnostic mode, emits a FAIL report (error_code=SHN-E001) instead per [D-010] B6.
```

`src/ucap/adapters/elt.py`:

```python
def parse_elt_log(path: str | Path, *, release: str) -> list[CanonicalUeCapability]
# v1: stub. Raises NotImplementedError with a message naming the sample-log artifact needed
# (ELT native log view or Wireshark-routed export).
# Under --diagnostic mode, emits a FAIL report (error_code=ELT-E001) instead per [D-010] B6.
```

Internal helpers (the 35+ leading-underscore functions and classes in `qcat.py` — `_parse_message`, `_build_tree`, `_map_eutra`, `_collect_nr_per_cc_tables`, etc.) are not part of the contract. Implementation can refactor freely without touching this MODULE.md.

**Invariants**

- **Every adapter returns `list[CanonicalUeCapability]`** — one record per `UE Capability Information` message in the input; empty list if none found. No `None`, no single-record return.
- **Adapters consume schema types; never mutate them.** Pydantic models are constructed via `Model(...)`; field assignments after construction are not used.
- **Pydantic `ValidationError` at the canonical-output boundary** is caught and wrapped in `QCT-E002` / `SHN-E002` / `ELT-E002` (via `[D-011]`'s `{validation_failure}` enum bucketing — `unknown_field` / `missing_required` / `type_mismatch` / `value_out_of_range`). Free-text validation error messages never propagate out of the adapter.
- **Adapters emit prefixed error codes via `ucap.diagnostics`** for any cross-boundary failure path: `QCT-E001` (parse fail), `QCT-E002` (canonical validation fail), `QCT-W001` (unmapped top-level field). Shannon and ELT have analogous codes (`SHN-E001`, `ELT-E001`); their stubs already cover the "not implemented" case.
- **No raw log content in diagnostic / report output.** Adapter contributions to RPT / MET / QC records are counts, timings, bounded-enum tokens, and registered error codes only — never line excerpts, never file paths, never device identifiers. Anchors `NFR-4`. Defense-in-depth via `Redactor` in `[D-012]`.
- **Trailing `Message dump (Hex)` blocks are stripped** before tree-building so they don't pollute the parsed structure (QCAT-specific quirk; QCT adapter only).
- **Stub adapters under `--diagnostic` mode emit `FAIL` reports** (`[D-010]` B6) rather than raising `NotImplementedError` — preserves the chat-mediated debugging contract across the vendor matrix.

**Key choices**

- `[D-003]` — per-vendor file pattern: one `.py` per vendor under `src/ucap/adapters/`, sharing `CanonicalUeCapability` but no parsing infrastructure. CLI dispatches by `--vendor`.
- `[D-004]` — indent-driven tree parser for QCAT, not a grammar-aware ASN.1 parser. Robust to QCAT's two indent styles, SEQUENCE-OF type-marker collapse, NR colon-spacing variant. Release-version handling is a mapper concern, not a grammar concern.
- `[D-009]`–`[D-013]` — chat-mediated debugging surface (error codes, reports, diagnostics module, redaction, output discipline). Each adapter participates by emitting prefixed errors and contributing counts/timings to compact reports.

**Non-goals**

- **Not a hex-dump decoder.** Adapters strip the trailing hex dump from QCAT output and ignore similar trailers in other vendors; they parse the structured text portion only.
- **Not a real-time tap.** ucap is a batch CLI over file inputs; adapters operate on complete log exports, not streaming tail-follows.
- **Not the implementations for `audit` / `diff` / `query`.** Those will live in their own modules (`src/ucap/audit/`, etc.) and consume `CanonicalUeCapability` records produced here.
- **Not a per-band detail parser.** `NrBand.scsSupported` ships empty (`FR-17` deferred); `mimo-ParametersPerBand` subtree is not parsed. v1 focus is band combinations, not per-band fine detail.
- **Not vendor-format-version-aware beyond what QCAT exports require.** The mapper handles Rel-10 / Rel-11 / Rel-15 / Rel-16 / Rel-17 field-name variations as they appear in QCAT output; chasing every ASN.1 release on every adapter is out of scope.

<!-- BEGIN:STRUCTURE -->
_Regenerated 2026-05-14 by regen-map. Do not hand-edit._

### `__init__.py`

*(empty — no top-level definitions)*

### `elt.py`

- `parse_elt_log` — function — pub — MediaTek ELT adapter; stub raising `NotImplementedError` pending a sample log.

### `qcat.py`

_File declares `__all__`; that list is authoritative for `pub`. All other top-level names are `internal`._

- `Message` — class — pub — Parsed QCAT message: title, direction, timestamp, line range, root `TreeNode`.
- `TreeNode` — class — pub — Node in the indent-driven parse tree.
- `_ComboFormat` — class — internal — EUTRA combo-format descriptor (Rel-10 inline vs Rel-11 wrapper).
- `_NrPerCcTables` — class — internal — Bundle of per-CC feature-set tables collected once per tree.
- `_ResolvedNrCaps` — class — internal — Per-CC capabilities resolved through the feature-set indirection chain.
- `_append_mrdc_combos` — function — internal — Append MRDC combos from a given source list to the section.
- `_build_tree` — function — internal — Build the indent-driven tree from tokenized lines.
- `_collapse_sequence_of_markers` — function — internal — Collapse SEQUENCE-OF type-marker rows so `[N]` items hang under the field name.
- `_collect_nr_per_cc_tables` — function — internal — Gather NR per-CC tables from anywhere in the tree.
- `_derive_fr` — function — internal — Derive frequency range (FR1 / FR2) from an NR band number.
- `_extract_combo_band_entries` — function — internal — Pull per-CC band entries out of a combo node.
- `_find_first` — function — internal — Find the first descendant node with a given name.
- `_get_bool` — function — internal — Read a boolean child value, defaulting to False.
- `_get_int` — function — internal — Read an integer child value, or None.
- `_list_under` — function — internal — Return the list-element children of a named field.
- `_make_combo_label` — function — internal — Build the human-readable combo label (e.g. `n78A-n41A`).
- `_map_eutra` — function — internal — Map the EUTRA RAT container to an `EutraSection`.
- `_map_eutra_ca_combo` — function — internal — Map a single EUTRA combo node to an `EutraCaCombination`.
- `_map_mrdc` — function — internal — Map the UE-MRDC-Capability container to an `MrdcSection`.
- `_map_mrdc_band_combination` — function — internal — Map a single MRDC combo node to an `MrdcBandCombination`.
- `_map_nr` — function — internal — Map the NR RAT container to an `NrSection`.
- `_map_nr_band_combination` — function — internal — Map a single NR combo node to an `NrBandCombination`.
- `_merge_eutra_bcs` — function — internal — Merge BCS bitmaps from `supportedBandCombinationExt-r10` into combo records.
- `_normalize_power_class` — function — internal — Normalize an NR power-class token to the canonical enum.
- `_parse_binary_string` — function — internal — Parse a BIT STRING node (old wrapper or new inline form) into a list of bits.
- `_parse_bw_class` — function — internal — Parse a CA bandwidth-class token (A–F).
- `_parse_channel_bw` — function — internal — Parse an NR channel-bandwidth node into a canonical string.
- `_parse_message` — function — internal — Parse one UE Capability Information block into a `Message`.
- `_parse_mimo` — function — internal — Parse a MIMO-layers token into an integer.
- `_parse_modulation` — function — internal — Parse a modulation-order token into the canonical enum.
- `_parse_scs` — function — internal — Parse a sub-carrier-spacing token into kHz.
- `_read_band_params_dl` — function — internal — Read DL band-parameter fields for an EUTRA combo entry.
- `_read_band_params_ul` — function — internal — Read UL band-parameter fields for an EUTRA combo entry.
- `_resolve_nr_caps` — function — internal — Resolve the NR feature-set indirection chain for one combo entry.
- `_resolve_per_cc` — function — internal — Resolve per-CC capabilities through the feature-set tables.
- `_split_line` — function — internal — Split a QCAT line into (indent, name, value).
- `_value` — function — internal — Read a node's value, or None.
- `map_message_to_canonical` — function — pub — Map a parsed `Message` to a `CanonicalUeCapability`.
- `parse_qcat_file` — function — pub — Parse a QCAT export file into a list of `Message`s.
- `parse_qcat_text` — function — pub — Yield each UE Capability Information message in the text.

### `shannon.py`

- `parse_shannon_log` — function — pub — Samsung Shannon DM adapter; stub raising `NotImplementedError` pending a sample log.
<!-- END:STRUCTURE -->

**Depends on**
- `src/ucap/schema/MODULE.md` — every adapter consumes `CanonicalUeCapability`, the section types (`EutraSection` / `NrSection` / `MrdcSection`), the combo types, and every Literal type alias for field values.
- `src/ucap/diagnostics/MODULE.md` — each adapter calls `format_code(...)` to raise prefixed errors and (in the future, post-development-phase) emits `RPT` / `QC` records via `ReportWriter`.
- Top-level `ucap` package (`src/ucap/__init__.py`) — `qcat.py` imports `__version__` as `_PARSER_VERSION` to populate `Meta.parserVersion`. Single-symbol leaf reference, not a contract dependency.

**Depended on by**
- `src/ucap/MODULE.md` — `cli.py`'s `_parse_log` dispatches by `--vendor` to `parse_qcat_file` / `parse_shannon_log` / `parse_elt_log` and (for QCAT) `map_message_to_canonical`.
- `tests/test_qcat.py` — exercises `parse_qcat_file` + `map_message_to_canonical` against the 5 vendored fixtures.

**Deferred**
- `FR-15`: Merge LTE extension flags (256QAM-DL / 64QAM-UL / 1024QAM-DL) from `supportedBandCombination-v1090` / `-v10i0` / `-v1430` into combo records.
- `FR-16`: Merge NR extension lists `-v1540` / `-v1590` (power-class extensions, additional BCS) into the canonical NR section.
- `FR-17`: Populate `NrBand.scsSupported` from `mimo-ParametersPerBand`.
- `FR-18`: Refine `supportsSUL` so it's emitted only on NR entries (omit on EUTRA bands; consider `bool | None`).
- `FR-19`: Shannon DM and ELT adapter implementations.

Each carries a revisit trigger in `docs/compact/requirements.md`'s Deferred section; `drift-check` reads these so the gaps surface as `[DEFERRED]` rather than drift.
