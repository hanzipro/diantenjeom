"""Pin the JP subset to behave as JP regardless of the document's OT
language tag.

Why this exists
---------------
Removing `locl` (see build.py KEEP_FEATURES) stops glyph-level locale
substitution, but Noto CJK also encodes locale variation a second way:
multiple `vert` / `vrt2` feature records, each bound to a different OT
LangSys (DFLT/JAN, KOR, ZHT, ZHS), each pointing at a different lookup
set. A page with `lang="zh-Hant"` resolves to the ZHT LangSys, which in
JP's source font omits the colon-rotation lookup (Chinese vertical
typesetting traditionally keeps the colon stacked, not rotated).

For a JP-locale subset we want every page — regardless of `lang` — to
render with JP conventions. The cleanest way is to strip every
non-default LangSysRecord from each Script. With no language-specific
override present, every OT language falls back to DefaultLangSys, which
holds the JAN-style vert / vrt2 wiring we want.
"""

from __future__ import annotations

from fontTools.ttLib import TTFont


# Feature tags whose locale-specific variants we collapse to the JAN
# (DefaultLangSys) version. CoreText reaches into orphaned LangSys-less
# feature records by tag, so stripping LangSysRecord isn't enough — every
# record sharing one of these tags must point at JAN's lookup list.
_LOCALE_VARIANT_TAGS = ("vert", "vrt2")


def _jan_vert_lookups(table) -> list[int] | None:
    """Return the lookup list that DefaultLangSys's `vert` feature uses
    (i.e. JAN convention — what JP renders in vertical mode)."""
    feature_list = table.FeatureList.FeatureRecord
    for sr in table.ScriptList.ScriptRecord:
        ds = sr.Script.DefaultLangSys
        if ds is None:
            continue
        for fi in ds.FeatureIndex:
            if feature_list[fi].FeatureTag == "vert":
                return list(feature_list[fi].Feature.LookupListIndex)
    return None


def _alias_vert_to_jan(table) -> None:
    """Rewrite every vert AND vrt2 feature record to reference JAN's vert
    lookup list.

    Why touch vrt2: Safari/CoreText prefers vrt2 over vert. The source's
    vrt2 only has [4, 9] which doesn't include the colon-rotation lookup
    that JAN's vert provides via #5, so Safari skips rotating `：`. Pinning
    vrt2 to JAN's superset gets Safari and Chrome aligned.

    Why NOT a union of all vert/vrt2 records: the KOR/ZHS-specific records
    also substitute `；！？` (rotated), which is wrong under JP convention
    where only `：` should rotate. Pulling JAN's list specifically pins JP
    behaviour cleanly.
    """
    jan = _jan_vert_lookups(table)
    if not jan:
        return
    for fr in table.FeatureList.FeatureRecord:
        if fr.FeatureTag in _LOCALE_VARIANT_TAGS:
            fr.Feature.LookupListIndex = list(jan)
            fr.Feature.LookupCount = len(jan)


# Tr-class codepoints (UTR50) that JP convention keeps upright in
# vertical mode but for which the font has no `vert` substitution. Without
# a vert entry, strict UTR50 implementations (Firefox) rotate them 90° CW
# per the Tr default. We register a self-substitution to signal "vert
# handling exists, render upright with the substituted (= same) glyph".
_TR_UPRIGHT_CODEPOINTS = (0xFF1B,)  # ；分號


def _force_upright(font: TTFont, table, codepoints: tuple[int, ...]) -> None:
    """Override existing vert/vrt2 SingleSubst entries for `codepoints`
    to map each source glyph to itself (no rotation).

    JP convention rotates ：(U+FF1A) 90° in vertical mode via a SingleSubst
    under JAN's vert. Centered / GB punct styles keep it upright. Stripping
    the entry outright would let Firefox apply the UTR50 Tr-class default
    rotation; rewriting to identity preserves a vert entry so all browsers
    see "vertical handling exists, render upright".
    """
    if not codepoints:
        return
    cmap = font.getBestCmap()
    src_glyphs = {cmap[cp] for cp in codepoints if cp in cmap}
    if not src_glyphs:
        return
    vert_lookups: set[int] = set()
    for fr in table.FeatureList.FeatureRecord:
        if fr.FeatureTag in _LOCALE_VARIANT_TAGS:
            vert_lookups.update(fr.Feature.LookupListIndex)
    for li in vert_lookups:
        lookup = table.LookupList.Lookup[li]
        if lookup.LookupType != 1:
            continue
        for st in lookup.SubTable:
            if hasattr(st, "mapping"):
                for g in src_glyphs:
                    if g in st.mapping:
                        st.mapping[g] = g


def _add_upright_self_substs(font: TTFont, table, extras: tuple[int, ...] = ()) -> None:
    cmap = font.getBestCmap()
    feature_list = table.FeatureList.FeatureRecord

    # Find JAN's vert lookup list.
    jan_lookups: list[int] | None = None
    for sr in table.ScriptList.ScriptRecord:
        ds = sr.Script.DefaultLangSys
        if ds is None:
            continue
        for fi in ds.FeatureIndex:
            if feature_list[fi].FeatureTag == "vert":
                jan_lookups = list(feature_list[fi].Feature.LookupListIndex)
                break
        if jan_lookups:
            break
    if not jan_lookups:
        return

    # Pick the first JAN-referenced SingleSubst (type 1) lookup and extend it.
    target_mapping = None
    for li in jan_lookups:
        lookup = table.LookupList.Lookup[li]
        if lookup.LookupType != 1:
            continue
        for st in lookup.SubTable:
            if hasattr(st, "mapping"):
                target_mapping = st.mapping
                break
        if target_mapping is not None:
            break
    if target_mapping is None:
        return

    for cp in _TR_UPRIGHT_CODEPOINTS + tuple(extras):
        glyph = cmap.get(cp)
        if glyph and glyph not in target_mapping:
            target_mapping[glyph] = glyph


def _empty_orphan_lookups(table) -> None:
    """Wipe the substitution maps of GSUB lookups that no feature record
    still references. Firefox has been observed applying orphan lookups
    by tag-walking; clearing the mappings makes them no-ops."""
    referenced: set[int] = set()
    for fr in table.FeatureList.FeatureRecord:
        for li in fr.Feature.LookupListIndex:
            referenced.add(li)
    for li_idx, lookup in enumerate(table.LookupList.Lookup):
        if li_idx in referenced:
            continue
        for st in lookup.SubTable:
            if hasattr(st, "mapping"):
                st.mapping = {}


def install(font: TTFont, extra_upright: tuple[int, ...] = ()) -> None:
    """Pin vert/vrt2 behaviour to JAN regardless of the document's OT
    language tag, plus add identity self-subst for upright codepoints.

    We deliberately do NOT strip non-default LangSysRecord entries from
    Script tables. Chrome's text-spacing-trim consults the GSUB Script /
    LangSys structure as part of its pair-squeeze classification, and
    emptying every LangSysRecord disables the squeeze for every CJK
    punctuation pair across the whole font. See
    `docs/chrome-pair-squeeze.md` for the bisect that pinned this down.

    Aliasing vert / vrt2 FeatureRecord LookupListIndex to JAN's lookup
    list makes the LangSys strip redundant anyway: whichever LangSys
    resolves for the document language, its vert FeatureRecord ends up
    pointing at JAN's lookups (which we then mutate for upright_cps).
    """
    if "GSUB" in font:
        gsub = font["GSUB"].table
        _alias_vert_to_jan(gsub)
        _force_upright(font, gsub, extra_upright)
        _add_upright_self_substs(font, gsub, extra_upright)
        _empty_orphan_lookups(gsub)
