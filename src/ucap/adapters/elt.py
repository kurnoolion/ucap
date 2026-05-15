"""MediaTek ELT (Engineer Log Tool) adapter — stub.

Awaiting a sample ``ueCapabilityInformation`` snippet from ELT's OTA/message
log view (requires the operator-specific ``MDDB_InfoCustomAppSrcP_*.EDB``
database loaded). A second viable input path is the Wireshark-routed export
that ELT supports — that path is publicly documented and may turn out to be
the more reliable adapter target. Both routes will be evaluated once a real
sample is available.
"""

from __future__ import annotations

from pathlib import Path

from ucap.schema import CanonicalUeCapability


def parse_elt_log(path: str | Path, *, release: str) -> list[CanonicalUeCapability]:
    raise NotImplementedError(
        "ELT adapter not yet implemented — needs a sample log snippet to ground "
        "the text format. Export a ueCapabilityInformation message from ELT "
        "(either the native log view or the Wireshark-routed export) and share."
    )
