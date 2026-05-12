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
from fontTools.ttLib.tables._f_v_a_r import NamedInstance

# CSS-standard wght-axis named instances. Source Han / Noto CJK ships
# a Sans/Serif-inconsistent set (Sans has Thin + DemiLight, Serif has
# ExtraLight + SemiBold; only Light/Regular/Medium/Bold/Black overlap).
# We replace those with this canonical CSS naming, filtered per font's
# actual axis range.
CANONICAL_INSTANCES: list[tuple[int, str]] = [
    (100, "Thin"),
    (200, "ExtraLight"),
    (300, "Light"),
    (400, "Regular"),
    (500, "Medium"),
    (600, "SemiBold"),
    (700, "Bold"),
    (800, "ExtraBold"),
    (900, "Black"),
]
INSTANCE_FLAG_ELIDABLE = 0x0001  # OpenType fvar: hide name in font menus

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
    # Punctuation positioning style. Empty string is the JP/recommended
    # default — no suffix appears in the family name or file stem.
    # Other anticipated values: "centered" (TW MOE-style 、，。 centred),
    # "gb" (mainland-style 、，。：；！？ side-aligned).
    punct: str
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
    # Different punctuation styles position 、，等 differently — pass the
    # right dict. Empty dict means "use source positions as-is".
    vert_nudges: dict[int, int] = field(default_factory=dict)

    @property
    def stem(self) -> str:
        suffix = f"-{self.punct}" if self.punct else ""
        return f"diantenjeom-{self.style}{suffix}"

    @property
    def family(self) -> str:
        suffix = f" {self.punct.title()}" if self.punct else ""
        return f"Diantenjeom {self.style.title()}{suffix}"


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

    _canonicalize_instances(font, postscript)


def _canonicalize_instances(font: TTFont, postscript: str) -> None:
    """Replace fvar instances with the CSS-standard set.

    Strips Noto's mixed naming (DemiLight on Sans, SemiBold-but-no-
    ExtraBold on Serif, etc.) and writes one consistent list across
    every style we ship. Each instance becomes a {Weight} entry whose
    PostScript name is `{postscript}-{Weight}`. Old per-instance name
    records (IDs 266-279 on the Source Han line) are left in place but
    no longer referenced — we allocate fresh IDs starting at 300 to
    avoid collisions with anything we haven't audited.

    STAT (the Style Attribute Table) also references instance names
    via axis values; we leave those pointing at the old records since
    the new records are a superset and STAT's role is style fallback
    metadata, not the user-visible instance menu.
    """
    name = font["name"]
    fvar = font["fvar"]
    wght_axis = next(a for a in fvar.axes if a.axisTag == "wght")
    wmin, wmax = wght_axis.minValue, wght_axis.maxValue

    # Which name-record slots (platform, encoding, lang) the existing
    # instance records used — we want to write into the same slots so
    # every platform that read the old names sees the new ones.
    sample_id = fvar.instances[0].subfamilyNameID if fvar.instances else None
    slots: set[tuple[int, int, int]] = set()
    if sample_id is not None:
        for rec in name.names:
            if rec.nameID == sample_id:
                slots.add((rec.platformID, rec.platEncID, rec.langID))
    if not slots:
        slots = {(3, 1, 0x409), (1, 0, 0)}

    next_id = 300
    new_instances: list[NamedInstance] = []
    for wght, weight_name in CANONICAL_INSTANCES:
        if wght < wmin or wght > wmax:
            continue
        sub_id = next_id
        ps_id = next_id + 1
        next_id += 2
        for plat, enc, lang in slots:
            name.setName(weight_name, sub_id, plat, enc, lang)
            name.setName(f"{postscript}-{weight_name}", ps_id, plat, enc, lang)

        inst = NamedInstance()
        inst.coordinates = {"wght": float(wght)}
        inst.subfamilyNameID = sub_id
        inst.postscriptNameID = ps_id
        inst.flags = INSTANCE_FLAG_ELIDABLE if weight_name == "Regular" else 0
        new_instances.append(inst)

    fvar.instances = new_instances


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

    # Scope: JP-style sans + serif (the recommended default; no suffix in
    # the family name). Add `punct="centered"` / `punct="gb"` variants
    # here as those positioning styles come online.
    variants: list[Variant] = [
        Variant(
            punct="",
            style="sans",
            source=args.sources / "NotoSansCJKjp-VF.otf",
            unicodes=codepoints.JP,
            vert_nudges=vert_nudge.JP,
        ),
        Variant(
            punct="",
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
