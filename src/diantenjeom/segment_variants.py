"""Segment family — Diantenjeom Sans/Serif per-punctuation-group faces.

Each variant carries a **single group** of punctuation, intended to be
combined via CSS `font-family` fallback chains. Two of the groups are
"must-have" anti-clobber faces (Joiner, Curly); the rest are optional
design picks (Dot Anchored / Centered, Bracket, Mark Centered / Centered
Rotated / Anchored). Full design rationale in
`docs/plans/diantenjeom-split.md`.

Built by `scripts/build_segment.py` → `dist/diantenjeom-segment.css`.

Recommended fallback chains documented in README.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from diantenjeom import codepoints, vert_nudge
from diantenjeom.build import Variant


@dataclass(frozen=True)
class SegmentVariant(Variant):
    """Variant subclass adding Segment-only fields. Locale variants
    don't subclass and never set these; `subset_one` accesses via
    `getattr(variant, ..., default)` so the calls are no-op for
    locale runs."""
    # Codepoints whose `locl` substitution targets should be overwritten
    # with the cmap source glyph's outline + metrics, so locl firing
    # renders visually identical to cmap. Used by Dot / Mark Centered
    # variants to keep design stable across document `lang`. Always
    # pass the whole kChar group (4 dots or 4 marks) — partial coverage
    # creates mixed-type post-locl group → Chrome 4-dot gate fails.
    # See `align_locl.install` docstring.
    align_locl_cps: tuple[int, ...] = ()
    # Per-codepoint (dx, dy) translations of the cmap glyph's outline.
    # Used by Dot Centered to translate ．(FF0E) from JP-corner position
    # (~lower-left) to em-centre so it groups as kMiddle alongside the
    # TC-grafted `、 。 ，`. Without this, ．'s lone kClose breaks the
    # 4-dot consistency gate → Chrome trim disables. Translation
    # preserves the outline's blend ops (variation across wght still
    # works); see `_outline.shift_in_place`.
    outline_shifts: dict[int, tuple[int, int]] = field(default_factory=dict)


def variants(sources: Path) -> list[SegmentVariant]:
    sans = sources / "NotoSansCJKjp-VF.otf"
    serif = sources / "NotoSerifCJKjp-VF.otf"
    sans_tc = sources / "NotoSansCJKtc-VF.otf"
    serif_tc = sources / "NotoSerifCJKtc-VF.otf"
    sans_sc = sources / "NotoSansCJKsc-VF.otf"
    serif_sc = sources / "NotoSerifCJKsc-VF.otf"

    return [
        # Joiner — must-have. Defends 中點 / 破折號 / 刪節號 against
        # being clobbered by Latin / system CJK fonts in the fallback
        # chain. No locale-specific behaviour needed.
        SegmentVariant(
            punct="joiner", style="sans",
            source=sans, unicodes=codepoints.JOINER,
            layout_features=("*",),
        ),
        SegmentVariant(
            punct="joiner", style="serif",
            source=serif, unicodes=codepoints.JOINER,
            layout_features=("*",),
        ),

        # Curly — locale-switch face. U+2018-201D have no half/full-
        # width codepoint siblings; same codepoint must render
        # proportional Latin under ja/zh-Hant and full-width under
        # zh-Hans. Relies on built-in locl (no pinning) for that
        # switch.
        SegmentVariant(
            punct="curly", style="sans",
            source=sans, unicodes=codepoints.CURLY,
            layout_features=("*",),
        ),
        SegmentVariant(
            punct="curly", style="serif",
            source=serif, unicodes=codepoints.CURLY,
            layout_features=("*",),
        ),

        # Dot — Anchored (JP corner). Ink at lower-left of em box.
        # `align_locl_cps=DOT` overwrites locl target glyphs so the
        # JP-corner design stays stable across `lang` (ZHT/ZHH locl
        # would otherwise substitute to TC centred under zh-Hant).
        SegmentVariant(
            punct="dot-anchored", style="sans",
            source=sans, unicodes=codepoints.DOT,
            vert_nudges=vert_nudge.JP,
            layout_features=("*",),
            align_locl_cps=tuple(codepoints.DOT),
        ),
        SegmentVariant(
            punct="dot-anchored", style="serif",
            source=serif, unicodes=codepoints.DOT,
            vert_nudges=vert_nudge.JP_SERIF,
            layout_features=("*",),
            align_locl_cps=tuple(codepoints.DOT),
        ),

        # Dot — Centered (TW MOE). 3 dots grafted from Noto TC, plus
        # ．(FF0E) programmatically shifted from JP-corner to em-centre
        # via `outline_shifts`. Why shift instead of graft / delegate:
        # TC's ．is also corner (so graft doesn't help), and Chrome's
        # gate reads the face's cmap directly (so the CSS unicode-range
        # delegate trick doesn't help either — the gate still sees the
        # face's own FF0E). Programmatic centring puts all 4 dots in
        # kMiddle → 4-dot consistency gate passes → trim works.
        #
        # Shift values picked to land ．ink centre at (500, 380),
        # matching the TC-grafted `、`'s ink centre (~499, 380).
        #   Sans: JP source uniFF0E centre (200, 46)  → dx=300, dy=334
        #   Serif: JP source uniFF0E centre (160, 58) → dx=340, dy=322
        SegmentVariant(
            punct="dot-centered", style="sans",
            source=sans, unicodes=codepoints.DOT,
            layout_features=("*",),
            grafts=((sans_tc, (0x3001, 0xFF0C, 0x3002)),),
            outline_shifts={0xFF0E: (300, 334)},
            align_locl_cps=tuple(codepoints.DOT),
        ),
        SegmentVariant(
            punct="dot-centered", style="serif",
            source=serif, unicodes=codepoints.DOT,
            layout_features=("*",),
            grafts=((serif_tc, (0x3001, 0xFF0C, 0x3002)),),
            outline_shifts={0xFF0E: (340, 322)},
            align_locl_cps=tuple(codepoints.DOT),
        ),

        # Bracket — 6 bracket pairs (12 codepoints). Brackets are
        # uniformly corner-designed in CJK, no Centered/Anchored
        # variation needed. Pair compression for `「『` / `」、` etc.
        # fires via Unicode-direct kOpen/kClose classification.
        SegmentVariant(
            punct="bracket", style="sans",
            source=sans, unicodes=codepoints.BRACKET,
            layout_features=("*",),
        ),
        SegmentVariant(
            punct="bracket", style="serif",
            source=serif, unicodes=codepoints.BRACKET,
            layout_features=("*",),
        ),

        # Mark Centered — JP source `！：；？` are designed centred in
        # the em (visually matches TW MOE convention for these glyphs).
        # `upright_cps=(0xFF1A,)` forces `:` upright in vertical
        # (TW MOE: don't rotate). `align_locl_cps=MARK` keeps the
        # centred design stable across `lang` (ZHS locl under
        # zh-Hans would otherwise substitute to SC corner alts).
        SegmentVariant(
            punct="mark-centered", style="sans",
            source=sans, unicodes=codepoints.MARK,
            upright_cps=(0xFF1A,),
            layout_features=("*",),
            align_locl_cps=tuple(codepoints.MARK),
        ),
        SegmentVariant(
            punct="mark-centered", style="serif",
            source=serif, unicodes=codepoints.MARK,
            upright_cps=(0xFF1A,),
            layout_features=("*",),
            align_locl_cps=tuple(codepoints.MARK),
        ),

        # Mark Centered Rotated — same JP centred design as Mark
        # Centered, but `:` ROTATES 90° in vertical (JP / Japanese
        # convention). For texts using JP-style typesetting where
        # `:` should look like ︰ in vertical. No `upright_cps`, so
        # the default JAN vert L50 substitution `uniFF1A → ︰-form`
        # fires.
        SegmentVariant(
            punct="mark-centered-rotated", style="sans",
            source=sans, unicodes=codepoints.MARK,
            layout_features=("*",),
            align_locl_cps=tuple(codepoints.MARK),
        ),
        SegmentVariant(
            punct="mark-centered-rotated", style="serif",
            source=serif, unicodes=codepoints.MARK,
            layout_features=("*",),
            align_locl_cps=tuple(codepoints.MARK),
        ),

        # Mark Anchored — SC mainland-GB-style. Graft `！：；？` cmap
        # outlines + vmtx from Noto SC (ink shifted to corner of em).
        # `pin_to_locale="ZHS"` + `pin_locl_to="ZHS"` together keep
        # the SC corner design stable across `lang`. `vert_nudges`
        # pushes the FE-form vert targets of `！？` down 5% em
        # (source positions sit too tight to the top in SC).
        # `center_punct_cps=()` skips the JP -50 dx shift (SC
        # outlines are already corner-aligned).
        SegmentVariant(
            punct="mark-anchored", style="sans",
            source=sans, unicodes=codepoints.MARK,
            vert_nudges={0xFF01: -50, 0xFF1F: -50},
            pin_to_locale="ZHS",
            pin_locl_to="ZHS",
            layout_features=("*",),
            grafts=((sans_sc, (0xFF01, 0xFF1A, 0xFF1B, 0xFF1F)),),
            center_punct_cps=(),
        ),
        SegmentVariant(
            punct="mark-anchored", style="serif",
            source=serif, unicodes=codepoints.MARK,
            vert_nudges={0xFF01: -50, 0xFF1F: -50},
            pin_to_locale="ZHS",
            pin_locl_to="ZHS",
            layout_features=("*",),
            grafts=((serif_sc, (0xFF01, 0xFF1A, 0xFF1B, 0xFF1F)),),
            center_punct_cps=(),
        ),
    ]
