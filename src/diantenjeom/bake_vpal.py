"""Bake `vpal` SinglePos adjustments into static vmtx metrics.

Background
----------
Chrome's vertical `text-spacing-trim` doesn't auto-apply `vhal` / `vpal`
at pair boundaries — empirically confirmed in this project (see memory:
`vertical-no-text-spacing-trim`). Without intervention, vertical
punctuation sits at full em advance regardless of neighbour, leaving
visible gaps for closing brackets / commas / periods between adjacent
glyphs.

GPOS PairPos under `vkrn` looked promising for context-aware
compression but turned out unworkable in this project's setup:

  1. The Segment family splits punctuation across multiple @font-face
     files (Bracket / Dot / Mark / ...). A `』，` pair has `』` shaped
     in the Bracket face and `，` in the Dot face — separate shaping
     runs. PairPos only matches glyphs within a single run, so the
     pair never fires the lookup.
  2. Chrome's vertical shaping doesn't auto-enable `vkrn` either
     (uharfbuzz confirms feature only fires under explicit toggle).

So we fall back to **always-on baking**: copy each glyph's vpal
YPlacement + YAdvance into vmtx. Compression then applies whether
the glyph is paired or isolated, whether the neighbour is in the same
face or not.

Trade-offs
----------
  * Closing brackets / commas etc. lose their trailing space even
    when followed by a regular character — acceptable per JP/CJK
    vertical convention (closing punct is supposed to hug the next
    glyph).
  * Opening brackets at paragraph start render with less leading
    space — minor visual cost.

After baking, vpal coverage is cleared (LookupListIndex emptied)
so explicit `font-feature-settings: 'vpal' 1` is a no-op and doesn't
double-apply on top of the baked vmtx. `vhal` is left untouched —
users can opt into the more aggressive half-width compression
explicitly.

Math
----
For each (glyph, ValueRecord) under vpal, scaled by `scale`:

    new_tsb     = old_tsb - YPlacement * scale  (YPlacement up → tsb shrinks)
    new_advance = old_advance + YAdvance * scale (YAdvance is normally negative)

`scale=0.5` is the project default — half of vpal's typical -500 amount,
tuned via demo-segment.html. Full -500 looked too tight in mixed text;
-250 keeps closing punctuation visibly tight without overlap.
"""

from __future__ import annotations

from fontTools.ttLib import TTFont


def _collect_vert_map(font: TTFont) -> dict[str, str]:
    """Flatten vert/vrt2 SingleSubst lookups into one glyph→glyph map."""
    out: dict[str, str] = {}
    if "GSUB" not in font:
        return out
    gsub = font["GSUB"].table
    for fr in gsub.FeatureList.FeatureRecord:
        if fr.FeatureTag not in ("vert", "vrt2"):
            continue
        for li in fr.Feature.LookupListIndex:
            lookup = gsub.LookupList.Lookup[li]
            for st in lookup.SubTable:
                while hasattr(st, "ExtSubTable"):
                    st = st.ExtSubTable
                if hasattr(st, "mapping"):
                    for src, tgt in st.mapping.items():
                        out.setdefault(src, tgt)
    return out


# Bracket codepoints — the kClass O (open) and C (close) per Chromium's
# han_kerning categorisation. Only these get baked; dots / marks / etc.
# stay at full em advance so they don't squeeze against neighbours.
# (User's design rule: "擠在引號，不擠 dot".)
BRACKET_CPS: tuple[int, ...] = (
    0x300C, 0x300D, 0x300E, 0x300F,          # 「 」 『 』
    0x3008, 0x3009, 0x300A, 0x300B,          # 〈 〉 《 》
    0x3014, 0x3015,                          # 〔 〕
    0xFF08, 0xFF09,                          # （ ）
    0xFF3B, 0xFF3D, 0xFF5B, 0xFF5D,          # ［ ］ ｛ ｝
    0xFE41, 0xFE42, 0xFE43, 0xFE44,          # vertical presentation forms
    0x2018, 0x2019, 0x201C, 0x201D,          # curly quotes (full-width grafts only)
)

# Curly quote codepoints whose inclusion is gated by advance — JP/Centered
# variants leave them as proportional Latin (~230-370 advance) and we
# don't want those squeezed; SC grafts them full-width.
_GATED_CPS = frozenset({0x2018, 0x2019, 0x201C, 0x201D})
_FULLWIDTH_MIN_ADVANCE = 700


def install(font: TTFont, scale: float = 0.5,
            codepoints: tuple[int, ...] = BRACKET_CPS) -> None:
    if "GPOS" not in font or "vmtx" not in font:
        return
    cmap = font.getBestCmap()
    hmtx = font["hmtx"].metrics if "hmtx" in font else {}

    # Glyph names eligible for baking: each codepoint's cmap glyph plus
    # every vert/vrt2 substitution target reachable from it. Curly
    # quote codepoints skipped when their cmap advance is small
    # (proportional Latin rendering — not a CJK bracket).
    eligible: set[str] = set()
    vert_map = _collect_vert_map(font)
    for cp in codepoints:
        glyph = cmap.get(cp)
        if glyph is None:
            continue
        if cp in _GATED_CPS:
            adv = hmtx.get(glyph, (0, 0))[0]
            if adv < _FULLWIDTH_MIN_ADVANCE:
                continue
        eligible.add(glyph)
        v = vert_map.get(glyph)
        if v:
            eligible.add(v)

    gpos = font["GPOS"].table
    vmtx_metrics = font["vmtx"].metrics

    bakes: dict[str, tuple[int, int]] = {}
    for fr in gpos.FeatureList.FeatureRecord:
        if fr.FeatureTag != "vpal":
            continue
        for li in fr.Feature.LookupListIndex:
            lookup = gpos.LookupList.Lookup[li]
            for st in lookup.SubTable:
                while hasattr(st, "ExtSubTable"):
                    st = st.ExtSubTable
                if not hasattr(st, "Coverage"):
                    continue
                cov = list(st.Coverage.glyphs)
                for i, g in enumerate(cov):
                    if g not in eligible or g in bakes:
                        continue
                    vr = st.Value if getattr(st, "Format", None) == 1 else st.Value[i]
                    y_placement = getattr(vr, "YPlacement", None) or 0
                    y_advance = getattr(vr, "YAdvance", None) or 0
                    bakes[g] = (y_placement, y_advance)

    for g, (y_pl, y_adv) in bakes.items():
        if g not in vmtx_metrics:
            continue
        adv, tsb = vmtx_metrics[g]
        vmtx_metrics[g] = (
            adv + int(round(y_adv * scale)),
            tsb - int(round(y_pl * scale)),
        )

    # Drop vpal feature's lookup references entirely so explicit
    # `font-feature-settings: 'vpal' 1` doesn't compound with the
    # baked vmtx. (An empty-Coverage subtable can confuse HarfBuzz —
    # discovered the hard way during the PairPos experiment.)
    for fr in gpos.FeatureList.FeatureRecord:
        if fr.FeatureTag != "vpal":
            continue
        fr.Feature.LookupListIndex = []
        fr.Feature.LookupCount = 0
