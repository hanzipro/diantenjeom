"""Copy per-glyph GPOS SinglePos entries (halt / palt) from a donor font
into our subset, so CJK punctuation squeeze works on glyphs we grafted.

Why this exists
---------------
For the SC variant we graft full-width curly quote cmap outlines from
Noto SC. The grafted glyph's advance becomes 1000, but the *squeeze*
that the half-width replacement (`halt`) and the proportional
replacement (`palt`) provide for consecutive CJK punctuation pairs
lives in GPOS — and that GPOS data is unique to Noto SC (JP source has
no halt/palt for curly quotes since JP keeps them proportional Latin).

Without copying these entries, `text-spacing-trim` (Chrome) and
explicit `font-feature-settings: 'halt'` see no value for the curly
quote glyphs and the squeeze never fires.

What we copy
------------
For each codepoint:
  * From donor's `halt` lookups → ValueRecord (XPlacement/XAdvance).
  * From donor's `palt` lookups → ValueRecord (per-glyph fine-tune;
    Sans typically has none, Serif has full set).

We install ONE new SinglePos Format 2 lookup per feature tag, covering
every codepoint we found in the donor, and wire its index into our
existing `halt` / `palt` FeatureRecord (which `KEEP_FEATURES` ensures
survives the subset).

Brackets (「」『』) are not in scope — JP source already carries their
halt/palt entries.
"""

from __future__ import annotations

from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot


def install(font: TTFont, source: Path, codepoints: tuple[int, ...]) -> None:
    if not codepoints or "GPOS" not in font:
        return
    src = TTFont(source)

    src_cmap = src.getBestCmap()
    dst_cmap = font.getBestCmap()
    # Map donor glyph name → destination glyph name. Names may diverge
    # (e.g. SC's `quoteleft` matches JP's `uni02BB`, but after grafting
    # from SC the dst cmap exposes `quoteleft` too — confirm via cmap).
    glyph_pairs: list[tuple[str, str]] = []
    for cp in codepoints:
        s = src_cmap.get(cp)
        d = dst_cmap.get(cp)
        if s and d:
            glyph_pairs.append((s, d))
    if not glyph_pairs:
        return

    for tag in ("halt", "palt"):
        donor_values = _collect_singlepos(src, tag, [s for s, _ in glyph_pairs])
        if not donor_values:
            continue
        # Map donor values onto destination glyph names.
        dst_values: dict[str, ot.ValueRecord] = {}
        for s_name, d_name in glyph_pairs:
            if s_name in donor_values:
                dst_values[d_name] = donor_values[s_name]
        if not dst_values:
            continue
        _install_singlepos(font, tag, dst_values)


def _collect_singlepos(
    font: TTFont, feature_tag: str, glyphs: list[str]
) -> dict[str, ot.ValueRecord]:
    """Return {glyph_name: ValueRecord} for each glyph that has a
    SinglePos entry under `feature_tag` in `font`. Format-1 (shared
    value) and Format-2 (per-glyph value) both handled."""
    gpos = font["GPOS"].table
    out: dict[str, ot.ValueRecord] = {}
    glyph_set = set(glyphs)
    for fr in gpos.FeatureList.FeatureRecord:
        if fr.FeatureTag != feature_tag:
            continue
        for li in fr.Feature.LookupListIndex:
            lookup = gpos.LookupList.Lookup[li]
            if lookup.LookupType != 1:
                continue
            for st in lookup.SubTable:
                while hasattr(st, "ExtSubTable"):
                    st = st.ExtSubTable
                cov = list(st.Coverage.glyphs)
                hits = [g for g in cov if g in glyph_set]
                if not hits:
                    continue
                if st.Format == 1:
                    for g in hits:
                        out[g] = _copy_value(st.Value)
                else:  # Format 2
                    for g in hits:
                        idx = cov.index(g)
                        out[g] = _copy_value(st.Value[idx])
    return out


def _copy_value(vr: ot.ValueRecord) -> ot.ValueRecord:
    """Return a fresh ValueRecord with the scalar placement/advance
    fields copied. Device tables and variation indices are dropped —
    halt/palt for CJK punctuation are static across the wght axis."""
    out = ot.ValueRecord()
    for attr in ("XPlacement", "YPlacement", "XAdvance", "YAdvance"):
        v = getattr(vr, attr, None)
        if v:
            setattr(out, attr, v)
    return out


def _install_singlepos(
    font: TTFont, feature_tag: str, values: dict[str, ot.ValueRecord]
) -> None:
    """Append a SinglePos Format 2 lookup with `values` and wire it
    into every existing FeatureRecord whose tag matches."""
    gpos = font["GPOS"].table

    glyphs = sorted(values.keys(), key=lambda g: font.getGlyphID(g))

    sub = ot.SinglePos()
    sub.Format = 2
    sub.Coverage = ot.Coverage()
    sub.Coverage.glyphs = glyphs
    value_format = 0
    for vr in values.values():
        for bit, attr in ((0x0001, "XPlacement"), (0x0002, "YPlacement"),
                          (0x0004, "XAdvance"), (0x0008, "YAdvance")):
            if getattr(vr, attr, None):
                value_format |= bit
    sub.ValueFormat = value_format
    sub.Value = [values[g] for g in glyphs]
    sub.ValueCount = len(sub.Value)

    lookup = ot.Lookup()
    lookup.LookupType = 1
    lookup.LookupFlag = 0
    lookup.SubTable = [sub]
    lookup.SubTableCount = 1

    new_idx = len(gpos.LookupList.Lookup)
    gpos.LookupList.Lookup.append(lookup)
    gpos.LookupList.LookupCount = len(gpos.LookupList.Lookup)

    for fr in gpos.FeatureList.FeatureRecord:
        if fr.FeatureTag == feature_tag:
            fr.Feature.LookupListIndex.append(new_idx)
            fr.Feature.LookupCount = len(fr.Feature.LookupListIndex)
