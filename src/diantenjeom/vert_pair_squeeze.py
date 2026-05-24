"""Vertical pair-squeeze for `：；！？` + opening bracket via GSUB.

Why GSUB (not GPOS)
-------------------
Chromium's vertical layout pipeline reads each glyph's vertical advance
from `vmtx` directly, bypassing GPOS YAdvance adjustments (verified:
PairPos with YAdvance −500 in `vkrn` shapes correctly via HarfBuzz but
produces no visual change in Chrome). GPOS YPlacement *is* respected
(used elsewhere by `vert_nudge`), but YAdvance specifically isn't.

The only reliable way to give a bracket a different vertical advance in
Chrome is to substitute it for a different glyph whose `vmtx` already
encodes the half advance.

Mechanism
---------
1. For each opening bracket's vert-substituted glyph, append a clone
   with outline shifted up by 500 units and `vmtx` advance = 500
   (`tsb` reduced by 500 to compensate the outline shift). The clone's
   ink lives in the top half of the em; in the half-em slot, the next
   character drops in right below.

2. Install a GSUB ChainContextSubst (type 6, format 3) in `ccmp`:

     backtrack: any of [`：` `；` `！` `？`] vert glyphs
     input    : any of the bracket vert glyphs
     action   : SingleSubst replacing the bracket with its clone

3. `ccmp` is required-always-on in every shaping engine, so the
   substitution fires whenever the pair appears regardless of CSS
   feature toggles.

Standalone brackets — or brackets after non-trigger glyphs — keep their
original vert glyph (full em). The squeeze only applies in the targeted
contexts.

Cross-font limitation
---------------------
GSUB only sees glyphs from a single font, so the substitution can only
fire when BOTH the trigger and the bracket render from Diantenjeom (the
common case since both are punctuation). For `中「字」` (CJK char from
a fallback font + bracket from Diantenjeom) the substitution can't see
the prior `中` and won't fire — but that case isn't handled by
Chrome's built-in vertical text-spacing-trim either, so this is no
regression.
"""

from __future__ import annotations

from fontTools.misc.transform import Transform
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot


TRIGGER_CPS: tuple[int, ...] = (
    0xFF1A,  # ：
    0xFF1B,  # ；
    0xFF01,  # ！
    0xFF1F,  # ？
)

BRACKET_CPS: tuple[int, ...] = (
    0x300C,  # 「
    0x300E,  # 『
    0xFF08,  # （
    0x3014,  # 〔
    0x3010,  # 【
    0x3008,  # 〈
    0x300A,  # 《
    0x3016,  # 〖
    0xFF3B,  # ［
    0xFF5B,  # ｛
)


def _find_vert_glyph(font: TTFont, codepoint: int) -> str | None:
    """Return the glyph `codepoint` ends up as in vertical layout. Some
    variants (e.g. GB, pinned to ZHS) have multiple vert/vrt2 lookups that
    chain — a no-op identity sub from one langsys's lookup list, then a
    real sub from another. HarfBuzz applies lookups in lookup-list order
    and each substitution feeds the next. We mirror that by walking every
    vert/vrt2 lookup in order and applying any matching SingleSubst."""
    cmap = font.getBestCmap()
    g = cmap.get(codepoint)
    if g is None:
        return None
    if "GSUB" not in font:
        return g
    gsub = font["GSUB"].table
    lookup_to_feats: dict[int, set[str]] = {}
    for fr in gsub.FeatureList.FeatureRecord:
        for li in fr.Feature.LookupListIndex:
            lookup_to_feats.setdefault(li, set()).add(fr.FeatureTag)
    for li_idx, lookup in enumerate(gsub.LookupList.Lookup):
        if not (lookup_to_feats.get(li_idx, set()) & {"vert", "vrt2"}):
            continue
        for st in lookup.SubTable:
            if hasattr(st, "mapping") and g in st.mapping:
                g = st.mapping[g]
                break  # one substitution per lookup, then move to next lookup
    return g


def _add_shifted_clone(font: TTFont, src_name: str, new_name: str, dy: int) -> None:
    """Append a glyph that's `src_name`'s outline translated by (0, dy).
    Matches `ellipsis_pair._add_translated_glyph` modulo metric defaults."""
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

    # hmtx: inherit from source (no horizontal change).
    src_h_adv, src_lsb = font["hmtx"][src_name]
    font["hmtx"].metrics[new_name] = (src_h_adv, src_lsb)

    _no_var = 0xFFFFFFFF
    for tag in ("HVAR", "VVAR"):
        if tag not in font:
            continue
        for attr in ("AdvWidthMap", "LsbMap", "RsbMap", "AdvHeightMap", "TsbMap", "BsbMap", "VOrgMap"):
            vmap = getattr(font[tag].table, attr, None)
            if vmap is not None and hasattr(vmap, "mapping"):
                vmap.mapping[new_name] = _no_var


def _attach_to_feature(table, tag: str, lookup_idx: int) -> None:
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


def _sorted_by_gid(font: TTFont, glyphs: list[str]) -> list[str]:
    return sorted(glyphs, key=lambda g: font.getGlyphID(g))


def install(
    font: TTFont,
    trigger_cps: tuple[int, ...] = TRIGGER_CPS,
    bracket_cps: tuple[int, ...] = BRACKET_CPS,
) -> None:
    """Install half-advance bracket clones and a `ccmp` chain-context
    substitution that swaps brackets after `：；！？` to their clones."""
    if "GSUB" not in font or "vmtx" not in font:
        return

    triggers = [g for g in (_find_vert_glyph(font, cp) for cp in trigger_cps) if g]
    if not triggers:
        return

    em = font["head"].unitsPerEm
    half = em // 2
    shift = em - half  # = +500 — outline lift and vmtx-tsb decrement

    vmtx = font["vmtx"]

    # 1. Clone every bracket vert glyph with outline shifted +shift up and
    #    vmtx (half-adv, tsb - shift).
    clone_map: dict[str, str] = {}
    for cp in bracket_cps:
        src = _find_vert_glyph(font, cp)
        if src is None or src not in vmtx.metrics:
            continue
        clone = f"{src}.half"
        if clone in font.getReverseGlyphMap():
            clone_map[src] = clone
            continue
        _add_shifted_clone(font, src, clone, shift)
        src_v_adv, src_tsb = vmtx.metrics[src]
        new_tsb = max(0, src_tsb - shift)
        vmtx.metrics[clone] = (half, new_tsb)
        clone_map[src] = clone

    if not clone_map:
        return

    bracket_glyphs = list(clone_map.keys())

    gsub = font["GSUB"].table

    # 2. Inner SingleSubst: bracket → bracket-half
    inner = ot.SingleSubst()
    inner.mapping = dict(clone_map)
    inner_lookup = ot.Lookup()
    inner_lookup.LookupType = 1
    inner_lookup.LookupFlag = 0
    inner_lookup.SubTable = [inner]
    inner_lookup.SubTableCount = 1
    inner_idx = len(gsub.LookupList.Lookup)
    gsub.LookupList.Lookup.append(inner_lookup)

    # 3. ChainContextSubst format 3: backtrack=triggers, input=brackets,
    #    invoke inner SingleSubst on the bracket (SequenceIndex 0).
    chain = ot.ChainContextSubst()
    chain.Format = 3
    chain.BacktrackGlyphCount = 1
    back_cov = ot.Coverage()
    back_cov.glyphs = _sorted_by_gid(font, triggers)
    chain.BacktrackCoverage = [back_cov]

    chain.InputGlyphCount = 1
    input_cov = ot.Coverage()
    input_cov.glyphs = _sorted_by_gid(font, bracket_glyphs)
    chain.InputCoverage = [input_cov]

    chain.LookAheadGlyphCount = 0
    chain.LookAheadCoverage = []

    subrec = ot.SubstLookupRecord()
    subrec.SequenceIndex = 0
    subrec.LookupListIndex = inner_idx
    chain.SubstLookupRecord = [subrec]
    chain.SubstCount = 1

    chain_lookup = ot.Lookup()
    chain_lookup.LookupType = 6  # ChainContextSubst
    chain_lookup.LookupFlag = 0
    chain_lookup.SubTable = [chain]
    chain_lookup.SubTableCount = 1
    chain_idx = len(gsub.LookupList.Lookup)
    gsub.LookupList.Lookup.append(chain_lookup)
    gsub.LookupList.LookupCount = len(gsub.LookupList.Lookup)

    # 4. Wire into ccmp (always-on, applied by every engine on every script).
    _attach_to_feature(gsub, "ccmp", chain_idx)
