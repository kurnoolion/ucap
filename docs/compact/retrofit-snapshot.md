# Retrofit snapshot

Generated 2026-05-14 by `project-init --retrofit`. Archival: do not update; re-run retrofit into a fresh project if the codebase shape changes materially.

## Detected languages

- Python — `pyproject.toml` (`requires-python = ">=3.11"`, hatchling build, deps: `pydantic>=2.6`, dev: `pytest`, `pytest-cov`)

Confirmed by user 2026-05-14: Python only for now; other stack elements may be added later as scope expands.

## Candidate modules

### Python

- `src/ucap/MODULE.md` — 1 public symbol observed at package root (`__version__`); public surface lives in submodules `cli.py` and `schema.py`.
- `src/ucap/adapters/MODULE.md` — empty `__init__.py`; public surface lives in submodules `qcat.py`, `shannon.py`, `elt.py`.

Module convention applied: Python — each directory containing `__init__.py` under the top-level package dir is a candidate module. Visibility mapping: non-underscore top-level names.

## Candidate public surface (per module)

### `src/ucap/` (Python)

From `src/ucap/__init__.py`:
- `__version__ = "0.1.0"`

From `src/ucap/cli.py` (public top-level names):
- `def main(argv: list[str] | None = None) -> int` — CLI entry point (registered as `ucap` console script in `pyproject.toml`).

From `src/ucap/schema.py` (public top-level names — Pydantic models + type aliases):
- Type aliases: `Vendor`, `Release`, `RatName`, `CaBandwidthClass`, `Modulation`, `FrequencyRange`, `PowerClassNR`, `EutraComboSource`, `NrComboSource`, `MrdcComboSource`, `NrComboKind`, `MrdcComboKind`.
- Pydantic models: `Meta`, `EutraBand`, `EutraComboBandEntry`, `EutraCaCombination`, `EutraSection`, `NrBand`, `NrComboBandEntry`, `NrBandCombination`, `NrSection`, `MrdcBandCombination`, `MrdcSection`, `CanonicalUeCapability`.

Note: `_M` (private base class) is intentionally excluded — leading underscore = internal.

### `src/ucap/adapters/` (Python)

From `src/ucap/adapters/qcat.py` (public top-level names; `__all__` is declared in the source):
- `class TreeNode` — indent-driven parse tree node.
- `class Message` — parsed QCAT message (title + tree root).
- `def parse_qcat_file(path: str | Path) -> list[Message]`
- `def parse_qcat_text(text: str) -> Iterator[Message]`
- `def map_message_to_canonical(...)` — maps a parsed `Message` to a `CanonicalUeCapability`.

From `src/ucap/adapters/shannon.py`:
- `def parse_shannon_log(path: str | Path, *, release: str) -> list[CanonicalUeCapability]` — **stub**, raises `NotImplementedError`.

From `src/ucap/adapters/elt.py`:
- `def parse_elt_log(path: str | Path, *, release: str) -> list[CanonicalUeCapability]` — **stub**, raises `NotImplementedError`.
