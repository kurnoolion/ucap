# Status

**Active phase**: architecture
**Last updated**: 2026-05-14

## Done

- 2026-05-14 — v1 QCAT parsing shipped end-to-end (LTE + NR + MRDC EN-DC, 5 vendored fixtures, 15 pytest tests passing).
- 2026-05-14 — `project-init --retrofit` scaffolded `docs/compact/` (phase prompts, PROJECT.md, STATUS.md, requirements.md, structure-conventions.md, retrofit-snapshot.md, project-init-interview.md).
- 2026-05-14 — Seven reconstructed DECISIONS entries logged: `D-001` Python 3.11+, `D-002` Pydantic v2 + `extra="forbid"`, `D-003` per-vendor adapter pattern, `D-004` indent-driven QCAT parser, `D-005` flat canonical JSON shape, `D-006` subcommand-style CLI, `D-007` `_meta` / `_unmapped` JSON aliases. Each marked `status: reconstructed`; Why / Consequences carry TODOs for the maintainer to fill in.
- 2026-05-14 — `D-008` logged: code partitioning (core / customizations / config) adopted in principle from hilda's `D-001`; structural reorg deferred until a concrete per-deployment artifact arrives. Forward-looking commitment with named reorg triggers; redaction maps stay on-prem under `.ucap/state/`, NOT in `customizations/`.
- 2026-05-14 — `D-009` logged: Pillar A ratified — error-code format `{PREFIX}-{E|W}{NNN}`, three report types (RPT/MET/QC), prefix set QCT/SHN/ELT/DGN/CLI, ReportRecord dataclass shape, pipe-delimited single-line serialization, immutability rules. Anchors FR-10/11, NFR-4, NFR-7. Adapted from hilda's `D-002` at ucap's smaller scale.
- 2026-05-14 — `D-010` logged: Pillar B ratified — `--diagnostic` / `--validate` / `--run-id` CLI flags; replace-don't-duplex toggle semantics; one aggregate report per run (not per message); 20-field RPT shape + 7-field QC shape for QCAT; stub adapters emit `FAIL` reports under diagnostic mode rather than raising `NotImplementedError`. Anchors FR-12/13.
- 2026-05-14 — `D-011` logged: Pillar C ratified — standalone diagnostics module at `src/ucap/diagnostics/` (sub-package; all v1 code in `__init__.py`; refines `D-009` A5). MODULE.md drafted with public surface (`ErrorCode`, `ReportRecord`, `ReportWriter`, `QCTemplate`, registries, accessors), leaf-node invariant (no ucap imports), 11 initial error codes including `QCT-E002`'s `{validation_failure}` bucketing rule, two pre-registered QC templates. Module marked `[DRAFT]` (no code yet — development-phase deliverable).
- 2026-05-14 — `D-012` logged: Pillar D ratified — redaction mapping protocol. Flat JSON map at `.ucap/state/<map>.json` (gitignored, hand-maintained); 6 placeholder categories `<DEV|FW|OP|ID|PATH|SESS>{N}` with stable indices; longest-match-first substitution at `ReportWriter.emit()` over the serialized line (defense-in-depth, not primary defense); `Redactor` class lives inside diagnostics module; `--redact-with <path>` CLI flag; `DGN-E004` added to registry (now 12 codes). Diagnostics MODULE.md updated with `Redactor` + `REDACTION_CATEGORIES` in public surface.
- 2026-05-14 — `D-013` logged: Pillar E ratified — formal line grammar, reserved characters (`|` and `\n` rejected at emit), 30-line per-session cap (target 15), lowercase snake_case field-name convention, timestamp format `YYYY-MM-DDTHH:MM:SSZ`. Emit-boundary order pinned: validate → to_line → redact → buffer. **All five chat-mediated debugging pillars (A–E) now ratified as `D-009`–`D-013`.**
- 2026-05-14 — `D-014` logged + executed: schema split into its own sub-package (`src/ucap/schema/__init__.py`) to resolve the `ucap ↔ adapters` package-level cycle that surfaced during MODULE.md curation. Zero import-statement changes (Python treats `ucap.schema` identically whether file or package). New `src/ucap/schema/MODULE.md` drafted.
- 2026-05-14 — Retrofit MODULE.md skeletons for `src/ucap/` and `src/ucap/adapters/` curated; `<!-- retrofit: skeleton -->` sentinels removed from both. All four module contracts (`ucap`, `ucap.adapters`, `ucap.schema`, `ucap.diagnostics`) now drafted with real Purpose / Public surface / Invariants / Key choices (D-XXX anchors) / Non-goals / Depends on / Depended on by.

## In progress

*(empty)*

## Next

- ~~Fill MODULE.md skeletons module-by-module (remove `<!-- retrofit: skeleton -->` sentinel once each is curated). Two seeded: `src/ucap/MODULE.md`, `src/ucap/adapters/MODULE.md`.~~ ✓ Done 2026-05-14 (both curated; sentinels removed; new `src/ucap/schema/MODULE.md` added via `D-014`).
- ~~Ratify the five limited-LLM-access pillars (A–E from `project-init-interview.md` Topic 5) as DECISIONS entries `D-009` through `D-013`.~~ ✓ Done 2026-05-14.
- ~~Draft `src/ucap/diagnostics/MODULE.md` (or `src/ucap/diagnostics.py` if single-file is the right scale for v1) — Pillar C.~~ ✓ Done 2026-05-14 as part of `D-011`.
- Briefly visit `/switch-phase requirements` to populate `docs/compact/requirements.md` with v1 FR / NFR covering current QCAT behavior + the chat-mediated debugging pillars.
- Run `/drift-check design` once enough MODULE.md skeletons are curated, to surface code capabilities lacking an owning FR / NFR.

## Flags

- **Limited LLM access** — Claude does not have access to actual logs. All testing / debugging uses compact redacted reports per Pillars A–E (`project-init-interview.md` Topic 5). This constraint applies to every phase prompt and to all module designs that emit diagnostic output.
- **Repo uncommitted** — v1 code, fixtures, README, STATUS, and new `docs/compact/` scaffold are all in working tree only. No commits yet.
- **Retrofit skeletons present** — `src/ucap/MODULE.md` and `src/ucap/adapters/MODULE.md` carry `<!-- retrofit: skeleton -->` sentinels; `close-session`'s hard-flag audit is suspended for those files until the sentinel is removed.
