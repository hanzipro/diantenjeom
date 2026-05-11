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
]
