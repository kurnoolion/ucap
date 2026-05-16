"""Command-line entry point.

``ucap`` is a subcommand-style CLI. Today only ``parse`` is wired up;
``audit`` / ``diff`` / ``query`` will land alongside their features.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import get_args

from ucap import __version__
from ucap.schema import Release, Vendor


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ucap",
        description="UE capability analysis toolkit.",
    )
    p.add_argument(
        "--version", action="version", version=f"ucap {__version__}",
    )
    sub = p.add_subparsers(dest="command", required=True, metavar="<command>")

    parse = sub.add_parser(
        "parse",
        help="parse a vendor-tool log into canonical JSON",
        description="Parse a modem-log UE Capability Information message into canonical JSON.",
    )
    parse.add_argument("log_file", type=Path, help="path to the vendor tool's text log export")
    parse.add_argument(
        "--vendor", required=True, choices=list(get_args(Vendor)),
        help="which vendor tool produced the log",
    )
    parse.add_argument(
        "--release", default="rel17", choices=list(get_args(Release)),
        help="3GPP release to interpret the log against (default: rel17)",
    )
    parse.add_argument(
        "-o", "--output", type=Path, default=None,
        help="write JSON to this file instead of stdout",
    )
    parse.add_argument(
        "--compact", action="store_true", help="emit compact JSON (default: indented)",
    )
    parse.set_defaults(func=_cmd_parse)

    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return args.func(args)


def _cmd_parse(args: argparse.Namespace) -> int:
    if not args.log_file.is_file():
        print(f"error: file not found: {args.log_file}", file=sys.stderr)
        return 2

    docs = _parse_log(args.log_file, vendor=args.vendor, release=args.release)
    payload = [
        d.model_dump(mode="json", by_alias=True, exclude_none=True) for d in docs
    ]

    indent = None if args.compact else 2
    text = json.dumps(payload, indent=indent)

    if args.output:
        args.output.write_text(text + ("" if args.compact else "\n"))
    else:
        sys.stdout.write(text)
        if not args.compact:
            sys.stdout.write("\n")
    return 0


def _parse_log(log_file: Path, *, vendor: str, release: str):
    if vendor == "qcat":
        from ucap.adapters.qcat import parse_qcat_to_canonical
        return parse_qcat_to_canonical(
            log_file,
            vendor="qcat",
            release=release,  # type: ignore[arg-type]
            source_file=log_file.name,
        )
    if vendor == "shannon":
        from ucap.adapters.shannon import parse_shannon_log
        return parse_shannon_log(log_file, release=release)
    if vendor == "elt":
        from ucap.adapters.elt import parse_elt_log
        return parse_elt_log(log_file, release=release)
    raise SystemExit(f"unsupported vendor: {vendor}")


if __name__ == "__main__":
    sys.exit(main())
