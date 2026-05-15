# Build Status

Last updated: 2026-05-15

Project renamed from `ucap` to **`ucap`** (broader scope: parse + audit +
diff + query + …). CLI restructured to subcommand shape — today only `ucap parse`
is wired, with the dispatcher ready for `audit` / `diff` / `query` as those land.

## v1 complete — QCAT parsing, end to end

All 16 build tasks are done. The pipeline parses real QCAT log exports for
UE Capability Information messages and emits canonical JSON focused on
band combinations. 15 pytest tests pass against 5 vendored fixtures.

### What works

- **Schema** (`src/ucap/schema.py`): Pydantic models for the flat canonical view —
  `Meta`, `EutraSection`, `NrSection`, `MrdcSection`, plus their combo/band-entry types.
  `_meta` / `_unmapped` carried via JSON aliases. `extra="forbid"` on every model.
- **QCAT adapter** (`src/ucap/adapters/qcat.py`):
  - Tokenizer + indent-driven tree builder; handles both QCAT line styles
    (`name : value` and the NR variant `name: value`).
  - SEQUENCE-OF type-marker collapse with a combined heuristic — collapses
    when the inner marker's name matches the parent (case-insensitive, for
    NR's `featureSetCombinations / featureSetCombinations :`) OR starts with
    an uppercase letter (for PascalCase markers like
    `BandCombinationParameters-r10 :` nested inside `[N]`).
  - Trailing `Message dump (Hex)` block stripped so it doesn't pollute the tree.
  - LTE mapper: extracts `supportedBandListEUTRA`, merges `supportedBandCombination-r10`
    (main) + `supportedBandCombinationAdd-r11` (addR11), pulls BCS bitmaps from
    `supportedBandCombinationExt-r10`. Both Rel-10 (`bandList` inline) and Rel-11
    (`bandParameterList-r11` wrapper) combo formats supported.
  - NR mapper: walks `ue-NR-Capability.supportedBandCombinationList` and resolves
    the full feature-set indirection chain. Per-CC tables (`featureSetsDownlink`,
    `featureSetsUplink`, `featureSetsDownlinkPerCC`, `featureSetsUplinkPerCC`) are
    pulled once from any `ue-NR-Capability.featureSets` in the tree and threaded
    through. `featureSetCombination` ID is 0-indexed; downstream IDs are 1-indexed
    with 0 = absent.
  - MRDC mapper: handles the separate `ue-MRDC-Capability` RAT container
    (RAT Type `eutra-nr` or `mrdc-XPDCP`). MRDC carries its own
    `featureSetCombinations` table but reuses the NR per-CC tables. Handles
    main EN-DC list plus Rel-16 `NEDC-Only-r16` and `NRDC-r16` sources.
  - Combo `kind` derivation: EN-DC if any EUTRA band entry or `mrdc-Parameters`;
    pure `caNR` otherwise. Labels formatted as `<band><BWClass>` joined by `-`
    (NR bands get `n` prefix: `"n78A-n41A"`, `"2C-66A-n41A"`).
  - BIT STRING parsing handles both old (`Binary string (Bin) : <bits>` wrapper)
    and new (inline `field : <bits>`) QCAT styles.
- **CLI** (`src/ucap/cli.py`):
  `ue-cap-parse <log-file> --vendor qcat --release rel17 [-o out.json] [--compact]`.
  Emits a JSON array (one document per message in the log).
- **Stubs** for Shannon DM (`adapters/shannon.py`) and ELT (`adapters/elt.py`) —
  raise `NotImplementedError` with a clear message about what sample is needed.
- **Tests** (`tests/test_qcat.py`): 15 cases — fixture-parse smoke, LTE combo
  counts/labels/BCS, S22 main+addR11 merge, NR/MRDC EN-DC resolution invariants,
  pure-NR-empty case, JSON roundtrip through Pydantic validation for all 5 fixtures.

### Verified parsed counts

| Fixture            | EUTRA combos | source mix              | MRDC combos | kind  |
|--------------------|--------------|-------------------------|-------------|-------|
| `OnePlus9_LTE.txt` | 29           | main                    | —           |       |
| `G960W_LTE.txt`    | 134          | main: 128, addR11: 6    | —           |       |
| `S22_LTE.txt`      | 260          | main: 128, addR11: 132  | —           |       |
| `OnePlus9_NR.txt`  | —            |                         | 23          | endc  |
| `S22_NR.txt`       | —            |                         | 26          | endc  |

### Known gaps (deferred; not blocking v1)

- **LTE extension data**: 256QAM-DL / 64QAM-UL / 1024QAM-DL flags from
  `supportedBandCombination-v1090` / `v10i0` / `v1430` not merged into combo records.
  Schema fields exist; merge logic is the work to add.
- **NR extension lists**: `supportedBandCombinationList-v1540` / `-v1590` are
  parallel extension arrays carrying additional combo data (power class extensions,
  more BCS, etc.) — not yet merged.
- **`scsSupported`** on `NrBand` always emits `[]`. The `mimo-ParametersPerBand`
  subtree isn't parsed for v1. (User scope is band combos; this is per-band detail.)
- **`supportsSUL`** defaults to `False` and gets emitted for every entry including
  EUTRA bands. Cosmetic noise. Cleaner: make it `bool | None` with default `None`.
- **Shannon DM and ELT adapters**: stubs only — both await a sample log snippet
  to ground their text format.

### How to run

```bash
cd /home/mohan/work/ucap

# Tests
PYTHONPATH=src python3 -m pytest tests/

# CLI
PYTHONPATH=src python3 -m ucap.cli parse \
    tests/fixtures/qcat/OnePlus9_NR.txt \
    --vendor qcat --release rel17
```

### Repo state

git initialized, no commits yet. Working tree contains the full v1.
