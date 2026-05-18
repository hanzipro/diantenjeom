"""Replace specific punctuation glyphs in a JP-derived subset with
versions sourced from a different Noto CJK locale (e.g. TC).

For the Centered variant we want TC-style centred 、，。 while keeping
JP behaviour for everything else. Building from JP and grafting these
three glyphs from TC is surgical and cheap.

What we copy
------------
For each codepoint we replace, in the destination font:
    * CFF2 CharString (outline, with blend operators preserved)
    * vmtx entry (advance + tsb, vertical positioning)
    * VORG entry (Vertical Origin Y)

We deliberately do NOT touch (by default):
    * hmtx — keeping the JP-base LSB preserves the pair-squeeze signal
      Chrome reads from horizontal metrics. Pass codepoints via
      `hmtx_cps` to override — needed when grafting glyphs whose
      horizontal advance must change too (e.g. SC's full-width curly
      quotes replacing JP's proportional Latin ones).
    * GPOS halt/vhal/palt/vpal — these stay structurally identical to
      the JP base so Chrome's pair-detection logic continues to fire
    * GSUB vert/vrt2 — pin_locale handles vert routing separately via
      `upright_cps`; touching it here would double up

Compatibility precondition
--------------------------
Source and target fonts must share fvar wght axis range and CFF2
VarStore region layout (otherwise blend operators inside the copied
CharStrings reference the wrong regions). Noto Sans CJK and Noto Serif
CJK share these across JP/KR/SC/TC per style, so the check is a guard.
"""

from __future__ import annotations

from pathlib import Path

from fontTools.ttLib import TTFont


def _check_compatible(src: TTFont, dst: TTFont) -> None:
    s_axes = {a.axisTag: (a.minValue, a.maxValue) for a in src["fvar"].axes}
    d_axes = {a.axisTag: (a.minValue, a.maxValue) for a in dst["fvar"].axes}
    if s_axes != d_axes:
        raise ValueError(f"fvar axes differ: src={s_axes} dst={d_axes}")

    def _region_signature(font: TTFont) -> list[tuple]:
        td = font["CFF2"].cff.topDictIndex[0]
        if not hasattr(td, "VarStore"):
            return []
        regions = td.VarStore.otVarStore.VarRegionList.Region
        return [
            tuple(
                (axis.StartCoord, axis.PeakCoord, axis.EndCoord)
                for axis in r.VarRegionAxis
            )
            for r in regions
        ]

    s_sig, d_sig = _region_signature(src), _region_signature(dst)
    if s_sig != d_sig:
        raise ValueError(f"CFF2 VarStore regions differ: src={s_sig} dst={d_sig}")


def _copy_charstring(src: TTFont, dst: TTFont, s_name: str, d_name: str) -> None:
    src_cs = src["CFF2"].cff.topDictIndex[0].CharStrings[s_name]
    src_cs.decompile()
    dst_charstrings = dst["CFF2"].cff.topDictIndex[0].CharStrings
    if d_name not in dst_charstrings:
        raise KeyError(f"{d_name!r} not in destination font")
    dst_cs = dst_charstrings[d_name]
    dst_cs.program = list(src_cs.program)
    dst_cs.bytecode = None


def _copy_vertical_metrics(src: TTFont, dst: TTFont, s_name: str, d_name: str) -> None:
    if "vmtx" in src and "vmtx" in dst and s_name in src["vmtx"].metrics:
        dst["vmtx"].metrics[d_name] = src["vmtx"].metrics[s_name]
    if "VORG" in src and "VORG" in dst:
        s_vorg = src["VORG"].VOriginRecords
        if s_name in s_vorg:
            dst["VORG"].VOriginRecords[d_name] = s_vorg[s_name]


def install(
    font: TTFont,
    source: Path,
    codepoints: tuple[int, ...],
    hmtx_cps: tuple[int, ...] = (),
) -> None:
    if not codepoints:
        return
    src = TTFont(source)
    _check_compatible(src, font)

    src_cmap = src.getBestCmap()
    dst_cmap = font.getBestCmap()
    hmtx_cps_set = set(hmtx_cps)

    for cp in codepoints:
        s_name = src_cmap.get(cp)
        d_name = dst_cmap.get(cp)
        if s_name is None or d_name is None:
            continue
        # Source and dst glyph names may differ even when codepoint is
        # shared (e.g. U+2018 = `quoteleft` in SC but `uni02BB` in JP).
        # We graft by codepoint, not by name: copy src[s_name]'s data
        # into dst[d_name]'s slot.
        _copy_charstring(src, font, s_name, d_name)
        _copy_vertical_metrics(src, font, s_name, d_name)
        if cp in hmtx_cps_set and s_name in src["hmtx"].metrics:
            font["hmtx"].metrics[d_name] = src["hmtx"].metrics[s_name]
