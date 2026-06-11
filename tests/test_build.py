"""Structural assertions on the built fonts.

These tests load each emitted OTF with fontTools and check that the build
honoured its contract — the things a careless edit to `build.py` or
`codepoints.py` could silently break:

  * every variant + format file is emitted,
  * the cmap carries exactly the variant's punctuation codepoint set,
  * the layout features that justify the project (vertical alternates,
    proportional/half-width squeezing) survived subsetting,
  * fvar named instances follow the CSS-standard wght grid, and
  * the name table no longer identifies the font as Noto CJK (OFL's
    Reserved Font Name clause).

Shaping correctness (does `「` actually substitute to its vertical form?)
and cross-browser positioning are out of scope here — those need HarfBuzz
golden tests and browser screenshot diffing respectively. See README /
docs for the testing layers.

The fonts are read from `dist/fonts`. If they are not present (fresh
checkout, no prior `pnpm build`), the session fixture builds them once via
`scripts/build_fonts.py`, which needs the Noto sources under `sources/`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from diantenjeom import codepoints  # noqa: E402
from diantenjeom.build import CANONICAL_INSTANCES  # noqa: E402

# (stem, style, punct, expected codepoint set). Stated independently of
# build.py's Variant list so the test asserts the contract rather than
# echoing the implementation.
VARIANTS = [
    ("diantenjeom-sans-jis", "sans", "jis", codepoints.BASE),
    ("diantenjeom-serif-jis", "serif", "jis", codepoints.BASE),
    ("diantenjeom-sans-moe", "sans", "moe", codepoints.BASE),
    ("diantenjeom-serif-moe", "serif", "moe", codepoints.BASE),
    ("diantenjeom-sans-gb", "sans", "gb", codepoints.GB),
    ("diantenjeom-serif-gb", "serif", "gb", codepoints.GB),
    ("diantenjeom-sans-kv", "sans", "kv", codepoints.BASE),
    ("diantenjeom-serif-kv", "serif", "kv", codepoints.BASE),
]

# Sans covers the full wght axis; Serif starts at 200 (no Thin).
WEIGHT_RANGE = {"sans": (100, 900), "serif": (200, 900)}

# Features the project exists to ship: vertical alternates (GSUB) and the
# proportional/half-width squeezing metrics (GPOS) that CSS text-spacing
# and `palt`/`vpal` rely on.
REQUIRED_GSUB = {"vert", "vrt2"}
REQUIRED_GPOS = {"palt", "vpal"}

NOTO_PATTERN = "NotoSansCJK", "NotoSerifCJK"


@pytest.fixture(scope="session")
def fonts_dir() -> Path:
    d = ROOT / "dist" / "fonts"
    if not list(d.glob("*.otf")):
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build_fonts.py")],
            check=True,
            cwd=ROOT,
        )
    return d


@pytest.fixture(scope="session")
def fonts(fonts_dir: Path) -> dict[str, TTFont]:
    return {
        stem: TTFont(fonts_dir / f"{stem}.otf")
        for stem, *_ in VARIANTS
    }


def _feature_tags(font: TTFont, table_tag: str) -> set[str]:
    if table_tag not in font:
        return set()
    feature_list = font[table_tag].table.FeatureList
    if feature_list is None:
        return set()
    return {fr.FeatureTag for fr in feature_list.FeatureRecord}


@pytest.mark.parametrize("stem,style,punct,_cps", VARIANTS)
def test_both_formats_emitted(fonts_dir: Path, stem, style, punct, _cps):
    for ext in ("otf", "woff2"):
        assert (fonts_dir / f"{stem}.{ext}").is_file(), f"missing {stem}.{ext}"


@pytest.mark.parametrize("stem,style,punct,expected_cps", VARIANTS)
def test_cmap_matches_codepoint_set(fonts, stem, style, punct, expected_cps):
    cmap = fonts[stem].getBestCmap()
    # Ignore C0 controls (.notdef/CR companions the subsetter may retain);
    # the contract is about the punctuation set, all of which is >= U+0020.
    present = {cp for cp in cmap if cp >= 0x20}
    assert present == set(expected_cps)


@pytest.mark.parametrize("stem,style,punct,_cps", VARIANTS)
def test_vertical_and_squeeze_features_survive(fonts, stem, style, punct, _cps):
    gsub = _feature_tags(fonts[stem], "GSUB")
    gpos = _feature_tags(fonts[stem], "GPOS")
    assert REQUIRED_GSUB <= gsub, f"{stem} GSUB missing {REQUIRED_GSUB - gsub}"
    assert REQUIRED_GPOS <= gpos, f"{stem} GPOS missing {REQUIRED_GPOS - gpos}"


@pytest.mark.parametrize("stem,style,punct,_cps", VARIANTS)
def test_named_instances_follow_css_grid(fonts, stem, style, punct, _cps):
    font = fonts[stem]
    name = font["name"]
    wmin, wmax = WEIGHT_RANGE[style]
    expected = [n for w, n in CANONICAL_INSTANCES if wmin <= w <= wmax]
    actual = [
        name.getDebugName(inst.subfamilyNameID)
        for inst in font["fvar"].instances
    ]
    assert actual == expected


@pytest.mark.parametrize("stem,style,punct,_cps", VARIANTS)
def test_family_name_is_diantenjeom(fonts, stem, style, punct, _cps):
    name = fonts[stem]["name"]
    expected = f"Diantenjeom {style.title()} {punct.upper()}"
    # Typographic family (16) when present, else legacy family (1).
    family = name.getDebugName(16) or name.getDebugName(1)
    assert family == expected


@pytest.mark.parametrize("stem,style,punct,_cps", VARIANTS)
def test_no_noto_reserved_font_name(fonts, stem, style, punct, _cps):
    # OFL Reserved Font Name: a derivative must not present itself as Noto.
    # Copyright (0) and trademark (7) legitimately mention Noto/Adobe/Google
    # and are preserved verbatim, so they are exempt.
    for rec in fonts[stem]["name"].names:
        if rec.nameID in (0, 7):
            continue
        try:
            value = rec.toUnicode()
        except UnicodeDecodeError:
            continue
        for needle in NOTO_PATTERN:
            assert needle not in value, (
                f"{stem} name ID {rec.nameID} still says Noto: {value!r}"
            )
