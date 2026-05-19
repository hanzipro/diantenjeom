"""Align `locl` substitution targets back to the cmap source glyph.

For split-family variants (Dot / Mark) we want the cmap-level design
to be the rendered design **regardless of document `lang`**. But
`lang` selects an OT LangSys whose `locl` lookups may substitute the
face's cmap glyphs to a different locale-specific alternate (e.g.
JP source's ZHT locl swaps `、 。 ， ．` to ZHT-centred forms).

Pinning locl to a langsys that doesn't substitute these codepoints
(via `pin_locale._alias_locl_to_locale`) doesn't work for small
subsets: the subsetter prunes locl FRs that have no entries on the
face's cmap. The target langsys we want to pin to has already been
dropped from GSUB, so the alias finds nothing and silently skips.

This module takes a different angle: **leave the locl mapping alone,
but overwrite the locl target glyph's outline + metrics with the cmap
source's**. Effect:

    * `locl` still fires (Chrome's `text-spacing-trim` gate sees
      substitutions on the face's cmap codepoints).
    * Post-`locl` rendered glyph is visually identical to the cmap
      glyph (the design we want).
    * Behaviour identical across all document `lang` values.

CRITICAL constraint
-------------------
Only safe when **every member of a kChar group** (the four dots
`、 。 ， ．`, or the four marks `： ； ！ ？`, etc.) has its locl
targets aligned uniformly. Doing only some — e.g. align `．`'s locl
target but not `、 。 ，`'s — creates mixed-type post-locl
classification across Chromium's 4-dot consistency check, disabling
the entire font's trim. See `docs/chrome-pair-squeeze.md` test 5.
"""

from __future__ import annotations

from fontTools.ttLib import TTFont


def install(font: TTFont, codepoints: tuple[int, ...]) -> None:
    """For each `cp` in `codepoints`:

    1. **Horizontal**: copy the cmap source glyph's outline + metrics
       into every `locl` SingleSubst target glyph so locl firing
       renders visually identical to cmap.

    2. **Vertical**: rewrite each locl target's `vert`/`vrt2`
       substitution to point at the same vert target as the cmap
       source. Without this step, paths diverge: under document
       `lang` that fires locl, vert tries to substitute on the
       locl-target glyph and either misses (no sub fires, locl-target
       renders as horizontal design in vertical slot) or hits a
       different vert form than the cmap path (e.g. SC FE13 form
       instead of the variant's intended vert design). This makes
       both shape paths (with / without locl) converge on the same
       final glyph in vertical layout too.
    """
    if not codepoints or "GSUB" not in font:
        return

    cmap = font.getBestCmap()
    gsub = font["GSUB"].table

    for cp in codepoints:
        src_name = cmap.get(cp)
        if src_name is None:
            continue
        locl_targets = _collect_locl_targets(gsub, src_name)

        # 1. Horizontal: copy outline + metrics into locl targets.
        for tgt_name in locl_targets:
            if tgt_name == src_name:
                continue
            _copy_charstring(font, src_name, tgt_name)
            _copy_metrics(font, src_name, tgt_name)

        # 2. Vertical: find cmap's vert target, and route locl targets
        #    to the same. If cmap has no vert sub, treat as self —
        #    locl target's vert sub becomes self too (i.e. render as
        #    locl-target glyph itself, whose horizontal outline we just
        #    aligned to cmap).
        v_target = _find_vert_target(gsub, src_name)
        if v_target is None:
            v_target = src_name
        for tgt_name in locl_targets:
            if tgt_name == src_name:
                continue
            _set_vert_sub(gsub, tgt_name, v_target)


def _collect_locl_targets(gsub_table, src_name: str) -> set[str]:
    """Return every glyph name that any `locl` SingleSubst lookup
    maps `src_name` to."""
    targets: set[str] = set()
    for fr in gsub_table.FeatureList.FeatureRecord:
        if fr.FeatureTag != "locl":
            continue
        for li in fr.Feature.LookupListIndex:
            lookup = gsub_table.LookupList.Lookup[li]
            # Don't filter by LookupType — locl lookups are often type
            # 7 (Extension) wrapping a type-1 SingleSubst. Deref into
            # ExtSubTable below; only entries with `.mapping` matter.
            for st in lookup.SubTable:
                while hasattr(st, "ExtSubTable"):
                    st = st.ExtSubTable
                if hasattr(st, "mapping") and src_name in st.mapping:
                    targets.add(st.mapping[src_name])
    return targets


def _find_vert_target(gsub_table, src_name: str) -> str | None:
    """Return the glyph name that `src_name` substitutes to under any
    `vert` / `vrt2` SingleSubst lookup. Returns `src_name` itself if a
    self-sub is present (e.g. from `upright_cps`). Returns `None` if
    `src_name` has no vert sub at all."""
    for fr in gsub_table.FeatureList.FeatureRecord:
        if fr.FeatureTag not in ("vert", "vrt2"):
            continue
        for li in fr.Feature.LookupListIndex:
            lookup = gsub_table.LookupList.Lookup[li]
            for st in lookup.SubTable:
                while hasattr(st, "ExtSubTable"):
                    st = st.ExtSubTable
                if hasattr(st, "mapping") and src_name in st.mapping:
                    return st.mapping[src_name]
    return None


def _set_vert_sub(gsub_table, src_glyph: str, target_glyph: str) -> None:
    """Ensure every `vert`/`vrt2` SingleSubst lookup that mentions
    `src_glyph` maps it to `target_glyph` (rewrites existing entries).
    If `src_glyph` isn't in any vert SingleSubst lookup, append the
    mapping to the first such lookup encountered (this guarantees the
    sub fires under whichever LangSys references that lookup, which
    `pin_locale._alias_vert_to_locale` has unified)."""
    found = False
    first_mapping = None
    for fr in gsub_table.FeatureList.FeatureRecord:
        if fr.FeatureTag not in ("vert", "vrt2"):
            continue
        for li in fr.Feature.LookupListIndex:
            lookup = gsub_table.LookupList.Lookup[li]
            for st in lookup.SubTable:
                while hasattr(st, "ExtSubTable"):
                    st = st.ExtSubTable
                if hasattr(st, "mapping"):
                    if first_mapping is None:
                        first_mapping = st.mapping
                    if src_glyph in st.mapping:
                        st.mapping[src_glyph] = target_glyph
                        found = True
    if not found and first_mapping is not None:
        first_mapping[src_glyph] = target_glyph


def _copy_charstring(font: TTFont, src_name: str, tgt_name: str) -> None:
    cs = font["CFF2"].cff[0].CharStrings
    if src_name not in cs.charStrings or tgt_name not in cs.charStrings:
        return
    src_cs = cs[src_name]
    src_cs.decompile()
    tgt_cs = cs[tgt_name]
    tgt_cs.program = list(src_cs.program)
    tgt_cs.bytecode = None


def _copy_metrics(font: TTFont, src_name: str, tgt_name: str) -> None:
    if "hmtx" in font:
        m = font["hmtx"].metrics
        if src_name in m and tgt_name in m:
            m[tgt_name] = m[src_name]
    if "vmtx" in font:
        m = font["vmtx"].metrics
        if src_name in m and tgt_name in m:
            m[tgt_name] = m[src_name]
    if "VORG" in font:
        vorg = font["VORG"].VOriginRecords
        if src_name in vorg:
            vorg[tgt_name] = vorg[src_name]
