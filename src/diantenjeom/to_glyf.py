"""Convert a CFF2 variable font to glyf+gvar in-place.

Called at the very end of subset_one(), after all CFF2 outline surgery.
The conversion is intentionally minimal: we only touch the outline tables
(CFF2 → glyf, add gvar for the wght variation) and leave every other table
(GSUB, GPOS, fvar, STAT, vmtx, …) untouched.

Why at the end: the surgery modules in this package all write CFF2 charstrings
and depend on CFF2 data structures.  Keeping them unchanged and converting
once at the end avoids porting ~600 lines of surgery code to TTGlyphPen.

Algorithm (1-axis wght VF):
  1. Drop HVAR/VVAR to work around an instancer bug (our subsets have ~0
     advance-width variation on the wght axis, so these tables carry no
     information).
  2. Instantiate two static CFF2 clones: one at wght-min (the default master)
     and one at wght-max.
  3. For each glyph, record cubic-bezier drawing from both masters and replay
     through Cu2QuMultiPen → TTGlyphPen.  Cu2QuMultiPen guarantees that the
     two masters end up with the same number of quadratic segments (a
     requirement for gvar interpolation).
  4. Assemble a glyf table from the default-master quads.
  5. Compute per-glyph gvar deltas as (max_coords − default_coords), plus
     four phantom-point deltas (all zeros because advances don't vary).
  6. Drop CFF2 / VORG (CFF-only tables); install glyf / loca / gvar / gasp.
"""
from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from fontTools.pens.cu2quPen import Cu2QuMultiPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import newTable
from fontTools.ttLib.tables import _g_l_y_f as _glyf_mod
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.varLib.instancer import instantiateVariableFont

if TYPE_CHECKING:
    from fontTools.ttLib import TTFont

# Maximum cu2qu approximation error in font units.  1.0 ≈ 0.1 % of a 1000-unit
# em — standard for web fonts; same value the upstream Noto CJK TTF uses.
_MAX_ERR = 1.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _make_instance(font: TTFont, wght: float) -> TTFont:
    """Return a static CFF2 copy of *font* pinned at the given wght value."""
    fc = copy.deepcopy(font)
    # Drop HVAR/VVAR before instantiating — they contain delta indices that
    # don't survive subsetting cleanly, and advances don't vary on wght anyway.
    for tbl in ("HVAR", "VVAR"):
        if tbl in fc:
            del fc[tbl]
    return instantiateVariableFont(fc, {"wght": wght}, inplace=True)


def _record(font: TTFont, glyph_name: str) -> list[tuple]:
    """Return the SegmentPen recording for *glyph_name* from *font*."""
    pen = RecordingPen()
    font.getGlyphSet()[glyph_name].draw(pen)
    return pen.value


def _convert_glyph(
    rec_def: list[tuple],
    rec_max: list[tuple],
    hmtx_def: dict[str, tuple[int, int]],
    glyph_name: str,
) -> tuple["_glyf_mod.Glyph | None", "_glyf_mod.Glyph | None"]:
    """Convert one glyph's cubic recordings to quadratic TTGlyph objects.

    Returns (glyph_at_default, glyph_at_max), or (None, None) for empty glyphs.
    """
    if not rec_def or rec_def == [("endPath", ())]:
        return None, None

    advance, lsb = hmtx_def.get(glyph_name, (0, 0))
    pen_def = TTGlyphPen(None)
    pen_max = TTGlyphPen(None)

    multi = Cu2QuMultiPen(
        [pen_def, pen_max],
        max_err=_MAX_ERR,
        reverse_direction=True,  # CFF uses clockwise; TrueType uses CCW
    )

    # Merge the two recordings into the Cu2QuMultiPen's multi-master protocol:
    # each segment method receives a list of per-master argument tuples.
    assert len(rec_def) == len(rec_max), (
        f"{glyph_name}: masters have different segment counts "
        f"({len(rec_def)} vs {len(rec_max)})"
    )
    for (op_d, args_d), (op_m, args_m) in zip(rec_def, rec_max):
        assert op_d == op_m, f"{glyph_name}: op mismatch {op_d!r} vs {op_m!r}"

        if op_d == "moveTo":
            # args: ((x, y),)  → list of single-point tuples, one per master
            multi.moveTo([args_d, args_m])
        elif op_d == "lineTo":
            multi.lineTo([args_d, args_m])
        elif op_d == "curveTo":
            # args: (cp1, cp2, end)  → list of cp-tuples, one per master
            multi.curveTo([args_d, args_m])
        elif op_d == "qCurveTo":
            multi.qCurveTo([args_d, args_m])
        elif op_d == "closePath":
            multi.closePath()
        elif op_d == "endPath":
            multi.endPath()

    g_def = pen_def.glyph()
    g_max = pen_max.glyph()
    g_def.recalcBounds(None)
    g_max.recalcBounds(None)
    return g_def, g_max


def _build_gvar(
    glyph_order: list[str],
    glyphs_def: dict[str, "_glyf_mod.Glyph | None"],
    glyphs_max: dict[str, "_glyf_mod.Glyph | None"],
    hmtx: dict[str, tuple[int, int]],
) -> object:
    from fontTools.ttLib.tables._g_v_a_r import table__g_v_a_r

    gvar = table__g_v_a_r()
    gvar.version = 1
    gvar.reserved = 0
    gvar.variations = {}

    # wght axis normalized: default=wmin=0, wmax=1
    axes = {"wght": (0.0, 1.0, 1.0)}

    for gname in glyph_order:
        g_def = glyphs_def.get(gname)
        g_max = glyphs_max.get(gname)
        if g_def is None or g_max is None:
            gvar.variations[gname] = []
            continue

        coords_def = list(g_def.coordinates)
        coords_max = list(g_max.coordinates)

        if len(coords_def) != len(coords_max):
            # Should not happen after Cu2QuMultiPen, but guard anyway.
            gvar.variations[gname] = []
            continue

        # Outline deltas
        deltas: list[tuple[int, int] | None] = []
        all_zero = True
        for (xd, yd), (xm, ym) in zip(coords_def, coords_max):
            dx, dy = xm - xd, ym - yd
            if dx or dy:
                all_zero = False
            deltas.append((dx, dy) if (dx or dy) else None)

        # 4 phantom points: LSB x, RSB x, TSB y, BSB y.  Advances don't
        # vary with wght in diantenjeom (confirmed empirically), so all zero.
        deltas += [None, None, None, None]

        if all_zero:
            gvar.variations[gname] = []
        else:
            gvar.variations[gname] = [TupleVariation(axes, deltas)]

    return gvar


def _add_gasp(font: TTFont) -> None:
    """Add a Noto-style gasp table so Windows doesn't alias unhinted glyphs."""
    if "gasp" in font:
        return
    g = newTable("gasp")
    g.version = 1
    g.gaspRange = {0xFFFF: 0x000F}  # gridfit+dogray+sym_gridfit+sym_smooth
    font["gasp"] = g


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def cff2_to_glyf(font: TTFont) -> None:
    """Convert *font* from CFF2+fvar to glyf+gvar in-place.

    All outline tables are replaced; everything else (GSUB, GPOS, fvar, STAT,
    hmtx, vmtx, …) is preserved.
    """
    fvar = font["fvar"]
    wght_ax = next(a for a in fvar.axes if a.axisTag == "wght")
    w_def = wght_ax.defaultValue
    w_max = wght_ax.maxValue

    f_def = _make_instance(font, w_def)
    f_max = _make_instance(font, w_max)

    glyph_order = font.getGlyphOrder()
    hmtx = font["hmtx"].metrics  # advance, lsb for every glyph

    glyphs_def: dict[str, "_glyf_mod.Glyph | None"] = {}
    glyphs_max: dict[str, "_glyf_mod.Glyph | None"] = {}

    for gname in glyph_order:
        rec_def = _record(f_def, gname)
        rec_max = _record(f_max, gname)
        g_def, g_max = _convert_glyph(rec_def, rec_max, hmtx, gname)
        glyphs_def[gname] = g_def
        glyphs_max[gname] = g_max

    # Build glyf table
    glyf_table = _glyf_mod.table__g_l_y_f()
    glyf_table.glyphs = {
        gname: g if g is not None else _glyf_mod.Glyph()
        for gname, g in glyphs_def.items()
    }
    glyf_table.glyphOrder = glyph_order

    gvar_table = _build_gvar(glyph_order, glyphs_def, glyphs_max, hmtx)

    # Replace CFF2 outline infrastructure with glyf
    for tbl in ("CFF2", "VORG", "HVAR", "VVAR"):
        if tbl in font:
            del font[tbl]

    font["glyf"] = glyf_table
    loca = newTable("loca")
    font["loca"] = loca
    font["gvar"] = gvar_table

    # The container must follow the outlines: 'OTTO' declares CFF/CFF2, and a
    # glyf font wearing it crashes FreeType outright (Android!) and fails OTS.
    # 0x00010000 is the TrueType-outline sfntVersion.
    font.sfntVersion = "\x00\x01\x00\x00"

    # head.indexToLocFormat: 0 = short (<=0xFFFF bytes), 1 = long.
    # With ~140 glyphs the table is small; fontTools picks the right value
    # on save, so just set a safe default.
    font["head"].indexToLocFormat = 1

    # Upgrade maxp from v0.5 (CFF) to v1.0 (glyf).  All the hinting-related
    # fields are 0 because we're unhinted.
    maxp = font["maxp"]
    if maxp.tableVersion != 0x00010000:
        maxp.tableVersion = 0x00010000
        for field in (
            "maxZones", "maxTwilightPoints", "maxStorage",
            "maxFunctionDefs", "maxInstructionDefs",
            "maxStackElements", "maxSizeOfInstructions",
            "maxComponentElements", "maxComponentDepth",
        ):
            setattr(maxp, field, 0)

    _add_gasp(font)
