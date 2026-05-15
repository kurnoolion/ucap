"""Samsung Shannon DM (Exynos) log adapter — stub.

Awaiting a sample ``ueCapabilityInformation`` snippet exported via Shannon
DM's right-click "Copy Details" (path: ``LTE RRC → ULDCCH →
ueCapabilityInformation``). Once a real format sample is available, this
will follow the same shape as the QCAT adapter: line-classifying
tokenizer + indent-driven tree builder + canonical mapper.
"""

from __future__ import annotations

from pathlib import Path

from ucap.schema import CanonicalUeCapability


def parse_shannon_log(path: str | Path, *, release: str) -> list[CanonicalUeCapability]:
    raise NotImplementedError(
        "Shannon DM adapter not yet implemented — needs a sample log snippet to "
        "ground the text format. Right-click a ueCapabilityInformation message "
        "in Shannon DM, choose 'Copy Details', and share the resulting text."
    )
