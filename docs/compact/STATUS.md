# Status

**Active phase**: architecture
**Last updated**: 2026-05-14

## Done

- 2026-05-14 — v1 QCAT parsing shipped end-to-end (LTE + NR + MRDC EN-DC, 5 vendored fixtures, 15 pytest tests passing).
- 2026-05-14 — `project-init --retrofit` scaffolded `docs/compact/` (phase prompts, PROJECT.md, STATUS.md, requirements.md, structure-conventions.md, retrofit-snapshot.md, project-init-interview.md).
- 2026-05-14 — Seven reconstructed DECISIONS entries logged: `D-001` Python 3.11+, `D-002` Pydantic v2 + `extra="forbid"`, `D-003` per-vendor adapter pattern, `D-004` indent-driven QCAT parser, `D-005` flat canonical JSON shape, `D-006` subcommand-style CLI, `D-007` `_meta` / `_unmapped` JSON aliases. Each marked `status: reconstructed`; Why / Consequences carry TODOs for the maintainer to fill in.
- 2026-05-14 — `D-008` logged: code partitioning (core / customizations / config) adopted in principle from hilda's `D-001`; structural reorg deferred until a concrete per-deployment artifact arrives. Forward-looking commitment with named reorg triggers; redaction maps stay on-prem under `.ucap/state/`, NOT in `customizations/`.

## In progress

*(empty)*

## Next

- Fill MODULE.md skeletons module-by-module (remove `<!-- retrofit: skeleton -->` sentinel once each is curated). Two seeded: `src/ucap/MODULE.md`, `src/ucap/adapters/MODULE.md`.
- Ratify the five limited-LLM-access pillars (A–E from `project-init-interview.md` Topic 5) as DECISIONS entries `D-009` through `D-013` (next available IDs — `D-001`..`D-007` are the reconstructed batch, `D-008` is the partition decision) before drafting new module designs beyond the retrofit skeletons.
- Draft `src/ucap/diagnostics/MODULE.md` (or `src/ucap/diagnostics.py` if single-file is the right scale for v1) — Pillar C.
- Briefly visit `/switch-phase requirements` to populate `docs/compact/requirements.md` with v1 FR / NFR covering current QCAT behavior + the chat-mediated debugging pillars.
- Run `/drift-check design` once enough MODULE.md skeletons are curated, to surface code capabilities lacking an owning FR / NFR.

## Flags

- **Limited LLM access** — Claude does not have access to actual logs. All testing / debugging uses compact redacted reports per Pillars A–E (`project-init-interview.md` Topic 5). This constraint applies to every phase prompt and to all module designs that emit diagnostic output.
- **Repo uncommitted** — v1 code, fixtures, README, STATUS, and new `docs/compact/` scaffold are all in working tree only. No commits yet.
- **Retrofit skeletons present** — `src/ucap/MODULE.md` and `src/ucap/adapters/MODULE.md` carry `<!-- retrofit: skeleton -->` sentinels; `close-session`'s hard-flag audit is suspended for those files until the sentinel is removed.
