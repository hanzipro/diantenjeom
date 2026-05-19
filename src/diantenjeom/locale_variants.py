"""Locale family — Diantenjeom Sans/Serif {JP-default, Centered, SC}.

Each variant carries the **full `codepoints.JP` set** rendered in one
locale's punctuation convention:

    JP-default — Adobe-Japan1 source straight-through; punct corners
                 hug top-left (`、`) / center (`！：；？`) per JP
                 typesetting.
    Centered  — TC-style centred `、，。` grafted from Noto TC, `：`
                 forced upright in vertical, `．` delegated to the
                 JP-default face via @font-face unicode-range (TC's `．`
                 is also corner; the unicode-range trick keeps the gate
                 happy by letting browsers pick whichever face has the
                 consistent design).
    SC        — Mainland-GB-style corner-aligned punct: `！：；？` cmap
                 outlines grafted from Noto SC, curly quotes ‘’“”
                 grafted full-width from Noto SC + locl-pinned to ZHS
                 so the design stays SC under any document `lang`.

Built by `scripts/build_locale.py` → `dist/diantenjeom.css`.
"""

from __future__ import annotations

from pathlib import Path

from diantenjeom import codepoints, vert_nudge
from diantenjeom.build import Variant


def variants(sources: Path) -> list[Variant]:
    return [
        # JP-default
        Variant(
            punct="",
            style="sans",
            source=sources / "NotoSansCJKjp-VF.otf",
            unicodes=codepoints.JP,
            vert_nudges=vert_nudge.JP,
        ),
        Variant(
            punct="",
            style="serif",
            source=sources / "NotoSerifCJKjp-VF.otf",
            unicodes=codepoints.JP,
            vert_nudges=vert_nudge.JP_SERIF,
        ),

        # Centered — TC graft for 、，。 + 　：forced upright, ．delegated
        # to JP-default face via @font-face unicode-range trick (see
        # docs/chrome-pair-squeeze.md). `layout_features=("*",)` keeps
        # locl present (gate requirement).
        Variant(
            punct="centered",
            style="sans",
            source=sources / "NotoSansCJKjp-VF.otf",
            unicodes=codepoints.JP,
            vert_nudges={},
            upright_cps=(0xFF1A, 0x3001, 0xFF0C, 0x3002),
            layout_features=("*",),
            grafts=(
                (sources / "NotoSansCJKtc-VF.otf", (0x3001, 0xFF0C, 0x3002)),
            ),
            css_delegate_donor_stem="diantenjeom-sans",
            css_delegate_cps=(0xFF0E,),
        ),
        Variant(
            punct="centered",
            style="serif",
            source=sources / "NotoSerifCJKjp-VF.otf",
            unicodes=codepoints.JP,
            vert_nudges={},
            upright_cps=(0xFF1A, 0x3001, 0xFF0C, 0x3002),
            layout_features=("*",),
            grafts=(
                (sources / "NotoSerifCJKtc-VF.otf", (0x3001, 0xFF0C, 0x3002)),
            ),
            css_delegate_donor_stem="diantenjeom-serif",
            css_delegate_cps=(0xFF0E,),
        ),

        # SC — mainland GB-style. Three layered mechanisms (see plan
        # docs/plans/gb-sc.md for full rationale):
        #   1. `！：；？` cmap outlines + vmtx grafted from Noto SC.
        #      pin_to_locale="ZHS" routes vert through L52 so FE13-FE16
        #      presentation forms fire in vertical.
        #   2. `‘’“”` cmap outlines + hmtx grafted from Noto SC (full-
        #      width corner-aligned). FE41-FE44 also grafted, plus a
        #      vert_subst lookup so vertical layout renders 「」『』
        #      corner brackets.
        #   3. `pin_locl_to="ZHS"` keeps the SC design stable across
        #      document `lang`. Under any lang, ZHS-pinned locl fires:
        #      no dot substitution (preserves cmap), quote/mark
        #      substitution to JP-source ZHS alts (visually = SC).
        # `、 。 ， ．` are identical between SC and JP, so they stay
        # JP-sourced.
        Variant(
            punct="sc",
            style="sans",
            source=sources / "NotoSansCJKjp-VF.otf",
            unicodes=codepoints.SC,
            # FE15 / FE16 (vert forms of ！？) sit too tight to the top
            # in SC vertical; nudge down 5% of em. ：；at source pos.
            vert_nudges={**vert_nudge.JP, 0xFF01: -50, 0xFF1F: -50},
            pin_to_locale="ZHS",
            pin_locl_to="ZHS",
            layout_features=("*",),
            grafts=(
                (sources / "NotoSansCJKsc-VF.otf",
                 (0xFF01, 0xFF1A, 0xFF1B, 0xFF1F,
                  0x2018, 0x2019, 0x201C, 0x201D,
                  0xFE41, 0xFE42, 0xFE43, 0xFE44)),
            ),
            hmtx_graft_cps=(0x2018, 0x2019, 0x201C, 0x201D),
            vert_substitutions={
                0x2018: 0xFE41,
                0x2019: 0xFE42,
                0x201C: 0xFE43,
                0x201D: 0xFE44,
            },
            gpos_squeeze_cps=(0x2018, 0x2019, 0x201C, 0x201D),
            center_punct_cps=(),
        ),
        Variant(
            punct="sc",
            style="serif",
            source=sources / "NotoSerifCJKjp-VF.otf",
            unicodes=codepoints.SC,
            vert_nudges={**vert_nudge.JP_SERIF, 0xFF01: -50, 0xFF1F: -50},
            pin_to_locale="ZHS",
            pin_locl_to="ZHS",
            layout_features=("*",),
            grafts=(
                (sources / "NotoSerifCJKsc-VF.otf",
                 (0xFF01, 0xFF1A, 0xFF1B, 0xFF1F,
                  0x2018, 0x2019, 0x201C, 0x201D,
                  0xFE41, 0xFE42, 0xFE43, 0xFE44)),
            ),
            hmtx_graft_cps=(0x2018, 0x2019, 0x201C, 0x201D),
            vert_substitutions={
                0x2018: 0xFE41,
                0x2019: 0xFE42,
                0x201C: 0xFE43,
                0x201D: 0xFE44,
            },
            gpos_squeeze_cps=(0x2018, 0x2019, 0x201C, 0x201D),
            center_punct_cps=(),
        ),
    ]
