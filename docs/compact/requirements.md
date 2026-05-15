# Requirements

Last updated: 2026-05-14. Behavioral specs only — project identity and scope live in `PROJECT.md`.

<!--
How to use this file:

- Each requirement has a stable ID. IDs are never reused and never renumbered.
  - New functional requirement → next `FR-N`.
  - New non-functional requirement → next `NFR-N`.
- One sentence per requirement. Active voice. Testable where possible.
- Removed requirements are struck through in place:
    ~~**FR-3** — <original text>~~ (removed YYYY-MM-DD: <reason>)
- Items agreed to postpone go under `## Deferred` — they are not drift.
- `drift-check` reads this file. Keep it current; it is the authority for what the
  system is supposed to do, which design and implementation are checked against.
-->

## Functional

*FR-1 through FR-9 cover behavior that ships in v1's QCAT parser (already implemented). FR-10 through FR-14 cover the chat-mediated debugging surface (committed in v1 scope, to be built during architecture + development).*

- **FR-1** — ucap accepts a QCAT text export and emits a JSON array of `CanonicalUeCapability` documents, one per UE Capability Information message in the input.
- **FR-2** — For LTE / EUTRA messages, ucap extracts supported bands (with half-duplex flag) and CA combinations — merging `supportedBandCombination-r10` (main) and `supportedBandCombinationAdd-r11` (addR11), with BCS bitmaps from `supportedBandCombinationExt-r10`. Both Rel-10 (`bandList` inline) and Rel-11 (`bandParameterList-r11` wrapper) combo formats are supported.
- **FR-3** — For NR messages, ucap extracts supported NR bands and resolves the feature-set indirection chain (`featureSetCombination` → per-CC `featureSetsDownlink` / `featureSetsUplink` / `featureSetsDownlinkPerCC` / `featureSetsUplinkPerCC`), emitting inline per-CC capabilities (SCS, channel BW, MIMO layers, modulation) on each combo entry.
- **FR-4** — ucap handles MRDC EN-DC combos from the separate `ue-MRDC-Capability` RAT container — using the container's own `featureSetCombinations` table but reusing the NR per-CC tables — including the main EN-DC list plus Rel-16 `NEDC-Only-r16` and `NRDC-r16` sources.
- **FR-5** — For each NR / MRDC band combination, ucap derives a `kind` (`caNR` / `endc` / `nedc` / `nrdc`) from the combo's band-entry mix and `mrdc-Parameters` presence; combo labels are formatted as `<band><BWClass>` joined by `-`, with NR bands prefixed `n` (e.g., `n78A-n41A`, `2C-66A-n41A`).
- **FR-6** — ucap accepts a 3GPP release selector via `--release` (`rel15` / `rel16` / `rel17` / `rel18`; default `rel17`) and applies release-appropriate field-name handling.
- **FR-7** — The CLI is a subcommand dispatcher: `ucap parse <log> --vendor <v> [--release <r>] [-o <path>] [--compact]`. `audit`, `diff`, `query` are reserved as future subcommands.
- **FR-8** — Shannon DM (`--vendor shannon`) and ELT (`--vendor elt`) adapters raise `NotImplementedError` with messages that name the specific sample-log artifact needed to ground each parser.
- **FR-9** — ucap parses BIT STRING values (BCS bitmaps, etc.) from both QCAT styles: the old `Binary string (Bin) : <bits>` wrapper and the new inline `field : <bits>` form.
- **FR-10** — Each cross-boundary failure path in ucap emits a stable prefixed error code of the form `{MODULE}-{E|W}{NNN}` (e.g., `QCT-E001`, `SHN-W002`). Codes are registered centrally; numbers are never renumbered or reused. *(Anchors Pillar A.)*
- **FR-11** — ucap emits compact report records of type **RPT** (run / parse activity), **MET** (timing + counts), or **QC** (fixed-field quality check), conforming to the schema defined by the diagnostics module. Records are one per line. *(Anchors Pillar A.)*
- **FR-12** — ucap supports a diagnostic mode (CLI flag named in architecture phase; current candidate `--diagnostic`) that emits a compact RPT summary of the parse run — combo counts per RAT, source mix, kind distribution, unmapped-key counts, and parse-stage timings — in lieu of or alongside the canonical JSON. *(Anchors Pillar B.)*
- **FR-13** — ucap supports a validation mode (CLI flag candidate `--validate`) that emits a compact QC line: schema-valid flag, unknown-field count, index-out-of-range count, and Y/N flags per known parser invariant. *(Anchors Pillar B.)*
- **FR-14** — ucap supports a redaction mode in which an on-prem JSON mapping of real → placeholder strings is forward-applied to every emitted RPT / MET / QC report before output. Placeholder categories: `<DEV{N}>` (device), `<FW{N}>` (firmware), `<OP{N}>` (operator), `<ID{N}>` (serial / IMEI / IMSI), `<PATH{N}>` (path), `<SESS{N}>` (session ID); indices are stable per real value across runs. *(Anchors Pillar D.)*

## Non-functional

- **NFR-1** — For each vendored fixture under `tests/fixtures/qcat/`, ucap produces EUTRA / NR / MRDC combo counts and source mixes that match the expected values pinned in `tests/test_qcat.py`. Regressions fail CI.
- **NFR-2** — Every canonical Pydantic model declares `extra="forbid"`. Emitting an undeclared field is a validation error, not a silent pass-through. *(Anchors `D-002`.)*
- **NFR-3** — ucap correctly parses fixtures known to contain Rel-15, Rel-16, and Rel-17 capability messages. Rel-18 coverage is opportunistic until a Rel-18 fixture exists.
- **NFR-4** — No RPT / MET / QC record contains any string field that is not (a) a registered error code, (b) a bounded enum token, or (c) a value substituted via the redaction mapping. Free-text strings are rejected at the `ReportWriter` boundary by construction. *(Anchors Pillar A; load-bearing for NFR-7.)*
- **NFR-5** — Each compact report emitted by ucap's diagnostic / validation modes is at most 30 lines, with a leading marker line of the form `RPT|<PREFIX>|<run-id>|<ISO-8601-UTC>|<field>=<value>|...`. No prose conclusions; no stack traces in error fields. *(Anchors Pillar E.)*
- **NFR-6** — The redaction mapping file lives only under `.ucap/state/` (gitignored). ucap has no mechanism to commit redaction-mapping content to any in-repo location.
- **NFR-7** — RPT / MET / QC output from any ucap CLI invocation, when paired with the redaction mapping if used, is safe to paste into a chat conversation with Claude without leaking proprietary log content. NFR-4 + NFR-6 are the constructive guarantees that produce this property; NFR-7 names it as the load-bearing v1 invariant of the limited-LLM-access model.
- **NFR-8** — The full pytest suite completes in under 30 seconds on a single core. Today trivially met; pinned as a regression budget against future fixture additions.

## Deferred

- **FR-15** — Merge LTE extension flags (256QAM-DL, 64QAM-UL, 1024QAM-DL) from `supportedBandCombination-v1090` / `v10i0` / `v1430` into combo records. *(deferred: schema fields exist; merge logic not written — revisit: when an audit / diff workflow requires the flag.)*
- **FR-16** — Merge NR extension lists `supportedBandCombinationList-v1540` / `-v1590` (power-class extensions, additional BCS) into the canonical NR section. *(deferred: not yet needed for v1 — revisit: when extension content is required for audit / diff against compliance sheets.)*
- **FR-17** — Populate `NrBand.scsSupported` by parsing the `mimo-ParametersPerBand` subtree. *(deferred: out of v1 scope — band-combo focus, not per-band detail — revisit: when query / audit needs per-band SCS.)*
- **FR-18** — Refine `supportsSUL` so it is emitted only when truly applicable (omit on EUTRA entries; consider `bool | None` with `None` default). *(deferred: cosmetic noise, not a correctness gap — revisit: when JSON output cleanliness becomes a fix-justified concern.)*
- **FR-19** — Shannon DM and ELT adapter implementations. *(deferred: stubs awaiting sample log snippets — revisit: when a real `ueCapabilityInformation` export from each vendor tool is available.)*
