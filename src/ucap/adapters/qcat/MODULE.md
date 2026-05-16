# qcat (adapter)

**Purpose**
Per-vendor parser for QCAT (Qualcomm Chipset Analyzer Toolkit) text exports of `UE Capability Information` messages. Handles **both** QCAT output formats per `[D-015]` / `[D-018]`: the indented tree format (RRC tree expanded inline) and the ASN.1 value notation format (with per-RAT containers held as PER-encoded `OCTET STRING`s requiring schema-driven decoding). Auto-detects format at dispatch time per `FR-21`. Serves `FR-1`, `FR-2`–`FR-5`, `FR-9`, `FR-20`–`FR-23`, plus the related deferred items `FR-15`..`FR-18`.

**Public surface**

```python
__all__ = [
    "TreeNode",
    "Message",
    "parse_qcat_text",
    "parse_qcat_file",
    "map_message_to_canonical",
]

@dataclass
class TreeNode:
    """Node in the indent-driven parse tree (indented-format adapter)."""
    name: str
    value: str | None
    children: list[TreeNode]
    line_no: int
    def is_list_element(self) -> bool: ...
    def get(self, name: str) -> TreeNode | None: ...
    def find_all(self, name: str) -> list[TreeNode]: ...
    def list_items(self) -> list[TreeNode]: ...

@dataclass
class Message:
    """One parsed `UE Capability Information` message: title + direction +
    timestamp + line range + root TreeNode.
    """
    title: str
    direction: str | None
    timestamp: str | None
    start_line: int
    end_line: int
    root: TreeNode

def parse_qcat_file(path: str | Path) -> list[Message]: ...
def parse_qcat_text(text: str) -> Iterator[Message]: ...
def map_message_to_canonical(
    msg: Message, *, vendor: Vendor, release: Release, source_file: str,
) -> CanonicalUeCapability: ...
```

The `TreeNode` and `Message` types are conceptually tied to the indented-format adapter — for ASN.1 inputs, the post-L1 representation is a dict (not a `TreeNode`), but `map_message_to_canonical` is the unified canonical-output contract regardless of source format. Implementation detail: for ASN.1 inputs, the dispatcher constructs a `Message`-shaped wrapper whose `root` field captures the L2-decoded structure suitable for `map_message_to_canonical`.

**Invariants**

- **Returns `list[CanonicalUeCapability]`** — one record per `UE Capability Information` message in the input; empty list if none found. No `None`, no single-record return shape. Applies to both formats.
- **Format auto-detected** per `FR-21` — the dispatcher in `__init__.py` reads the first ~50 lines of input and routes:
  - Presence of `message c1 : ueCapabilityInformation` (or `message c1: ueCapabilityInformation`) → ASN.1 adapter path (`_asn1.py`).
  - Otherwise, with `UE Capability Information (...)` title present → indented tree adapter path (`_indented.py`).
- **Indented format invariants**:
  - Trailing `Message dump (Hex)` blocks are stripped before tree-building.
  - BIT STRING values parse from both QCAT styles: old `Binary string (Bin) : <bits>` wrapper and new inline `field : <bits>` form (`FR-9`).
  - SEQUENCE-OF type-marker lines (e.g., `SupportedBandListEUTRA :` between a field and its `[N]` list elements) are collapsed so list items hang directly under the field.
- **ASN.1 value-notation format invariants** (`D-015` + `D-018`):
  - Parser entry point is the `message c1 : ueCapabilityInformation : { ... }` block. The outer `value UL-DCCH-Message ::= { ... }` envelope is intentionally skipped.
  - End-of-message detected by brace matching from the opening `{` of the entry block. No hex-dump or footer expected after the closing brace.
  - No `-- comment` syntax is expected in the format; tokenizer doesn't handle comments.
  - Per-RAT `ue-CapabilityRAT-Container` `OCTET STRING`s are PER-decoded against the appropriate 3GPP RRC schema (TS 36.331 for `rat-Type eutra`; TS 38.331 for `rat-Type nr` / `eutra-nr`) using `pycrate`'s precompiled schemas — `pycrate_asn1dir.RRCLTE.EUTRA_RRC_Definitions.UE_EUTRA_Capability`, `pycrate_asn1dir.RRCNR.NR_RRC_Definitions.UE_NR_Capability`, and `.UE_MRDC_Capability` (per `[D-019]`). The result is a Python dict consumed by the L3 mapper.
- **Adapters consume schema types; never mutate them.** Pydantic models constructed via `Model(...)`; no post-construction field assignment.
- **Pydantic `ValidationError` at the canonical-output boundary** is caught and wrapped in `QCT-E002` per `[D-011]`'s `{validation_failure}` enum bucketing — extended with `per_decode_failed` for ASN.1-path PER decode failures (`D-015`). Free-text validation error messages never propagate out of the adapter.
- **Prefixed error codes via `ucap.diagnostics`** for cross-boundary failure paths: `QCT-E001` (parse fail), `QCT-E002` (canonical validation fail), `QCT-W001` (unmapped top-level field). Plus, post-`D-015` development: `QCT-E003` (ASN.1 syntax error in outer parser), `QCT-E004` (PER decode failure).
- **No raw log content in diagnostic / report output.** Adapter contributions to RPT / MET / QC records are counts, timings, bounded-enum tokens, and registered error codes only — never line excerpts, never file paths, never device identifiers. Anchors `NFR-4`. Defense-in-depth via `Redactor` in `[D-012]`.

**Key choices**

- `[D-003]` — per-vendor adapter pattern: one logical adapter per vendor (`qcat`, `shannon`, `elt`). File-vs-sub-package is per-adapter; qcat is a sub-package per `[D-018]`.
- `[D-004]` — indent-driven tree parser for the indented format (not a grammar-aware ASN.1 parser). Robust to QCAT's two indent styles, SEQUENCE-OF type-marker collapse, NR colon-spacing variant.
- `[D-015]` — v1 scope expansion to handle the ASN.1 value notation format with PER-decoded inner per-RAT containers. *(Partially superseded by `[D-019]` — decoder choice; scope remains.)*
- ~~`[D-016]` — schema sourcing (OpenAirInterface primary, open5gs secondary, direct 3GPP TS extraction fallback) for the bundled `.asn` files this adapter consumes during PER decoding.~~ *(Entirely superseded by `[D-019]` — pycrate provides schemas; no ucap-internal bundling. D-016 retained as historical record only.)*
- `[D-019]` — pivot decoder from `asn1tools` to `pycrate`; schemas come from pycrate as a runtime PyPI dependency; eliminates the `src/ucap/schemas/<release>/` bundling layer entirely.
- `[D-017]` — paired test fixtures (`tests/fixtures/qcat/asn1/<name>_ASN1.txt`) for NFR-9 round-trip verification.
- `[D-018]` — sub-package promotion. Dispatcher in `__init__.py`; `_indented.py` + `_asn1.py` (post-development) split.
- `[D-009]`–`[D-013]` — chat-mediated debugging surface (error codes, reports, diagnostics module, redaction, output discipline). Adapter participates by emitting prefixed errors and contributing counts/timings to compact reports.

**Non-goals**

- **Not a hex-dump decoder for the trailing block.** Adapters strip `Message dump (Hex)` trailers from the indented format and don't process them.
- **Not a real-time tap.** ucap is a batch CLI over file inputs; this adapter operates on complete log exports.
- **Not the implementations for `audit` / `diff` / `query`.** Those will live in their own modules and consume `CanonicalUeCapability` records produced here.
- **Not a per-band detail parser.** `NrBand.scsSupported` ships empty in v1 (`FR-17` deferred); `mimo-ParametersPerBand` subtree is not parsed.
- **Not vendor-format-version-aware beyond what QCAT exports require.** The mapper handles Rel-10 / Rel-11 / Rel-15..Rel-18 field-name variations as they appear in QCAT output; chasing every ASN.1 release variant exhaustively is out of scope.

<!-- BEGIN:STRUCTURE -->
_Regenerated 2026-05-14 by regen-map. Do not hand-edit._

### `__init__.py`

_Dispatcher + public-API re-exports. The canonical contract is the Public surface section above; `__all__` here is authoritative for module-level imports._

- `Message` — class — pub — Re-exported from `_indented`.
- `TreeNode` — class — pub — Re-exported from `_indented`.
- `map_message_to_canonical` — function — pub — Re-exported from `_indented`.
- `parse_qcat_file` — function — pub — Re-exported from `_indented`.
- `parse_qcat_text` — function — pub — Re-exported from `_indented`.

### `_indented.py`

_File declares `__all__`; that list is what `__init__.py` re-exports and what `_asn1.py` (post-D-015) may import. All other top-level names are internal to this file._

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

*(`_asn1.py` lands during D-015 development; not present in this commit.)*
<!-- END:STRUCTURE -->

**Depends on**
- `src/ucap/schema/MODULE.md` — consumes `CanonicalUeCapability`, all section types, combo types, and every Literal type alias for field values.
- `src/ucap/diagnostics/MODULE.md` — calls `format_code(...)` to raise prefixed errors; emits `RPT` / `QC` records via `ReportWriter` (post-D-015 development for the ASN.1 path).
- *(post-D-015 + D-019)* `pycrate>=0.8.1` PyPI package for PER decoding of inner per-RAT OCTET STRINGs in the ASN.1 format path. pycrate ships TS 36.331 + TS 38.331 v17.4.0 (Rel-17) precompiled schemas in `pycrate_asn1dir/` — no separate in-repo schema bundle. License: LGPL-2.1 (runtime linking from Apache 2.0 ucap is the standard exemption pattern; documented in `NFR-13`).

**Depended on by**
- `src/ucap/adapters/MODULE.md` — umbrella module references this sub-package's contract.
- `src/ucap/MODULE.md` — `cli.py`'s `_parse_log` dispatches by `--vendor qcat` into this sub-package's public API.
- `tests/test_qcat.py` — exercises `parse_qcat_file` + `map_message_to_canonical` against the 5 vendored indented fixtures; post-D-017 paired-fixture commit, will exercise the ASN.1 path too.

**Deferred**
- `FR-15` — Merge LTE extension flags (256QAM-DL / 64QAM-UL / 1024QAM-DL) from `supportedBandCombination-v1090` / `v10i0` / `v1430` into combo records.
- `FR-16` — Merge NR extension lists `-v1540` / `-v1590` (power-class extensions, additional BCS) into the canonical NR section.
- `FR-17` — Populate `NrBand.scsSupported` from `mimo-ParametersPerBand`.
- `FR-18` — Refine `supportsSUL` so it's emitted only on NR entries.

Each carries a revisit trigger in `docs/compact/requirements.md`'s Deferred section; `drift-check` reads these so the gaps surface as `[DEFERRED]` rather than drift.
