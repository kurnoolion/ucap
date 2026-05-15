# adapters

**Purpose**
Umbrella module for per-vendor parsers that map chipset-vendor modem-log text exports to `CanonicalUeCapability` records — one record per `UE Capability Information` message in the input. Defines cross-adapter conventions (return shape, error-code prefixes, diagnostics conformance, schema dependency). Per-vendor implementation contracts live in each adapter's own MODULE.md (for sub-package adapters per `[D-018]`) or in this MODULE.md's Public surface section (for flat-file adapters).

**Public surface**

The umbrella exports nothing of its own — adapters are consumed by `ucap.cli` via direct import of the per-vendor module's public symbols. Adapter directory contents:

| Adapter | Path | Status | Contract |
|---|---|---|---|
| QCAT (Qualcomm) | `src/ucap/adapters/qcat/` | **Sub-package** per `[D-018]` — two formats (indented tree + ASN.1 value notation with PER decoding) | [src/ucap/adapters/qcat/MODULE.md](qcat/MODULE.md) |
| Shannon DM (Samsung LSI) | `src/ucap/adapters/shannon.py` | Flat-file **stub** — awaiting sample log | This MODULE.md (below) |
| ELT (MediaTek) | `src/ucap/adapters/elt.py` | Flat-file **stub** — awaiting sample log | This MODULE.md (below) |

### Flat-file adapter contracts

`src/ucap/adapters/shannon.py`:

```python
def parse_shannon_log(path: str | Path, *, release: str) -> list[CanonicalUeCapability]
# v1: stub. Raises NotImplementedError with a message naming the sample-log
# artifact needed (Shannon DM right-click "Copy Details" path: LTE RRC → ULDCCH
# → ueCapabilityInformation). Under --diagnostic mode, emits a FAIL report
# with error_code=SHN-E001 instead of raising, per [D-010] B6.
```

`src/ucap/adapters/elt.py`:

```python
def parse_elt_log(path: str | Path, *, release: str) -> list[CanonicalUeCapability]
# v1: stub. Raises NotImplementedError with a message naming the sample-log
# artifact needed (ELT native log view or Wireshark-routed export). Under
# --diagnostic mode, emits a FAIL report with error_code=ELT-E001 instead
# of raising, per [D-010] B6.
```

**Invariants** *(cross-adapter; per-vendor specifics in each adapter's MODULE.md)*

- **Every adapter returns `list[CanonicalUeCapability]`** — one record per `UE Capability Information` message in the input; empty list if none found. No `None`, no single-record return.
- **Adapters consume schema types; never mutate them.** Pydantic models constructed via `Model(...)`; field assignments after construction are not used.
- **Adapters emit prefixed error codes via `ucap.diagnostics`** for every cross-boundary failure path: `QCT-*` for qcat, `SHN-*` for shannon, `ELT-*` for elt.
- **No raw log content in diagnostic / report output.** Adapter contributions to RPT / MET / QC records are counts, timings, bounded-enum tokens, and registered error codes only — never line excerpts, never file paths, never device identifiers. Anchors `NFR-4`. Defense-in-depth via `Redactor` in `[D-012]`.
- **Stub adapters under `--diagnostic` mode emit `FAIL` reports** (`[D-010]` B6) rather than raising `NotImplementedError` — preserves the chat-mediated debugging contract across the vendor matrix.
- **File-vs-sub-package is per-adapter.** Flat-file is the default; promotion to sub-package (per `[D-018]`'s pattern) is justified when internal complexity warrants it.

**Key choices**

- `[D-003]` — per-vendor adapter pattern: one logical adapter per vendor, sharing only `CanonicalUeCapability` (no shared parsing infrastructure). CLI dispatches by `--vendor`.
- `[D-018]` — sub-package promotion: when an adapter's internal complexity grows past a single file's readability budget (e.g., qcat at ~2000 LOC after `[D-015]`), promote to `<vendor>/__init__.py` + internal files. Each sub-package gets its own MODULE.md as the adapter's contract.

**Non-goals**

- **Not a hex-dump decoder.** Adapters strip vendor-specific trailers (e.g., QCAT's `Message dump (Hex)` block) and ignore similar trailers in other vendors; they parse the structured text portion only.
- **Not a real-time tap.** ucap is a batch CLI over file inputs.
- **Not the implementations for `audit` / `diff` / `query`.** Those will live in their own modules and consume `CanonicalUeCapability` records produced by adapters.

<!-- BEGIN:STRUCTURE -->
_Regenerated 2026-05-14 by regen-map. Do not hand-edit._

### `__init__.py`

*(empty — no top-level definitions)*

### `elt.py`

- `parse_elt_log` — function — pub — MediaTek ELT adapter; stub raising `NotImplementedError` pending a sample log.

### `shannon.py`

- `parse_shannon_log` — function — pub — Samsung Shannon DM adapter; stub raising `NotImplementedError` pending a sample log.

*(qcat is its own sub-module per `[D-018]`; see [src/ucap/adapters/qcat/MODULE.md](qcat/MODULE.md) for its Structure.)*
<!-- END:STRUCTURE -->

**Depends on**
- `src/ucap/schema/MODULE.md` — every adapter consumes `CanonicalUeCapability` and the Literal type aliases.
- `src/ucap/diagnostics/MODULE.md` — every adapter raises prefixed errors and (post-`D-015` development) emits compact records.

**Depended on by**
- `src/ucap/MODULE.md` — `cli.py`'s `_parse_log` dispatches by `--vendor` to each adapter's public surface.
- `tests/test_qcat.py` — exercises the qcat adapter.

**Deferred**
- `FR-19` — Shannon DM and ELT adapter implementations. Stubs await sample log snippets to ground their text format. (qcat-specific deferred items have migrated to `src/ucap/adapters/qcat/MODULE.md` per `[D-018]`.)
