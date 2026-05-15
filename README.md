# ucap

A toolkit for UE capability analysis. Parses UE Capability Information from
chipset-vendor modem-log tool exports (QCAT, Shannon DM, ELT) into a canonical
JSON, then layers further tools on top — compliance audits, diffs, ad-hoc
queries.

## Scope

- **Parse**: vendor text exports → canonical JSON. Focused on band
  combinations (LTE CA, NR CA, EN-DC / NE-DC / NR-DC).
- **Audit** *(planned)*: compare parsed capabilities against a compliance
  sheet, surface discrepancies.
- **Diff** *(planned)*: compare two capability snapshots — across firmware
  versions, across UEs.
- **Query** *(planned)*: ad-hoc questions like "does this UE support band X
  with class Y?"

Standards reference: 3GPP TS 36.331 (`UE-EUTRA-Capability`), TS 38.331
(`UE-NR-Capability`, `UE-MRDC-Capability`). Default grammar release is Rel-17;
selectable per log.

## Adapters

| Vendor       | Tool       | Adapter |
|--------------|------------|---------|
| Qualcomm     | QCAT       | v1      |
| Samsung LSI  | Shannon DM | stub    |
| MediaTek     | ELT        | stub    |

Shannon DM and ELT adapters await sample log snippets to ground their text format.

## CLI

```
ucap parse <log-file> --vendor qcat --release rel17 [-o out.json]
```

Further subcommands (`audit`, `diff`, `query`) will land as those features are built.
