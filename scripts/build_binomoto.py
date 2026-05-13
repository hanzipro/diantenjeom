#!/usr/bin/env python3
"""Diagnostic build: minimal Noto Sans/Serif TC subset, no transforms.

Purpose: isolate why Chrome's text-spacing-trim works on the full Noto
Sans TC served by Google Fonts but not on diantenjeom-sans-centered.
We strip the codepoint set to just the punctuation under investigation
and KEEP every layout feature, every locale, every GSUB / GPOS lookup
the source ships. No graft, no pin_locale, no center_punct, no rename
of family / instances. The only difference from the source is the
codepoint set.

Codepoints:
    、(U+3001) 。(U+3002) ，(U+FF0C)
    「(U+300C) 」(U+300D) 『(U+300E) 』(U+300F)
    （(U+FF08) ）(U+FF09)
    ［(U+FF3B) ］(U+FF3D)
    〔(U+3014) 〕(U+3015)

If pair-squeeze works on these but not on the Centered build, the
problem is in one of the transforms we apply. If it doesn't work
here either, the problem is the subsetter itself.

Outputs `dist/fonts/binomoto-{sans,serif}.{otf,woff2}` and a
`dist/binomoto.css` that wires up @font-face under family names
`Binomoto Sans` / `Binomoto Serif`.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTFont

CODEPOINTS = [
    0x3001, 0x3002, 0xFF0C,
    0x300C, 0x300D, 0x300E, 0x300F,
    0xFF08, 0xFF09,
    0xFF3B, 0xFF3D,
    0x3014, 0x3015,
]

VARIANTS = [
    ("sans",  ROOT / "sources" / "NotoSansCJKtc-VF.otf"),
    ("serif", ROOT / "sources" / "NotoSerifCJKtc-VF.otf"),
]

DIST = ROOT / "dist"
FONTS_OUT = DIST / "fonts"


def rename(font: TTFont, family: str) -> None:
    """Minimal rename so the font doesn't shadow installed Noto.

    We touch only name IDs 1, 4, 6, 16, 21 (family / full / PostScript /
    typographic / WWS). We do NOT canonicalize fvar instances or
    rewrite per-instance PostScript names — keep the source structure
    intact for the diagnostic.
    """
    name = font["name"]
    postscript = family.replace(" ", "")
    payloads = {1: family, 4: family, 6: postscript, 16: family, 21: family}
    slots: dict[int, set] = {}
    for rec in name.names:
        slots.setdefault(rec.nameID, set()).add((rec.platformID, rec.platEncID, rec.langID))
    for nid, value in payloads.items():
        existing = slots.get(nid) or {(3, 1, 0x409), (1, 0, 0)}
        for plat, enc, lang in existing:
            name.setName(value, nid, plat, enc, lang)


def subset_one(style: str, source: Path) -> tuple[Path, Path, tuple[int, int]]:
    font = TTFont(source)

    opts = Options()
    # KEEP everything — pass through every layout feature the source ships.
    opts.layout_features = ["*"]
    opts.layout_scripts = ["*"]
    opts.name_IDs = ["*"]
    opts.name_legacy = True
    opts.name_languages = ["*"]
    opts.glyph_names = True
    opts.legacy_kern = True
    opts.notdef_outline = True
    opts.recommended_glyphs = True
    opts.recalc_bounds = True
    opts.recalc_timestamp = False
    opts.canonical_order = True
    opts.drop_tables.remove("DSIG") if "DSIG" in opts.drop_tables else None

    subsetter = Subsetter(options=opts)
    subsetter.populate(unicodes=set(CODEPOINTS))
    subsetter.subset(font)

    font["OS/2"].recalcUnicodeRanges(font)
    rename(font, f"Binomoto {style.title()}")

    FONTS_OUT.mkdir(parents=True, exist_ok=True)
    otf = FONTS_OUT / f"binomoto-{style}.otf"
    font.flavor = None
    font.save(otf)

    woff2 = FONTS_OUT / f"binomoto-{style}.woff2"
    font.flavor = "woff2"
    font.save(woff2)

    wght_axis = next(a for a in font["fvar"].axes if a.axisTag == "wght")
    return otf, woff2, (int(wght_axis.minValue), int(wght_axis.maxValue))


def unicode_range(cps: list[int]) -> str:
    sorted_cps = sorted(set(cps))
    parts: list[str] = []
    run_start = run_end = sorted_cps[0]
    for cp in sorted_cps[1:]:
        if cp == run_end + 1:
            run_end = cp
        else:
            parts.append(f"U+{run_start:04X}" if run_start == run_end
                         else f"U+{run_start:04X}-{run_end:04X}")
            run_start = run_end = cp
    parts.append(f"U+{run_start:04X}" if run_start == run_end
                 else f"U+{run_start:04X}-{run_end:04X}")
    return ", ".join(parts)


def main() -> None:
    blocks = []
    for style, source in VARIANTS:
        if not source.exists():
            raise SystemExit(f"source missing: {source}")
        otf, woff2, (wmin, wmax) = subset_one(style, source)
        print(f"built {otf.relative_to(ROOT)}")
        print(f"built {woff2.relative_to(ROOT)}")
        blocks.append(
            "@font-face {\n"
            f"  font-family: 'Binomoto {style.title()}';\n"
            f"  src: url('./fonts/binomoto-{style}.woff2') format('woff2-variations');\n"
            f"  font-weight: {wmin} {wmax};\n"
            "  font-display: swap;\n"
            f"  unicode-range: {unicode_range(CODEPOINTS)};\n"
            "}"
        )
    css = DIST / "binomoto.css"
    css.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    print(f"wrote {css.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
