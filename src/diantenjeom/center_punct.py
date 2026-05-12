"""Brute-force horizontal shift on `! : ; ?` to compensate for the
~10 %-em cross-axis right offset Chrome / Safari apply to these glyphs
in vertical mode.

The offset is reproducible with original (unsubsetted) Noto Sans CJK JP
renamed and shipped as a webfont — so it's not introduced by any of our
fontTools transforms; it's something Chrome / Safari do downstream that
we couldn't pin to any specific font metadata. We translate the source
outline LEFT by `_SHIFT_DX` units (and update hmtx LSB to match) so
the visible position lands back on the line centre in Chrome / Safari.

Firefox renders these glyphs at their outline coords without the same
shift, so it WILL move slightly left too. The hope is the resulting
offset is small enough to be visually acceptable across all three.
"""

from __future__ import annotations

from fontTools.ttLib import TTFont

from diantenjeom._outline import shift_in_place

# Codepoints to shift. Locale-agnostic.
JP: tuple[int, ...] = (0xFF01, 0xFF1A, 0xFF1B, 0xFF1F)  # ! : ; ?

# Shift in font units (em = 1000). Negative = left. The observed C/S
# offset is ~10 % em (-100); Firefox is centred. Shifting outlines
# affects all three browsers equally, so -50 splits the visible delta:
# C/S end up ~5 % right of centre, Firefox ~5 % left, both close enough.
_SHIFT_DX: int = -50


def install(font: TTFont, codepoints: tuple[int, ...] = JP) -> None:
    for cp in codepoints:
        for glyph in _reachable_glyphs(font, cp):
            _shift_outline(font, glyph, _SHIFT_DX)


def _reachable_glyphs(font: TTFont, codepoint: int) -> set[str]:
    """Return the cmap glyph for `codepoint` plus any glyph it
    substitutes to under a `vert` lookup."""
    cmap = font.getBestCmap()
    src = cmap.get(codepoint)
    if src is None:
        return set()
    glyphs = {src}

    if "GSUB" in font:
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
                    target = st.mapping[src]
                    if target != src:
                        glyphs.add(target)
    return glyphs


def _shift_outline(font: TTFont, glyph_name: str, dx: int) -> None:
    """Translate `glyph_name`'s CFF2 outline by (dx, 0) preserving blend
    operators, and update hmtx LSB to track the new bbox x_min."""
    shift_in_place(font, glyph_name, dx, 0)
    if glyph_name in font["hmtx"].metrics:
        adv, lsb = font["hmtx"].metrics[glyph_name]
        font["hmtx"].metrics[glyph_name] = (adv, lsb + dx)
