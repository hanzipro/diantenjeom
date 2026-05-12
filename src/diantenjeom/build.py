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
import re
from dataclasses import dataclass, field
from pathlib import Path

from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTFont

from diantenjeom import (
    center_punct,
    codepoints,
    ellipsis_pair,
    pin_locale,
    rotate_quotes,
    vert_nudge,
)

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
    # Per-codepoint rotation configs (which glyphs get a pre-rotated vert
    # alternate, and how to position them). Latin curly quotes + dashes
    # are universal across CJK locales, so the default set applies as-is.
    rotate_configs: dict[int, rotate_quotes.RotateConfig] = field(
        default_factory=lambda: dict(rotate_quotes.ROTATE_CONFIGS)
    )
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

    # Source Han / Noto ships per-instance PostScript names (IDs 267, 269,
    # 271, …) of the form `NotoSansCJKjp-Regular` and a Unique ID (ID 3)
    # of `2.004;ADBO;NotoSansCJKjp-Thin;ADOBE`. These still identify the
    # font as Noto inside OS font-management UIs / app font menus, which
    # is exactly what OFL's Reserved Font Name clause prohibits in a
    # derivative. Rewrite any occurrence of `Noto{Sans,Serif}CJK{jp,kr,
    # sc,tc}` to our own PostScript family prefix. We deliberately only
    # touch records that already contain the substring — name IDs 0
    # (copyright) and 7 (trademark) on Source Han mention "Source" /
    # "Noto" / "Adobe" / "Google" and MUST be preserved verbatim per OFL.
    pattern = re.compile(r"Noto(Sans|Serif)CJK(jp|kr|sc|tc)")
    for rec in name.names:
        if rec.nameID in (0, 7):  # copyright + trademark — leave alone
            continue
        try:
            value = rec.toUnicode()
        except UnicodeDecodeError:
            continue
        if not pattern.search(value):
            continue
        rewritten = pattern.sub(postscript, value)
        name.setName(rewritten, rec.nameID, rec.platformID, rec.platEncID, rec.langID)


def subset_one(variant: Variant) -> tuple[list[Path], tuple[int, int]]:
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
    rotate_quotes.install(font, variant.rotate_configs)
    vert_nudge.install(font, variant.vert_nudges)
    ellipsis_pair.install(font)
    # Brute-force horizontal shift on ! : ; ? to compensate for the
    # Chrome/Safari ~10% cross-axis right offset on these glyphs (see
    # README TODO / docs/vertical-text.md).
    center_punct.install(font)

    # Recompute OS/2 Unicode Range bits from the final cmap. The subsetter
    # leaves stale bits behind — bit 31 (General Punctuation, where U+2026
    # / U+2014 / U+201x live) was unset, which made Firefox skip our font
    # for those codepoints inside mixed-script runs and fall back to the
    # next CJK font in the CSS stack.
    font["OS/2"].recalcUnicodeRanges(font)

    _rename_family(font, variant.family)

    FONTS_OUT.mkdir(parents=True, exist_ok=True)

    otf_path = FONTS_OUT / f"{variant.stem}.otf"
    font.flavor = None
    font.save(otf_path)

    woff2_path = FONTS_OUT / f"{variant.stem}.woff2"
    font.flavor = "woff2"
    font.save(woff2_path)

    # Pull the actual wght-axis range out of fvar so the @font-face
    # block advertises what the variable font really supports (Serif
    # starts at 200, not 100).
    wght_axis = next(a for a in font["fvar"].axes if a.axisTag == "wght")
    weight_range = (int(wght_axis.minValue), int(wght_axis.maxValue))

    return [otf_path, woff2_path], weight_range


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


def write_css(entries: list[tuple[Variant, tuple[int, int]]]) -> Path:
    blocks: list[str] = []
    for v, (wmin, wmax) in entries:
        url = f"./fonts/{v.stem}.woff2"
        blocks.append(
            "@font-face {\n"
            f"  font-family: '{v.family}';\n"
            f"  src: url('{url}') format('woff2-variations');\n"
            f"  font-weight: {wmin} {wmax};\n"
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

    # Scope: Japanese sans + serif. Add Variant rows here as locales come online.
    variants: list[Variant] = [
        Variant(
            locale="jp",
            style="sans",
            source=args.sources / "NotoSansCJKjp-VF.otf",
            unicodes=codepoints.JP,
            vert_nudges=vert_nudge.JP,
        ),
        Variant(
            locale="jp",
            style="serif",
            source=args.sources / "NotoSerifCJKjp-VF.otf",
            unicodes=codepoints.JP,
            vert_nudges=vert_nudge.JP_SERIF,
        ),
    ]

    entries: list[tuple[Variant, tuple[int, int]]] = []
    for v in variants:
        if not v.source.exists():
            raise SystemExit(f"source missing: {v.source}")
        paths, weight_range = subset_one(v)
        for path in paths:
            print(f"built {path.relative_to(ROOT)}")
        entries.append((v, weight_range))

    css = write_css(entries)
    print(f"wrote {css.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
