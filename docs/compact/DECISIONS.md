# Decisions

ADR-style append-only log. IDs are sequential and stable. Decisions are immutable; supersede with a new entry that links back.

---

## D-001: Python 3.11+ as the language floor

**Status**: reconstructed
**Date**: 2026-05-14
**Context**: Retrofit backfill — rationale not captured at time of decision. `pyproject.toml` declares `requires-python = ">=3.11"`.
**Decision**: ucap targets Python 3.11 or newer; older versions are unsupported.
**Why**: TODO — fill in from team knowledge (likely candidates: PEP 604 `X | Y` union syntax used throughout `schema.py`, PEP 673 `Self`, structural pattern matching availability, dataclass / typing improvements).
**Consequences**: TODO — fill in from team knowledge. (Observed: pinned ceiling not declared; assumed any 3.11+ is acceptable. Bytecode compatibility, distribution requirements, CI matrix all bound by this choice.)

---

## D-002: Pydantic v2 with `extra="forbid"` as the canonical schema layer

**Status**: reconstructed
**Date**: 2026-05-14
**Context**: Retrofit backfill — rationale not captured at time of decision. `pyproject.toml` requires `pydantic>=2.6`; `src/ucap/schema.py` defines every model with `extra="forbid"` via a shared `_M` base.
**Decision**: Use Pydantic v2 (≥2.6) for all canonical-schema models. Every model rejects unknown fields by construction (`extra="forbid"`). Forward-compatibility for unknown content rides on the explicit `_meta` / `_unmapped` aliases, not on permissive validators.
**Why**: TODO — fill in from team knowledge (candidates: validation strictness as a hard guard against schema drift; JSON aliases for `_`-prefixed fields; runtime validation cost acceptable for batch parsing; v2 performance vs v1).
**Consequences**: Every adapter must map to declared schema fields — emitting an undeclared field is a validation error, not a silent pass-through. Schema additions are an explicit, reviewable event. Downstream consumers can assume strict shape. Alternatives (dataclasses, TypedDict, attrs, Pydantic v1) are not in v1 scope. Alternatives considered: TODO.

---

## D-003: Per-vendor adapter pattern under `src/ucap/adapters/`, one file per vendor

**Status**: reconstructed
**Date**: 2026-05-14
**Context**: Retrofit backfill — rationale not captured at time of decision. `src/ucap/adapters/{qcat,shannon,elt}.py` — one file per vendor; CLI dispatches on `--vendor`.
**Decision**: Each chipset-vendor modem-log tool gets its own adapter module file under `src/ucap/adapters/`. Adapters share the canonical output type (`CanonicalUeCapability`) but do not share parsing infrastructure. The CLI dispatcher selects an adapter by the `--vendor` flag.
**Why**: TODO — fill in from team knowledge (candidates: vendor formats diverge enough that shared parsing primitives would leak; flat file-per-vendor avoids premature abstraction; new vendor = new file, no plugin loader needed).
**Consequences**: Adding a vendor adds one file under `adapters/` plus a CLI dispatch arm. No plugin discovery, no entry-point registration. Cross-vendor refactors must touch each adapter explicitly. Boundaries are clear at the cost of some duplication if multiple vendors share a parse style. Alternatives considered: TODO (single dispatching parser, plugin loader via `importlib.metadata` entry points, ABC hierarchy).

---

## D-004: Indent-driven tree parser for QCAT, not a grammar-aware ASN.1 parser

**Status**: reconstructed
**Date**: 2026-05-14
**Context**: Retrofit backfill — rationale not captured at time of decision. `src/ucap/adapters/qcat.py` builds a `TreeNode` parse tree from QCAT's indented text export using a tokenizer + indent-counting algorithm; mapping to canonical shape walks the tree by node name. There is no embedded ASN.1 grammar.
**Decision**: QCAT exports are parsed as indented text into a generic `TreeNode` tree, then mapped to the canonical schema by name-driven tree walks. The 3GPP ASN.1 grammar is not embedded in the parser.
**Why**: TODO — fill in from team knowledge (candidates: QCAT output is not strict ASN.1 — vendor-specific framing, hex-dump trailers, marker rows; an indent-driven parser is robust to small format drift; embedding the grammar would pin the parser to a release and turn every Rel-NN change into a parser change).
**Consequences**: Parser handles vendor-format quirks (two indent styles, SEQUENCE-OF type-marker collapse, hex-dump trailer strip) at the tree-builder layer; mapping to canonical lives in named per-section helpers (`_map_eutra`, `_map_nr`, `_map_mrdc`). Release-version handling is a mapper concern, not a grammar concern. Trade-off: silent acceptance of structurally-valid but semantically-wrong input — caught only by downstream Pydantic validation or test fixtures. Alternatives considered: TODO (asn1tools / pycrate grammar-driven parsing, hand-rolled recursive-descent on the ASN.1 syntax).

---

## D-005: Flat canonical JSON shape focused on band combinations

**Status**: reconstructed
**Date**: 2026-05-14
**Context**: Retrofit backfill — rationale not captured at time of decision. `src/ucap/schema.py`'s `CanonicalUeCapability` carries `_meta`, `eutra`, `nr`, `mrdc` sections; each section's combos / bands are flat lists with denormalized fields rather than a hierarchical mirror of the ASN.1 tree.
**Decision**: The canonical JSON output is a flat, denormalized view oriented around band combinations and per-band entries. It is **not** a hierarchical mirror of the 3GPP ASN.1 structure. Feature-set indirection chains in the source format are resolved by the adapter; the output carries per-CC details inline on each combo entry.
**Why**: TODO — fill in from team knowledge (candidates: downstream tools — audit, diff, query — work over combos as their primary unit; resolving indirection at parse time means consumers compare directly, no second-pass walking; flat shape is JSON-Pointer-friendly for diff tooling).
**Consequences**: This shape is the public API for every downstream consumer (`ucap audit`, `ucap diff`, `ucap query` once they land). Changing it is a breaking change — handle via Pydantic schema versioning, not silent edits. `_meta` carries provenance (vendor, release, tool version); `_unmapped` is the escape hatch for fields the adapter saw but didn't claim. Alternatives considered: TODO (mirror ASN.1 tree, two-tier model with raw + canonical layers, protobuf shape).

---

## D-006: `ucap` subcommand-style CLI with audit / diff / query slots pre-shaped

**Status**: reconstructed
**Date**: 2026-05-14
**Context**: Retrofit backfill — rationale not captured at time of decision. `src/ucap/cli.py` builds an `argparse` subcommand dispatcher: today only `parse` is wired, but `STATUS.md` notes `audit` / `diff` / `query` are planned subcommands. The console script is registered as `ucap` (not `ucap-parse`).
**Decision**: The CLI is structured as `ucap <subcommand> [options]` with `parse` as the v1 subcommand and `audit` / `diff` / `query` reserved as future subcommands. Single binary, subcommand dispatch.
**Why**: TODO — fill in from team knowledge (candidates: planned scope spans 4 subcommands sharing the canonical schema; one entry point is friendlier than four installable scripts; subcommand shape is familiar to telecom engineers from `iperf`, `kubectl`, `git`).
**Consequences**: Every future subcommand is a new dispatcher arm in `cli.py` and (likely) a new module — `audit`, `diff`, `query` each get their own MODULE.md when designed. Shared CLI infrastructure (vendor / release flag handling, output flags) lives in `cli.py`. Alternatives considered: TODO (one binary per subcommand, plugin-loaded subcommands, `argparse` vs `click` vs `typer`).

---

## D-007: `_meta` / `_unmapped` JSON aliases on every canonical model

**Status**: reconstructed
**Date**: 2026-05-14
**Context**: Retrofit backfill — rationale not captured at time of decision. The shared `_M` base in `src/ucap/schema.py` declares Pydantic field aliases for `_meta` and `_unmapped` so the underscore-prefixed JSON keys round-trip through validation.
**Decision**: Every canonical model carries (a) a `_meta` field for adapter / source provenance (vendor, release, tool version, parse timestamps) and (b) an `_unmapped` field as a structured escape hatch for source-format content the adapter chose not to claim. Both are surfaced as JSON keys with leading underscores via Pydantic field aliases; Python attribute names are unprefixed.
**Why**: TODO — fill in from team knowledge (candidates: `_`-prefixed JSON keys are a clear out-of-band marker that the value is meta vs canonical; forward-compatibility — adapter can preserve unrecognized content without violating `extra="forbid"`; debuggability — adapter source / tool version traveling with the parsed output makes regression triage cheaper).
**Consequences**: Every adapter must populate `_meta` consistently. `_unmapped` is the documented place for "we saw this but didn't model it" — diff / audit / query tools must ignore it or surface it as opaque. Schema additions can pull content out of `_unmapped` into typed fields without breaking downstream JSON. Alternatives considered: TODO (allow `extra` permissively, separate sidecar metadata file, distinct request/response envelope).

---

## D-008: Code partitioning — core / customizations / config (adopted in principle; structural reorg deferred)

**Status**: Active
**Date**: 2026-05-14
**Context**: A sibling project (hilda at `~/work/hilda`) established a three-tier code organization in its own `D-001`: `core/` for platform code shared across deployments, `customizations/` for per-deployment / per-customer artifacts (often code generated on-prem from proprietary inputs by ingestor modules), `config/` for per-deployment configuration. The pattern earns its keep when generated code, per-deployment data, or proprietary on-prem outputs would otherwise pollute the platform layer.

ucap today has none of those triggers: no ingestor modules, no generated code, no per-customer compliance sheets, no per-deployment service config. v1's only per-deployment artifact is the redaction mapping (Pillar D — to be ratified in architecture phase as `D-012`), which is gitignored under `.ucap/state/` — *stronger* isolation than `customizations/` would give. The planned roadmap (`audit`, `diff`, `query`) does suggest future per-deployment artifacts: per-operator or per-customer compliance sheets for `audit`, possibly per-customer device-codename mappings.

**Decision**: Adopt the three-tier rule **in principle**. When the first per-deployment / per-customer / per-operator artifact arrives, it lands under `customizations/<axis>/<id>/` rather than inline in `src/ucap/`. Configuration that varies by deployment (output preset, default vendor / release, audit rule-set selection) lands under `config/`. Until a concrete trigger fires (see below), no directory reorg — `src/ucap/` continues as the implicit platform tier.

**Reorg trigger** — any of these fires the structural move:
1. The first `audit` compliance sheet that's operator- or customer-specific.
2. Device-codename redaction maps move from on-prem `.ucap/state/` into the repo as shared resources (a deliberate change of trust boundary, not an automatic consequence).
3. A non-vendor third axis emerges (per-customer baselines, per-deployment override rules, multi-tenant config, etc.).
4. A contributor finds themselves about to add a per-deployment artifact and has no natural home under `src/ucap/`.

**Why**: Per hilda's `D-001` logic plus the "don't design for hypothetical requirements" rule. Importing the partition *concept* now is cheap and serves as a tripwire — the next time a per-deployment artifact would land, this entry directs it to `customizations/` instead of inline. Reorganizing the directory tree before any customization exists is aspirational churn against an empty plan; deferring keeps the working tree honest. The "free-now / expensive-later" argument that worked for master→main does **not** apply here: master→main is a content-free rename, whereas the core/customizations split bakes in a specific judgment about which tier each future artifact lives in — better to make that judgment when concrete content forces it.

**Consequences**:
- `docs/compact/structure-conventions.md` keeps the current single-tier Python convention; when the reorg trigger fires, it gains per-tier subsections (`### core` / `### customizations` / `### config`).
- `docs/compact/MAP.md` continues listing modules under `src/ucap/`. Reorg trigger fires a new `MAP.md` plus updated MODULE.md paths.
- **The redaction mapping (Pillar D) does NOT become a `customizations/` artifact.** It stays gitignored under `.ucap/state/`. Deliberate split: `customizations/` is for *in-repo shared per-deployment artifacts*; `.ucap/state/` is for *on-prem-only secrets / mappings the dev LLM must never see*.
- **Hilda `D-003`'s public-vs-proprietary adapter split does NOT transfer.** ucap's vendor adapters (QCAT / Shannon DM / ELT) all parse proprietary vendor *output* formats, but the adapter *code* is reverse-engineered text-format handling with no proprietary content of its own — no ingestors, no codegen. All vendor adapters remain in the platform tier (whatever its name) even after the eventual reorg.
- When architecture phase ratifies Pillars A–E (planned as `D-009`..`D-013`), each pillar should cross-reference this entry: any pillar-related artifact that's per-deployment (e.g., a per-operator default QC template baseline, a per-operator compliance rule-set) belongs in the future `customizations/` tier.
- **Naming may shift at trigger time** — hilda's "customer" axis doesn't map cleanly to ucap's domain; the actual tier directory might be `operators/`, `customers/`, `deployments/`, or `tenants/` depending on what arrives first. The DECISIONS entry that fires the reorg will pin the names.

**Alternatives considered**:
- *Reorg now while the repo is tiny.* Rejected — real cost today (import renames, `pyproject.toml` hatch wheel target update, MODULE.md path edits, test invocation changes) against zero current payoff. The "do-it-cheap-now" argument from master→main doesn't transfer: master→main is content-free; this reorg encodes a judgment about future-artifact placement.
- *Skip importing the concept entirely.* Rejected — the `audit` roadmap creates a clear pull toward per-operator artifacts; without this entry, the first such artifact would likely land inline under `src/ucap/audit/`, polluting the platform tier and making a later extraction painful.
- *Import the partition in `structure-conventions.md` only, no DECISIONS entry.* Rejected — `structure-conventions.md` describes how the *current* code is organized; a forward-looking partition rule with named triggers belongs in DECISIONS.

---

## D-009: Pillar A — Stable error codes + compact report types (RPT / MET / QC)

**Status**: Active
**Date**: 2026-05-14
**Context**: ucap's `Topic 5` interview commitment names a chat-mediated debugging surface as v1 scope: Claude has no access to actual logs, so testing / debugging happens via compact redacted reports the user pastes from local runs. Pillar A is the schema layer of that surface — the stable error-code + report-record vocabulary every other pillar (B, C, D, E) builds on. Pattern adapted from hilda's own `D-002` (which has been proving itself in hilda's 18-module scale); ucap inherits the shape, scaled down to its current 5-prefix scope. Anchors `FR-10`, `FR-11`, `NFR-4`, and (jointly with `D-013`) `NFR-7`.

**Decision**:

1. **Error-code format** — `{PREFIX}-{SEVERITY}{NUMBER}`, three-letter `PREFIX`, severity `E` (error) or `W` (warning), three-digit `NUMBER`. Codes are registered in a central `ERROR_CODES` dict (home pinned in `D-011`); once registered, neither the number nor the message template may change. Deprecation adds a `deprecated: True` field; codes are never renumbered, reused, or deleted.

2. **v1 prefix set** — five module prefixes, registered up-front in `PREFIX_REGISTRY`:

   | Prefix | Module |
   |---|---|
   | `QCT` | `src/ucap/adapters/qcat.py` |
   | `SHN` | `src/ucap/adapters/shannon.py` |
   | `ELT` | `src/ucap/adapters/elt.py` |
   | `DGN` | `src/ucap/diagnostics` (registry's own home — Pillar C) |
   | `CLI` | `src/ucap/cli.py` |

   Reserved for future modules (registered when those modules exist): `AUD` (audit), `DIF` (diff), `QRY` (query). `SCH` (schema) is **not** registered — schema-validation errors bubble through the calling module's prefix (e.g. a Pydantic `ValidationError` raised inside the QCAT mapper becomes `QCT-E003 invalid_canonical_output`, not a `SCH-` code).

3. **Severities — `E` + `W` only**. No `I` (info). Info-level events use stdlib `logging`, which is outside the chat-mediated debugging surface — pasteable compact reports are for *anomalies and outcomes*, not chatter.

4. **Three report types** — `RPT` (run / parse activity, what happened, pass/fail, item counts), `MET` (metrics — timing, rates, counts), `QC` (quality check — fixed-field, numbers + Y/N + bounded-enum tokens). No `FIX` (hilda has it for human-correction workflows; ucap has no correction surface in v1 — revisit if `audit`/`diff` ever consumes user corrections).

5. **`ReportRecord` shape**:

   ```python
   @dataclass(frozen=True)
   class ReportRecord:
       report_type: ReportType           # enum {RPT, MET, QC}
       module_prefix: str                # 3-letter, must be in PREFIX_REGISTRY
       run_id: str                       # UUIDv4 default; CLI-overridable via --run-id
       timestamp: datetime               # UTC, ISO-8601 serialized
       fields: dict[str, int | float | bool | str]
   ```

   String values in `fields` are constrained to: (a) a registered error code, or (b) a bounded-enum token registered by a `QCTemplate` for the `(module_prefix, artifact_type)` pair (Pillar C / `D-011`). Free-text strings are rejected at the `ReportWriter` emit boundary — this is the constructive guarantee behind `NFR-4`.

6. **One-line pipe-delimited serialization** — verbatim from hilda's pattern:

   ```
   RPT|QCT|run-3f2a18b9|2026-05-14T22:01:31Z|combos_eutra=260|combos_mrdc=0|kind_endc=0|kind_canr=0|parse_ms=412
   QC|QCT|run-3f2a18b9|2026-05-14T22:01:31Z|schema_valid=true|unknown_field_count=0|off_by_one_count=0|result=OK
   ```

   Round-trippable via `ReportRecord.to_line()` / `ReportRecord.from_line()`. Pipe chosen because it doesn't appear in any QCAT field name, error code, or canonical-enum token — no escaping needed.

**Why**:
- The pattern earns its keep at hilda's scale (18 modules, ~50+ error codes in flight) and the *invariants* — stable codes, fixed-field reports, no free text — are exactly what ucap's Topic 5 access constraint demands. Re-deriving them from scratch would invent the same shape with less battle-testing.
- Three-letter prefixes give enough distinguishing capacity for the v1 + future modules (5 + 3 reserved = 8) without padding (a 4-letter scheme would feel arbitrary at this scale).
- `E + W` only keeps the compact-report surface narrow — every report line is either an outcome or an anomaly worth paste-and-paste-into-chat, not background noise.
- Pipe delimiters tested in hilda; trivial to grep, parse with `str.split('|')`, or eyeball at a glance. Comma-delimited would require quoting; CSV is overkill; JSON-per-line was considered but eats more screen and obscures the field=value pattern that's actually useful to humans.

**Consequences**:
- **`D-011` (Pillar C) inherits the registry's home decision** — single file `src/ucap/diagnostics.py` for v1, holding `PREFIX_REGISTRY`, `ERROR_CODES`, `ReportType`, `ReportRecord`, `ReportWriter`. **Split trigger**: refactor to a sub-package when prefix count exceeds 8 OR when `QCTemplate` count exceeds 6 forces error-code locality (codes for `audit` rules in their own file, etc.). Both are concrete and grep-able.
- **Every adapter and CLI dispatcher emits prefixed error codes** — no bare `raise Exception(...)`. Existing code in `src/ucap/cli.py` (`raise SystemExit(f"unsupported vendor: ...")`) and the Shannon/ELT stubs (`raise NotImplementedError(...)`) become development-phase soft flags to convert to `{PREFIX}-{E|W}{NNN}` raises, anchored by their owning module's prefix.
- **`extra="forbid"` violations from `D-002` map to `QCT-E???` / `SHN-E???` / `ELT-E???` codes** (caller's prefix), not to a schema-specific code. Adapter-mapper code wraps Pydantic `ValidationError` with the appropriate prefixed error code at the canonical-output boundary.
- **`run_id` defaults to UUIDv4**; `ucap parse --run-id <slug>` lets the user supply a stable slug for grouping multi-invocation runs (e.g. running across a directory of fixtures and bundling reports). The CLI parses `--run-id`; the diagnostics module accepts any string.
- **Test contract**: every error code added gets a pytest case that triggers it (or, if not feasible, asserts the registry holds the entry). The `--validate` mode (Pillar B / `D-010`) checks for orphan codes and missing-prefix codes at runtime, surfacing them as `DGN-W001` / `DGN-E002`.
- **Per `D-008`**: no part of Pillar A's machinery is per-deployment — error codes, registry, report shapes all live in the platform tier (`src/ucap/`). If `audit` later carries per-operator error codes (e.g. operator-specific compliance failure modes), those go in `customizations/<axis>/<id>/` with their own prefix and registration call, not inline in the platform registry.
- **Forward link**: `D-010` (Pillar B) uses this `ReportRecord` + `ReportWriter` as its emit target. `D-011` (Pillar C) defines the file/class layout. `D-013` (Pillar E) constrains `ReportWriter`'s emit shape (max 30 lines, leading marker, no prose). `D-012` (Pillar D) wraps the emit boundary with redaction substitution.

**Alternatives considered**:
- *Looser format `{MODULE}_{SEVERITY}{NUMBER}` or `{MODULE}.{SEVERITY}.{NUMBER}`.* Rejected — hyphen is already the de-facto separator in 3GPP error nomenclature (`SEC-FAIL-001` etc.); telecom engineers parse this shape on sight. Underscores already do work in field names; dots already do work as path separators.
- *Allow `I` (info) severity.* Rejected — info events belong in stdlib logging, not the compact-report surface. Letting `I` in would dilute the "every line is worth pasting" property of compact reports.
- *Allow free-text descriptions in `RPT` field values (e.g. `error_msg=could not parse line 42`).* Rejected — defeats the entire point of Pillar A. Free-text leaks; bounded enums don't. The `ReportWriter` enforces this at emit time.
- *Per-module local error-code registries (no central `ERROR_CODES` dict).* Rejected — central registration catches prefix collisions at import time; per-module registration means the collision only surfaces when both modules happen to load together. Hilda learned this the hard way.
- *Use Pydantic models for `ReportRecord` instead of `@dataclass(frozen=True)`.* Rejected for the diagnostics module specifically — `D-011`'s leaf-node invariant says diagnostics imports nothing from ucap, and `ucap.schema` is a ucap import. Frozen dataclass + stdlib `datetime` + stdlib `enum` keeps diagnostics independent of Pydantic.
- *JSON-per-line serialization instead of pipe-delimited.* Rejected — JSON eats more screen real-estate and hides the field=value pattern behind quoting. Pipe-delimited at 12-15 columns fits in a terminal width; the eye finds anomalies faster.

---

## D-010: Pillar B — `--diagnostic` / `--validate` CLI modes

**Status**: Active
**Date**: 2026-05-14
**Context**: Pillar B is the user-facing entry point to `D-009`'s compact-report machinery. Without it, RPT / MET / QC records have no way to leave the process; with it, the user runs `ucap parse <log> --diagnostic` (or `--validate`) and gets a chat-pasteable summary instead of canonical JSON. Anchors `FR-12`, `FR-13`. Depends on `D-009` for the record schema and `D-011` (Pillar C) for the `ReportWriter` implementation.

**Decision**:

1. **CLI flag set**:

   ```
   ucap parse <log> --vendor <v> [--release <r>] [-o <path>] [--compact]
                                 [--diagnostic] [--validate] [--run-id <slug>]
   ```

   `--diagnostic` and `--validate` are independent boolean flags. `--run-id <slug>` overrides the default UUIDv4 `run_id`; useful when the user wants a stable slug across a batch.

2. **Toggle semantics — replace, don't duplex**. `--diagnostic` causes ucap to emit one aggregate `RPT` record instead of the canonical JSON. `--validate` causes ucap to emit one `QC` record instead of the canonical JSON. `--diagnostic --validate` emits the `RPT` followed by the `QC` (in that order), still no JSON. Neither flag emits anything to stderr; both go to stdout, replacing whatever JSON output would have gone there.

3. **Aggregation — one record per run, not per message**. A QCAT log can carry N `UE Capability Information` messages. Reports sum counts across all parsed messages; per-message diagnostic mode is deferred. Single aggregate keeps the pasteable block to one or two lines (combine-mode = two lines), well within Pillar E's 30-line cap.

4. **`RPT` field set for `ucap parse --diagnostic` (QCAT)** — 20 fields, all bounded types:
   - Provenance: `vendor` (enum), `release` (enum), `messages_parsed` (int).
   - Combo counts: `combos_eutra` / `combos_nr` / `combos_mrdc` (int).
   - Source mix: `source_eutra_main`, `source_eutra_addr11`, `source_mrdc_main`, `source_mrdc_nedconly`, `source_mrdc_nrdc` (int).
   - Kind distribution: `kind_endc`, `kind_canr`, `kind_nedc`, `kind_nrdc` (int).
   - Coverage: `unmapped_top_level_count` (int), `hex_dump_stripped` (bool).
   - Timings: `parse_ms_tokenize`, `parse_ms_tree`, `parse_ms_map`, `parse_ms_total` (int).
   - Outcome: `result` (enum `OK` / `WARN` / `FAIL`).

5. **`QC` field set for `ucap parse --validate`** — 7 invariant checks, all bounded:
   - Provenance: `vendor` (enum), `release` (enum).
   - Schema: `schema_valid` (bool — Pydantic round-trip succeeded for every output).
   - Anomalies: `unknown_field_count` (int), `index_out_of_range_count` (int), `off_by_one_count` (int — heuristic).
   - Coverage: `mrdc_rel16_handled` (bool — saw NEDC-Only-r16 or NRDC-r16 sources and produced corresponding combos), `bcs_parsed` (bool — at least one BCS bitmap parsed).
   - Outcome: `result` (enum `OK` / `WARN` / `FAIL`).

   **`result` rollup** (concrete mapping pinned in development phase against test fixtures): `OK` when `schema_valid=true` AND all counts are zero AND all coverage bools are true (or vacuously satisfied — e.g., a log without MRDC content can have `mrdc_rel16_handled=false` without it counting as a WARN); `WARN` when `schema_valid=true` AND at least one count is non-zero OR a coverage bool is false in a non-vacuous case; `FAIL` when `schema_valid=false`.

6. **Stub-adapter behavior under diagnostic mode** — Shannon DM and ELT adapters do **not** raise `NotImplementedError` when invoked under `--diagnostic` or `--validate`. They emit a minimal `RPT` / `QC` with `result=FAIL` and an `error_code` field (e.g. `SHN-E001` for "adapter not implemented"). Maintains compact-report discipline; surfaces the stub state in a chat-pasteable way. The default JSON-output path still raises `NotImplementedError` per `FR-8`.

7. **All output to stdout**. No stderr-vs-stdout split. Compact reports redirect with `>` / pipe normally. Errors that prevent any report emission (file not found, unsupported vendor) still go to stderr as the existing `print(f"error: ...", file=sys.stderr)` pattern — those are CLI-shell-level errors, distinct from compact reports.

**Why**:
- **Flag names** match the FR-12/13 candidates already committed in `requirements.md` and match hilda's vocabulary — keeps cross-project mental model coherent for the user.
- **Replace semantics** are the only choice that preserves chat-paste safety. Duplex output mixes JSON with reports; users paste both into chat or have to surgically extract; the property the limited-LLM-access model depends on starts to leak.
- **Aggregation** matches the chat-paste use case: the user is debugging a *parse run*, not a *single message*. Per-message detail can be added later under a separate flag if a real debugging session demands it.
- **Stub adapters as `FAIL` reports** keep the compact-report surface uniform across vendors. A user running `ucap parse <some-shannon-log> --diagnostic` should get back a report, not a Python traceback — the chat-mediated surface promises that.

**Consequences**:
- `src/ucap/cli.py` adds three flag definitions in `_build_parser` and a control-flow branch in `_cmd_parse` for the diagnostic/validate paths. Implementation lives in development phase; no design surprises.
- The parse-stage timings (`parse_ms_tokenize` / `_tree` / `_map`) require timestamping at three explicit boundaries in `parse_qcat_text` / `_build_tree` / `map_message_to_canonical`. Adapter modules acquire a small timing API from the diagnostics module (Pillar C's `D-011`).
- `mrdc_rel16_handled` and `bcs_parsed` are coverage signals, not correctness signals — they can be `false` on a log that legitimately has neither, so the `result` rollup treats them as "vacuously satisfied" if the input has no MRDC or no BCS content. Heuristic; development phase tunes against fixtures.
- `--run-id` becomes a soft-required convention in scripted pipelines (a script processing many logs sets a stable run-id per log file for grouping). Default UUIDv4 stays for one-off interactive use.
- Per `D-008`: the `--diagnostic` / `--validate` CLI flags live in core (`src/ucap/cli.py`). If a future audit / diff subcommand needs operator-specific QC fields, those fields' enum tokens get registered through the customizations tier; the platform CLI doesn't know operator names.
- **Forward link**: `D-011` (Pillar C) provides the `ReportWriter` that emits the records described here. `D-013` (Pillar E) constrains the emit shape (one-line, no prose). `D-012` (Pillar D) applies redaction substitution to any string field in the emitted records before they reach stdout.

**Alternatives considered**:
- *`--diagnostic=per-message` mode for per-message RPT lines.* Deferred — useful when debugging a specific message in a multi-message log, but adds complexity without a concrete v1 driver. Revisit when a real chat-debug session needs the granularity.
- *Stderr for compact reports, stdout reserved for JSON.* Rejected — splits the user's mental model and complicates `>` redirection. Replace semantics keep one stream of output, one paste.
- *Combined `--report=rpt,qc,json` mode flag instead of independent booleans.* Rejected — boolean combinations are simpler to teach, simpler to grep for in shell history, and the matrix is small (2² = 4 combinations, of which the JSON case is the default).
- *Have stub adapters raise an error code instead of emitting a `FAIL` report.* Rejected — that would force the CLI to catch the error code at the dispatch boundary and synthesize a report anyway; cleaner to push the convention into the adapter itself (`stub adapters under diagnostic mode return a FAIL report, not raise`).

---

## D-011: Pillar C — Standalone diagnostics module (`src/ucap/diagnostics/`)

**Status**: Active
**Date**: 2026-05-14
**Context**: `D-009` codified the schema (error-code format, report-record shape, serialization) and `D-010` codified the CLI entry points; both depend on a physical home that provides the registry, the `ReportWriter`, and the `QCTemplate` machinery. `D-011` is that home. Pattern adapted from hilda's `D-017` (standalone leaf-node diagnostics module) at ucap's smaller scale. Refines `D-009` A5's single-file commitment: the v1 layout is a sub-package whose entire code lives in a single `__init__.py`, not a flat `diagnostics.py` — this preserves the "single file of code" intent while gaining a dedicated MODULE.md slot at `src/ucap/diagnostics/MODULE.md` per the structure-conventions rule. Anchors `FR-10`, `FR-11`, `NFR-4`, `NFR-5`, `NFR-7`.

**Decision**:

1. **Module layout**:

   ```
   src/ucap/diagnostics/
   ├── MODULE.md          # contract (architecture phase)
   └── __init__.py        # all of v1's code in one file
   ```

   The `__init__.py` is broken into named sections (severities → registries → accessors → report types → writer → QC machinery) but stays one physical file. The **split trigger** from `D-009` A5 stands: `__init__.py` is refactored into `error_codes.py` + `report.py` + `qc.py` when prefix count > 8 OR `QCTemplate` count > 6.

2. **Public surface (in `__all__`)**:
   - `ErrorSeverity`, `ErrorCode`
   - `ReportType`, `ReportRecord`, `ReportWriter`
   - `QCField`, `QCTemplate`
   - `get_code`, `format_code`
   - `PREFIX_REGISTRY`, `ERROR_CODES`, `QC_REGISTRY` (read-only intent; Python doesn't enforce)

3. **Leaf-node invariant (hard)** — `src/ucap/diagnostics/__init__.py` imports only stdlib: `dataclasses`, `enum`, `datetime`, `typing`, `sys`, `uuid`, `io`. Any `from ucap.*` import is a cycle and a hard error. Pinned by `tests/test_diagnostics.py::test_no_ucap_imports` (uses `ast` to scan the file at runtime and assert no `ucap` prefix appears in any `ImportFrom` node).

4. **`PREFIX_REGISTRY` pre-populated with v1's five prefixes** (per `D-009` A2):
   ```python
   PREFIX_REGISTRY = {
       "QCT": "qcat",
       "SHN": "shannon",
       "ELT": "elt",
       "DGN": "diagnostics",
       "CLI": "cli",
   }
   ```
   Reserved future prefixes (`AUD`, `DIF`, `QRY`) are added when those modules land.

5. **`ERROR_CODES` initial content (11 codes)** — all registered at module load time so prefix-foreign-key violations and duplicate-prefix collisions surface at import:

   | Code | Severity | Template message |
   |---|---|---|
   | `DGN-E001` | E | Duplicate prefix `{prefix}` registered |
   | `DGN-E002` | E | Unknown error code `{code}` referenced |
   | `DGN-E003` | E | Invalid `QCField` type `{ft}` (allowed: int, float, bool, enum) |
   | `DGN-W001` | W | Module `{module}` has no `QCTemplate` registered |
   | `QCT-E001` | E | Failed to parse QCAT message at line `{line}` |
   | `QCT-E002` | E | Canonical-output validation failed for message at line `{line}`: `{validation_failure}` |
   | `QCT-W001` | W | Unmapped top-level field `{field}` in container `{container}` |
   | `SHN-E001` | E | Shannon DM adapter not implemented — sample log needed |
   | `ELT-E001` | E | ELT adapter not implemented — sample log needed |
   | `CLI-E001` | E | Input file not found: `{path}` |
   | `CLI-E002` | E | Unsupported vendor `{vendor}` (valid: qcat, shannon, elt) |

   **Placeholder enforcement**: `format_code(code, **kwargs)` accepts only registered error codes and known bounded-enum tokens for `str`-typed placeholders. `{validation_failure}` in `QCT-E002` is a bounded enum (`unknown_field` / `missing_required` / `type_mismatch` / `value_out_of_range`) computed at the adapter's canonical-output boundary — Pydantic's free-text `ValidationError.errors()` is **mapped down** to one of these tokens, never passed through. No path lets unbounded `str` reach a compact report.

6. **Initial `QCTemplate` registrations** (two templates, pre-registered at module load):
   - `qcat:parse_diagnostic` — 20-field RPT shape per `D-010` B4.
   - `qcat:parse_validation` — 7-field QC shape per `D-010` B5.

   Future templates follow the `<prefix-lower>:<artifact-type>` key convention.

7. **`ReportWriter` API**:
   ```python
   class ReportWriter:
       def __init__(self, module_prefix: str, run_id: str) -> None: ...
       def emit(self, record: ReportRecord) -> None: ...   # validates via QCTemplate if registered
       def flush(self, dest: TextIO = sys.stdout) -> None: ...
       def __enter__(self) -> "ReportWriter": ...
       def __exit__(self, *exc) -> None: ...                # auto-flushes to sys.stdout
   ```
   Context-manager usage is documented; explicit `flush()` is supported for non-trivial destinations. `emit()` validates the record against the registered `QCTemplate` (if any); validation failures raise `ValueError` immediately — the goal is to catch field-name typos and free-text leakage in development, not to silently emit malformed records.

8. **Test interface** — `tests/test_diagnostics.py` (development-phase deliverable) covers:
   - Leaf-node invariant: AST scan asserts no `ucap` import.
   - Prefix uniqueness: no duplicate values in `PREFIX_REGISTRY`.
   - Foreign-key sanity: every `ERROR_CODES` key's prefix appears in `PREFIX_REGISTRY`.
   - `QCTemplate.validate_record` rejects free-text strings.
   - `ReportRecord.to_line()` ↔ `from_line()` round-trip.
   - Two registered templates load.

   No dedicated `ucap diagnostics` CLI subcommand in v1; can be added later (`ucap diagnostics validate` would emit a `DGN-QC` line with registry health).

**Why**:
- **Sub-package over flat file**: refining `D-009` A5 — the structure-conventions rule expects every module to have a MODULE.md at its directory root; the cost of `mkdir diagnostics && mv code to __init__.py` is trivial compared to folding two contracts into `src/ucap/MODULE.md`. The "single file of code" intent (avoiding fragmentation prematurely) is preserved by keeping all code in `__init__.py`.
- **Leaf-node invariant** keeps the registry available to every consumer without import-cycle risk. Hilda learned this in `D-017`'s rationale: any backwards import from `diagnostics` into the rest of the project would cycle through every module that emits a code.
- **Pre-populated registries at module load** (vs lazy registration in each module's import path) catch collisions and orphan codes at import time — earliest possible failure point. This is the same argument hilda used in `D-002`.
- **`QCT-E002`'s `{validation_failure}` bucketing**: lets ucap pass Pydantic's structured error info into a compact report without leaking the free-text error message that Pydantic produces. The bucket enum is small (4 tokens) and covers the failures that actually matter for debugging; if a fifth bucket is needed later, it gets added as an enum value.

**Consequences**:
- **Adapters (`qcat.py`, `shannon.py`, `elt.py`) and `cli.py` gain a new dependency on `ucap.diagnostics`** for: `get_code` / `format_code` for raising prefixed errors; `ReportWriter` for emitting RPT / QC; `ReportRecord` and `ReportType` for constructing records.
- **MODULE.md skeletons need their `Depends on` sections updated** when curated (in the upcoming `ucap` + `adapters` curation tasks): both add `src/ucap/diagnostics/MODULE.md` as a dependency. The retrofit-skeleton placeholder cycle (`ucap ↔ adapters`) gets resolved during that same curation.
- **MAP.md gets a third module row** and a new node in the Mermaid graph. `regen-map` re-run produces the updated map; the module will be marked `[DRAFT]` until `__init__.py` is implemented in development phase.
- **`tests/test_diagnostics.py` is a development-phase deliverable** that lands alongside `__init__.py` itself. Until then, the diagnostics module is doc-only.
- **The `--diagnostic` / `--validate` CLI modes from `D-010` are unbuildable until this module's `__init__.py` ships** — `ReportWriter`, `ReportType`, `ReportRecord` all live here.
- **Per `D-008`**: the diagnostics module lives in the platform tier. If `audit` later registers operator-specific error codes (e.g. compliance-failure codes for AT&T-specific rules), those get registered through the customizations tier with their own prefix (e.g. `customizations/operators/att/error_codes.py` calling `PREFIX_REGISTRY` extension hooks). The platform registry stays vendor-agnostic.
- **Forward link**: `D-012` (Pillar D) wraps `ReportWriter.emit` with redaction substitution. `D-013` (Pillar E) constrains what `emit` accepts (line shape).

**Alternatives considered**:
- *Flat file `src/ucap/diagnostics.py` per the literal reading of `D-009` A5.* Refined to sub-package — the doc-first MODULE.md slot is more valuable than the file-flatness it costs.
- *Three files from day 1 (`error_codes.py`, `report.py`, `qc.py`).* Deferred — premature fragmentation given the v1 surface (11 codes, 2 templates) fits readably in one file. The split trigger gives a concrete pivot.
- *Pydantic models for `ReportRecord` / `QCTemplate`.* Rejected — would require importing Pydantic in the leaf-node module, which then bleeds into every consumer. Frozen dataclasses + stdlib `enum` keep diagnostics self-contained.
- *Lazy registration (each module calls `register_prefix` / `register_code` at its own import time).* Rejected — defers collision detection past module-load, makes the registry's state implicitly dependent on import order, and obscures the v1 scope from a single grep at `__init__.py`.
- *Pass Pydantic `ValidationError.errors()` content through to compact reports.* Rejected — would leak free-text field names and offending values, defeating `NFR-4`. The bucketing approach loses information but stays inside the bounded-enum contract.

---

## D-012: Pillar D — Redaction mapping protocol

**Status**: Active
**Date**: 2026-05-14
**Context**: ucap's chat-mediated debugging surface (`D-009`/`D-010`/`D-011`) is designed so that compact reports contain only bounded-enum tokens, error codes, and numerics — no proprietary content by construction. Pillar D is defense-in-depth: a forward-substitution layer that runs over every emitted line, catching anything the field-level invariants might miss (a future schema field that accepts a string, a bug that lets free text into a field, an interpolated path that wasn't bounded). Pattern adapted from hilda's `.clinerules/02-content-safety.md` + `mapping.md` playbook. Anchors `FR-14`, `NFR-6` (file location), and (jointly with `D-009`/`D-011`) `NFR-7`. Resolves the PROJECT.md open question about map location.

**Decision**:

1. **Mapping file shape** — flat top-level `mappings` dict, adopted verbatim from hilda:
   ```json
   {
     "version": 1,
     "mappings": {
       "<real-string-1>": "<placeholder-1>",
       "<real-string-2>": "<placeholder-2>"
     }
   }
   ```
   Multi-string disambiguation is handled by longest-match-first ordering at substitution time, not by per-category sub-objects. The map is hand-maintained.

2. **Placeholder category set** — six categories (per `FR-14`):

   | Pattern | Category |
   |---|---|
   | `<DEV{N}>` | device model / SKU / codename |
   | `<FW{N}>` | firmware / build ID |
   | `<OP{N}>` | operator / carrier |
   | `<ID{N}>` | IMEI / IMSI / serial / other identifier |
   | `<PATH{N}>` | log file path |
   | `<SESS{N}>` | session / capture ID |

   `{N}` is a stable non-negative integer; allocated next-free within its category and never reused. Indexing gaps (`<DEV0>`, `<DEV2>` without `<DEV1>`) are operationally tolerated — hand-maintained maps don't enforce monotonicity.

3. **Load-time validation** — `Redactor.from_file(path)` enforces:
   - Top-level keys exactly `version` and `mappings`.
   - `version == 1`.
   - Every value in `mappings` matches `<(DEV|FW|OP|ID|PATH|SESS)\d+>`. Violations raise `DGN-E004 Invalid redaction category in mapping: '{value}'` (new code, see Consequences).
   - No duplicate placeholders (two real strings mapping to the same `<DEV0>` raises a load-time error — propose `DGN-E005 Duplicate placeholder '{placeholder}' in mapping` as a follow-on if needed; not registered in v1 because the case is rare and dataclass equality can surface it implicitly).

4. **Redactor class lives inside `src/ucap/diagnostics/__init__.py`** — alongside `ReportWriter`. Public additions to the diagnostics module's surface:

   ```python
   REDACTION_CATEGORIES: tuple[str, ...] = ("DEV", "FW", "OP", "ID", "PATH", "SESS")

   @dataclass(frozen=True)
   class Redactor:
       mappings: tuple[tuple[str, str], ...]   # (real, placeholder) pairs, sorted longest-first
       def apply(self, text: str) -> str: ...
       @classmethod
       def from_file(cls, path: Path) -> "Redactor": ...
       @classmethod
       def empty(cls) -> "Redactor": ...
   ```

   `ReportWriter.__init__` gains an optional `redactor: Redactor = Redactor.empty()` parameter. Both `Redactor` and `REDACTION_CATEGORIES` are added to `__all__`.

5. **Substitution timing — at `emit()` over the serialized line**. Pipeline inside `ReportWriter.emit(record)`:
   1. Validate the record against `QCTemplate` (raises `ValueError` on failure).
   2. Call `record.to_line()` to produce the pipe-delimited string.
   3. If the configured `redactor` is non-empty, apply: `line = redactor.apply(line)`.
   4. Append redacted line to the writer's internal buffer.

   Substitution is applied to the **serialized line**, not to individual field values. Field-level guarantees from `D-009`/`D-011` mean a well-formed report shouldn't contain anything proprietary, so the redactor is defense-in-depth — the cheapest place to apply it correctly is once per line at the emit boundary.

6. **CLI flag**: `--redact-with <path>` on `ucap parse`. Optional; when omitted, `ReportWriter` uses `Redactor.empty()` and lines pass through unmodified. Path is resolved relative to cwd; absolute paths also accepted. Convention: maps live under `.ucap/state/` (gitignored per `NFR-6` and the project root's `.gitignore`).

7. **Map is read-only from ucap's perspective** — ucap reads the JSON; it never writes. The map is hand-maintained. No auto-suggestion of new entries in v1; no observation-mode that proposes additions. (Hilda's `mapping` playbook actively grows entries during ingestion; ucap's redaction is intentionally passive — the active growth pattern earns its keep at hilda's scale and customer count, not at ucap's solo-developer scope.)

8. **Reverse-apply (placeholder → real) deferred for v1**. The user can grep the JSON map directly to look up a placeholder. A future `ucap diagnostics unredact <text>` subcommand would mechanize it; not v1 scope.

**Why**:
- **Defense-in-depth, not primary defense.** The primary guarantee against proprietary-content leakage is structural — fields are bounded enums + error codes + numerics, enforced at `ReportWriter.emit`-time validation. Redaction is the second layer that catches whatever slips. Putting it at the line-serialization boundary makes the substitution surface trivially auditable (one function, applied once, on the way out).
- **Flat mapping dict over per-category nesting.** Hand-maintained JSON benefits from simplicity. Per-category nesting would force a category lookup before substitution; the longest-match-first sort handles disambiguation cleanly at zero cost. (Hilda made the same call for the same reason.)
- **Redactor lives in `diagnostics`.** Splitting it into a separate `redaction.py` module would force one of: (a) `ReportWriter` importing `Redactor` from elsewhere, complicating the leaf-node invariant; (b) inversion of control where `Redactor` wraps `ReportWriter` from outside — awkward to teach, awkward to test. Co-locating keeps the chat-mediated debugging surface in one module, which `D-011` already committed to.
- **No auto-write to the map.** ucap is a parser; the map's content is a human judgment about what's proprietary. Auto-suggesting entries would risk the map filling with non-proprietary noise (e.g., common Pydantic field names) and erodes the user's mental model of what's redacted vs not. v1 keeps the human in the loop.

**Consequences**:
- **Registry addition (forward-link to `D-011`)**: `DGN-E004 Invalid redaction category in mapping: '{value}'` is added to `ERROR_CODES`. As of this decision, the registry contains 12 codes — `D-011`'s initial 11 plus this one. The `{value}` placeholder accepts the offending string from the JSON map (raw, because the load-time error is itself a hard failure that prevents any compact-report emission; the error surfaces to the user via the CLI's stderr path, not via a `ReportRecord`).
- **`diagnostics/MODULE.md` updated**: `Redactor`, `REDACTION_CATEGORIES`, and the substitution semantics added to Public surface and Invariants. The "no free-text in reports by construction" invariant is augmented with "redaction layer is the defense-in-depth catch."
- **`src/ucap/cli.py` gains the `--redact-with` flag** in `_build_parser` and threads the loaded `Redactor` into the `ReportWriter` constructor at the report-emission site (currently to be added; today's `cli.py` only emits canonical JSON).
- **Test coverage** (development-phase deliverable): `tests/test_diagnostics.py` adds cases for `Redactor.from_file` validation (bad version, bad category, bad shape), `Redactor.apply` correctness (longest-match-first ordering, empty redactor identity, multi-pattern substitution), and `ReportWriter` end-to-end with a redactor (real string in a field gets substituted in the emitted line).
- **`.gitignore`'s `.ucap/` entry** (added at project-init) covers the map file location. No change needed.
- **Per `D-008`**: redaction maps are explicitly **not** a `customizations/` artifact — they stay on-prem under `.ucap/state/` because they contain *real proprietary values* (the dev LLM must never see them). `customizations/` is for *in-repo shared per-deployment content*; `.ucap/state/` is for *on-prem-only secrets / mappings*. Two different trust boundaries.
- **Forward link**: `D-013` (Pillar E) constrains line shape (max length, marker line, field=value form); redaction operates on the line *after* `to_line()` produces it, so the two are composable — `D-013`'s invariants survive substitution as long as placeholders don't introduce `|` characters or newlines (which the `<CATEGORY{N}>` shape doesn't).

**Alternatives considered**:
- *Per-category sub-objects in the map (`{"DEV": {"X": "<DEV0>"}, "FW": {...}}`).* Rejected — hand-maintenance is harder; the user has to know the category upfront when adding a new value. Flat dict + longest-match-first handles it.
- *Apply substitution to individual field values pre-serialization.* Rejected — would require type-aware substitution (don't substitute inside a count field even if it happens to match), more complex test surface, more places to get it wrong. Line-level substitution is the simpler boundary.
- *Auto-write entries to the map when ucap sees a likely-proprietary string in a report.* Rejected for v1 — opens too many "is this proprietary?" judgments to a parser. A future `ucap diagnostics suggest-redactions` could surface candidates the user accepts manually.
- *Reverse-apply at runtime (ucap reads Claude's response, expands placeholders).* Rejected — that workflow isn't a thing ucap supports (no AI interaction at runtime; Claude is purely a development-time partner). The reverse map exists as a hand-lookup resource only.
- *User-level mapping at `~/.config/ucap/`.* Rejected per `NFR-6`'s project-local pin — keeps redaction state co-located with the project it serves, which matters when a developer has multiple ucap-driven projects with different proprietary axes.

---

## D-013: Pillar E — Output discipline rules (line grammar + enforcement)

**Status**: Active
**Date**: 2026-05-14
**Context**: `D-009` named the one-line pipe-delimited serialization and gave examples; `D-011` banned free text in field values via `QCTemplate`; `D-010` pinned the field menus per CLI mode. `D-013` formalizes the line grammar, declares reserved characters, sets the per-session line cap, and pins the field-name convention — turning the implicit shape into an explicit emit-boundary contract. Pattern adapted from hilda's `.clinerules/03-output-discipline.md`. Anchors `NFR-5`, contributes to `NFR-4` and `NFR-7` jointly with `D-011`/`D-012`.

**Decision**:

1. **Formal line grammar**:

   ```
   LINE        := TYPE "|" PREFIX "|" RUN_ID "|" TIMESTAMP ("|" FIELD)*
   TYPE        := "RPT" | "MET" | "QC"
   PREFIX      := <three uppercase ASCII letters; must be in PREFIX_REGISTRY>
   RUN_ID      := <non-empty string; no "|" or "\n">
   TIMESTAMP   := <ISO-8601 UTC, format "YYYY-MM-DDTHH:MM:SSZ"; no microseconds, no offset>
   FIELD       := FIELD_NAME "=" FIELD_VALUE
   FIELD_NAME  := <lowercase snake_case, matches [a-z][a-z0-9_]*>
   FIELD_VALUE := <int> | <float> | "true" | "false" | <error-code> | <bounded-enum-token>
   ```

   `ReportRecord.to_line()` is the canonical formatter; `ReportRecord.from_line()` is the parser. Round-trip is exact.

2. **Timestamp format — `YYYY-MM-DDTHH:MM:SSZ`**, no microseconds, no offset, always literal `Z`. Example: `2026-05-14T22:01:31Z`. Sub-second timing belongs in MET fields (e.g. `parse_ms_total=412`), not in the record timestamp. Eliminates whitespace variation, eliminates timezone ambiguity, keeps the line scannable at fixed column positions.

3. **Reserved characters: `|` and `\n`**. Neither may appear in any field name or any field value. `ReportWriter.emit(record)` validates this and raises `ValueError` on violation — development-phase bug, never reaches stdout. The bounded-type constraints from `D-009`/`D-011` already preclude these characters in practice (numerics, error codes, registered enum tokens are all `|`/`\n`-free); E3 is belt-and-suspenders for future field types.

4. **Per-session line cap — 30 lines hard, 15 target**. A "session" = one `ReportWriter` lifetime (`__init__` → `flush()`). Today a `ucap parse --diagnostic --validate` emits 2 lines; the cap is forward-looking and bounds compound emissions (a future `audit` that emits one RPT per compliance rule must aggregate, not enumerate). Enforced at `flush()`-time: buffer length > 30 raises `ValueError`.

5. **One record = one line**. `to_line()` returns a string without embedded `\n`. Multi-record flushes concatenate with `\n` between records and a single trailing `\n`. Empty flush writes nothing (no spurious blank line).

6. **No prose conclusions — cultural rule, mechanical enforcement**. Reports are data; Claude interprets. Mechanical: `QCTemplate.validate_record` rejects any `str`-typed field value that isn't a registered error code or a bounded-enum token registered for that `(prefix, artifact_type, field)` triple. Interpretive enum tokens like `severity=needs_attention` fail at validation unless `needs_attention` is explicitly registered — forcing the developer to register vocabulary deliberately rather than improvising it inline.

7. **No stack traces, no raw exception text** (reaffirms `D-011`'s QCT-E002 bucketing rule generally). Any `Exception` caught in adapter / CLI code becomes an `error_code=<PREFIX>-E???` field in the compact report. The full traceback goes to stderr (local terminal); the compact report (chat-bound) carries only the bounded error-code identifier.

8. **Field-name convention — lowercase snake_case ASCII**: matches `[a-z][a-z0-9_]*`. Hyphens, uppercase letters, dots, unicode — all forbidden. Trivial to grep, split, parse; consistent with Python identifier convention; no quoting concerns.

9. **Output destination — `sys.stdout`** (reaffirms `D-010` B7). `ReportWriter.flush(dest=...)` accepts override for tests / future use cases (file write, network send); default unchanged.

10. **Per-line length uncapped**. A single line with 25 field=value pairs at ~200 chars is valid. The 30-line cap (E3) prevents *flooding*; per-line length is bounded only by what fits the registered field menu.

**Why**:
- Formal grammar makes the surface auditable — `from_line()` can verify any line claimed to be ucap output round-trips, which is the property tests assert against fixtures.
- Reserved characters give pipe-delimited parsing zero edge cases — `line.split('|')` always recovers the structure correctly.
- The 30-line cap matches hilda's chat-paste use case at a similar resolution. ucap's lines are copied-not-typed (hilda hand-types), so the cap is less urgent for the typing-effort reason but still meaningful for "fit in a chat reply without flooding context."
- The lowercase snake_case rule matches the rest of the Python codebase's conventions — no mental switch between code identifiers and report field names.
- Mechanical enforcement of "no prose" via `QCTemplate` is the same mechanism `D-011` introduced — `D-013` just lifts the rule to module-doc status so it's a documented contract, not an implementation accident.

**Consequences**:
- `ReportRecord.to_line()` / `from_line()` get strict format pins; deviations fail at boundary. Test-fixture-driven; round-trip tests in `tests/test_diagnostics.py` (development-phase deliverable).
- `ReportWriter.emit()` adds three rejection paths: embedded `|`, embedded `\n`, buffer-length-exceeds-30. Each raises `ValueError` with a clear message naming the offense (these are development-phase bugs, not user-facing errors; no error-code registry entry needed since they never reach stdout).
- All current and future field names must conform to lowercase snake_case. The 20 fields named in `D-010` B4 and the 7 in B5 already conform; the rule pins the convention rather than changing it.
- A future audit / diff / query subcommand designing its own RPT/QC fields starts from this grammar — name fields snake_case, use bounded-enum values, register them in `QCTemplate` before emit.
- **Composability with `D-012` redaction**: redaction operates on the serialized line *after* `to_line()` produces it. `Redactor.apply` substitutes `(real → placeholder)` pairs; placeholders match `<(DEV|FW|OP|ID|PATH|SESS)\d+>` per `D-012` and therefore never contain `|` or `\n`. So the line-grammar invariants survive substitution. Order of operations at emit: validate → to_line → redact → buffer.
- **`from_line()` requirement** — `ReportRecord.from_line()` must accept un-redacted lines (placeholders allowed in `str` field values during round-trip tests). Implementation note: relax the bounded-enum-token check in `from_line()` to allow `<CATEGORY\d+>`-shaped placeholders in string positions, since a redacted line is still a valid line.

**Alternatives considered**:
- *Allow `|` in field values via escaping (`field=a\|b`).* Rejected — adds parsing complexity, breaks `line.split('|')` simplicity, and the bounded-type contract makes the case vacuous.
- *Allow microsecond precision in timestamps (`YYYY-MM-DDTHH:MM:SS.ffffffZ`).* Rejected — variable-width columns hurt readability; the use case for microsecond-resolution in compact reports is approximately zero (timing data goes in MET fields with explicit unit suffixes like `_ms`, `_us`).
- *Per-line length cap (e.g. 200 chars).* Rejected — would force splitting wide RPTs across lines, breaking the "one record one line" rule. The 30-line per-session cap is the right level to bound flooding.
- *Allow uppercase / hyphens in field names (`combos-eutra` or `combosEUTRA`).* Rejected — inconsistent with Python conventions and hilda's pattern; adds case-folding worries to grep / parse.
- *Move the "no prose" rule into a separate decision (`D-013-prose`) rather than a clause of `D-013`.* Rejected — it's the same emit-boundary enforcement mechanism (`QCTemplate.validate_record`) and naturally belongs alongside the grammar.

---

## D-014: Schema split into its own sub-package (`src/ucap/schema/`)

**Status**: Active
**Date**: 2026-05-14
**Context**: Curating the retrofit MODULE.md skeletons for `src/ucap/` and `src/ucap/adapters/` surfaced a documentation cycle at the *package-granularity* dependency graph: `ucap → adapters` (because `cli.py`'s `_parse_log` calls into specific adapter functions) and `adapters → ucap` (because every adapter imports types from `ucap.schema`). At the *file-granularity* the chain is acyclic (`cli → adapters → schema`, and `schema` is a leaf), but the package-as-module view collapses `cli.py` and `schema.py` into a single `ucap` node — creating the cycle. The architecture-phase exit criterion requires either an acyclic dependency graph or a DECISIONS-entry justification for each cycle.

**Decision**: Promote `src/ucap/schema.py` to a sub-package `src/ucap/schema/__init__.py` containing the existing schema code unchanged. Add a dedicated `src/ucap/schema/MODULE.md`. The split is mechanical: `mkdir src/ucap/schema && git mv src/ucap/schema.py src/ucap/schema/__init__.py`. No import-statement changes anywhere in the codebase — Python treats `from ucap.schema import X` identically whether `ucap.schema` is a module or package.

After the split, the dependency graph at module-granularity is:

- `src/ucap/schema/` — depends on nothing inside ucap (external: `pydantic>=2.6`). Leaf.
- `src/ucap/diagnostics/` — depends on nothing inside ucap (stdlib only, per `[D-011]`). Leaf.
- `src/ucap/adapters/` — depends on `src/ucap/schema/` (types) and `src/ucap/diagnostics/` (error codes, ReportWriter).
- `src/ucap/` (top-level: `cli.py` + `__init__.py`) — depends on `src/ucap/schema/`, `src/ucap/adapters/`, `src/ucap/diagnostics/`.

Acyclic.

**Why**:
- The reorg costs are negligible — zero behavior change, zero import-statement changes, zero pyproject changes, zero test changes, zero CI changes. The only edits are `git mv` + the new MODULE.md + the (1-line) note in `structure-conventions.md`.
- It earns schema its own MODULE.md contract, consistent with `[D-011]`'s sub-package pattern for `diagnostics`. The canonical types are a load-bearing public-API layer; treating them as a peer module rather than a subfile of the CLI dispatcher makes the contract auditable.
- It eliminates the cycle structurally rather than papering over it with a justified-cycle DECISIONS note. Justifying a cycle is documentation debt that propagates to MAP.md and to every future drift-check pass; this resolves the issue at the source.
- `[D-008]` (the partition decision) deferred the *core / customizations / config* reorg because that move encodes a forward-looking judgment about future-artifact placement against an empty plan. This reorg is different: it's a *structural cleanup that surfaces during architecture-phase curation*, with concrete current value (cycle resolution + contract slot). The do-it-cheap-now argument applies cleanly.

**Consequences**:
- **`src/ucap/schema/MODULE.md` is a new contract**, drafted 2026-05-14 alongside this entry. Its Public surface is the type aliases + Pydantic models that were previously documented as "rolled up into `src/ucap/MODULE.md`". Key choices cite `[D-002]`, `[D-005]`, `[D-007]`, and this `[D-014]`.
- **`src/ucap/MODULE.md`'s Public surface contracts**: now just `__version__` and `main()`. The Pydantic models and type aliases no longer appear there.
- **`docs/compact/structure-conventions.md`'s "Single-file submodules" note updated** — `schema.py` removed from the example list, with a 2026-05-14 note pointing at this entry. `cli.py` remains the only single-file submodule of the top-level `ucap` package.
- **`docs/compact/retrofit-snapshot.md` becomes slightly outdated** in its "Candidate modules" listing (which still says 2 modules under Python). The snapshot is archival per `project-init --retrofit` rules; the correction lives here, not in a snapshot edit.
- **`pyproject.toml`'s hatch wheel target is unchanged** — `packages = ["src/ucap"]` already recursively covers any sub-package, including the new `schema/`.
- **MAP.md regenerated** after the split — module count goes from 2 to 4 (`ucap`, `ucap.adapters`, `ucap.diagnostics`, `ucap.schema`); Mermaid graph becomes acyclic.
- **No Python code in `__init__.py` was modified** during the move. Test fixtures, adapter mappers, CLI dispatcher all still import `from ucap.schema import ...` and resolve identically.
- **Per `[D-008]`**: `schema/` lives in the platform tier. If a future per-operator extension to the canonical schema is ever needed (unlikely — schema is the cross-operator interoperability layer), it would NOT go in `customizations/<id>/schema/` — it would go through schema evolution (new `_unmapped` extraction → typed field via Pydantic schema versioning), keeping the platform schema as the single canonical type.

**Alternatives considered**:
- *Log a justified-cycle DECISIONS entry and leave schema as a single file.* Rejected — the cycle is real (file-level edges chain `cli → adapters → schema` with schema bundled in ucap), and a justification-without-resolution is documentation debt that survives every subsequent drift-check. The split costs nothing and is a clean architectural improvement.
- *Split `cli.py` into its own sub-package too (`src/ucap/cli/__init__.py`).* Rejected — `cli.py` is a single-file dispatcher; making it a sub-package adds zero contract value. Schema is the type-API surface — that's what earns the dedicated MODULE.md.
- *Move schema higher in the tree (e.g. `src/schema/` as a sibling of `src/ucap/`).* Rejected — the canonical schema is part of ucap's identity (`from ucap.schema import CanonicalUeCapability` is the natural import); sibling placement would dilute the package boundary and break the "ucap is one Python package" mental model.
- *Wait until development phase to do the reorg.* Rejected — the architecture-phase task is MODULE.md curation; resolving the cycle as part of that curation is the natural place to do it. Deferring would leave the cycle in MAP.md for the duration of architecture phase and bleed into development.
