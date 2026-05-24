"""Force select codepoints to render rotated 90° CW in vertical writing
mode by baking a pre-rotated glyph + a `vert` / `vrt2` substitution.

Why this exists
---------------
UTR50 classifies all four curly-quote codepoints as `R` (rotate), so by spec
a vertical-mode renderer should rotate them. In practice Chrome / Safari /
Firefox don't all rotate them when they sit at the boundary between CJK and
Latin runs — the shaping engine groups them with CJK neighbours and renders
them upright. There's no CSS-side fix that works per-codepoint without
wrapping every quote in a span.

The font-side fix is to bake a pre-rotated copy of each curly quote, then
register a GSUB `vert` / `vrt2` substitution mapping the original glyph to
the rotated copy. In vertical mode the engine then:

    1. Sees `vert` substitution → uses the rotated glyph
    2. Renders it upright (no further rotation) — which visually IS the 90°
       rotation we want, because the outline is already rotated.

This is the *opposite* of how `vert` is conventionally used (which is to
keep CJK punctuation upright by swapping in a pre-positioned variant), but
the mechanism is the same.

Positioning
-----------
The source glyphs are proportional Latin (advance ~0.23 em for single
quotes, ~0.37 em for double). After rotation we keep the vertical advance
equal to the original horizontal advance — the rotated quote occupies the
same tight footprint vertically, so it hugs the adjacent characters with no
extra padding. The rotated outline is centred horizontally within its
advance and placed around the em mid-line vertically.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from fontTools.misc.transform import Transform
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot


@dataclass(frozen=True)
class RotateConfig:
    """Per-codepoint rotation parameters.

    `x_em` / `y_em` — where the rotated glyph's centre ends up, in em units
        (multiplied by `head.unitsPerEm`).
    `v_advance_em` — vertical advance in em units. `None` means "use the
        source glyph's horizontal advance unchanged" (right for full-width
        glyphs like em-dashes); a small fraction (e.g. 0.4) gives a tight
        slot for narrow Latin curly quotes.
    """
    x_em: float = 0.5
    y_em: float = 0.5
    v_advance_em: float | None = None


# Curly quotes: hug the right side of the line at roughly Latin cap height,
# tight vertical advance so they don't bloat line spacing.
_QUOTE_CONFIG = RotateConfig(x_em=0.35, y_em=0.5, v_advance_em=0.4)

# Default mapping. Locale-agnostic — every CJK locale uses this set
# because Latin curly quotes don't have CJK locale variants.
#
# NOTE: em-dash (U+2014) and 2-em dash (U+2E3A) were attempted here and
# reverted. UTR50 marks them as `R` (always rotate), which Chrome and
# Firefox honour by auto-rotating the source glyph and ignoring `vert`
# substitutions, while Safari applies vert inconsistently between the
# two codepoints. See docs/vertical-text.md "Dash alignment" for the
# full investigation.
ROTATE_CONFIGS: dict[int, RotateConfig] = {
    0x2018: _QUOTE_CONFIG,
    0x2019: _QUOTE_CONFIG,
    0x201C: _QUOTE_CONFIG,
    0x201D: _QUOTE_CONFIG,
}

# Backward-compat shim — only kept for the unlikely caller that imports
# `ROTATE_QUOTES` directly. New code should use `ROTATE_CONFIGS`.
ROTATE_QUOTES: tuple[int, ...] = (0x2018, 0x2019, 0x201C, 0x201D)


def _add_rotated_glyph(
    font: TTFont, src_name: str, new_name: str, cfg: RotateConfig
) -> None:
    """Append a 90°-CW-rotated copy of `src_name` to the font as `new_name`,
    positioned per `cfg`."""
    advance, _ = font["hmtx"][src_name]
    em = font["head"].unitsPerEm

    glyph_set = font.getGlyphSet()
    bp = BoundsPen(glyph_set)
    glyph_set[src_name].draw(bp)
    if bp.bounds is None:
        return  # empty glyph (e.g. .notdef) — nothing to rotate

    x_min, y_min, x_max, y_max = bp.bounds
    cx = (x_min + x_max) / 2
    cy = (y_min + y_max) / 2

    # Compose right-to-left: translate(-cx,-cy) brings glyph centre to
    # origin, then rotate -π/2 (CW), then translate to (x_em, y_em) in em
    # units. Curly quotes anchor at x_em=0.35 to hug the right side of the
    # vertical line at roughly Latin cap height; dashes anchor at 0.5/0.5
    # to sit on the line's centre axis like the ellipsis.
    t = (
        Transform()
        .translate(em * cfg.x_em, em * cfg.y_em)
        .rotate(-math.pi / 2)
        .translate(-cx, -cy)
    )

    # CFF2 stores advance widths in hmtx, not in the charstring, so the pen
    # must be initialised with width=None.
    pen = T2CharStringPen(None, glyph_set, CFF2=True)
    glyph_set[src_name].draw(TransformPen(pen, t))

    top_dict = font["CFF2"].cff[0]
    charstrings = top_dict.CharStrings
    src_cs = charstrings[src_name]
    new_cs = pen.getCharString(private=src_cs.private, globalSubrs=src_cs.globalSubrs)

    # CharStrings.__setitem__ requires the name to already exist (it edits
    # in place). To append a brand-new glyph we have to extend the underlying
    # index and register the name → index mapping ourselves.
    charstrings.charStringsIndex.append(new_cs)
    charstrings.charStrings[new_name] = len(charstrings.charStringsIndex.items) - 1

    # FDSelect maps glyph-id → Font DICT index in CID-keyed CFF2. The new
    # glyph must inherit the source's FD so it picks up the right Private
    # subrs / vstore at runtime.
    src_gid = font.getGlyphID(src_name)
    top_dict.FDSelect.append(top_dict.FDSelect[src_gid])

    # CFF2 top dict tracks numGlyphs separately; keep it in sync.
    top_dict.numGlyphs = len(charstrings.charStringsIndex.items)

    if hasattr(top_dict, "charset") and new_name not in top_dict.charset:
        top_dict.charset.append(new_name)

    # Update the font-level glyph order LAST, after the CFF internals are in
    # place; some fontTools paths derive names from this list.
    glyph_order = font.getGlyphOrder()
    if new_name not in glyph_order:
        font.setGlyphOrder(glyph_order + [new_name])

    # hmtx: keep the same advance so an accidental horizontal use is sane.
    font["hmtx"].metrics[new_name] = (advance, 0)

    # Vertical advance: small em-fraction for curly quotes (tight slot),
    # source hAdvance for dashes (one or two em — consecutive dashes meet
    # end-to-end). Firefox ignores tiny vAdvance and falls back to an
    # OS/2-derived slot; em*0.4 is small enough to feel tight but large
    # enough to keep Firefox in agreement with Chrome/Safari.
    v_advance = round(em * cfg.v_advance_em) if cfg.v_advance_em is not None else advance
    bp_new = BoundsPen(glyph_set)
    glyph_set[src_name].draw(TransformPen(bp_new, t))
    if bp_new.bounds is not None:
        _, ny_min, _, ny_max = bp_new.bounds
        outline_centre = (ny_min + ny_max) / 2
        v_org = round(outline_centre + v_advance / 2)
        tsb = v_org - round(ny_max)
    else:
        v_org = round(em * 0.5 + v_advance / 2)
        tsb = 0

    if "vmtx" in font:
        font["vmtx"].metrics[new_name] = (v_advance, tsb)
    # VORG: pin the per-glyph vertical origin so Safari / Firefox / HarfBuzz
    # know where to place the slot top. Without an explicit entry they fall
    # back to defaultVertOriginY (~880 in Noto CJK) which is far above our
    # rotated outline, pushing the glyph into the gap between characters.
    if "VORG" in font:
        font["VORG"].VOriginRecords[new_name] = v_org

    # HVAR/VVAR maps every glyph → variation index. New glyphs need an entry,
    # otherwise compile fails. 0xFFFFFFFF = "no variation, use default" — the
    # rotated quote keeps fixed metrics across the wght axis, which is fine
    # given it's tiny and unweighted-by-design.
    _no_variation = 0xFFFFFFFF
    for tag in ("HVAR", "VVAR"):
        if tag not in font:
            continue
        for attr in ("AdvWidthMap", "LsbMap", "RsbMap", "AdvHeightMap", "TsbMap", "BsbMap", "VOrgMap"):
            vmap = getattr(font[tag].table, attr, None)
            if vmap is not None and hasattr(vmap, "mapping"):
                vmap.mapping[new_name] = _no_variation


def _attach_vert_lookup(font: TTFont, mapping: dict[str, str]) -> None:
    """Add a SingleSubst lookup and wire it into every `vert` / `vrt2` feature."""
    gsub = font["GSUB"].table

    sub = ot.SingleSubst()
    sub.mapping = dict(mapping)

    lookup = ot.Lookup()
    lookup.LookupType = 1  # SingleSubst
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


def install(
    font: TTFont,
    configs: dict[int, RotateConfig] = ROTATE_CONFIGS,
    clear_locl_for_cps: tuple[int, ...] = (),
) -> dict[str, str]:
    """Bake pre-rotated alternates + `vert`/`vrt2` substitutions for each
    codepoint in `configs`. Returns the {src: rotated} glyph mapping
    that was installed.

    Skips codepoints whose source glyph already has an existing `vert`
    substitution — overriding those would fight the font's designed
    vertical alternates (e.g. ellipsis already has one).

    `clear_locl_for_cps` removes any existing `locl` SingleSubst entry
    keyed on a codepoint's cmap glyph BEFORE installing the vert sub.
    Needed for MOE: `pin_locl_to="ZHT"` brings in Source Han JP's ZHT
    locl, which substitutes the curly quotes to slightly-lifted alternates
    that (a) shift horizontal y by +100 vs JIS and (b) break the kern
    table's PairPos coverage (kern is keyed on the cmap glyph, not the
    locl output) — so MOE horizontal quotes lose the negative kern that
    pulls them tight against neighbours, opening visible gaps absent in
    JIS. Clearing the locl entry restores both behaviours.

    Also extends the vert sub to cover the post-`locl` glyph for each
    src as a defensive fallback for variants that don't clear locl but
    still want the rotated vertical form.
    """
    cmap = font.getBestCmap()
    if clear_locl_for_cps:
        _clear_locl_subs(font, set(clear_locl_for_cps))
    existing_vert = _vert_substitution_sources(font)
    locl_outputs = _locl_outputs(font)
    mapping: dict[str, str] = {}
    for cp, cfg in configs.items():
        src = cmap.get(cp)
        if src is None or src in existing_vert:
            continue
        rotated = f"{src}.rot90"
        _add_rotated_glyph(font, src, rotated, cfg)
        mapping[src] = rotated
        locl_dst = locl_outputs.get(src)
        if locl_dst and locl_dst != src and locl_dst not in existing_vert:
            mapping[locl_dst] = rotated

    if mapping:
        _attach_vert_lookup(font, mapping)
    return mapping


def _clear_locl_subs(font: TTFont, codepoints: set[int]) -> None:
    """Remove SingleSubst entries from every `locl` lookup whose source
    glyph is a cmap entry for any codepoint in `codepoints`. Leaves the
    lookup in place (other entries untouched) — only the targeted keys
    are dropped. Drills into `ExtensionSubst` wrappers, which Source Han
    uses for the bulk of its locl lookups."""
    cmap = font.getBestCmap()
    targets = {cmap[cp] for cp in codepoints if cp in cmap}
    if not targets or "GSUB" not in font:
        return
    gsub = font["GSUB"].table
    lookup_to_feats: dict[int, set[str]] = {}
    for fr in gsub.FeatureList.FeatureRecord:
        for li in fr.Feature.LookupListIndex:
            lookup_to_feats.setdefault(li, set()).add(fr.FeatureTag)
    for li_idx, lookup in enumerate(gsub.LookupList.Lookup):
        if "locl" not in lookup_to_feats.get(li_idx, set()):
            continue
        for st in lookup.SubTable:
            inner = getattr(st, "ExtSubTable", st)
            if not hasattr(inner, "mapping"):
                continue
            for g in list(inner.mapping):
                if g in targets:
                    del inner.mapping[g]


def _locl_outputs(font: TTFont) -> dict[str, str]:
    """Return {src_glyph: locl_substituted_glyph} for every SingleSubst
    in any `locl` lookup. Used to keep the vert rotation alive after a
    locl swap (see install)."""
    out: dict[str, str] = {}
    if "GSUB" not in font:
        return out
    gsub = font["GSUB"].table
    lookup_to_feats: dict[int, set[str]] = {}
    for fr in gsub.FeatureList.FeatureRecord:
        for li in fr.Feature.LookupListIndex:
            lookup_to_feats.setdefault(li, set()).add(fr.FeatureTag)
    for li_idx, lookup in enumerate(gsub.LookupList.Lookup):
        if "locl" not in lookup_to_feats.get(li_idx, set()):
            continue
        for st in lookup.SubTable:
            inner = getattr(st, "ExtSubTable", st)
            if hasattr(inner, "mapping"):
                out.update(inner.mapping)
    return out


def _vert_substitution_sources(font: TTFont) -> set[str]:
    """Return the set of source glyph names that already have a `vert`
    substitution defined in GSUB."""
    sources: set[str] = set()
    if "GSUB" not in font:
        return sources
    gsub = font["GSUB"].table
    lookup_to_feats: dict[int, set[str]] = {}
    for fr in gsub.FeatureList.FeatureRecord:
        for li in fr.Feature.LookupListIndex:
            lookup_to_feats.setdefault(li, set()).add(fr.FeatureTag)
    for li_idx, lookup in enumerate(gsub.LookupList.Lookup):
        if "vert" not in lookup_to_feats.get(li_idx, set()):
            continue
        for st in lookup.SubTable:
            if hasattr(st, "mapping"):
                sources.update(st.mapping.keys())
    return sources
