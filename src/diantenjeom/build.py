"""Shared pipeline library — `Variant` dataclass + `subset_one` +
`write_css` + `run_build`.

This module is a library; `main()` lives in two scripts:
    scripts/build_locale.py  → Locale family (JP/Centered/SC × Sans/Serif)
    scripts/build_segment.py → Segment family (per-group Sans/Serif faces)

Both scripts import `Variant` (or subclass), populate a list of variants,
and call `run_build(variants, output_css_path)`.

Pipeline per variant:
    1. Load a source Noto CJK variable font.
    2. Subset to the per-variant codepoint set (`codepoints.py`).
    3. Keep GSUB/GPOS layout features so vertical typesetting (`vert`,
       `vrt2`) and punctuation squeezing (`palt`, `vpal`, `halt`,
       `vhal`) survive.
    4. Apply per-variant adjustments via the helper modules
       (`pin_locale`, `graft`, `gpos_graft`, `vert_subst`, `vert_nudge`,
       `dash_center`, `ellipsis_pair`, `center_punct`, `circle`,
       `rotate_quotes`, and — segment-only — `align_locl`).
    5. Rewrite name records so the OTF doesn't shadow installed Noto CJK.
    6. Emit OTF + WOFF2 to dist/.

The CSS bundle is written separately per script (each gets its own
output_css_path).
"""

from __future__ import annotations

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
    _outline,
    align_locl,
    center_punct,
    circle,
    codepoints,
    dash_center,
    ellipsis_pair,
    gpos_graft,
    graft,
    pin_locale,
    rotate_quotes,
    vert_nudge,
    vert_subst,
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
    # Codepoints whose JP-default vert rotation should be cancelled (kept
    # upright in vertical mode). Centered / GB conventions keep ：upright;
    # JP rotates it. Default empty = behave as JP source.
    upright_cps: tuple[int, ...] = ()
    # Diagnostic: pass ["*"] to KEEP every layout feature from source,
    # bypassing the curated KEEP_FEATURES list. Used while bisecting
    # which stripped feature breaks Chrome's pair-squeeze on Centered.
    layout_features: tuple[str, ...] | None = None
    # Optional grafts: tuples of (secondary_source, codepoints). Each
    # pair grafts those codepoints' cmap glyphs (CharString + vmtx +
    # VORG) from the named source. Centered grafts 、，。 from TC to
    # get the centred form.
    grafts: tuple[tuple[Path, tuple[int, ...]], ...] = ()
    # Subset of graft codepoints whose hmtx (advance + LSB) should ALSO
    # be copied from the donor. Default behaviour preserves the JP base
    # hmtx — required for Chrome pair-squeeze on punctuation. Override
    # for codepoints where the donor's horizontal width is integral to
    # the glyph design (e.g. SC's full-width curly quotes replacing
    # JP's proportional Latin curly quotes).
    hmtx_graft_cps: tuple[int, ...] = ()
    # GSUB SingleSubst lookup wired into vert/vrt2: {src_cp: target_cp}.
    # Used by SC variant to substitute curly quotes (2018/2019/201C/201D)
    # to corner-bracket vertical presentation forms (FE41-FE44) under
    # vertical layout — mirroring Noto SC's default ZHS routing.
    vert_substitutions: dict[int, int] = field(default_factory=dict)
    # Codepoints for which to also graft GPOS halt/palt SinglePos entries
    # from the *first* graft's donor font. Required when the grafted
    # cmap glyph's CJK-punctuation squeeze data lives in the donor's
    # GPOS but not the JP base (e.g. SC's full-width curly quotes —
    # halt/palt entries exist in Noto SC but not Noto JP).
    gpos_squeeze_cps: tuple[int, ...] = ()
    # CSS-side delegation: emit a second @font-face under the same
    # family name that serves `css_delegate_cps` from a sibling
    # variant's woff2. Used by Centered to keep ．(FF0E) as JP-corner
    # while the rest of the family stays TC-centred — see
    # docs/chrome-pair-squeeze.md for why this side-steps Chrome's
    # han_kerning consistency check (each @font-face passes the gate
    # internally with its own consistent dot group).
    css_delegate_donor_stem: str | None = None
    css_delegate_cps: tuple[int, ...] = ()
    # Codepoints to pass through `center_punct` (Chrome/Safari ~10 %-em
    # right-offset compensation on ! : ; ?). SC-style variants graft SC
    # outlines that are already corner-aligned to the front of the em box,
    # so the additional -50 shift would over-correct — set to `()` to skip.
    center_punct_cps: tuple[int, ...] = center_punct.JP
    # OT LangSys tag whose vert/vrt2 lookup list should drive vertical
    # substitution across all LangSys. "JAN" (default) gives JP-style
    # vertical (rotated ：, JP brackets, no FE13-FE16 mapping for !:;?).
    # "ZHS" gives mainland-style vertical (no ：rotation, FE13-FE16 for
    # !:;? presentation forms, FE41-FE44 for vertical brackets).
    pin_to_locale: str = "JAN"
    # If set, alias every `locl` FeatureRecord's LookupListIndex to
    # this langsys's locl lookup list, making locl behaviour invariant
    # across the document's `lang`. Used by:
    #   - Locale SC (pin to ZHS) — keeps SC's grafted cmap design from
    #     being overwritten by ZHT/ZHH/etc. locl under non-zh-Hans
    #     document lang.
    #   - Segment Mark Anchored (pin to ZHS) — same rationale.
    # See `pin_locale._alias_locl_to_locale` docstring.
    pin_locl_to: str | None = None

    @property
    def stem(self) -> str:
        suffix = f"-{self.punct}" if self.punct else ""
        return f"diantenjeom-{self.style}{suffix}"

    @property
    def family(self) -> str:
        # Locale codes (sc/tc/jp/kr) stay upper-case; hyphenated punct
        # values ("dot-anchored", "mark-centered") split into space-
        # separated title-cased words; everything else title-cases.
        if not self.punct:
            suffix = ""
        elif self.punct in {"sc", "tc", "jp", "kr"}:
            suffix = f" {self.punct.upper()}"
        else:
            suffix = " " + " ".join(w.title() for w in self.punct.split("-"))
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
    opts.layout_features = list(variant.layout_features) if variant.layout_features else KEEP_FEATURES
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
    pin_locale.install(
        font,
        variant.upright_cps,
        variant.pin_to_locale,
        variant.pin_locl_to,
    )
    for graft_source, graft_cps in variant.grafts:
        if graft_cps:
            graft.install(font, graft_source, graft_cps, variant.hmtx_graft_cps)
    if variant.gpos_squeeze_cps and variant.grafts:
        # Donor for halt/palt is the same as the first cmap graft's
        # donor — the assumption that holds for our current variants.
        gpos_graft.install(font, variant.grafts[0][0], variant.gpos_squeeze_cps)
    # Install vert substitutions BEFORE rotate_quotes so that
    # rotate_quotes' "skip codepoints with existing vert sub" check
    # picks them up and doesn't bake a rotated alternate on top.
    vert_subst.install(font, variant.vert_substitutions)
    rotate_quotes.install(font, variant.rotate_configs)
    vert_nudge.install(font, variant.vert_nudges)
    dash_center.install(font)
    ellipsis_pair.install(font)
    # Brute-force horizontal shift on ! : ; ? to compensate for the
    # Chrome/Safari ~10% cross-axis right offset on these glyphs (see
    # README TODO / docs/vertical-text.md).
    center_punct.install(font, variant.center_punct_cps)

    # Hand-drawn U+25CF for CSS `text-emphasis: circle`. No-op when the
    # variant's codepoint set doesn't include U+25CF (the source font's
    # cmap doesn't have it either after subset; circle.install guards
    # on "already in cmap" so the second call is harmless).
    if 0x25CF in variant.unicodes:
        circle.install(font)

    # Overwrite locl target glyphs to match cmap sources, so locl-fired
    # substitutions render visually identical to the cmap design.
    # Used by Segment variants (e.g. Dot / Mark) which subclass Variant
    # and add an `align_locl_cps` attribute. Locale variants don't
    # subclass and have no such attribute — `getattr` returns the empty
    # tuple and the call no-ops.
    # Per-codepoint cmap-glyph outline translation. Run BEFORE
    # align_locl so the shifted outline propagates into locl targets.
    # (Segment-only field; Locale variants don't subclass.)
    outline_shifts = getattr(variant, "outline_shifts", {})
    if outline_shifts:
        cmap = font.getBestCmap()
        for cp, (dx, dy) in outline_shifts.items():
            glyph = cmap.get(cp)
            if glyph is not None:
                _outline.shift_in_place(font, glyph, dx, dy)
                # Update hmtx lsb so glyph metadata matches new outline.
                if glyph in font["hmtx"].metrics:
                    adv, lsb = font["hmtx"].metrics[glyph]
                    font["hmtx"].metrics[glyph] = (adv, lsb + dx)

    align_cps = getattr(variant, "align_locl_cps", ())
    if align_cps:
        align_locl.install(font, align_cps)

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


def _face_block(family: str, stem: str, wmin: int, wmax: int, unicodes: list[int]) -> str:
    return (
        "@font-face {\n"
        f"  font-family: '{family}';\n"
        f"  src: url('./fonts/{stem}.woff2') format('woff2-variations');\n"
        f"  font-weight: {wmin} {wmax};\n"
        "  font-display: swap;\n"
        f"  unicode-range: {_unicode_range(unicodes)};\n"
        "}"
    )


def write_css(
    entries: list[tuple[Variant, tuple[int, int]]],
    output_path: Path,
) -> Path:
    """Emit all `entries`' @font-face blocks (incl. css_delegate side-
    faces) to `output_path` as a single CSS file. Returns the path."""
    weight_by_stem = {v.stem: wr for v, wr in entries}

    blocks: list[str] = []
    for v, (wmin, wmax) in entries:
        # Main face — exclude any codepoints delegated to a sibling
        # variant's font file via @font-face unicode-range split.
        main_cps = [cp for cp in v.unicodes if cp not in v.css_delegate_cps]
        blocks.append(_face_block(v.family, v.stem, wmin, wmax, main_cps))
        # Delegated face(s) — same family name, different woff2 + a
        # narrow unicode-range. Lets the browser pick the donor's glyph
        # for the delegated codepoints while leaving Chrome's per-face
        # han_kerning trim qualification intact (each face's four-dot
        # group stays internally consistent).
        if v.css_delegate_cps and v.css_delegate_donor_stem:
            donor_stem = v.css_delegate_donor_stem
            donor_wmin, donor_wmax = weight_by_stem.get(donor_stem, (wmin, wmax))
            blocks.append(
                _face_block(
                    v.family,
                    donor_stem,
                    donor_wmin,
                    donor_wmax,
                    list(v.css_delegate_cps),
                )
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    return output_path


def run_build(
    variants: list[Variant],
    output_css_path: Path,
) -> None:
    """Orchestrate: subset each variant, then write a single CSS bundle.
    Both `scripts/build_locale.py` and `scripts/build_segment.py` call
    this with their own variant list + css output path."""
    entries: list[tuple[Variant, tuple[int, int]]] = []
    for v in variants:
        if not v.source.exists():
            raise SystemExit(f"source missing: {v.source}")
        paths, weight_range = subset_one(v)
        for path in paths:
            print(f"built {path.relative_to(ROOT)}")
        entries.append((v, weight_range))

    css = write_css(entries, output_css_path)
    print(f"wrote {css.relative_to(ROOT)}")


