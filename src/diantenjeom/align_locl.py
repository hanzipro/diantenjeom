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
from fontTools.ttLib.tables import otTables as ot


def install(font: TTFont, codepoints: tuple[int, ...]) -> None:
    """For each `cp` in `codepoints`:

    1. **Horizontal outline**: copy cmap source's outline + metrics
       into every `locl` SingleSubst target glyph, so locl firing
       renders visually identical to cmap.

    2. **GSUB vert sub**: rewrite each locl target's `vert`/`vrt2`
       SingleSubst to point at the same vert target as cmap. Without
       this, paths diverge: locl-target either misses vert subs (so
       horizontal design renders in vertical slot) or hits a different
       vert form than cmap's. Aligning makes both shape paths converge.

    3. **GPOS halt/vhal/palt/vpal**: ensure cmap glyph is covered by
       each tag (so pair compression fires when cmap renders directly).
       If cmap isn't covered but any locl target IS, copy the locl
       target's ValueRecord to cmap. Locl targets aren't touched
       (they already had their entries from the source). One-way
       copy avoids double-coverage which would compound advance
       reductions across multiple SinglePos lookups for the same
       glyph.
    """
    if not codepoints or "GSUB" not in font:
        return

    cmap = font.getBestCmap()
    gsub = font["GSUB"].table

    for cp in codepoints:
        src_name = cmap.get(cp)
        if src_name is None:
            continue
        locl_targets = [t for t in _collect_locl_targets(gsub, src_name)
                        if t != src_name]

        # 1. Horizontal: copy outline + metrics into locl targets.
        for tgt_name in locl_targets:
            _copy_charstring(font, src_name, tgt_name)
            _copy_metrics(font, src_name, tgt_name)

        # 2. Vertical: find cmap's vert target, route locl targets
        #    to the same. If cmap has no vert sub, treat as self.
        v_target = _find_vert_target(gsub, src_name)
        if v_target is None:
            v_target = src_name
        for tgt_name in locl_targets:
            _set_vert_sub(gsub, tgt_name, v_target)

        # 3. GPOS: add cmap glyph to each halt/vhal/palt/vpal coverage
        #    if it's missing, using a locl-target's ValueRecord as
        #    template. Locl targets are left alone.
        for tag in ("halt", "vhal", "palt", "vpal"):
            _ensure_cmap_covered(font, tag, src_name, locl_targets)


def _ensure_cmap_covered(
    font: TTFont,
    tag: str,
    cmap_glyph: str,
    locl_targets: list[str],
) -> None:
    """If `cmap_glyph` isn't in any `tag` SinglePos coverage but some
    `locl_targets` glyph IS, copy that locl-target's ValueRecord into
    the lookup that contains it, adding `cmap_glyph` to coverage."""
    if "GPOS" not in font:
        return
    gpos = font["GPOS"].table

    # First pass: is cmap_glyph already covered anywhere under this tag?
    # NOTE: don't filter by LookupType — vpal etc. are often type 9
    # (Extension) wrapping a type 1 SinglePos. ExtSubTable deref handles
    # both transparently. Skip subtables without a Coverage attribute
    # (e.g., type 2 PairPos has different shape).
    for fr in gpos.FeatureList.FeatureRecord:
        if fr.FeatureTag != tag:
            continue
        for li in fr.Feature.LookupListIndex:
            lookup = gpos.LookupList.Lookup[li]
            for st in lookup.SubTable:
                while hasattr(st, "ExtSubTable"):
                    st = st.ExtSubTable
                if not hasattr(st, "Coverage"):
                    continue
                if cmap_glyph in st.Coverage.glyphs:
                    return  # already covered, nothing to do

    # Second pass: find first locl-target with an entry and clone it.
    for fr in gpos.FeatureList.FeatureRecord:
        if fr.FeatureTag != tag:
            continue
        for li in fr.Feature.LookupListIndex:
            lookup = gpos.LookupList.Lookup[li]
            for st in lookup.SubTable:
                while hasattr(st, "ExtSubTable"):
                    st = st.ExtSubTable
                if not hasattr(st, "Coverage"):
                    continue
                cov = st.Coverage.glyphs
                donor = next((L for L in locl_targets if L in cov), None)
                if donor is None:
                    continue
                idx = cov.index(donor)
                if st.Format == 1:
                    cov.append(cmap_glyph)
                else:
                    donor_vr = st.Value[idx]
                    new_vr = ot.ValueRecord()
                    for attr in ("XPlacement", "YPlacement",
                                 "XAdvance", "YAdvance"):
                        v = getattr(donor_vr, attr, None)
                        if v:
                            setattr(new_vr, attr, v)
                    cov.append(cmap_glyph)
                    st.Value.append(new_vr)
                    st.ValueCount = len(st.Value)
                return


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
