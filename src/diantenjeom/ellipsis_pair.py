"""Split U+2026 behaviour between single (Latin) and paired (CJK).

When `…` appears alone, render the Latin convention — three small dots
near the baseline (used in English / Western text). When `…` is followed
by another `…`, swap both occurrences back to the CJK form — three dots
centred on the line, so the pair reads as six centred dots (used in
Chinese / Japanese).

How it works
------------
1. Copy the source `ellipsis` outline into a new sibling glyph
   `ellipsis.cjk` — preserves the CJK-middle form for the paired case.
2. Modify the original `ellipsis` glyph in place: translate its outline
   down by `_LATIN_LOW_DY`. Keeping the same glyph ID means every
   metric table (hmtx LSB, vmtx, HVAR / VVAR) keeps referencing the
   same id, no rename gymnastics from fontTools on save.
3. Clear HVAR / VVAR entries on the modified glyph (set to
   "no variation"). The source's varStore deltas were calibrated for
   the original outline; applying them to the shifted outline shifts
   position at non-default weights.
4. Retarget the existing `vert` substitution (originally
   `ellipsis → glyph00042`) to fire on `ellipsis.cjk` instead, so single
   ellipsis in vertical mode no longer maps to the CJK vertical stack.
5. Add a Chain Context Substitution (GSUB Type 6) under `ccmp`: when
   `ellipsis` is followed by another `ellipsis`, substitute both with
   `ellipsis.cjk`. We use `ccmp` because every shaping engine applies
   it in every writing mode (calt and liga were observed flaky for
   CJK runs in Firefox vertical-rl). The two input positions get
   separate Coverage objects — Safari/CoreText silently ignores a
   chain context whose input positions share one Coverage reference.

Vertical mode mostly emerges for free:
    - Paired `……` → ellipsis.cjk × 2 → (vert subst) glyph00042 × 2 →
      six dots stacked vertically on the line centre. Identical to the
      previous vertical behaviour for `……`.
    - Single `…` has no `vert` substitution any more, so the browser
      auto-rotates / positions it per its own logic. Chrome and Safari
      place it on the Latin baseline; Firefox places it slightly higher
      (within a rotated Latin run) — `_LATIN_LOW_DY = -360` is the
      compromise that's least-wrong across all three.
"""

from __future__ import annotations

from fontTools.misc.transform import Transform
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot


# Distance (font units) by which to translate the ellipsis outline
# downward. Source dots sit at y ~ 330-430 (em*0.4 centre); shifting by
# -330 puts them at y ~ 0-100, resting on the Latin baseline.
_LATIN_LOW_DY: int = -360

# Codepoint we're switching.
_CP: int = 0x2026


def install(font: TTFont) -> None:
    cmap = font.getBestCmap()
    src_name = cmap.get(_CP)
    if src_name is None:
        return
    cjk_name = f"{src_name}.cjk"

    # 1. Copy the original CJK-middle outline to a NEW glyph that will
    #    only be reachable through the pair substitution.
    _add_translated_glyph(font, src_name, cjk_name, dy=0)

    # 2. Modify the ORIGINAL `ellipsis` glyph in place — shift the outline
    #    down to baseline level. Keeping the same glyph ID means every
    #    metric table (hmtx LSB, vmtx tsb, HVAR / VVAR variation maps)
    #    keeps referring to the right thing automatically, and fontTools
    #    won't need to rename anything on save under post format 3.0.
    _shift_glyph_outline_in_place(font, src_name, dy=_LATIN_LOW_DY)
    _clear_variation_entries(font, src_name)

    # 3. Retarget the existing `ellipsis → glyph00042` vertical
    #    substitution to use the new CJK-middle copy instead, so single
    #    ellipsis in vertical mode no longer gets the CJK vertical stack
    #    (which would defeat the Latin-low intent).
    _retarget_vert_subst(font, src_name, cjk_name)

    # 4. Pair chain context: ellipsis ellipsis → ellipsis.cjk ellipsis.cjk
    _add_pair_chain_context(font, find=src_name, replace=cjk_name)


def _add_translated_glyph(
    font: TTFont, src_name: str, new_name: str, dy: int
) -> None:
    """Append a new glyph that's `src_name`'s outline translated by (0, dy)."""
    em = font["head"].unitsPerEm
    advance, _ = font["hmtx"][src_name]

    glyph_set = font.getGlyphSet()
    pen = T2CharStringPen(None, glyph_set, CFF2=True)
    glyph_set[src_name].draw(TransformPen(pen, Transform().translate(0, dy)))

    top_dict = font["CFF2"].cff[0]
    charstrings = top_dict.CharStrings
    src_cs = charstrings[src_name]
    new_cs = pen.getCharString(private=src_cs.private, globalSubrs=src_cs.globalSubrs)

    charstrings.charStringsIndex.append(new_cs)
    charstrings.charStrings[new_name] = len(charstrings.charStringsIndex.items) - 1

    src_gid = font.getGlyphID(src_name)
    top_dict.FDSelect.append(top_dict.FDSelect[src_gid])
    top_dict.numGlyphs = len(charstrings.charStringsIndex.items)

    if hasattr(top_dict, "charset") and new_name not in top_dict.charset:
        top_dict.charset.append(new_name)

    glyph_order = font.getGlyphOrder()
    if new_name not in glyph_order:
        font.setGlyphOrder(glyph_order + [new_name])

    # Inherit hmtx LSB from source — our translation is y-only, so the
    # x-extent of the bbox is unchanged. Setting LSB=0 here would make
    # Firefox think the glyph starts 117 units further left than it
    # actually does; in a rotated Latin run that maps to a 117-unit
    # vertical offset (the dots float above the baseline).
    src_adv, src_lsb = font["hmtx"][src_name]
    font["hmtx"].metrics[new_name] = (src_adv, src_lsb)
    if "vmtx" in font:
        # vmtx tsb = VORG_y − bbox_y_max. We shifted bbox_y_max DOWN by
        # |dy|, so tsb grows by |dy| to stay consistent. Keeping the
        # inherited source tsb would leave a mismatch some engines pick
        # up as a layout hint.
        src_v_adv, src_tsb = font["vmtx"].metrics.get(src_name, (em, 0))
        font["vmtx"].metrics[new_name] = (src_v_adv, src_tsb - dy)

    _no_var = 0xFFFFFFFF
    for tag in ("HVAR", "VVAR"):
        if tag not in font:
            continue
        for attr in ("AdvWidthMap", "LsbMap", "RsbMap", "AdvHeightMap", "TsbMap", "BsbMap", "VOrgMap"):
            vmap = getattr(font[tag].table, attr, None)
            if vmap is not None and hasattr(vmap, "mapping"):
                vmap.mapping[new_name] = _no_var


def _clear_variation_entries(font: TTFont, glyph_name: str) -> None:
    """Set HVAR/VVAR entries for `glyph_name` to 'no variation' (0xFFFFFFFF).
    Otherwise the source's varStore deltas keep getting applied to the
    modified outline, shifting position at non-default weights."""
    _no_var = 0xFFFFFFFF
    for tag in ("HVAR", "VVAR"):
        if tag not in font:
            continue
        for attr in ("AdvWidthMap", "LsbMap", "RsbMap", "AdvHeightMap", "TsbMap", "BsbMap", "VOrgMap"):
            vmap = getattr(font[tag].table, attr, None)
            if vmap is not None and hasattr(vmap, "mapping"):
                vmap.mapping[glyph_name] = _no_var


def _shift_glyph_outline_in_place(font: TTFont, glyph_name: str, dy: int) -> None:
    """Translate `glyph_name`'s CFF2 outline by (0, dy) and update vmtx
    tsb to stay consistent with the new bbox top."""
    if "CFF2" not in font:
        return
    charstrings = font["CFF2"].cff[0].CharStrings
    if glyph_name not in charstrings.charStrings:
        return
    target_cs = charstrings[glyph_name]

    glyph_set = font.getGlyphSet()
    pen = T2CharStringPen(None, glyph_set, CFF2=True)
    glyph_set[glyph_name].draw(TransformPen(pen, Transform().translate(0, dy)))
    new_cs = pen.getCharString(private=target_cs.private, globalSubrs=target_cs.globalSubrs)

    idx = charstrings.charStrings[glyph_name]
    charstrings.charStringsIndex.items[idx] = new_cs
    # vmtx tsb intentionally left at the source value (no recompute).
    # Tested both ways: tsb tracking the new bbox vs. left as-is made no
    # difference to Firefox's baseline placement in rotated Latin runs.


def _retarget_vert_subst(font: TTFont, old_src: str, new_src: str) -> None:
    """Rewrite any `vert`/`vrt2` SingleSubst whose input is `old_src` so
    it triggers on `new_src` instead."""
    if "GSUB" not in font:
        return
    gsub = font["GSUB"].table
    lookup_to_feats: dict[int, set[str]] = {}
    for fr in gsub.FeatureList.FeatureRecord:
        for li in fr.Feature.LookupListIndex:
            lookup_to_feats.setdefault(li, set()).add(fr.FeatureTag)
    for li_idx, lookup in enumerate(gsub.LookupList.Lookup):
        if not (lookup_to_feats.get(li_idx, set()) & {"vert", "vrt2"}):
            continue
        for st in lookup.SubTable:
            if hasattr(st, "mapping") and old_src in st.mapping:
                st.mapping[new_src] = st.mapping.pop(old_src)


def _add_pair_chain_context(font: TTFont, find: str, replace: str) -> None:
    """Add a GSUB Chain Context lookup under `calt` that, when two `find`
    glyphs appear in a row, substitutes BOTH with `replace`."""
    gsub = font["GSUB"].table

    # Nested SingleSubst: find -> replace
    inner = ot.SingleSubst()
    inner.mapping = {find: replace}
    inner_lookup = ot.Lookup()
    inner_lookup.LookupType = 1
    inner_lookup.LookupFlag = 0
    inner_lookup.SubTable = [inner]
    inner_lookup.SubTableCount = 1
    inner_idx = len(gsub.LookupList.Lookup)
    gsub.LookupList.Lookup.append(inner_lookup)

    # Chain Context Format 3: input = [find, find], apply inner at both
    # positions when the run matches. Build TWO separate Coverage objects
    # — CoreText (Safari) has been observed silently ignoring a chain
    # context whose input positions share the same Coverage reference.
    chain = ot.ChainContextSubst()
    chain.Format = 3
    chain.BacktrackGlyphCount = 0
    chain.BacktrackCoverage = []
    cov_a = ot.Coverage()
    cov_a.glyphs = [find]
    cov_b = ot.Coverage()
    cov_b.glyphs = [find]
    chain.InputGlyphCount = 2
    chain.InputCoverage = [cov_a, cov_b]
    chain.LookAheadGlyphCount = 0
    chain.LookAheadCoverage = []

    sub0 = ot.SubstLookupRecord()
    sub0.SequenceIndex = 0
    sub0.LookupListIndex = inner_idx
    sub1 = ot.SubstLookupRecord()
    sub1.SequenceIndex = 1
    sub1.LookupListIndex = inner_idx
    chain.SubstLookupRecord = [sub0, sub1]
    chain.SubstCount = 2

    chain_lookup = ot.Lookup()
    chain_lookup.LookupType = 6
    chain_lookup.LookupFlag = 0
    chain_lookup.SubTable = [chain]
    chain_lookup.SubTableCount = 1
    chain_idx = len(gsub.LookupList.Lookup)
    gsub.LookupList.Lookup.append(chain_lookup)
    gsub.LookupList.LookupCount = len(gsub.LookupList.Lookup)

    # Attach to ccmp (Glyph Composition/Decomposition). ccmp is in the
    # "required" feature set — every shaping engine applies it on every
    # script in every writing mode. calt/liga are nominally always-on but
    # some engines (Firefox observed) skip them for CJK runs in vertical
    # writing mode. Putting our chain context in ccmp avoids the issue.
    _attach_to_feature(gsub, "ccmp", chain_idx)


def _attach_to_feature(table, tag: str, lookup_idx: int) -> None:
    """Attach `lookup_idx` to every existing feature record with `tag`,
    or create the feature record (and wire it into every script's
    DefaultLangSys) if none exists."""
    records = [fr for fr in table.FeatureList.FeatureRecord if fr.FeatureTag == tag]
    if records:
        for fr in records:
            fr.Feature.LookupListIndex.append(lookup_idx)
            fr.Feature.LookupCount = len(fr.Feature.LookupListIndex)
        return

    feature = ot.Feature()
    feature.FeatureParams = None
    feature.LookupListIndex = [lookup_idx]
    feature.LookupCount = 1

    fr = ot.FeatureRecord()
    fr.FeatureTag = tag
    fr.Feature = feature

    new_feat_idx = len(table.FeatureList.FeatureRecord)
    table.FeatureList.FeatureRecord.append(fr)
    table.FeatureList.FeatureCount = len(table.FeatureList.FeatureRecord)

    for script_rec in table.ScriptList.ScriptRecord:
        script = script_rec.Script
        lang_systems = []
        if script.DefaultLangSys is not None:
            lang_systems.append(script.DefaultLangSys)
        for lsr in script.LangSysRecord:
            lang_systems.append(lsr.LangSys)
        for lang_sys in lang_systems:
            lang_sys.FeatureIndex.append(new_feat_idx)
            lang_sys.FeatureCount = len(lang_sys.FeatureIndex)
