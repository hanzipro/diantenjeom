"""Extract CJK punctuation glyphs from Noto Sans/Serif CJK.

Pipeline:
    1. Load a source Noto CJK variable font.
    2. Subset to the per-locale punctuation codepoint set (see `codepoints.py`).
    3. Keep GSUB/GPOS layout features so vertical typesetting (`vert`, `vrt2`)
       and CSS punctuation-squeezing (`palt`, `vpal`, `halt`, `vhal`) survive.
    4. Rewrite the name table so the OTF doesn't shadow installed Noto CJK.
    5. Emit OTF (desktop: InDesign, apps) and WOFF2 (web) to dist/.
    6. Generate a sample @font-face CSS.

Current scope: Noto Sans JP only. Other locales/styles wired up later.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTFont

from diantenjeom import codepoints, pin_locale, rotate_quotes, vert_nudge

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "dist"
FONTS_OUT = DIST / "fonts"

# Layout features to retain. Closure under these tags pulls in the alternate
# glyphs they reference (vertical forms, half/proportional widths, kerning).
#
# NOTE: `locl` is intentionally OMITTED for now. Keeping it makes a single
# Noto-CJK-JP subset shape correctly for ZHT/ZHS/KOR too (via OT language
# tags), but Safari doesn't yet implement `font-language-override`, so we
# can't reliably force a locale from CSS — we have to ship one file per
# locale and bake each locale's glyph forms into its own file. Dropping
# `locl` also prunes the now-unreachable alternate glyphs (e.g. zh-Hant
# 居中 versions of 。、，) from the output, shrinking the file.
# TODO(font-language-override): once Safari ships it and Chrome's
# precedence bug w.r.t. HTML lang is resolved, re-add "locl" here and
# collapse the per-locale files into one shared subset.
KEEP_FEATURES = [
    # GSUB — shape substitution
    "ccmp", "calt", "rlig",
    "vert", "vrt2",          # vertical alternates
    "fwid", "hwid", "pwid",  # width variants
    # GPOS — positioning / squeezing
    "kern", "vkrn",
    "palt", "vpal",          # proportional alternate metrics (CSS "palt")
    "halt", "vhal",          # half-width alternate metrics
    "mark", "mkmk",
]


@dataclass(frozen=True)
class Variant:
    locale: str   # "sc" | "tc" | "jp" | "kr"
    style: str    # "sans" | "serif"
    source: Path
    unicodes: list[int]
    # Codepoints to force-rotate 90° CW in vertical mode (Latin curly
    # quotes are universal; CJK locales share this set).
    rotate_quotes: tuple[int, ...] = rotate_quotes.ROTATE_QUOTES
    # Per-codepoint vertical-mode y nudges for vert-substituted glyphs.
    # Different locales position 、，等 differently — pass the right dict.
    vert_nudges: dict[int, int] = field(default_factory=dict)

    @property
    def stem(self) -> str:
        return f"diantenjeom-{self.style}-{self.locale}"

    @property
    def family(self) -> str:
        return f"Diantenjeom {self.style.title()} {self.locale.upper()}"


def _rename_family(font: TTFont, family: str) -> None:
    """Replace family/full/postscript/preferred-family names.

    Without this, the subset still identifies itself as the source font
    and collides with an installed Noto CJK at the OS font-management level.
    """
    name = font["name"]
    postscript = family.replace(" ", "")
    full = family

    # (nameID, value) pairs we overwrite for every (platform, encoding, language)
    # tuple already present in the name table for that ID.
    payloads = {
        1: family,        # Family
        4: full,          # Full name
        6: postscript,    # PostScript name
        16: family,       # Typographic family
        21: family,       # WWS family
    }
    # Collect existing (platformID, platEncID, langID) sets per nameID so we
    # only write into slots the source already populated — avoids inventing
    # records for platforms the font never targeted.
    slots: dict[int, set[tuple[int, int, int]]] = {}
    for rec in name.names:
        slots.setdefault(rec.nameID, set()).add((rec.platformID, rec.platEncID, rec.langID))

    for nid, value in payloads.items():
        # If the source didn't have this ID at all, seed the standard slots.
        existing = slots.get(nid) or {(3, 1, 0x409), (1, 0, 0)}
        for plat, enc, lang in existing:
            name.setName(value, nid, plat, enc, lang)


def subset_one(variant: Variant) -> list[Path]:
    font = TTFont(variant.source)

    opts = Options()
    opts.layout_features = KEEP_FEATURES
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
    # Keep VORG/vhea/vmtx/VVAR — vertical metrics tables are essential for
    # `writing-mode: vertical-rl`.

    subsetter = Subsetter(options=opts)
    subsetter.populate(unicodes=set(variant.unicodes))
    subsetter.subset(font)

    # Strip non-default LangSysRecord entries so every OT language tag
    # (ZHT/ZHS/KOR/etc.) falls back to JAN-style vert wiring. Without this
    # a page with `lang="zh-Hant"` would resolve to a vert feature record
    # that omits some substitutions — e.g. ：(U+FF1A) wouldn't rotate.
    pin_locale.install(font)

    # Bake rotated copies of the Latin curly quotes and wire them into
    # vert/vrt2 — forces 90° CW rotation in vertical mode regardless of
    # the browser's run-segmentation heuristics. See rotate_quotes.py.
    rotate_quotes.install(font, variant.rotate_quotes)
    # Apply per-codepoint vertical-mode nudges (vmtx tsb + VORG + GPOS).
    vert_nudge.install(font, variant.vert_nudges)

    _rename_family(font, variant.family)

    FONTS_OUT.mkdir(parents=True, exist_ok=True)

    otf_path = FONTS_OUT / f"{variant.stem}.otf"
    font.flavor = None
    font.save(otf_path)

    woff2_path = FONTS_OUT / f"{variant.stem}.woff2"
    font.flavor = "woff2"
    font.save(woff2_path)

    return [otf_path, woff2_path]


def _unicode_range(unicodes: list[int]) -> str:
    """Build a compact CSS `unicode-range` value, collapsing runs."""
    sorted_cps = sorted(set(unicodes))
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


def write_css(variants: list[Variant]) -> Path:
    blocks: list[str] = []
    for v in variants:
        url = f"./fonts/{v.stem}.woff2"
        blocks.append(
            "@font-face {\n"
            f"  font-family: '{v.family}';\n"
            f"  src: url('{url}') format('woff2-variations');\n"
            "  font-weight: 100 900;\n"
            "  font-display: swap;\n"
            f"  unicode-range: {_unicode_range(v.unicodes)};\n"
            "}"
        )
    out = DIST / "diantenjeom.css"
    out.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
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

    # Scope: Japanese sans only. Add Variant rows here as locales come online.
    variants: list[Variant] = [
        Variant(
            locale="jp",
            style="sans",
            source=args.sources / "NotoSansCJKjp-VF.otf",
            unicodes=codepoints.JP,
            vert_nudges=vert_nudge.JP,
        ),
    ]

    for v in variants:
        if not v.source.exists():
            raise SystemExit(f"source missing: {v.source}")
        for path in subset_one(v):
            print(f"built {path.relative_to(ROOT)}")

    css = write_css(variants)
    print(f"wrote {css.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
