# ucap

**Purpose**
The user-facing top-level package: hosts the `ucap` console-script CLI (subcommand-style dispatcher) and the package version. v1 wires the `parse` subcommand; `audit`, `diff`, `query` are reserved as future subcommands. Serves `FR-6` (release selector), `FR-7` (subcommand CLI shape), `FR-8` (stub-adapter messaging), `FR-12`–`FR-14` (chat-mediated debugging entry points: `--diagnostic` / `--validate` / `--redact-with`).

**Public surface**

```python
__version__: str                                   # package version (currently "0.1.0")
def main(argv: list[str] | None = None) -> int    # CLI entry point; registered as the `ucap` console script
```

The CLI's user-facing surface (flag set, subcommand list, output forms) is *also* a public contract even though it's exercised through `main()`:

```
ucap parse <log> --vendor <qcat|shannon|elt> [--release rel15|rel16|rel17|rel18]
                                            [-o <path>] [--compact]
                                            [--diagnostic] [--validate]
                                            [--run-id <slug>] [--redact-with <path>]
```

Future subcommands (`audit` / `diff` / `query`) land as additional `sub.add_parser(...)` arms in `_build_parser`.

**Invariants**

- **One console script: `ucap`.** Single entry point; subcommands dispatched within `main()`. No per-subcommand console scripts (`ucap-parse`, `ucap-audit`, etc.).
- **Adapter dispatch is by `--vendor` value.** The CLI selects adapter by the `Vendor` literal value from `src/ucap/schema/`; new vendors require both a `Vendor` literal addition and a dispatcher arm in `_parse_log`. Plugin loading is explicitly out of scope (`[D-003]`).
- **`--release` argument is validated against `Release` literals** at argparse time via `get_args(Release)`. Adding a release value is additive across the project.
- **Error paths emit prefixed `CLI-E???` codes** via `ucap.diagnostics.format_code` rather than raising `Exception(...)` directly. Current `print(f"error: ...", file=sys.stderr)` + `return 2` pattern in `_cmd_parse` and `raise SystemExit(f"unsupported vendor: ...")` in `_parse_log` are development-phase soft-flag candidates to convert (`CLI-E001` file-not-found, `CLI-E002` unsupported-vendor; registered in `[D-011]`).
- **`--diagnostic` / `--validate` replace canonical JSON on stdout** rather than appending or duplexing (`[D-010]`). Both are independently usable; combining emits RPT then QC, in that order.
- **`--run-id` is opaque to the CLI** — passed verbatim to `ReportWriter`. UUIDv4 default applied at the dispatcher boundary when the flag is omitted.

**Key choices**

- `[D-001]` — Python 3.11+ as the language floor.
- `[D-006]` — subcommand-style CLI with `audit` / `diff` / `query` slots pre-shaped for future work.
- `[D-010]` — `--diagnostic` / `--validate` / `--run-id` flag set + replace-don't-duplex toggle semantics + the field menus for QCAT.
- `[D-011]` — `CLI-E001` / `CLI-E002` codes registered in the central diagnostics registry; `format_code` / `get_code` used at every error path.
- `[D-012]` — `--redact-with <path>` flag; loaded `Redactor` threaded into `ReportWriter` constructor.

**Non-goals**

- **Not a service or daemon.** ucap is a batch CLI; no long-running process, no port binding, no scheduler.
- **Not a plugin loader.** Adapters are statically registered in `_parse_log`'s dispatch arms. New vendors require source changes, not configuration.
- **Not a web UI.** Future stakeholder interfaces beyond CLI (e.g., compliance-sheet ingestion for `audit`) require dedicated modules per `[D-008]`, not extensions of this package.
- **Not a schema definition.** Canonical types live in `src/ucap/schema/` (`[D-014]`); this package only references them.
- **Not a parser.** Per-vendor parsing lives in `src/ucap/adapters/`; this package only dispatches to it.

<!-- BEGIN:STRUCTURE -->
_Regenerated 2026-05-14 by regen-map. Do not hand-edit._

### `__init__.py`

- `__version__` — value — pub — Package version string.

### `cli.py`

- `_build_parser` — function — internal — Build the argparse parser for the `ucap` CLI.
- `_cmd_parse` — function — internal — Handler for the `parse` subcommand.
- `_parse_log` — function — internal — Dispatch to the per-vendor adapter.
- `main` — function — pub — CLI entry point; registered as the `ucap` console script.
<!-- END:STRUCTURE -->

**Depends on**
- `src/ucap/schema/MODULE.md` — `cli.py` uses `Vendor` and `Release` literal types as argparse `choices`.
- `src/ucap/adapters/MODULE.md` — `cli.py`'s `_parse_log` calls into each adapter's public surface (`parse_qcat_file`, `map_message_to_canonical`, `parse_shannon_log`, `parse_elt_log`); signature changes there force changes here.
- `src/ucap/diagnostics/MODULE.md` — `cli.py` uses `ReportWriter`, `ReportRecord`, `ReportType`, `Redactor`, `format_code`, `get_code` for `--diagnostic` / `--validate` / `--redact-with` modes and for `CLI-E???` error emission.

**Depended on by**
*(external)* — anyone running the `ucap` console script. No in-repo Python module imports from `ucap.cli` or `ucap.__version__` except `ucap.adapters.qcat` (which imports `__version__` as `_PARSER_VERSION` for `Meta.parserVersion`); that single edge is a leaf-level reference, not a contract dependency.
