# Workflow: ucap-diag

Run the ucap structural diagnostic on a UE Capability log and surface the output
for pasting into chat. Built for the limited-LLM-access model: the assistant can't
see the log, so this produces a compact, paste-safe structural report instead.

## When to use

Parse output looks wrong — missing/incorrect bands, 0 combos, unexpected values —
and the assistant needs to see the *decoded structure* of a log it cannot access.

## Steps

1. Collect: log file path, vendor (`qcat` | `wireshark`), release (default `rel17`).
2. Run from the repo root:

   ```
   python3 tools/ucap_diag.py <logfile> --vendor <vendor> --release <release>
   ```

3. Return the **full `DIAG|...` output verbatim** so the user can paste it into chat.

## What it reports

- **Envelope** — detected format (asn1 / indented), message count, per-message RAT types.
- **EUTRA decoded-structure dump** — the `nonCriticalExtension` spine layer-by-layer,
  the *shape* of every `lateNonCriticalExtension` (tuple / bytes / dict), recursion into
  the late-extension chain, and a key-hunt for `rf-Parameters*` / `supportedBand*` /
  `bandParameterList*` with paths + shapes.
- **Canonical summary** — EUTRA bands + CA-combo counts/sources/labels; NR/MRDC counts.

## Paste-safety

Emits ASN.1 field **names** (public 3GPP identifiers), list **counts**, band numbers,
and BW classes only. No raw hex, no file paths beyond the basename, no free-form log
text. Safe to share in chat.
