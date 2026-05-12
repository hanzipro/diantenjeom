"""CFF2 charstring helpers that preserve blend / variation data.

`T2CharStringPen` redraws an outline at the default variation instance
and produces a static charstring — useful for new glyphs but lethal
when modifying an existing variable glyph: the wght axis stops working.

`shift_in_place()` prepends a translate operation to a charstring's
program so the entire outline moves by (dx, dy) while the original
blend operators (and therefore the wght-axis variation) stay intact.
"""

from __future__ import annotations

from fontTools.ttLib import TTFont


def shift_in_place(font: TTFont, glyph_name: str, dx: int, dy: int) -> None:
    """Translate `glyph_name`'s CFF2 outline by (dx, dy) without losing
    the existing blend / variation operators."""
    if dx == 0 and dy == 0:
        return
    if "CFF2" not in font:
        return
    charstrings = font["CFF2"].cff[0].CharStrings
    if glyph_name not in charstrings.charStrings:
        return
    cs = charstrings[glyph_name]
    cs.decompile()
    # Prepend `dx dy rmoveto` so the existing first rmoveto runs from
    # (dx, dy) instead of (0, 0). All subsequent ops are relative, so
    # the whole outline shifts uniformly. Blend operators on the
    # original rmoveto / lineto / curveto operators stay untouched.
    cs.program = [dx, dy, "rmoveto"] + cs.program
    cs.bytecode = None  # force re-encode from program on save
