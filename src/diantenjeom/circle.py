"""Hand-drawn U+25CF (BLACK CIRCLE) for CSS `text-emphasis: circle`.

Most CJK fonts draw U+25CF very large (often >50 % em) — visually
overpowering when used as a `text-emphasis` mark above each emphasised
character. We **replace** the source font's existing U+25CF CharString
with our own small clean circle (~30 % em) positioned slightly above
em centre, so emphasis marks read as a tasteful dot rather than a
heavy bullet.

Replacing (rather than adding a new glyph + cmap-rerouting) keeps the
font structure minimal: glyph ID, glyph name, FDSelect entry,
HVAR/VVAR delta-set bindings all stay as the subsetter left them.
The new CharString carries **no blend operators**, so the circle is
static across the wght axis (emphasis marks read better at constant
size, not tracking surrounding text weight). The HVAR/VVAR advance
deltas still apply but their magnitude is small (~tens of units),
visually negligible.

Output design:

    Diameter   500 units (0.50 em) — matches Roboto / Georgia visual
                                     scale; CJK source's own U+25CF
                                     is closer to 0.85 em (too heavy).
    Centre     (500, 650)         — em-horizontal centre, slightly above
                                     mid-line. Sits cleanly above the
                                     character when CSS `text-emphasis-
                                     position: over` is in effect.
    Bbox ink   x ∈ [250, 750], y ∈ [400, 900]
    Advance    1000 horizontal, 1000 vertical
    VORG       880               — Source Han / Noto CJK ascender
    vmtx tsb   −20               — VORG (880) − top-of-ink (900); the
                                    ink top peeks past the ascender by
                                    20 units which is fine for an
                                    emphasis mark (browser positions
                                    above the line anyway).
"""

from __future__ import annotations

from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont


def install(
    font: TTFont,
    codepoint: int = 0x25CF,
    diameter: int = 500,
    cx: int = 500,
    cy: int = 650,
    advance: int = 1000,
    vertical_advance: int = 1000,
    vorg: int = 880,
) -> None:
    """Replace `codepoint`'s CharString + metrics with a hand-drawn
    static circle. No-op if `codepoint` isn't in cmap (e.g., the
    variant's codepoint set excludes U+25CF)."""
    cmap = font.getBestCmap()
    if codepoint not in cmap:
        return

    glyph_name = cmap[codepoint]
    r = diameter / 2
    k = r * 0.5523  # standard cubic-Bezier κ for a 4-segment circle approx

    # CFF2 doesn't encode width in the charstring (it lives in hmtx);
    # pass width=None.
    pen = T2CharStringPen(width=None, glyphSet=None, CFF2=True)
    pen.moveTo((cx + r, cy))
    pen.curveTo((cx + r, cy + k), (cx + k, cy + r), (cx, cy + r))
    pen.curveTo((cx - k, cy + r), (cx - r, cy + k), (cx - r, cy))
    pen.curveTo((cx - r, cy - k), (cx - k, cy - r), (cx, cy - r))
    pen.curveTo((cx + k, cy - r), (cx + r, cy - k), (cx + r, cy))
    pen.closePath()
    new_cs = pen.getCharString()

    # Replace the existing CharString's program (preserves the glyph's
    # FD / private-dict binding and its HVAR/VVAR slot). We swap the
    # program list and clear cached bytecode so the next save re-encodes
    # from `program`.
    existing = font["CFF2"].cff[0].CharStrings[glyph_name]
    existing.decompile()
    existing.program = new_cs.program
    existing.bytecode = None

    # Replace metrics. The source glyph was full-width too (Source Han's
    # U+25CF is a big black disc filling most of em), so advances stay 1000
    # — only lsb (and vmtx tsb) need adjusting to track our smaller bbox.
    font["hmtx"].metrics[glyph_name] = (advance, int(cx - r))
    if "vmtx" in font:
        font["vmtx"].metrics[glyph_name] = (vertical_advance, vorg - int(cy + r))
    if "VORG" in font:
        font["VORG"].VOriginRecords[glyph_name] = vorg
