"""Punctuation codepoint sets per locale.

The lists mirror the punctuation tables in the repo's HTML demos
(`ja.html`, `index.html`); keep them in sync when the demos change.

Each entry is annotated with the row's 標點 name so a diff against the
demo table reads naturally. Don't fold characters together — the
demo is the source of truth and we want one line per cell.
"""

from __future__ import annotations

# ja.html — Japanese (Noto Sans JP). Order matches the table top-to-bottom.
JP: list[int] = [
    0x3002,                  # 句號 。
    0xFF0E,                  # 單點全形句號 ．
    0xFF0C,                  # 逗號 ，
    0x3001,                  # 頓號 、
    0xFF1B,                  # 分號 ；
    0xFF1A,                  # 冒號 ：
    0xFF1F,                  # 問號 ？
    0xFF01,                  # 驚嘆號 ！
    0x00B7,                  # 間隔號 ·
    0x30FB,                  # 間隔號（片假名中點） ・
    0x300C, 0x300D,          # 引號 「」
    0x300E, 0x300F,          # 引號 『』
    # 彎引號 — ja.html marks these as 不修正 (don't apply CJK conventions).
    # Noto Sans CJK JP maps them to proportional Latin curly glyphs by
    # default (~0.23–0.37 em). UTR50 classifies them as `R` (rotate) so by
    # spec they should rotate 90° CW in vertical mode, but Chrome/Safari's
    # run-segmentation lumps them with adjacent CJK and renders upright.
    # `rotate_quotes.py` bakes pre-rotated glyphs + a `vert`/`vrt2`
    # substitution to force the rotation regardless of run context.
    0x201C, 0x201D,          # 彎引號 “”
    0x2018, 0x2019,          # 彎引號 ‘’
    0x300A, 0x300B,          # 書名號 《》
    0x3008, 0x3009,          # 書名號 〈〉
    0xFF08, 0xFF09,          # 括號 （）
    0x3014, 0x3015,          # 括號 〔〕
    0x2014,                  # 破折號 —
    0x2E3A,                  # 二字寬破折號 ⸺
    0x2026,                  # 刪節號 …
    0xFF0D,                  # 連接號 －
    0xFF0F, 0xFF3C,          # 斜線 ／＼
    0x25CF,                  # 著重號 ●（hand-drawn, for CSS text-emphasis: circle）
]

# --- Per-group split of the JP set ---------------------------------
#
# Used by the production `Diantenjeom Sans/Serif {Joiner,Curly,Dot,
# Bracket,Mark}` faces and the `demo-split.html` harness. Design intent
# (see docs/plans/diantenjeom-split.md):
#
#   * Joiner — must-have face. These codepoints overlap Latin / system
#     CJK fonts and get clobbered if Diantenjeom isn't first in the
#     fallback chain: `·` is in Latin-1 (almost every Western font has
#     it as a narrow proportional dot), `—` and `…` are commonly
#     half-em + baseline-sitting in Western fonts.
#   * Curly — locale-switch face. U+2018-201D have no half/full-width
#     codepoint siblings; same codepoint must render proportional Latin
#     in JP/TC and fullwidth in SC. Isolated so callers can override
#     per-locale.
#   * Dot / Bracket / Mark — optional faces. Pure fullwidth CJK
#     codepoints (no Latin overlap), so natural fallback already
#     produces sensible output; split lets designers pick punct style
#     per group independently.
JOINER: list[int] = [
    0x00B7,                  # 間隔號 ·       (Latin-1 — Latin fonts clobber)
    0x30FB,                  # 假名中點 ・
    0x2014,                  # 破折號 —       (Latin em-dash often half-em + breaks)
    0x2E3A,                  # 二字寬破折號 ⸺
    0x2026,                  # 刪節號 …       (Latin ellipsis sits on baseline)
    0xFF0D,                  # 連接號 －
    0xFF0F, 0xFF3C,          # 斜線 ／＼
    0x25CF,                  # 著重號 ●（hand-drawn, for CSS text-emphasis: circle）
]

CURLY: list[int] = [
    0x2018, 0x2019,          # ‘ ’
    0x201C, 0x201D,          # “ ”
]

DOT: list[int] = [
    0x3001,                  # 、
    0x3002,                  # 。
    0xFF0C,                  # ，
    0xFF0E,                  # ．
]

BRACKET: list[int] = [
    0x300C, 0x300D,          # 「 」
    0x300E, 0x300F,          # 『 』
    0xFF08, 0xFF09,          # （ ）
    0x3008, 0x3009,          # 〈 〉
    0x300A, 0x300B,          # 《 》
    0x3014, 0x3015,          # 〔 〕
]

MARK: list[int] = [
    0xFF1A,                  # ：
    0xFF1B,                  # ；
    0xFF1F,                  # ？
    0xFF01,                  # ！
]

# Invariant: the 5 split groups partition codepoints.JP exactly — no
# overlaps, no gaps. Any future addition to JP must be assigned to a
# group, or the assert below trips the build.
assert sorted(JOINER + CURLY + DOT + BRACKET + MARK) == sorted(JP), (
    "split groups must partition codepoints.JP exactly; "
    f"missing: {sorted(set(JP) - set(JOINER + CURLY + DOT + BRACKET + MARK))}, "
    f"extra: {sorted(set(JOINER + CURLY + DOT + BRACKET + MARK) - set(JP))}"
)


# SC — JP set plus the four corner-bracket vertical presentation forms.
# Required because the SC variant installs a vert/vrt2 substitution that
# maps ‘’“” (U+2018/2019/201C/201D) to U+FE41/FE42/FE43/FE44 (per Noto SC's
# default ZHS convention — Chinese vertical typesetting renders curly quotes
# as 「」『』 corner brackets). The FE41-FE44 glyphs must be present in the
# subset so the substitution targets resolve at render time.
SC: list[int] = JP + [
    0xFE41, 0xFE42, 0xFE43, 0xFE44,  # 直角引號直排 presentation forms
]
