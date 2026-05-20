"""Pin the JP-source subset to behave as a specific OT LangSys regardless
of the document's HTML lang attribute.

Why this exists
---------------
Removing `locl` (see build.py KEEP_FEATURES) stops glyph-level locale
substitution, but Noto CJK also encodes locale variation a second way:
multiple `vert` / `vrt2` feature records, each bound to a different OT
LangSys (DFLT/JAN, KOR, ZHT, ZHS), each pointing at a different lookup
set. A page with `lang="zh-Hant"` resolves to the ZHT LangSys, which in
JP's source font omits the colon-rotation lookup (Chinese vertical
typesetting traditionally keeps the colon stacked, not rotated).

For a JP-style subset we want every page — regardless of `lang` — to
render with JAN's wiring. For an SC/mainland subset we want every page
to render with ZHS's wiring (FE13-FE16 presentation forms for the four
non-rotated puncts plus FE41-FE44 vertical brackets). The cleanest way
is to alias every vert/vrt2 feature record to the chosen LangSys's
lookup list, so whichever LangSys resolves at runtime, the resulting
vertical-substitution behaviour is identical.
"""

from __future__ import annotations

from fontTools.ttLib import TTFont


# Feature tags whose locale-specific variants we collapse to the JAN
# (DefaultLangSys) version. CoreText reaches into orphaned LangSys-less
# feature records by tag, so stripping LangSysRecord isn't enough — every
# record sharing one of these tags must point at JAN's lookup list.
_LOCALE_VARIANT_TAGS = ("vert", "vrt2")


def _locale_feature_lookups(
    table, locale: str, feature_tag: str
) -> list[int] | None:
    """Return the lookup list that `locale`'s `feature_tag` feature uses.

    `locale="JAN"` resolves to DefaultLangSys (Noto CJK Source Han uses
    JAN as the script default). Anything else walks LangSysRecord for a
    matching `LangSysTag`. Returns `None` if no match.
    """
    feature_list = table.FeatureList.FeatureRecord
    for sr in table.ScriptList.ScriptRecord:
        target_langsys = None
        if locale == "JAN":
            target_langsys = sr.Script.DefaultLangSys
        else:
            for lr in sr.Script.LangSysRecord:
                # OT LangSysTag is 4 bytes, space-padded (e.g. "ZHS ").
                if lr.LangSysTag.strip() == locale:
                    target_langsys = lr.LangSys
                    break
        if target_langsys is None:
            continue
        for fi in target_langsys.FeatureIndex:
            if feature_list[fi].FeatureTag == feature_tag:
                return list(feature_list[fi].Feature.LookupListIndex)
    return None


def _locale_vert_lookups(table, locale: str) -> list[int] | None:
    return _locale_feature_lookups(table, locale, "vert")


def _alias_locl_to_locale(table, locale: str) -> None:
    """Rewrite every `locl` FeatureRecord to reference `locale`'s locl
    lookup list. Makes the locl substitution invariant across document
    `lang`: whatever lang the page sets, the same locl lookup list
    fires (and thus the same glyph substitutions), preserving the
    face's design.

    Used by GB variant (pin to ZHS) so that ZHT/ZHH/JAN locl can't
    overwrite our SC-style cmap design under non-zh-Hans document lang.
    """
    lookups = _locale_feature_lookups(table, locale, "locl")
    if lookups is None:
        return
    for fr in table.FeatureList.FeatureRecord:
        if fr.FeatureTag == "locl":
            fr.Feature.LookupListIndex = list(lookups)
            fr.Feature.LookupCount = len(lookups)


def _alias_vert_to_locale(table, locale: str) -> None:
    """Rewrite every vert AND vrt2 feature record to reference `locale`'s
    vert lookup list.

    Why touch vrt2: Safari/CoreText prefers vrt2 over vert. The source's
    per-LangSys vrt2 lookup lists are subsets of the corresponding vert
    lists (often only [49] — the generic CJK shared substitutions). To
    keep all three browsers aligned, point vrt2 at the same lookups as
    vert.

    Why NOT a union of all vert/vrt2 records: the KOR/ZHS/ZHT-specific
    records substitute different glyphs for the same codepoints (e.g.
    ZHS sends `:!;?` to FE13-FE16 presentation forms, JAN sends `：` to
    a JP-rotated form). Unioning would chain incompatible substitutions.
    Pinning to a single LangSys keeps the substitution flow coherent.
    """
    lookups = _locale_vert_lookups(table, locale)
    if not lookups:
        return
    for fr in table.FeatureList.FeatureRecord:
        if fr.FeatureTag in _LOCALE_VARIANT_TAGS:
            fr.Feature.LookupListIndex = list(lookups)
            fr.Feature.LookupCount = len(lookups)


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


def _add_upright_self_substs(
    font: TTFont, table, locale: str, extras: tuple[int, ...] = ()
) -> None:
    cmap = font.getBestCmap()

    jan_lookups = _locale_vert_lookups(table, locale)
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


def install(
    font: TTFont,
    extra_upright: tuple[int, ...] = (),
    pin_to_locale: str = "JAN",
    pin_locl_to: str | None = None,
) -> None:
    """Pin vert/vrt2 behaviour to `pin_to_locale` regardless of the
    document's OT language tag, plus add identity self-subst for upright
    codepoints.

    We deliberately do NOT strip non-default LangSysRecord entries from
    Script tables. Chrome's text-spacing-trim consults the GSUB Script /
    LangSys structure as part of its pair-squeeze classification, and
    emptying every LangSysRecord disables the squeeze for every CJK
    punctuation pair across the whole font. See
    `docs/chrome-pair-squeeze.md` for the bisect that pinned this down.

    Aliasing vert / vrt2 FeatureRecord LookupListIndex to the chosen
    LangSys's lookup list makes the LangSys strip redundant anyway:
    whichever LangSys resolves for the document language, its vert
    FeatureRecord ends up pointing at the same lookups (which we then
    mutate for upright_cps).
    """
    if "GSUB" in font:
        gsub = font["GSUB"].table
        _alias_vert_to_locale(gsub, pin_to_locale)
        if pin_locl_to is not None:
            _alias_locl_to_locale(gsub, pin_locl_to)
        _force_upright(font, gsub, extra_upright)
        _add_upright_self_substs(font, gsub, pin_to_locale, extra_upright)
        _empty_orphan_lookups(gsub)
