<!-- retrofit: skeleton -->
# adapters

**Purpose**
TODO — retrofit skeleton; please fill in. Per-vendor parsers that take a vendor-tool text export and emit a list of `CanonicalUeCapability` records (one per UE Capability Information message in the log). One adapter per vendor: QCAT (Qualcomm, v1 shipped), Shannon DM (Samsung LSI, stub), ELT (MediaTek, stub).

**Public surface**
<!-- Candidates observed in code (curate; don't copy verbatim): -->
<!-- From src/ucap/adapters/qcat.py (__all__ is authoritative): -->
<!-- - class TreeNode  # indent-driven parse tree node -->
<!-- - class Message  # parsed QCAT message (title + tree root) -->
<!-- - def parse_qcat_file(path: str | Path) -> list[Message] -->
<!-- - def parse_qcat_text(text: str) -> Iterator[Message] -->
<!-- - def map_message_to_canonical(...) -> CanonicalUeCapability -->
<!-- From src/ucap/adapters/shannon.py: -->
<!-- - def parse_shannon_log(path: str | Path, *, release: str) -> list[CanonicalUeCapability]  # STUB — raises NotImplementedError -->
<!-- From src/ucap/adapters/elt.py: -->
<!-- - def parse_elt_log(path: str | Path, *, release: str) -> list[CanonicalUeCapability]  # STUB — raises NotImplementedError -->
TODO

**Invariants**
TODO — likely candidates worth committing to:
- Every adapter returns `list[CanonicalUeCapability]` — one record per UE Capability Information message in the input log; empty list if none found.
- Adapters never write to disk and never raise unprefixed `Exception` — failures emit a prefixed error code per Pillar A (`QCT-…`, `SHN-…`, `ELT-…`).
- Adapters never include raw log content in any diagnostic / report output (Pillars A + E).

**Key choices**
TODO — link to DECISIONS entries once architecture phase formalizes them. Candidates: indent-driven tree parser vs ASN.1-aware grammar (chose indent — simpler, robust to non-canonical QCAT output); per-vendor file rather than a plugin loader; hand-rolled SEQUENCE-OF type-marker collapse heuristic.

**Non-goals**
TODO — likely:
- Not a hex-dump decoder — adapters strip trailing `Message dump (Hex)` blocks.
- Not a real-time tap — batch tool over file input only.
- Adapters do not implement the audit / diff / query subcommands (those will live in their own modules).
- Shannon DM and ELT adapters are stubs in v1 — implementations await sample logs.

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
- `_collect_nr_per_cc_tables` — function — internal — Gather NR per-CC tables (DL / UL / DL-per-CC / UL-per-CC) from anywhere in the tree.
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
TODO — link peer MODULE.md files.
- `src/ucap/MODULE.md` (consumes `CanonicalUeCapability` and the Literal type aliases from `schema.py`).
- Future `src/ucap/diagnostics/MODULE.md` (Pillar C) — for `ErrorCode`, `ReportRecord`, `ReportWriter`, `QCTemplate`.

**Depended on by**
TODO — `src/ucap/cli.py` dispatches to the appropriate adapter based on `--vendor`. `tests/test_qcat.py` exercises the QCAT adapter directly.
