# project-init interview — ucap

Captured 2026-05-14 by `project-init --retrofit`. Source of truth for `--re-init`.

## Retrofit snapshot

See `docs/compact/retrofit-snapshot.md` — detected language Python, 2 candidate modules (`src/ucap/`, `src/ucap/adapters/`), public-surface inventory.

## Topic 1 — What we're building

A toolkit for UE capability analysis. Parses **UE Capability Information** messages from chipset-vendor modem-log exports (QCAT, Shannon DM, ELT) into a canonical flat JSON focused on band combinations (LTE CA, NR CA, EN-DC / NE-DC / NR-DC). Planned subcommands layer compliance audit, snapshot diff, and ad-hoc query on top of the canonical view.

**Core problem.** Vendor log dumps are noisy and inconsistently formatted; cross-firmware / cross-UE / cross-vendor comparison today is hand-decoded and error-prone. ucap canonicalizes the parsed view so audit / diff / query are mechanical against a single schema.

## Topic 2 — How we're building

- Language: **Python 3.11+**.
- Schema: **Pydantic v2** (`extra="forbid"`, JSON aliases for `_meta` / `_unmapped`).
- CLI: `argparse`, exposed as the `ucap` console script via `pyproject.toml`'s `[project.scripts]`.
- Build: **hatchling** (`pyproject.toml`).
- Tests: **pytest** + `pytest-cov`.
- Layout: single repo, hand-rolled adapter per vendor under `src/ucap/adapters/`.
- v1 has no web UI, no service, no persistent storage.

**Module convention (Python).** Each directory containing `__init__.py` under the top-level package dir (`src/ucap/`) is a candidate module. MODULE.md lives at `src/ucap/<module>/MODULE.md` (or `src/ucap/MODULE.md` for the package root).

**Visibility mapping.** Non-underscore top-level names are public; leading underscore = internal. When a file declares `__all__`, that list is the authoritative public surface for the file.

## Topic 3 — Stakeholder map & contribution surfaces

Solo project. Single row in Contributors:

| Stakeholder | Contributes | Interface | Feedback loop |
|---|---|---|---|
| kurnoolion | Code, design, requirements, fixtures, telecom-domain validation | Direct git, CLI | Commit to repo |

No TPMs, QA, external domain validators, or non-dev end users in scope for v1. Future audit / diff / query subcommands stay CLI-only unless that changes.

**Open question (flagged for PROJECT.md):** if `audit` ever consumes a compliance sheet authored by non-devs, that becomes a new contribution surface (spreadsheet → ingestion) and is new architecture work — not a v1 commitment.

## Topic 4 — Domain constraints

- Domain: 3GPP TS 36.331 (`UE-EUTRA-Capability`), TS 38.331 (`UE-NR-Capability`, `UE-MRDC-Capability`); grammar releases Rel-15 through Rel-18, selectable per log.
- Not a regulated runtime; not real-time; no scale pressure (single-log batch tool).
- Data sensitivity: vendor logs may carry proprietary device / firmware / operator info — see Topic 5. No PII expected.
- **Dominant constraint:** correctness against the 3GPP grammar across releases, plus robustness to small vendor-tool formatting drift.

## Topic 5 — LLM access model (LIMITED ACCESS)

**Claude does NOT have access to actual logs.** Logs are proprietary and stay on-prem. Claude works with source code, vendored / public fixtures, and **compact redacted reports** the user pastes from local runs.

This is a hard constraint on every phase prompt. The "Limited LLM access" branch of the customizer applies — phase prompts must include diagnostic-CLI, structural-fingerprint, fixed-field QC, and contribution-file patterns.

### Pillars (imported from `~/work/hilda`, adapted to ucap's solo-Python-CLI scale)

These five pillars are committed by the user during init. Architecture phase formalizes them as the first DECISIONS entries (`D-001` through `D-005`) before drafting new module designs beyond the retrofit skeletons.

**Pillar A — Stable error codes + compact report types** *(adapts hilda `D-002`)*.
Every adapter / CLI command emits prefixed error codes `{MODULE}-{E|W}{NNN}` — e.g. `QCT-E001`, `SHN-W002`. Stable, never renumbered, registered centrally. Cross-boundary artifacts have paired compact formats: **RPT** (run / parse activity), **MET** (timing + counts), **QC** (fixed-field quality check). One record per line, field=value pairs, leading marker line. Fields are int / float / bool / bounded-enum tokens / error codes only — **no free prose, no log content**.

**Pillar B — Per-adapter `--diagnostic` CLI mode** *(adapts hilda `D-005`)*.
`ucap parse <log> --diagnostic` emits a compact `RPT` line: combo counts per RAT, source mix, kind distribution, unmapped-key counts, parse-stage timings — alongside or instead of the full canonical JSON. `--validate` emits a `QC` line: schema-valid / unknown-field-count / index-out-of-range-count / Y or N flags per known invariant. Output is safe to paste into chat for debugging without sharing the log.

**Pillar C — Standalone diagnostics module** *(adapts hilda `D-017`)*.
`src/ucap/diagnostics/` as a leaf-node module: `error_codes.py` (prefix registry + `ErrorCode` dataclass), `report.py` (`ReportRecord`, `ReportWriter`), `qc.py` (`QCTemplate` with `int / float / bool / enum` fields only — no free text by construction). Every other module imports from here; this imports nothing else from ucap.

> Open detail (decide during architecture phase): single-file `src/ucap/diagnostics.py` vs. sub-package `src/ucap/diagnostics/{error_codes,report,qc}.py`. For 3 adapters, single-file may be the right scale initially.

**Pillar D — Redaction mapping protocol** *(adapts hilda `.clinerules/02-content-safety.md` + `mapping.md`)*.
On-prem mapping file (gitignored, project-local under `.ucap/state/` or user-level under `~/.config/ucap/`): JSON map of real → placeholder strings. Placeholder format: angle-bracketed, category-prefixed, stable index. Categories for ucap:

| Category | Pattern | Example |
|---|---|---|
| Device model / SKU | `<DEV{N}>` | internal codename → `<DEV0>` |
| Firmware / build ID | `<FW{N}>` | `S908UXXU3CWA1` → `<FW0>` |
| Operator / carrier | `<OP{N}>` | operator-internal name → `<OP0>` |
| IMEI / IMSI / serial | `<ID{N}>` | full digit string → `<ID0>` |
| Log file path | `<PATH{N}>` | `/customer/site/dump.txt` → `<PATH0>` |
| Session / capture ID | `<SESS{N}>` | UUID-style trace ID → `<SESS0>` |

Forward (real → placeholder) before emitting any report; reverse (placeholder → real) when acting on Claude's response. Longest-match-first ordering so multi-word strings match before substrings. Architecture phase decides path placement and CLI flag (`--redact-with <map.json>`).

**Pillar E — Output discipline rules** *(adapts hilda `.clinerules/03-output-discipline.md`)*.
Max 30 lines per report (target 15). Tabular, one observation per line. Leading marker line: `RPT|QCT|run-<id>|<ISO-8601-UTC>|...`. `field=value` pairs separated by `|`. No prose conclusions in reports — Claude interprets. Error codes only for errors; never raw exception text or stack traces in compact output.

## Topic 6 — Pain points / what AI should catch

- Vendor log formats are loosely specified; small format shifts (QCAT's two indent styles, hex-dump trailer, NR colon-spacing variant) silently break parsing.
- 3GPP ASN.1 release drift — fields rename or move (`-r10` → `-r11` → `-v1090` → `-v10i0` → `-v1430`); easy to merge the wrong extension list into the wrong combo source.
- Off-by-one between 0-indexed and 1-indexed feature-set references; "0 = absent" sentinel.
- Pure-NR vs MRDC RAT container confusion — separate `ue-MRDC-Capability` container, separate `featureSetCombinations` table, but reuses NR per-CC tables.
- Pydantic schema drift — adding a field without `extra="forbid"` discipline lets garbage in.

**What AI should catch:** parser regressions against the 5 vendored fixtures; combo counts changing unexpectedly; new fields emitted that aren't declared in `schema.py`; indexing off-by-one; silent loss of MRDC Rel-16 sources (`NEDC-Only-r16`, `NRDC-r16`).

## Topic 7 — Artifact preferences

- Markdown for all docs (README, STATUS, decisions, MODULE.md).
- Pytest as the executable spec — "if the test passes against the fixture, the behavior is correct."
- No separate design doc tool.
- ATTRIBUTION.md alongside fixtures for log provenance.

## Team experience level (derived)

**Experienced.** User is a telecom SW engineer with deep 3GPP / modem-log expertise, comfortable invoking COMPACT skills directly. EIP tone in phase prompts uses experienced-team phrasing (terse, "mark uncertainty," "challenge weak premises") rather than newer-team phrasing.
