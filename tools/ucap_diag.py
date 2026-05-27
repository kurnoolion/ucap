#!/usr/bin/env python3
"""ucap structural diagnostic — local, paste-safe.

Run this on a UE Capability log the assistant can't see, then paste the output
into chat. It emits:

  1. Envelope: detected format, vendor, message count, per-message RAT types.
  2. EUTRA decoded-structure dump: the nonCriticalExtension spine layer-by-layer,
     the *shape* of every lateNonCriticalExtension (tuple / bytes / dict), recursion
     into the late-extension chain, and a hunt for rf-Parameters* / supportedBand* /
     bandParameterList* keys with their paths and shapes.
  3. Canonical summary: EUTRA bands + CA-combo counts/sources/labels, NR/MRDC counts.

Paste-safety: emits ASN.1 field NAMES (public 3GPP identifiers), list COUNTS,
band numbers and BW classes (these appear in vendor capability sheets and are not
device/firmware/operator identifiers). It does NOT emit raw hex, file paths beyond
the basename, or any free-form log text.

Usage:
    python3 tools/ucap_diag.py <logfile> --vendor qcat --release rel17
"""

from __future__ import annotations

import argparse
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src"))


def _describe(v: object) -> str:
    if isinstance(v, tuple):
        return f"tuple[{len(v)}]({','.join(type(x).__name__ for x in v)})"
    if isinstance(v, (bytes, bytearray)):
        return f"bytes[{len(v)}]"
    if isinstance(v, dict):
        return f"dict{{{len(v)}}}"
    if isinstance(v, list):
        return f"list[{len(v)}]"
    return type(v).__name__


def _dump_spine(node: object, label: str, out: list[str], depth: int = 0) -> None:
    """Walk a nonCriticalExtension spine; reveal each lateNonCriticalExtension's
    shape and recurse into the late chain (tuple[1] dict, or a bare dict)."""
    cur = node
    layer = 0
    while isinstance(cur, dict):
        keys = [k for k in cur if k not in ("nonCriticalExtension", "lateNonCriticalExtension")]
        out.append(f"  {label} L{layer} keys={keys}")
        lnce = cur.get("lateNonCriticalExtension")
        if lnce is not None:
            out.append(f"  {label} L{layer} lateNonCriticalExtension={_describe(lnce)}")
            inner = None
            if isinstance(lnce, tuple) and len(lnce) == 2 and isinstance(lnce[1], dict):
                inner = lnce[1]
            elif isinstance(lnce, dict):
                inner = lnce
            if inner is not None and depth < 10:
                _dump_spine(inner, f"{label}/late{layer}", out, depth + 1)
        cur = cur.get("nonCriticalExtension")
        layer += 1
        if layer > 50:
            out.append(f"  {label} (spine truncated at 50)")
            break


def _hunt(obj: object, pats: tuple[str, ...], path: str = "", out: list | None = None, depth: int = 0) -> list:
    if out is None:
        out = []
    if depth > 30:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            kp = f"{path}.{k}" if path else k
            if any(p in k for p in pats):
                out.append((kp, _describe(v)))
            _hunt(v, pats, kp, out, depth + 1)
    elif isinstance(obj, tuple):
        for i, el in enumerate(obj):
            _hunt(el, pats, f"{path}(t{i})", out, depth + 1)
    elif isinstance(obj, list) and obj:
        _hunt(obj[0], pats, f"{path}[0]", out, depth + 1)
    return out


def _dump_asn1_structure(text: str) -> None:
    from ucap.adapters.qcat._asn1 import decode_rat_container, parse_asn1_text

    msgs = list(parse_asn1_text(text))
    print(f"DIAG|messages={len(msgs)}")
    for mi, m in enumerate(msgs):
        print(f"DIAG|msg{mi}|rat_types={[c.rat_type for c in m.rat_containers]}")
        for c in m.rat_containers:
            if c.rat_type != "eutra":
                print(f"DIAG|msg{mi}|{c.rat_type}|structural-dump-skipped (focus=eutra)")
                continue
            try:
                d = decode_rat_container(c)
            except Exception as e:  # noqa: BLE001 - diagnostic wants the class name
                print(f"DIAG|msg{mi}|eutra|DECODE-FAILED:{type(e).__name__}")
                continue
            out = [f"DIAG|msg{mi}|eutra|top-level-keys={sorted(d.keys())}"]
            _dump_spine(d, "spine", out)
            hits = _hunt(d, ("rf-Parameters", "supportedBand", "bandParameterList", "bandEUTRA-v9e0"))
            out.append(f"DIAG|msg{mi}|eutra|key-hunt ({len(hits)} hits):")
            for kp, shape in hits:
                out.append(f"  {kp} -> {shape}")
            print("\n".join(out))


def _canonical_summary(path: str, vendor: str, release: str) -> None:
    if vendor == "qcat":
        from ucap.adapters.qcat import parse_qcat_to_canonical
        docs = parse_qcat_to_canonical(path, vendor="qcat", release=release)
    elif vendor == "wireshark":
        from ucap.adapters.wireshark import parse_wireshark_to_canonical
        docs = parse_wireshark_to_canonical(path, vendor="wireshark", release=release)
    else:
        print(f"DIAG|canonical|unsupported-vendor={vendor}")
        return

    print(f"DIAG|canonical|documents={len(docs)}")
    for mi, doc in enumerate(docs):
        j = doc.model_dump(mode="json", by_alias=True, exclude_none=True)
        print(f"DIAG|msg{mi}|ratsPresent={j.get('ratsPresent')}")
        eu = j.get("eutra")
        if eu:
            combos = eu.get("caCombinations", [])
            srcs = sorted({c["source"] for c in combos})
            print(f"DIAG|msg{mi}|eutra|bands={[b['band'] for b in eu.get('supportedBands', [])]}")
            print(f"DIAG|msg{mi}|eutra|combos={len(combos)}|sources={srcs}|"
                  f"sample_labels={[c['label'] for c in combos[:8]]}")
        for rat in ("nr", "mrdc"):
            sec = j.get(rat)
            if sec:
                print(f"DIAG|msg{mi}|{rat}|combos={len(sec.get('bandCombinations', []))}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ucap_diag", description="ucap structural diagnostic")
    p.add_argument("logfile")
    p.add_argument("--vendor", default="qcat", choices=["qcat", "wireshark"])
    p.add_argument("--release", default="rel17")
    args = p.parse_args(argv)

    if not os.path.isfile(args.logfile):
        print(f"DIAG|ERROR|file-not-found={os.path.basename(args.logfile)}", file=sys.stderr)
        return 2

    text = open(args.logfile, encoding="utf-8", errors="replace").read()
    print(f"DIAG|file={os.path.basename(args.logfile)}|vendor={args.vendor}|release={args.release}")

    if args.vendor == "qcat":
        from ucap.adapters.qcat import detect_format
        fmt = detect_format(text)
        print(f"DIAG|format={fmt}")
        if fmt == "asn1":
            try:
                _dump_asn1_structure(text)
            except Exception as e:  # noqa: BLE001
                print(f"DIAG|structural-dump|ERROR:{type(e).__name__}:{e}")
        else:
            print("DIAG|format=indented (structural dump is the indented tree; "
                  "see canonical summary below)")

    try:
        _canonical_summary(args.logfile, args.vendor, args.release)
    except Exception as e:  # noqa: BLE001
        print(f"DIAG|canonical|ERROR:{type(e).__name__}:{e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
