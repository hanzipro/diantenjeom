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
    """For each `cp` in `codepoints`, walk every `locl` SingleSubst
    lookup; any entry whose source is `cmap[cp]` has its target glyph
    overwritten with the source's outline + metrics."""
    if not codepoints or "GSUB" not in font:
        return

    cmap = font.getBestCmap()
    gsub = font["GSUB"].table

    for cp in codepoints:
        src_name = cmap.get(cp)
        if src_name is None:
            continue
        for tgt_name in _collect_locl_targets(gsub, src_name):
            if tgt_name == src_name:
                continue
            _copy_charstring(font, src_name, tgt_name)
            _copy_metrics(font, src_name, tgt_name)


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
