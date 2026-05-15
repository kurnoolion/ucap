# Project: ucap

*Identity: who / why / scope boundaries. Behavioral specs (FR / NFR) live in `requirements.md`.*

**One-line**: A CLI toolkit that parses UE Capability Information from chipset-vendor modem-log exports into canonical JSON, with planned subcommands for compliance audit, snapshot diff, and ad-hoc query.

**Problem**: UE capability negotiation data emitted by chipset-vendor modem-log tools (QCAT, Shannon DM, ELT) is the authoritative source for *what RF / radio features a device actually supports* — but the exports are noisy, vendor-specific text dumps. Cross-firmware comparison, cross-UE comparison, and audit against compliance / certification sheets today happen by hand-decoding ASN.1-flavored text — slow, error-prone, and tribal-knowledge-heavy. ucap canonicalizes the parsed view into a single Pydantic-validated schema so downstream comparison, compliance audit, and ad-hoc query are mechanical.

**Users**: One developer (kurnoolion) — telecom SW engineer working around 3GPP TS 36.331 / 38.331 UE capability ASN.1. No external users in v1. Future audit / diff / query subcommands remain CLI-only.

**In scope for v1**:
- `ucap parse` for **QCAT** exports — LTE + NR + MRDC EN-DC band combinations, Rel-15 through Rel-18 grammar.
- `ucap parse` accepts **both** QCAT export formats: the indented tree format (FR-2..FR-9) and the ASN.1 value notation form with PER-decoded inner per-RAT containers (FR-20..FR-23 per `D-015`). Format auto-detected; same canonical output for both.
- 3GPP RRC ASN.1 schemas (TS 36.331 + TS 38.331 v17.4.0) provided by `pycrate` (runtime PyPI dependency, LGPL-2.1) per `D-019`. No ucap-internal schema bundle. `--release rel15..rel18` is metadata input; PER decoding uses pycrate's Rel-17 v17.4.0 schemas, which decode Rel-15/16 messages too (additive 3GPP extensions); Rel-18-specific IEs surface as `QCT-E004`.
- Canonical flat JSON output per the Pydantic schema in `src/ucap/schema/`.
- Stub adapters for Shannon DM and ELT raising `NotImplementedError` with clear messages.
- Chat-mediated debugging surface — compact RPT / MET / QC report types, per-adapter `--diagnostic` / `--validate` CLI modes, redaction mapping protocol, output discipline rules (Pillars A–E from Topic 5; ratified as `D-009`..`D-013`).
- Pytest regression suite against the 5 vendored indented fixtures (OnePlus9 LTE/NR, G960W LTE, S22 LTE/NR) plus paired ASN.1 fixtures sourced from the user's QCAT install that produces the proprietary format (per NFR-9; one paired fixture sufficient for v1 round-trip verification).

**Out of scope (explicit non-goals)**:
- `ucap audit`, `ucap diff`, `ucap query` subcommands — planned, not v1.
- Shannon DM and ELT adapter implementations — awaiting sample logs.
- Web UI, persistent storage, service deployment.
- Per-band `mimo-ParametersPerBand` parsing, `scsSupported`, NR `-v1540` / `-v1590` extension lists, LTE `-v1090` / `-v10i0` / `-v1430` extension merges (deferred — see `requirements.md`).
- Non-Python contributors and any non-CLI contribution surface.

**Success criteria**: v1 is done when `ucap parse` round-trips the 5 vendored QCAT fixtures through canonical JSON + Pydantic validation, the chat-mediated debugging pillars are anchored in DECISIONS and reflected in working code (compact reports, `--diagnostic` mode, redaction tooling, output-discipline enforcement at the `ReportWriter` boundary), and a fresh session can be debugged from a pasted RPT line without the log itself ever leaving the developer's machine.

**Constraints**:
- **Limited LLM access.** Claude does not have access to actual logs. Logs are proprietary and stay on-prem. Claude works with source code, vendored / public fixtures, and compact redacted reports the user pastes from local runs. This drives every phase prompt and forces the chat-mediated debugging pillars (A–E) into v1 scope.
- **3GPP grammar fidelity.** Behavior is judged against TS 36.331 / 38.331 across Rel-15 through Rel-18. Grammar drift across releases is a known source of bugs (see `requirements.md` Pain points). Defer fields rather than guess at them.
- **No PII expected** in logs, but vendor / device / firmware / operator identifiers are proprietary — redaction protocol (Pillar D) is the contract for any shared output.

**Open questions** *(maintained during Requirements phase; removed when resolved or deferred)*:
- ~~Single-file `src/ucap/diagnostics.py` vs sub-package `src/ucap/diagnostics/` for the diagnostics module — pick during architecture.~~ ✓ Resolved by `D-009` A5 + `D-011`: sub-package with single `__init__.py`; split trigger at prefix-count > 8 or QCTemplate-count > 6.
- ~~Redaction mapping file location — project-local `.ucap/state/` vs user-level `~/.config/ucap/`.~~ ✓ Resolved by `NFR-6` + `D-012`: project-local `.ucap/state/`, gitignored.
- If / when `audit` consumes a compliance sheet authored by non-devs, that's a new contribution surface (spreadsheet → ingestion) needing architecture; not a v1 commitment.
- ~~**3GPP `.asn` schema sourcing** *(architecture-phase blocker per `D-015`)* — where to obtain canonical `.asn` files for TS 36.331 + TS 38.331 Rel-15..Rel-18 for bundling under `src/ucap/schemas/<release>/`.~~ ✓ Resolved 2026-05-14 by `D-019`: pycrate provides schemas as a runtime dependency; no ucap-internal bundling. The original sourcing strategy (OAI / open5gs / 3GPP direct, per `D-016`) was made moot when investigation revealed `asn1tools` cannot compile 3GPP RRC parameterized types.
- **Paired test fixtures for NFR-9** *(test-setup item per `D-015`)* — at least one `UE Capability Information` message exported in both indented tree format and ASN.1 value notation from the same source log, for round-trip equivalence verification. Plan: user re-exports one of the existing 5 fixtures' proprietary source binary in ASN.1 form using a QCAT install that produces that format, vetted per Pillar D and committed under `tests/fixtures/qcat/asn1/`.

**Contributors**:

| Stakeholder / Role | Contributes | Interface | Feedback loop |
|---|---|---|---|
| kurnoolion (sole maintainer) | Code, design, requirements, fixtures, telecom-domain validation, compact-report interpretation | Direct git, `ucap` CLI | Commit to repo; chat-mediated debugging via pasted compact reports |

*Solo project; no unowned validation channel, no separate eval-data path needed for v1. If the contribution map changes (audit ingestion, external compliance reviewers), revisit Open questions and architecture.*
