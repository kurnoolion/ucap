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
