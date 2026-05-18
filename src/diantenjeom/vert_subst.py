"""Install a GSUB SingleSubst lookup wired into every `vert` / `vrt2`
feature record, mapping cmap codepoint → cmap codepoint.

Used by the SC variant to mirror Noto Sans/Serif CJK SC's default ZHS
behaviour: in vertical mode, the four curly quotes (U+2018/2019/201C/201D)
are substituted to U+FE41-FE44 (corner-bracket vertical presentation
forms). Chinese vertical typesetting conventionally renders 「」『』 in
place of "" '' — Noto SC bakes that as a vert lookup; we replicate it
on the JP-sourced subset.

Mechanism is identical to `rotate_quotes._attach_vert_lookup`. Kept
separate so callers (build.py Variant config) don't have to import
rotate_quotes' private helper.
"""

from __future__ import annotations

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot


def install(font: TTFont, mapping_cps: dict[int, int]) -> None:
    """`mapping_cps`: {src_codepoint: target_codepoint}. Both must already
    resolve via `font.getBestCmap()` (i.e. both glyphs must be present in
    the subset — typically the target codepoint is added to the
    Variant's `unicodes` list and the target glyph grafted from the donor
    locale)."""
    if not mapping_cps or "GSUB" not in font:
        return

    cmap = font.getBestCmap()
    glyph_mapping: dict[str, str] = {}
    for src_cp, tgt_cp in mapping_cps.items():
        src_name = cmap.get(src_cp)
        tgt_name = cmap.get(tgt_cp)
        if src_name is None or tgt_name is None:
            continue
        glyph_mapping[src_name] = tgt_name
    if not glyph_mapping:
        return

    gsub = font["GSUB"].table

    sub = ot.SingleSubst()
    sub.mapping = dict(glyph_mapping)

    lookup = ot.Lookup()
    lookup.LookupType = 1
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
