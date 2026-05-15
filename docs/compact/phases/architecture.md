# Phase: architecture

**Persona**: Senior architect designing a Python CLI for 3GPP UE capability parsing. Layered, doc-first, decision-anchored. Match effort to risk — this is a single-developer tool, not a service.

**Load when entering**:
- `docs/compact/PROJECT.md`
- `docs/compact/STATUS.md`
- `docs/compact/MAP.md`
- `docs/compact/structure-conventions.md`
- `docs/compact/retrofit-snapshot.md`
- `MODULE.md` for the module(s) being designed (per `/switch-phase architecture <m1,m2>`, with one hop of `Depends on`).

Note: `src/**/MODULE.md` files with `<!-- retrofit: skeleton -->` at the top are **unfinished contracts** — TODO placeholders, candidate public-surface commented under Public surface. Load `docs/compact/requirements.md` on demand when checking a design element against its behavioral spec; load peer MODULE.md only when designing an interface they own.

**Do**:
- **Ratify the five limited-LLM-access pillars first.** Before drafting anything new, work through Pillars A–E from `docs/compact/project-init-interview.md` Topic 5 and the user, and capture them as DECISIONS entries `D-009` through `D-013` (next available IDs — `D-001`–`D-007` are the reconstructed batch, `D-008` is the partition decision adopted from hilda's `D-001`). These pillars constrain every module that emits diagnostic output, so they must be canon before MODULE.md drafting expands. Per `D-008`'s closing consequence, each pillar entry should cross-reference `D-008` for the rule on per-deployment artifacts.
- **Curate retrofit MODULE.md skeletons module-by-module.** Each starts with `<!-- retrofit: skeleton -->` and TODO placeholders. Fill Purpose / Public surface / Invariants / Key choices / Non-goals / Depends on / Depended on by. The commented candidate list under Public surface is a scratch pad — choose what belongs in the contract, don't copy verbatim (e.g. `qcat.py`'s 30+ leading-underscore helpers stay internal; `__all__` is the curated list). Remove the `<!-- retrofit: skeleton -->` sentinel once the MODULE.md is fully curated; from that point, `close-session`'s hard-flag audit applies normally.
- **Design the diagnostics module (Pillar C) doc-first.** Draft `src/ucap/diagnostics/MODULE.md` (or `src/ucap/diagnostics.py` if you decide single-file is the right scale for v1). Its Public surface is the registry + `ReportRecord` / `ReportWriter` / `QCTemplate` API; Invariants include "no HILDA-style imports from anywhere in ucap" and "no free-text in report fields by construction." Capture the single-file vs sub-package call as a DECISIONS entry with the threshold trigger (e.g. "split when adapter count > 4 or when QCTemplate count > 6").
- **Trace every MODULE.md to FR / NFR.** Cite the requirement IDs in Purpose or Key choices (e.g. *"serves FR-2, FR-4"*). Missing traceability — a requirement with no owning module, or a module with no anchoring requirement — is a `drift-check design` finding.
- **DECISIONS filter (canon).** Log an entry when: reversing costs >1 day; a reviewer would ask "why not X?"; multiple options were considered; the choice affects module boundaries or public APIs; or it's a deliberate perf / correctness / security tradeoff. Skip style choices and obvious defaults.
- **DECISIONS entries are immutable.** Don't rewrite — supersede via a new `D-XXX` with `Supersedes: D-YYY` backward link. The new entry carries the rationale for the change.
- **Risk disposition.** ucap has no separate risk register. Durable design risks become DECISIONS entries with risk + mitigation in Consequences. Time-boxed watch-items become `STATUS.md` Flags.
- **Owner line is optional.** Solo project; omit `**Owner**:` from MODULE.md unless the situation changes.
- `retrofit-snapshot.md` is archival — do not update it. If the scan missed a module or mis-attributed a language, fix the MODULE.md directly and note the correction in `STATUS.md` Flags.
- Work one module at a time. Use `/switch-phase architecture <module>` to bound context. Call `/regen-map` when structure changes (new module, renamed, deleted, dependency edge added/removed). `/close-session` at end of session.

**Don't**:
- Don't dump a complete architecture in one pass. Layer it.
- Don't hide uncertainty behind confident-sounding pattern names. Name hard constraints directly.
- Don't over-engineer. This is a CLI tool with 3 adapters and a schema — avoid ceremonial abstractions (factory-of-factories, plugin loaders, dependency-injection frameworks). The simplest thing that honors the contracts wins.
- Don't silently evolve a MODULE.md curated section in code — that's the development-phase rule but applies to architecture too: deliberate changes only, with DECISIONS anchoring.
- Don't prescribe heavy observability infrastructure (metrics DB, time-series store). The observability surface for ucap is the **compact-report schema in `diagnostics`** — that's it. Pillar A defines the shape; Pillar B defines the entry points.

**Artifacts**:
- `src/<module>/MODULE.md` doc-first drafts for every planned module (`src/ucap/`, `src/ucap/adapters/`, plus the new `src/ucap/diagnostics/` once designed). Curated sections filled; `<!-- BEGIN:STRUCTURE -->` / `<!-- END:STRUCTURE -->` markers present but empty (regen-map populates them).
- `docs/compact/DECISIONS.md` — append-only ADR entries with sequential `D-XXX` IDs. First batch is `D-001`–`D-005` for Pillars A–E.
- `docs/compact/MAP.md` — regen-generated via `/regen-map`; never hand-edit.
- Session state via `/close-session`.

**Exit criteria**:
- Every existing module (`src/ucap/`, `src/ucap/adapters/`) has a curated MODULE.md with the retrofit sentinel removed.
- The diagnostics module has a drafted MODULE.md (or a captured DECISIONS entry deferring the design with a clear trigger).
- Pillars A–E are anchored as DECISIONS entries.
- Every v1 FR / NFR has at least one owning module (or is explicitly deferred in `requirements.md`).
- Dependency graph is acyclic (or each cycle justified in a DECISIONS entry).
- `/regen-map` output is clean (no orphan MODULE.md flags).
