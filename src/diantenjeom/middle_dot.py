"""Unify `·` (U+00B7, Latin middle dot) with `・` (U+30FB, katakana
middle dot) — both codepoints render as the full-width katakana mark.

Background
----------
Source Noto CJK maps `·` to the Latin `periodcentered` glyph (small
proportional dot, ~0.25 em advance) and `・` to a full-width CJK dot
glyph. Visually they're very different — Latin `·` sits on the
baseline and takes about a quarter em; CJK `・` is a small mark
centred in a full em box, with `halt` / `palt` / `vhal` / `vpal`
designer-tuned half-width variants.

In CJK typography both characters serve the same role (name
separator: `武那·禮告` / `ハンナ・伍茂`), but the Latin codepoint
U+00B7 is what most input methods produce. Without intervention the
two codepoints render inconsistently — same conceptual mark, two
different shapes, font-size dependent.

This module re-routes the `cmap` entry for U+00B7 to point at the
same glyph as U+30FB. Effect:

  * Both codepoints render the full-width CJK middle dot.
  * The Latin `periodcentered` glyph becomes orphaned in the cmap
    (the subsetter could prune it on a later pass, but it's small
    so we leave it).
  * GPOS halt/palt/vhal/vpal coverage on `・`'s glyph applies to
    `·` too — automatic half-width behaviour in horizontal mode
    when Chromium fires halt.
  * vert/vrt2 lookups are keyed by glyph name, not codepoint, so
    `·` inherits whatever vertical handling `・`'s glyph has
    (Noto's `・` has no vert sub — relies on vhal/vpal positioning).
  * Lang-invariant: cmap is a single table, no LangSys context.

Trade-off
---------
Loses the Latin proportional `·` rendering. Users who want the
narrow Latin middle dot need to use a different font for U+00B7
(or work around with `font-variant-east-asian` / explicit glyph
selection — neither of which Diantenjeom supports today).

This trade-off is intentional per the project's design rationale:
Diantenjeom is a CJK punctuation font; the Latin `·` rendering of
U+00B7 is a fallback default that doesn't match the CJK typography
conventions Diantenjeom enforces.
"""

from __future__ import annotations

from fontTools.ttLib import TTFont


def install(font: TTFont,
            src_codepoint: int = 0x00B7,
            target_codepoint: int = 0x30FB) -> None:
    """Re-route every `cmap` subtable's `src_codepoint` entry to point
    at `target_codepoint`'s glyph. No-op if either codepoint isn't
    present in the cmap."""
    cmap = font.getBestCmap()
    target_glyph = cmap.get(target_codepoint)
    if target_glyph is None:
        return
    for table in font["cmap"].tables:
        if src_codepoint in table.cmap:
            table.cmap[src_codepoint] = target_glyph
