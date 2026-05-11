"""Force-shift specific CJK punctuation glyphs in vertical writing mode.

Why this is needed
------------------
Locales place certain punctuation differently in vertical text. JP's
《注字後下》 convention puts 、(U+3001) and ，(U+FF0C) tight to the top of
the vert-substituted glyph's em box; TW / ZHT convention centres them; SC
puts them slightly differently again. The default `vert` alternates in
Noto CJK JP follow JP convention by design, so for a JP-locale subset we
nudge them downward to better match common digital body text expectations.
Other locales' subsets should pass their own offsets (or none).

Why three mechanisms
--------------------
No single OpenType knob shifts a CFF2 vertical-mode glyph consistently
across browsers, so we set all three and let each engine pick the one it
listens to:

  * **vmtx tsb** — Chrome's CFF2 vertical pipeline derives glyph y-position
    from top side bearing. Raising tsb by |dy| pushes the glyph down.
  * **VORG (Vertical Origin)** — Safari / CoreText use this. Raising the
    per-glyph VORG_y by |dy| pushes the rendered glyph down.
  * **GPOS SinglePos under `vkrn`** — HarfBuzz / Firefox apply this; on by
    default in vertical mode in every major browser.

Sign convention exposed to callers: a NEGATIVE dy means "move the glyph
DOWN". (Internally vmtx/VORG go up, GPOS YPlacement goes down — we flip
the sign as needed so callers don't have to think about it.)
"""

from __future__ import annotations

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot

# Per-locale default offsets, in font units. Keep keys explicit and
# locale-named so build.py can pick the right dict per Variant.
JP: dict[int, int] = {
    0x3001: -120,  # 、頓號 — Noto JP places it at top-right; nudge down.
    0xFF0C: -120,  # ，全形逗號 — same JP convention.
}


def _find_vert_target(font: TTFont, codepoint: int) -> str | None:
    """Return the glyph name that `codepoint` substitutes to under `vert`."""
    cmap = font.getBestCmap()
    src = cmap.get(codepoint)
    if src is None:
        return None
    gsub = font["GSUB"].table
    lookup_to_feats: dict[int, set[str]] = {}
    for fr in gsub.FeatureList.FeatureRecord:
        for li in fr.Feature.LookupListIndex:
            lookup_to_feats.setdefault(li, set()).add(fr.FeatureTag)
    for li_idx, lookup in enumerate(gsub.LookupList.Lookup):
        if "vert" not in lookup_to_feats.get(li_idx, set()):
            continue
        for st in lookup.SubTable:
            if hasattr(st, "mapping") and src in st.mapping:
                return st.mapping[src]
    return None


def _add_vkrn_singlepos(font: TTFont, offsets: dict[str, tuple[int, int]]) -> None:
    """Add a GPOS SinglePos lookup under `vkrn` with per-glyph (dx, dy)
    placement offsets. Creates the `vkrn` feature record if the subset
    pruned it for being empty."""
    gpos = font["GPOS"].table

    glyph_ids = {g: font.getGlyphID(g) for g in offsets}
    glyphs = sorted(offsets.keys(), key=lambda g: glyph_ids[g])

    sub = ot.SinglePos()
    sub.Format = 2
    sub.Coverage = ot.Coverage()
    sub.Coverage.glyphs = glyphs
    sub.ValueFormat = 0x0001 | 0x0002  # XPlacement | YPlacement
    sub.Value = []
    for g in glyphs:
        dx, dy = offsets[g]
        v = ot.ValueRecord()
        v.XPlacement = dx
        v.YPlacement = dy
        sub.Value.append(v)
    sub.ValueCount = len(sub.Value)

    lookup = ot.Lookup()
    lookup.LookupType = 1  # SinglePos
    lookup.LookupFlag = 0
    lookup.SubTable = [sub]
    lookup.SubTableCount = 1

    new_lookup_idx = len(gpos.LookupList.Lookup)
    gpos.LookupList.Lookup.append(lookup)
    gpos.LookupList.LookupCount = len(gpos.LookupList.Lookup)

    vkrn_records = [
        i for i, fr in enumerate(gpos.FeatureList.FeatureRecord) if fr.FeatureTag == "vkrn"
    ]
    if vkrn_records:
        for i in vkrn_records:
            fr = gpos.FeatureList.FeatureRecord[i]
            fr.Feature.LookupListIndex.append(new_lookup_idx)
            fr.Feature.LookupCount = len(fr.Feature.LookupListIndex)
        return

    feature = ot.Feature()
    feature.FeatureParams = None
    feature.LookupListIndex = [new_lookup_idx]
    feature.LookupCount = 1

    fr = ot.FeatureRecord()
    fr.FeatureTag = "vkrn"
    fr.Feature = feature

    new_feat_idx = len(gpos.FeatureList.FeatureRecord)
    gpos.FeatureList.FeatureRecord.append(fr)
    gpos.FeatureList.FeatureCount = len(gpos.FeatureList.FeatureRecord)

    for script_rec in gpos.ScriptList.ScriptRecord:
        script = script_rec.Script
        lang_systems = []
        if script.DefaultLangSys is not None:
            lang_systems.append(script.DefaultLangSys)
        for lsr in script.LangSysRecord:
            lang_systems.append(lsr.LangSys)
        for lang_sys in lang_systems:
            lang_sys.FeatureIndex.append(new_feat_idx)
            lang_sys.FeatureCount = len(lang_sys.FeatureIndex)


def install(font: TTFont, nudges: dict[int, int]) -> None:
    """Apply per-codepoint vertical-mode nudges.

    `nudges` is {codepoint: dy} where dy is signed font units. Negative dy
    moves the rendered glyph DOWN in the vertical slot.
    """
    if not nudges:
        return

    nudge_offsets: dict[str, tuple[int, int]] = {}
    vmtx = font.get("vmtx")
    vorg = font.get("VORG")
    for cp, dy in nudges.items():
        target = _find_vert_target(font, cp)
        if target is None:
            continue
        nudge_offsets[target] = (0, dy)
        if vmtx is not None and target in vmtx.metrics:
            adv, tsb = vmtx.metrics[target]
            vmtx.metrics[target] = (adv, tsb - dy)
        if vorg is not None:
            current = vorg.VOriginRecords.get(target, vorg.defaultVertOriginY)
            vorg.VOriginRecords[target] = current - dy
    if nudge_offsets:
        _add_vkrn_singlepos(font, nudge_offsets)
