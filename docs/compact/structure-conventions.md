# Structure conventions

Defines what counts as a "module" in this repository and how Python visibility maps to `pub` / `internal` for the `regen-map` skill.

Populated 2026-05-14 by `project-init --retrofit` from Topic 2 of the interview. Edit as conventions evolve.

## Module definition

Each directory containing `__init__.py` under the top-level package directory (`src/ucap/`) is a module. A module's MODULE.md lives at the directory root — i.e. `src/ucap/MODULE.md` for the top-level package, and `src/ucap/<submodule>/MODULE.md` for each submodule (e.g. `src/ucap/adapters/MODULE.md`).

Sub-modules deeper than one level (e.g. `src/ucap/adapters/qcat/` if it ever becomes a package) follow the same rule. Single-file submodules (e.g. `src/ucap/cli.py`) are part of their parent module — their public surface rolls up into the parent's MODULE.md, not a separate one. **Note (2026-05-14, `[D-014]`)**: `src/ucap/schema.py` was promoted to a sub-package `src/ucap/schema/` with its own `MODULE.md` during architecture-phase MODULE.md curation, to resolve the package-level `ucap ↔ adapters` cycle.

## Visibility mapping

- **Non-underscore top-level name** (`def foo`, `class Foo`, `FOO = ...`) → `pub`.
- **Leading-underscore top-level name** (`def _foo`, `class _Foo`, `_FOO = ...`) → `internal`.
- **`__all__` declaration** — when a file declares `__all__`, that list is the **authoritative** public surface for the file. Names not in `__all__` are `internal` even if they lack a leading underscore. Example: `src/ucap/adapters/qcat.py` declares `__all__` covering `parse_qcat_file`, `parse_qcat_text`, `map_message_to_canonical`, `TreeNode`, `Message`.

`regen-map` reads this convention to compute the Public surface section of each MODULE.md's Structure block (regen-only, bounded by `<!-- BEGIN:STRUCTURE -->` / `<!-- END:STRUCTURE -->`).

## Description source

- `*.py`: first line of the module docstring (the `"""..."""` immediately following the file header). If absent, no description.
- Directories with `MODULE.md`: first sentence of the Purpose section.
- Other files / directories: no automatic description (path-only row).

Rows in MAP.md's Project File Structure section are alphabetical within each directory; files and directories intermix alphabetically.

## Module doc schema

Each MODULE.md carries the following curated sections (plus a regen-only Structure block):

- **Owner** *(optional)* — single contributor owning the module; omit if shared or unassigned. Currently omitted across ucap (solo project).
- **Purpose** — 1-2 sentences. Cite the FR / NFR IDs this module serves (e.g. *"serves FR-2, FR-4"*).
- **Public surface** — signatures + semantics. Includes the public type aliases / Pydantic models / functions callers rely on. For files with `__all__`, the list there is authoritative.
- **Invariants** — what callers can count on (schema-validity guarantees, error-code contract, no-free-text-in-reports, threading / state / ordering).
- **Key choices** — each linked to DECISIONS.md by `[D-XXX]`.
- **Non-goals** — deliberate omissions (e.g. "does not parse `mimo-ParametersPerBand`").
- **Structure** — regen-only; bounded by `<!-- BEGIN:STRUCTURE -->` / `<!-- END:STRUCTURE -->`; never hand-edited.
- **Depends on** / **Depended on by** — links to other MODULE.md files.
- **Deferred** *(optional)* — planned-but-unbuilt module-level behaviors. Read by `drift-check` to classify matching items as `[DEFERRED]` rather than drift.

## Retrofit skeleton sentinel

MODULE.md files seeded by `project-init --retrofit` begin with the marker `<!-- retrofit: skeleton -->`. While present, `close-session` treats curated-section edits as expected (not hard flags). Remove the sentinel once the MODULE.md is fully curated; from that point, normal audit rules apply.

Files currently bearing the sentinel: *(none — both `src/ucap/MODULE.md` and `src/ucap/adapters/MODULE.md` were curated 2026-05-14; `src/ucap/schema/MODULE.md` and `src/ucap/diagnostics/MODULE.md` are fresh drafts and never bore the sentinel)*.
