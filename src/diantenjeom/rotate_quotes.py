"""Force Latin curly quotes (U+2018/2019/201C/201D) to render rotated 90° CW
in vertical writing mode.

Why this exists
---------------
UTR50 classifies all four curly-quote codepoints as `R` (rotate), so by spec
a vertical-mode renderer should rotate them. In practice Chrome / Safari /
Firefox don't all rotate them when they sit at the boundary between CJK and
Latin runs — the shaping engine groups them with CJK neighbours and renders
them upright. There's no CSS-side fix that works per-codepoint without
wrapping every quote in a span.

The font-side fix is to bake a pre-rotated copy of each curly quote, then
register a GSUB `vert` / `vrt2` substitution mapping the original glyph to
the rotated copy. In vertical mode the engine then:

    1. Sees `vert` substitution → uses the rotated glyph
    2. Renders it upright (no further rotation) — which visually IS the 90°
       rotation we want, because the outline is already rotated.

This is the *opposite* of how `vert` is conventionally used (which is to
keep CJK punctuation upright by swapping in a pre-positioned variant), but
the mechanism is the same.

Positioning
-----------
The source glyphs are proportional Latin (advance ~0.23 em for single
quotes, ~0.37 em for double). After rotation we keep the vertical advance
equal to the original horizontal advance — the rotated quote occupies the
same tight footprint vertically, so it hugs the adjacent characters with no
extra padding. The rotated outline is centred horizontally within its
advance and placed around the em mid-line vertically.
"""

from __future__ import annotations

import math
from typing import Iterable

from fontTools.misc.transform import Transform
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot

# Codepoints whose glyphs must be rotated 90° CW in vertical mode.
ROTATE_QUOTES: tuple[int, ...] = (0x2018, 0x2019, 0x201C, 0x201D)


def _add_rotated_glyph(font: TTFont, src_name: str, new_name: str) -> None:
    """Append a 90°-CW-rotated copy of `src_name` to the font as `new_name`."""
    advance, _ = font["hmtx"][src_name]
    em = font["head"].unitsPerEm

    glyph_set = font.getGlyphSet()
    bp = BoundsPen(glyph_set)
    glyph_set[src_name].draw(bp)
    if bp.bounds is None:
        return  # empty glyph (e.g. .notdef) — nothing to rotate

    x_min, y_min, x_max, y_max = bp.bounds
    cx = (x_min + x_max) / 2
    cy = (y_min + y_max) / 2

    # Compose right-to-left: translate(-cx,-cy) brings glyph centre to origin,
    # then rotate -π/2 (CW), then translate to the destination centre.
    # In vertical-rl: glyph local +X is the horizontal cross-axis of the
    # line (high x → right side of line). Latin curly quotes sit near cap
    # height (~0.66 em) in horizontal text; we put the rotated centre at
    # x = 0.66 em so they hug the right side of the vertical line, mirroring
    # that convention. Y centres on em/2 since vAdvance = the glyph's tight
    # advance and the inline placement is decided by the renderer, not by
    # our intra-glyph y.
    t = (
        Transform()
        .translate(em * 0.35, em * 0.5)
        .rotate(-math.pi / 2)
        .translate(-cx, -cy)
    )

    # CFF2 stores advance widths in hmtx, not in the charstring, so the pen
    # must be initialised with width=None.
    pen = T2CharStringPen(None, glyph_set, CFF2=True)
    glyph_set[src_name].draw(TransformPen(pen, t))

    top_dict = font["CFF2"].cff[0]
    charstrings = top_dict.CharStrings
    src_cs = charstrings[src_name]
    new_cs = pen.getCharString(private=src_cs.private, globalSubrs=src_cs.globalSubrs)

    # CharStrings.__setitem__ requires the name to already exist (it edits
    # in place). To append a brand-new glyph we have to extend the underlying
    # index and register the name → index mapping ourselves.
    charstrings.charStringsIndex.append(new_cs)
    charstrings.charStrings[new_name] = len(charstrings.charStringsIndex.items) - 1

    # FDSelect maps glyph-id → Font DICT index in CID-keyed CFF2. The new
    # glyph must inherit the source's FD so it picks up the right Private
    # subrs / vstore at runtime.
    src_gid = font.getGlyphID(src_name)
    top_dict.FDSelect.append(top_dict.FDSelect[src_gid])

    # CFF2 top dict tracks numGlyphs separately; keep it in sync.
    top_dict.numGlyphs = len(charstrings.charStringsIndex.items)

    if hasattr(top_dict, "charset") and new_name not in top_dict.charset:
        top_dict.charset.append(new_name)

    # Update the font-level glyph order LAST, after the CFF internals are in
    # place; some fontTools paths derive names from this list.
    glyph_order = font.getGlyphOrder()
    if new_name not in glyph_order:
        font.setGlyphOrder(glyph_order + [new_name])

    # hmtx: keep the same advance so an accidental horizontal use is sane.
    font["hmtx"].metrics[new_name] = (advance, 0)
    # vmtx: vertical advance = original horizontal advance (tight footprint).
    if "vmtx" in font:
        font["vmtx"].metrics[new_name] = (advance, 0)

    # HVAR/VVAR maps every glyph → variation index. New glyphs need an entry,
    # otherwise compile fails. 0xFFFFFFFF = "no variation, use default" — the
    # rotated quote keeps fixed metrics across the wght axis, which is fine
    # given it's tiny and unweighted-by-design.
    _no_variation = 0xFFFFFFFF
    for tag in ("HVAR", "VVAR"):
        if tag not in font:
            continue
        for attr in ("AdvWidthMap", "LsbMap", "RsbMap", "AdvHeightMap", "TsbMap", "BsbMap", "VOrgMap"):
            vmap = getattr(font[tag].table, attr, None)
            if vmap is not None and hasattr(vmap, "mapping"):
                vmap.mapping[new_name] = _no_variation


def _attach_vert_lookup(font: TTFont, mapping: dict[str, str]) -> None:
    """Add a SingleSubst lookup and wire it into every `vert` / `vrt2` feature."""
    gsub = font["GSUB"].table

    sub = ot.SingleSubst()
    sub.mapping = dict(mapping)

    lookup = ot.Lookup()
    lookup.LookupType = 1  # SingleSubst
    lookup.LookupFlag = 0
    lookup.SubTable = [sub]
    lookup.SubTableCount = 1

    new_idx = len(gsub.LookupList.Lookup)
    gsub.LookupList.Lookup.append(lookup)
    gsub.LookupList.LookupCount = len(gsub.LookupList.Lookup)

    for fr in gsub.FeatureList.FeatureRecord:
        if fr.FeatureTag in ("vert", "vrt2"):
            fr.Feature.LookupListIndex.append(new_idx)
            fr.Feature.LookupCount = len(fr.Feature.LookupListIndex)


def install(font: TTFont, codepoints: Iterable[int] = ROTATE_QUOTES) -> dict[str, str]:
    """Add rotated alternates and `vert`/`vrt2` substitutions for `codepoints`.

    Returns the {src_glyph: rotated_glyph} mapping that was installed.
    """
    cmap = font.getBestCmap()
    mapping: dict[str, str] = {}
    for cp in codepoints:
        src = cmap.get(cp)
        if src is None:
            continue
        rotated = f"{src}.rot90"
        _add_rotated_glyph(font, src, rotated)
        mapping[src] = rotated

    if mapping:
        _attach_vert_lookup(font, mapping)
    return mapping
