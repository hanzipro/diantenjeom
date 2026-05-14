"""Shift em dash and 2-em dash outlines up to the CJK character body centre.

The Noto Sans/Serif CJK source ships `—` (U+2014) and `⸺` (U+2E3A) at the
Latin x-height middle (y_center ≈ 275 of em=1000) — designed for Latin
sentences. Under our `lang="zh-Hant"` `locl` chain in the Centered build,
they're substituted to Chinese alternates centred at y ≈ 380 (matches
the CJK character body, e.g. `中` y_center=381). The JP-default build
has `locl` stripped so the cmap glyph renders directly — which leaves
em dashes visually sinking below the CJK character line.

This module nudges the cmap `emdash` / `uni2E3A` outlines up by
`_CJK_CENTER_DY` so both builds render the dashes on the CJK centre line
regardless of locl. Ellipsis (`…`) deliberately stays at Latin-low for
the single-occurrence case (the paired `……` is already a separate
substitution via `ellipsis_pair`).

Why touch cmap outline directly (instead of e.g. adding a GSUB
substitution): the dash is a pure CJK punctuation glyph for this font's
target use; shifting the cmap glyph is the simplest and works in every
shaping mode / language. HVAR / VVAR entries get cleared on the modified
glyph so wght-axis interpolation doesn't drift the dash position.
"""

from __future__ import annotations

from fontTools.ttLib import TTFont

from diantenjeom._outline import shift_in_place


_CJK_CENTER_DY: int = 105
_CODEPOINTS: tuple[int, ...] = (0x2014, 0x2E3A)


def install(font: TTFont) -> None:
    cmap = font.getBestCmap()
    for cp in _CODEPOINTS:
        glyph_name = cmap.get(cp)
        if glyph_name is None:
            continue
        shift_in_place(font, glyph_name, 0, _CJK_CENTER_DY)
        _clear_variation_entries(font, glyph_name)


def _clear_variation_entries(font: TTFont, glyph_name: str) -> None:
    """Set HVAR / VVAR entries for `glyph_name` to 'no variation' so the
    source's varStore deltas (calibrated for the original outline
    position) don't re-shift the dash at non-default weights."""
    _no_var = 0xFFFFFFFF
    for tag in ("HVAR", "VVAR"):
        if tag not in font:
            continue
        for attr in (
            "AdvWidthMap", "LsbMap", "RsbMap",
            "AdvHeightMap", "TsbMap", "BsbMap", "VOrgMap",
        ):
            vmap = getattr(font[tag].table, attr, None)
            if vmap is not None and hasattr(vmap, "mapping"):
                vmap.mapping[glyph_name] = _no_var
