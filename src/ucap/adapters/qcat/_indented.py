"""QCAT log text parser and canonical mapper.

Two layers in this file:
1. **Parser**: tokenize a QCAT text export, build an indent-driven tree of
   nodes. SEQUENCE-OF type-marker lines (``SupportedBandListEUTRA :`` between
   a field and its ``[N]`` list elements) are collapsed so list elements
   hang directly under the field name.
2. **Mapper**: walk that tree and produce a :class:`CanonicalUeCapability`
   document populated with band-combination data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from ucap import __version__ as _PARSER_VERSION
from ucap.schema import (
    CaBandwidthClass,
    CanonicalUeCapability,
    EutraBand,
    EutraCaCombination,
    EutraComboBandEntry,
    EutraSection,
    FrequencyRange,
    Meta,
    Modulation,
    MrdcBandCombination,
    MrdcComboKind,
    MrdcComboSource,
    MrdcSection,
    NrBand,
    NrBandCombination,
    NrComboBandEntry,
    NrComboKind,
    NrComboSource,
    NrSection,
    PowerClassNR,
    RatName,
    Release,
    Vendor,
)

__all__ = [
    "TreeNode",
    "Message",
    "parse_qcat_text",
    "parse_qcat_file",
    "map_message_to_canonical",
]


_TITLE_RE = re.compile(r"UE Capability Information \(([^)]+)\)")
_LIST_INDEX_RE = re.compile(r"^\[\s*\d+\s*\]$")
_SUBSCRIPTION_MARKER_RE = re.compile(r"^EQ\d+\s*$")
_NR_COLON_RE = re.compile(r"^([A-Za-z][\w\-]*)\s*:\s*(\S.*)$")


@dataclass
class TreeNode:
    name: str
    value: str | None = None
    children: list[TreeNode] = field(default_factory=list)
    line_no: int = 0

    def is_list_element(self) -> bool:
        return bool(_LIST_INDEX_RE.match(self.name))

    def get(self, name: str) -> TreeNode | None:
        for c in self.children:
            if c.name == name:
                return c
        return None

    def find_all(self, name: str) -> list[TreeNode]:
        return [c for c in self.children if c.name == name]

    def list_items(self) -> list[TreeNode]:
        return [c for c in self.children if c.is_list_element()]


@dataclass
class Message:
    title: str
    direction: str | None
    timestamp: str | None
    start_line: int
    end_line: int
    root: TreeNode


def parse_qcat_file(path: str | Path) -> list[Message]:
    return list(parse_qcat_text(Path(path).read_text()))


def parse_qcat_text(text: str) -> Iterator[Message]:
    """Yield each UE Capability Information message found in the text."""
    lines = text.splitlines()
    starts = [
        i for i, line in enumerate(lines)
        if line.strip().startswith("UE Capability Information")
    ]
    for k, start in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(lines)
        adj_start = start - 1 if start > 0 and _SUBSCRIPTION_MARKER_RE.match(lines[start - 1]) else start
        yield _parse_message(lines[adj_start:end], start_line=adj_start + 1)


def _parse_message(block: list[str], start_line: int) -> Message:
    title = ""
    direction: str | None = None
    timestamp: str | None = None
    body_start = 0
    for i, raw in enumerate(block):
        stripped = raw.strip()
        if not title and stripped.startswith("UE Capability Information"):
            title = stripped
            m = _TITLE_RE.match(stripped)
            if m:
                direction = m.group(1)
            continue
        if title and stripped.startswith("Time :"):
            timestamp = stripped.split(":", 1)[1].strip()
            continue
        if title and stripped:
            body_start = i
            break

    # QCAT appends a "Message dump (Hex)" block after the decoded body.
    # Truncate at that boundary so it doesn't become part of the tree.
    body_end = len(block)
    for i in range(body_start, len(block)):
        if block[i].lstrip().startswith("Message dump"):
            body_end = i
            break

    body = block[body_start:body_end]
    root = _build_tree(body, base_line=start_line + body_start)
    _collapse_sequence_of_markers(root)
    return Message(
        title=title,
        direction=direction,
        timestamp=timestamp,
        start_line=start_line,
        end_line=start_line + len(block),
        root=root,
    )


def _split_line(line: str) -> tuple[int, str, str | None]:
    """Return ``(indent, name, value)`` for a QCAT line.

    ``value`` is:
      - ``None``     for container headers (no colon at all)
      - ``""``       for SEQUENCE-OF type / list markers (``"Name :"`` with empty after)
      - ``"<text>"`` for scalar fields (``"Name : value"`` or NR's ``"Name: value"``)
    """
    stripped_left = line.lstrip(" ")
    indent = len(line) - len(stripped_left)
    content = stripped_left.rstrip()
    if not content:
        return indent, "", None

    pos = content.find(" : ")
    if pos >= 0:
        return indent, content[:pos], content[pos + 3:]
    if content.endswith(" :"):
        return indent, content[:-2], ""
    if content.endswith(":"):
        return indent, content[:-1], ""
    m = _NR_COLON_RE.match(content)
    if m:
        return indent, m.group(1), m.group(2)
    return indent, content, None


def _build_tree(lines: list[str], base_line: int = 1) -> TreeNode:
    root = TreeNode(name="__root__", line_no=base_line)
    stack: list[tuple[int, TreeNode]] = [(-1, root)]
    for offset, raw in enumerate(lines):
        if not raw.strip():
            continue
        indent, name, value = _split_line(raw)
        if not name:
            continue
        while stack and stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]
        node = TreeNode(name=name, value=value, line_no=base_line + offset)
        parent.children.append(node)
        stack.append((indent, node))
    return root


def _collapse_sequence_of_markers(node: TreeNode) -> None:
    """Collapse the QCAT SEQUENCE-OF type-marker idiom in place.

    Walks bottom-up so nested SEQUENCE-OF patterns flatten cleanly.
    """
    for child in node.children:
        _collapse_sequence_of_markers(child)

    # SEQUENCE-OF type-marker idiom. Parent must be structural (bare name or
    # ``Name :``) with exactly one child, whose value is also empty and whose
    # children are list elements. The marker is identified by EITHER its name
    # matching the parent (case-insensitive — covers QCAT's NR rendering of
    # ``featureSetCombinations / featureSetCombinations :``) OR its name
    # starting with an uppercase letter (covers PascalCase type names like
    # ``BandCombinationParameters-r10 :`` nested inside an outer ``[N]`` list
    # element, where the parent name doesn't match the child name).
    if len(node.children) == 1 and (node.value is None or node.value == ""):
        child = node.children[0]
        if (
            child.value == ""
            and child.name
            and child.children
            and all(c.is_list_element() for c in child.children)
            and (
                child.name.lower() == node.name.lower()
                or child.name[0].isupper()
            )
        ):
            node.children = child.children


# ─── Mapper: tree → canonical schema ────────────────────────────────


def map_message_to_canonical(
    message: Message,
    *,
    vendor: Vendor = "qcat",
    release: Release = "rel17",
    source_file: str = "",
) -> CanonicalUeCapability:
    """Map one parsed QCAT message tree to the canonical schema."""
    root = message.root
    rats_present: list[RatName] = []
    eutra_section: EutraSection | None = None
    nr_section: NrSection | None = None
    mrdc_section: MrdcSection | None = None

    ue_cap_r8 = _find_first(root, "ueCapabilityInformation-r8")
    if ue_cap_r8 is None:
        raise ValueError("no ueCapabilityInformation-r8 found in message tree")

    # Per-CC feature-set tables live exclusively under UE-NR-Capability.featureSets
    # and are referenced from both NR's own and MRDC's combination lists.
    nr_per_cc = _collect_nr_per_cc_tables(root)

    container_list = _find_first(ue_cap_r8, "ue-CapabilityRAT-ContainerList")
    if container_list is not None:
        for rat_container in container_list.list_items():
            rt = _value(rat_container.get("RAT Type"))
            rt = rt.strip() if rt else None
            if rt == "eutra":
                eutra_section = _map_eutra(rat_container)
                rats_present.append("eutra")
            elif rt == "nr":
                nr_section = _map_nr(rat_container, nr_per_cc)
                rats_present.append("nr")
            elif rt in ("eutra-nr", "mrdc-XPDCP"):
                mrdc_section = _map_mrdc(rat_container, nr_per_cc)
                rats_present.append("mrdc")

    meta = Meta(
        vendor=vendor,
        release=release,
        sourceFile=source_file,
        sourceLineRange=(message.start_line, message.end_line),
        timestamp=message.timestamp,
        decodedAt=datetime.now(timezone.utc),
        parserVersion=_PARSER_VERSION,
    )
    return CanonicalUeCapability(
        _meta=meta,
        ratsPresent=rats_present,
        eutra=eutra_section,
        nr=nr_section,
        mrdc=mrdc_section,
    )


def _map_eutra(rat_container: TreeNode) -> EutraSection:
    ue_eutra = rat_container.get("UE EUTRA Capability")
    if ue_eutra is None:
        return EutraSection(accessStratumRelease="unknown", supportedBands=[], caCombinations=[])

    asr_node = ue_eutra.get("accessStratumRelease")
    asr = asr_node.value.strip() if asr_node and asr_node.value else "unknown"

    bands: list[EutraBand] = []
    rf = ue_eutra.get("rf-Parameters")
    if rf is not None:
        sbl = rf.get("supportedBandListEUTRA")
        if sbl is not None:
            for item in sbl.list_items():
                b = _get_int(item, "bandEUTRA")
                if b is not None:
                    bands.append(EutraBand(band=b, halfDuplex=_get_bool(item, "halfDuplex")))

    combos: list[EutraCaCombination] = []
    # Rel-10 main list — combo is a direct SEQUENCE OF BandParameters-r10
    _R10 = _ComboFormat(
        cc_list_field=None,
        band_field="bandEUTRA-r10",
        ul_field="bandParametersUL-r10",
        dl_field="bandParametersDL-r10",
    )
    # Rel-11 Add list — combo wraps a bandParameterList-r11
    _R11 = _ComboFormat(
        cc_list_field="bandParameterList-r11",
        band_field="bandEUTRA-r11",
        ul_field="bandParametersUL-r11",
        dl_field="bandParametersDL-r11",
    )

    sbc = _find_first(ue_eutra, "supportedBandCombination-r10")
    if sbc is not None:
        for i, combo_node in enumerate(sbc.list_items()):
            combo = _map_eutra_ca_combo(combo_node, fmt=_R10, idx=i, source="main")
            if combo is not None:
                combos.append(combo)
    main_count = len(combos)

    sbc_add = _find_first(ue_eutra, "supportedBandCombinationAdd-r11")
    if sbc_add is not None:
        for i, combo_node in enumerate(sbc_add.list_items()):
            combo = _map_eutra_ca_combo(combo_node, fmt=_R11, idx=main_count + i, source="addR11")
            if combo is not None:
                combos.append(combo)

    # Merge BCS bitmaps from parallel Ext lists
    _merge_eutra_bcs(combos[:main_count], _find_first(ue_eutra, "supportedBandCombinationExt-r10"))
    _merge_eutra_bcs(combos[main_count:], _find_first(ue_eutra, "supportedBandCombinationExtAdd-r11"))

    return EutraSection(
        accessStratumRelease=asr,
        supportedBands=bands,
        caCombinations=combos,
    )


@dataclass(frozen=True)
class _ComboFormat:
    """How a particular EUTRA combo list addresses its CC entries.

    Tracks where the per-CC list lives (direct or via a wrapper field) and
    the spec-version suffix on the inner field names.
    """

    cc_list_field: str | None  # if set, descend into this child to find the [N] entries
    band_field: str
    ul_field: str
    dl_field: str
    # Inner field names below bandParameters{DL,UL} re-use the r10 suffix in r11
    ul_class_field: str = "ca-BandwidthClassUL-r10"
    dl_class_field: str = "ca-BandwidthClassDL-r10"
    dl_mimo_field: str = "supportedMIMO-CapabilityDL-r10"


def _map_eutra_ca_combo(
    combo_node: TreeNode, *, fmt: _ComboFormat, idx: int, source: str
) -> EutraCaCombination | None:
    cc_parent = (
        combo_node.get(fmt.cc_list_field)
        if fmt.cc_list_field
        else combo_node
    )
    if cc_parent is None:
        return None

    entries: list[EutraComboBandEntry] = []
    for cc_node in cc_parent.list_items():
        band = _get_int(cc_node, fmt.band_field)
        if band is None:
            continue
        dl_class, dl_mimo = _read_band_params_dl(cc_node.get(fmt.dl_field), fmt)
        ul_class = _read_band_params_ul(cc_node.get(fmt.ul_field), fmt)
        entries.append(
            EutraComboBandEntry(
                band=band,
                caBandwidthClassDL=dl_class,
                caBandwidthClassUL=ul_class,
                maxLayersDL=dl_mimo,
            )
        )
    if not entries:
        return None

    label = "-".join(f"{e.band}{e.caBandwidthClassDL or ''}" for e in entries)
    return EutraCaCombination(
        combinationId=idx,
        label=label,
        bands=entries,
        source=source,  # type: ignore[arg-type]
    )


def _read_band_params_dl(
    node: TreeNode | None, fmt: _ComboFormat
) -> tuple[CaBandwidthClass | None, int | None]:
    if node is None or not node.children:
        return None, None
    inner = node.children[0]
    cls = _parse_bw_class(_value(inner.get(fmt.dl_class_field)))
    mimo = _parse_mimo(_value(inner.get(fmt.dl_mimo_field)))
    return cls, mimo


def _read_band_params_ul(node: TreeNode | None, fmt: _ComboFormat) -> CaBandwidthClass | None:
    if node is None or not node.children:
        return None
    inner = node.children[0]
    return _parse_bw_class(_value(inner.get(fmt.ul_class_field)))


def _merge_eutra_bcs(combos: list[EutraCaCombination], ext_node: TreeNode | None) -> None:
    """Patch BCS bitmaps from a parallel Ext list into combos in place."""
    if ext_node is None:
        return
    for combo, ext_item in zip(combos, ext_node.list_items()):
        bcs = _parse_binary_string(ext_item.get("supportedBandwidthCombinationSet-r10"))
        if bcs:
            combo.bcs = bcs


def _parse_binary_string(node: TreeNode | None) -> list[int] | None:
    """Parse a QCAT BIT STRING node, returning the positions of set bits.

    QCAT uses two forms:
      Form A (LTE Ext-r10): ``field`` contains a ``Binary string (Bin) : <bits>`` child.
      Form B (NR inline):   ``field : <bits>`` with no inner wrapper.
    """
    if node is None:
        return None
    bin_node = node.get("Binary string (Bin)")
    if bin_node is not None and bin_node.value:
        bits = bin_node.value.strip()
    elif node.value:
        bits = node.value.strip()
    else:
        return None
    if not bits or any(c not in "01" for c in bits):
        return None
    return [i for i, b in enumerate(bits) if b == "1"]


# ─── NR section mapping ─────────────────────────────────────────────


@dataclass(frozen=True)
class _NrPerCcTables:
    """Per-CC feature-set tables (always sourced from UE-NR-Capability.featureSets)."""

    downlink: list[TreeNode]
    uplink: list[TreeNode]
    dl_per_cc: list[TreeNode]
    ul_per_cc: list[TreeNode]


@dataclass(frozen=True)
class _ResolvedNrCaps:
    scs: int | None = None
    channel_bw_dl: str | None = None
    channel_bw_ul: str | None = None
    max_layers_dl: int | None = None
    max_layers_ul: int | None = None
    modulation_dl: Modulation | None = None
    modulation_ul: Modulation | None = None


def _collect_nr_per_cc_tables(root: TreeNode) -> _NrPerCcTables:
    ue_nr = _find_first(root, "ue-NR-Capability")
    if ue_nr is None:
        return _NrPerCcTables([], [], [], [])
    fs = ue_nr.get("featureSets")
    if fs is None:
        return _NrPerCcTables([], [], [], [])
    return _NrPerCcTables(
        downlink=_list_under(fs, "featureSetsDownlink"),
        uplink=_list_under(fs, "featureSetsUplink"),
        dl_per_cc=_list_under(fs, "featureSetsDownlinkPerCC"),
        ul_per_cc=_list_under(fs, "featureSetsUplinkPerCC"),
    )


def _map_nr(rat_container: TreeNode, per_cc: _NrPerCcTables) -> NrSection:
    ue_nr = rat_container.get("ue-NR-Capability")
    if ue_nr is None:
        return NrSection(accessStratumRelease="unknown", supportedBands=[], bandCombinations=[])

    asr = _value(ue_nr.get("accessStratumRelease")) or "unknown"

    bands: list[NrBand] = []
    rf = ue_nr.get("rf-Parameters")
    if rf is not None:
        sbl = rf.get("supportedBandListNR")
        if sbl is not None:
            for item in sbl.list_items():
                b = _get_int(item, "bandNR")
                if b is not None:
                    bands.append(NrBand(band=b, fr=_derive_fr(b), scsSupported=[]))

    # UE-NR-Capability's own featureSetCombinations sits inside featureSets.
    fs_root = ue_nr.get("featureSets")
    combinations = _list_under(fs_root, "featureSetCombinations") if fs_root else []

    combos: list[NrBandCombination] = []
    main = _find_first(ue_nr, "supportedBandCombinationList")
    if main is not None:
        for i, c in enumerate(main.list_items()):
            combo = _map_nr_band_combination(
                c, idx=i, source="main", combinations=combinations, per_cc=per_cc
            )
            if combo is not None:
                combos.append(combo)

    return NrSection(
        accessStratumRelease=asr,
        supportedBands=bands,
        bandCombinations=combos,
    )


def _list_under(parent: TreeNode, name: str) -> list[TreeNode]:
    n = parent.get(name)
    return n.list_items() if n is not None else []


def _map_nr_band_combination(
    combo_node: TreeNode,
    *,
    idx: int,
    source: NrComboSource,
    combinations: list[TreeNode],
    per_cc: _NrPerCcTables,
) -> NrBandCombination | None:
    entries, has_eutra, has_nr, fsc_id = _extract_combo_band_entries(
        combo_node, combinations, per_cc
    )
    if not entries:
        return None

    has_mrdc = combo_node.get("mrdc-Parameters") is not None
    if has_eutra:
        kind: NrComboKind = "endc"
    elif has_mrdc and has_nr:
        kind = "nrdc"
    else:
        kind = "caNR"

    return NrBandCombination(
        combinationId=idx,
        label=_make_combo_label(entries),
        kind=kind,
        bands=entries,
        bcs=_parse_binary_string(combo_node.get("supportedBandwidthCombinationSet")),
        featureSetCombinationId=fsc_id if fsc_id >= 0 else None,
        powerClassNR=_normalize_power_class(_value(combo_node.get("powerClass-v1530"))),
        source=source,
    )


# ─── MRDC mapper ────────────────────────────────────────────────────


def _map_mrdc(rat_container: TreeNode, per_cc: _NrPerCcTables) -> MrdcSection:
    ue_mrdc = rat_container.get("ue-MRDC-Capability")
    if ue_mrdc is None:
        return MrdcSection(bandCombinations=[])

    # MRDC's combinations table is a direct child of ue-MRDC-Capability
    # (not under a `featureSets` wrapper as in NR).
    combinations = _list_under(ue_mrdc, "featureSetCombinations")

    rfm = ue_mrdc.get("rf-ParametersMRDC")
    if rfm is None:
        return MrdcSection(bandCombinations=[])

    combos: list[MrdcBandCombination] = []
    _append_mrdc_combos(combos, rfm.get("supportedBandCombinationList"),
                        kind="endc", source="main", combinations=combinations, per_cc=per_cc)
    _append_mrdc_combos(combos, rfm.get("supportedBandCombinationListNEDC-Only-r16"),
                        kind="nedc", source="nedcOnlyR16", combinations=combinations, per_cc=per_cc)
    _append_mrdc_combos(combos, rfm.get("supportedBandCombinationListNRDC-r16"),
                        kind="nrdc", source="nrdcR16", combinations=combinations, per_cc=per_cc)
    return MrdcSection(bandCombinations=combos)


def _append_mrdc_combos(
    combos: list[MrdcBandCombination],
    list_node: TreeNode | None,
    *,
    kind: MrdcComboKind,
    source: MrdcComboSource,
    combinations: list[TreeNode],
    per_cc: _NrPerCcTables,
) -> None:
    if list_node is None:
        return
    start_idx = len(combos)
    for i, c in enumerate(list_node.list_items()):
        combo = _map_mrdc_band_combination(
            c, idx=start_idx + i, kind=kind, source=source,
            combinations=combinations, per_cc=per_cc,
        )
        if combo is not None:
            combos.append(combo)


def _map_mrdc_band_combination(
    combo_node: TreeNode,
    *,
    idx: int,
    kind: MrdcComboKind,
    source: MrdcComboSource,
    combinations: list[TreeNode],
    per_cc: _NrPerCcTables,
) -> MrdcBandCombination | None:
    entries, _, _, fsc_id = _extract_combo_band_entries(combo_node, combinations, per_cc)
    if not entries:
        return None
    return MrdcBandCombination(
        combinationId=idx,
        label=_make_combo_label(entries),
        kind=kind,
        bands=entries,
        bcs=_parse_binary_string(combo_node.get("supportedBandwidthCombinationSet")),
        featureSetCombinationId=fsc_id if fsc_id >= 0 else None,
        powerClassNR=_normalize_power_class(_value(combo_node.get("powerClass-v1530"))),
        source=source,
    )


# ─── Shared NR/MRDC band-list walk + label ───────────────────────────


def _extract_combo_band_entries(
    combo_node: TreeNode,
    combinations: list[TreeNode],
    per_cc: _NrPerCcTables,
) -> tuple[list[NrComboBandEntry], bool, bool, int]:
    """Walk ``combo.bandList``, resolve NR feature sets per band, return entries.

    Returns ``(entries, has_eutra, has_nr, fsc_id)`` where ``fsc_id`` is the
    0-indexed ``featureSetCombination`` or -1 if absent.
    """
    band_list = combo_node.get("bandList")
    if band_list is None:
        return [], False, False, -1

    fsc_id_raw = _get_int(combo_node, "featureSetCombination")
    fsc_id = fsc_id_raw if fsc_id_raw is not None else -1

    has_eutra = False
    has_nr = False
    entries: list[NrComboBandEntry] = []

    for i, band_node in enumerate(band_list.list_items()):
        flavor = _value(band_node.get("BandParameters"))
        flavor = flavor.strip() if flavor else None
        if flavor == "eutra":
            has_eutra = True
            entries.append(
                NrComboBandEntry(
                    bandEUTRA=_get_int(band_node, "bandEUTRA"),
                    caBandwidthClassDL=_parse_bw_class(_value(band_node.get("ca-BandwidthClassDL-EUTRA"))),
                    caBandwidthClassUL=_parse_bw_class(_value(band_node.get("ca-BandwidthClassUL-EUTRA"))),
                )
            )
        elif flavor == "nr":
            has_nr = True
            caps = _resolve_nr_caps(
                band_idx=i, fsc_id=fsc_id, combinations=combinations, per_cc=per_cc
            )
            entries.append(
                NrComboBandEntry(
                    bandNR=_get_int(band_node, "bandNR"),
                    caBandwidthClassDL=_parse_bw_class(_value(band_node.get("ca-BandwidthClassDL-NR"))),
                    caBandwidthClassUL=_parse_bw_class(_value(band_node.get("ca-BandwidthClassUL-NR"))),
                    scs=caps.scs,
                    channelBWDL=caps.channel_bw_dl,
                    channelBWUL=caps.channel_bw_ul,
                    maxLayersDL=caps.max_layers_dl,
                    maxLayersUL=caps.max_layers_ul,
                    modulationDL=caps.modulation_dl,
                    modulationUL=caps.modulation_ul,
                )
            )

    return entries, has_eutra, has_nr, fsc_id


def _make_combo_label(entries: list[NrComboBandEntry]) -> str:
    parts: list[str] = []
    for e in entries:
        cls = (e.caBandwidthClassDL or "").upper()
        if e.bandNR is not None:
            parts.append(f"n{e.bandNR}{cls}")
        elif e.bandEUTRA is not None:
            parts.append(f"{e.bandEUTRA}{cls}")
    return "-".join(parts)


def _resolve_nr_caps(
    *,
    band_idx: int,
    fsc_id: int,
    combinations: list[TreeNode],
    per_cc: _NrPerCcTables,
) -> _ResolvedNrCaps:
    """Walk the feature-set indirection for one band in one combo.

    ``fsc_id`` is the 0-indexed ``featureSetCombination`` reference; the
    downstream ``downlinkSetNR`` / ``uplinkSetNR`` / CC IDs are 1-indexed
    with 0 meaning "no feature set."
    """
    if fsc_id < 0 or fsc_id >= len(combinations):
        return _ResolvedNrCaps()
    per_band_entries = combinations[fsc_id].list_items()
    if band_idx >= len(per_band_entries):
        return _ResolvedNrCaps()
    fspb_alts = per_band_entries[band_idx].list_items()
    if not fspb_alts:
        return _ResolvedNrCaps()
    first_alt = fspb_alts[0]
    if _value(first_alt.get("FeatureSet")) != "nr":
        return _ResolvedNrCaps()

    dl_set = _get_int(first_alt, "downlinkSetNR") or 0
    ul_set = _get_int(first_alt, "uplinkSetNR") or 0
    dl = _resolve_per_cc(
        dl_set, per_cc.downlink, per_cc.dl_per_cc,
        cc_list_field="featureSetListPerDownlinkCC",
        scs_field="supportedSubcarrierSpacingDL",
        bw_field="supportedBandwidthDL",
        mimo_field="maxNumberMIMO-LayersPDSCH",
        mod_field="supportedModulationOrderDL",
    )
    ul = _resolve_per_cc(
        ul_set, per_cc.uplink, per_cc.ul_per_cc,
        cc_list_field="featureSetListPerUplinkCC",
        scs_field="supportedSubcarrierSpacingUL",
        bw_field="supportedBandwidthUL",
        mimo_field="maxNumberMIMO-LayersPUSCH",
        mod_field="supportedModulationOrderUL",
    )

    return _ResolvedNrCaps(
        scs=dl["scs"] or ul["scs"],
        channel_bw_dl=dl["bw"],
        channel_bw_ul=ul["bw"],
        max_layers_dl=dl["layers"],
        max_layers_ul=ul["layers"],
        modulation_dl=dl["mod"],
        modulation_ul=ul["mod"],
    )


def _resolve_per_cc(
    set_idx: int,
    fs_list: list[TreeNode],
    per_cc_list: list[TreeNode],
    *,
    cc_list_field: str,
    scs_field: str,
    bw_field: str,
    mimo_field: str,
    mod_field: str,
) -> dict:
    """Resolve a FeatureSetDownlink/Uplink → first CC → FeatureSetXPerCC entry."""
    empty = {"scs": None, "bw": None, "layers": None, "mod": None}
    if set_idx <= 0 or set_idx > len(fs_list):
        return empty
    cc_list = fs_list[set_idx - 1].get(cc_list_field)
    if cc_list is None or not cc_list.children:
        return empty
    # List items have form "[N] : <cc_id>"
    first = cc_list.children[0]
    try:
        cc_id = int(first.value.strip()) if first.value else 0
    except (AttributeError, ValueError):
        cc_id = 0
    if cc_id <= 0 or cc_id > len(per_cc_list):
        return empty
    fspc = per_cc_list[cc_id - 1]
    return {
        "scs": _parse_scs(_value(fspc.get(scs_field))),
        "bw": _parse_channel_bw(fspc.get(bw_field)),
        "layers": _parse_mimo(_value(fspc.get(mimo_field))),
        "mod": _parse_modulation(_value(fspc.get(mod_field))),
    }


_SCS_MAP: dict[str, int] = {
    "kHz15": 15,
    "kHz30": 30,
    "kHz60": 60,
    "kHz120": 120,
    "kHz240": 240,
    "kHz480": 480,
    "kHz960": 960,
}

_MOD_MAP: dict[str, Modulation] = {
    "qam64": "qam64",
    "qam256": "qam256",
    "qam1024": "qam1024",
}

_POWER_CLASS_MAP: dict[str, PowerClassNR] = {
    "pc1dot5": "pc1dot5",
    "pc2": "pc2",
    "pc3": "pc3",
    "pc5": "pc5",
}


def _parse_scs(s: str | None) -> int | None:
    return _SCS_MAP.get(s.strip()) if s else None


def _parse_channel_bw(node: TreeNode | None) -> str | None:
    """``supportedBandwidthDL`` is a CHOICE { fr1, fr2 } — pick the chosen branch's value."""
    if node is None:
        return None
    flavor = _value(node.get("SupportedBandwidth"))
    if not flavor:
        return None
    branch = node.get(flavor.strip())
    return branch.value.strip() if branch and branch.value else None


def _parse_modulation(s: str | None) -> Modulation | None:
    return _MOD_MAP.get(s.strip()) if s else None


def _normalize_power_class(s: str | None) -> PowerClassNR | None:
    return _POWER_CLASS_MAP.get(s.strip()) if s else None


def _derive_fr(band: int) -> FrequencyRange:
    """Bands 1..256 → FR1, 257+ → FR2 (heuristic; spec-tracked actually)."""
    return "FR2" if band >= 257 else "FR1"


_MIMO_LAYERS: dict[str, int] = {
    "oneLayer": 1,
    "twoLayers": 2,
    "fourLayers": 4,
    "eightLayers": 8,
}


def _parse_mimo(s: str | None) -> int | None:
    return _MIMO_LAYERS.get(s.strip()) if s else None


def _parse_bw_class(s: str | None) -> CaBandwidthClass | None:
    if not s:
        return None
    upper = s.strip().upper()
    if upper in ("A", "B", "C", "D", "E", "F"):
        return upper  # type: ignore[return-value]
    return None


def _value(node: TreeNode | None) -> str | None:
    return node.value if node and node.value is not None else None


def _get_int(parent: TreeNode, name: str) -> int | None:
    node = parent.get(name)
    if node is None or not node.value:
        return None
    try:
        return int(node.value.strip())
    except ValueError:
        return None


def _get_bool(parent: TreeNode, name: str) -> bool:
    node = parent.get(name)
    if node is None or not node.value:
        return False
    return node.value.strip().lower() == "true"


def _find_first(root: TreeNode, name: str) -> TreeNode | None:
    """Breadth-first search for the first node whose ``name`` matches."""
    queue: list[TreeNode] = [root]
    while queue:
        n = queue.pop(0)
        if n.name == name:
            return n
        queue.extend(n.children)
    return None
