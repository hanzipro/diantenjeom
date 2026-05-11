"""Extract CJK punctuation glyphs from Noto Sans/Serif CJK.

Pipeline:
    1. Load a source Noto CJK font (.otf / .ttc).
    2. Subset to the punctuation codepoint set per locale (zh-Hans, zh-Hant, ja, ko).
    3. Emit OTF (desktop: InDesign, apps) and WOFF2 (web) to dist/.
    4. Generate a sample @font-face CSS — convenience for web users; ignore otherwise.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "dist"
FONTS_OUT = DIST / "fonts"

# CJK punctuation blocks. Refine per-locale as the project matures.
PUNCT_RANGES: list[tuple[int, int]] = [
    (0x2000, 0x206F),  # General Punctuation (—, …, etc.)
    (0x3000, 0x303F),  # CJK Symbols and Punctuation (、。「」《》etc.)
    (0xFF00, 0xFFEF),  # Halfwidth and Fullwidth Forms
    (0xFE30, 0xFE4F),  # CJK Compatibility Forms (vertical punctuation)
    (0xFE10, 0xFE1F),  # Vertical Forms
]


@dataclass(frozen=True)
class Variant:
    locale: str   # "sc" | "tc" | "jp" | "kr"
    style: str    # "sans" | "serif"
    source: Path  # path to source .otf/.ttc
    ttc_index: int | None = None


def codepoints() -> set[int]:
    return {cp for lo, hi in PUNCT_RANGES for cp in range(lo, hi + 1)}


def subset_one(variant: Variant) -> list[Path]:
    font = (
        TTFont(variant.source, fontNumber=variant.ttc_index)
        if variant.ttc_index is not None
        else TTFont(variant.source)
    )

    opts = Options()
    opts.desubroutinize = True
    opts.drop_tables += ["GSUB", "GPOS"]  # punctuation rarely needs shaping

    subsetter = Subsetter(options=opts)
    subsetter.populate(unicodes=codepoints())
    subsetter.subset(font)

    FONTS_OUT.mkdir(parents=True, exist_ok=True)
    stem = f"diantenjeom-{variant.style}-{variant.locale}"

    otf_path = FONTS_OUT / f"{stem}.otf"
    font.flavor = None
    font.save(otf_path)

    woff2_path = FONTS_OUT / f"{stem}.woff2"
    font.flavor = "woff2"
    font.save(woff2_path)

    return [otf_path, woff2_path]


def write_css(variants: list[Variant]) -> Path:
    lines: list[str] = []
    for v in variants:
        family = f"Diantenjeom {v.style.title()} {v.locale.upper()}"
        url = f"./fonts/diantenjeom-{v.style}-{v.locale}.woff2"
        lines.append(
            "@font-face {\n"
            f"  font-family: '{family}';\n"
            f"  src: url('{url}') format('woff2');\n"
            "  font-display: swap;\n"
            "  unicode-range: U+2000-206F, U+3000-303F, U+FE10-FE1F,\n"
            "    U+FE30-FE4F, U+FF00-FFEF;\n"
            "}\n"
        )
    out = DIST / "diantenjeom.css"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Build diantenjeom punctuation fonts.")
    parser.add_argument(
        "--sources",
        type=Path,
        default=ROOT / "sources",
        help="Directory containing Noto CJK source fonts.",
    )
    args = parser.parse_args()

    # TODO: replace with real mapping once source filenames are pinned.
    variants: list[Variant] = [
        # Variant("sc", "sans", args.sources / "NotoSansCJKsc-Regular.otf"),
        # Variant("tc", "sans", args.sources / "NotoSansCJKtc-Regular.otf"),
        # Variant("jp", "sans", args.sources / "NotoSansCJKjp-Regular.otf"),
        # Variant("kr", "sans", args.sources / "NotoSansCJKkr-Regular.otf"),
    ]

    if not variants:
        raise SystemExit(
            f"No source fonts configured. Place Noto CJK files under {args.sources}/ "
            "and populate the variants list in build.py."
        )

    for v in variants:
        for path in subset_one(v):
            print(f"built {path.relative_to(ROOT)}")

    css = write_css(variants)
    print(f"wrote {css.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
