"""Punctuation codepoint sets per variant.

The constants here mirror the punctuation tables in the repo's HTML demos
(`ja.html`, `index.html`, `ko.html`) — keep them in sync when the demos
change.

Each entry is annotated with its 標點 name so a diff against the demos
reads naturally. Don't fold characters together — the demos are the
source of truth and we want one line per cell.

Variant constants:

  BASE  Shared full set covering every CJK punctuation codepoint each
        Diantenjeom variant carries. JIS / MOE / KV all use `BASE` as-is;
        GB adds vertical-presentation-form brackets on top.
  GB    `BASE` plus U+FE41-FE44 corner-bracket vertical presentation
        forms required by the GB variant's curly-quote → corner-bracket
        vert substitution (Noto SC default ZHS routing).

`JP` is kept as a back-compat alias for `BASE`.
"""

from __future__ import annotations

# BASE — shared codepoint set across all variants.
BASE: list[int] = [
    # U+0020 SPACE — required by WebKit for `text-emphasis` skip handling.
    # When the base char is punctuation, WebKit replaces the emphasis
    # glyph with `spaceGlyph()` (the font's U+0020), which on a font
    # missing U+0020 falls through to `.notdef` and renders as boxed-X
    # tofu next to every punct in vertical CJK. Including U+0020 fixes
    # this without affecting anything else — the source's space outline
    # is empty, just an advance width.
    0x0020,                  # SPACE
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
    0x301C,                  # 波浪號 〜（韓文 물결표 / 日文 波ダッシュ）
    0x25CF,                  # 著重號 ●（hand-drawn, for CSS text-emphasis: circle）
]

# Back-compat alias — older call sites used `codepoints.JP`. Kept so
# external scripts / demos referencing this name keep working.
JP: list[int] = BASE

# GB — `BASE` plus the four corner-bracket vertical presentation forms.
# Required because the GB variant installs a vert/vrt2 substitution that
# maps ‘’“” (U+2018/2019/201C/201D) to U+FE41/FE42/FE43/FE44 (per Noto
# SC's default ZHS convention — Chinese vertical typesetting renders
# curly quotes as 「」『』 corner brackets). The FE41-FE44 glyphs must be
# present in the subset so the substitution targets resolve at render
# time.
GB: list[int] = BASE + [
    0xFE41, 0xFE42, 0xFE43, 0xFE44,  # 直角引號直排 presentation forms
]

# Back-compat alias.
SC: list[int] = GB
