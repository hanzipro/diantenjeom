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

from diantenjeom import (
    center_punct,
    circle,
    codepoints,
    dash_center,
    ellipsis_pair,
    gpos_graft,
    graft,
    middle_dot,
    pin_locale,
    rotate_quotes,
    vert_nudge,
    vert_subst,
)

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
    # Codepoints whose Source Han `locl` SingleSubst should be cleared
    # BEFORE rotate_quotes installs its vert sub. Used by MOE: `pin_locl_to=
    # "ZHT"` brings in a locl that lifts the curly quotes +100u (visible
    # y offset in horizontal) AND breaks the kern table's PairPos coverage
    # — both diverge from JIS. Clearing the locl entries makes MOE quotes
    # render identically to JIS in both writing modes.
    rotate_clear_locl_cps: tuple[int, ...] = ()
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
    # If set, alias every `locl` FeatureRecord to this langsys's locl
    # lookup list. Makes locl behaviour invariant across the document's
    # `lang`. Used by GB variant (pin to "ZHS") so ZHT locl can't
    # substitute our SC-design cmap glyphs to TC-centred alternates
    # under `lang="zh-Hant"`. See `pin_locale._alias_locl_to_locale`.
    pin_locl_to: str | None = None

    @property
    def stem(self) -> str:
        return f"diantenjeom-{self.style}-{self.punct}"

    @property
    def family(self) -> str:
        # `punct` is always a short standards-body acronym (jis / moe /
        # gb); upper-case it for the user-facing family name. The
        # naming decouples punctuation style from text locale: callers
        # can pair `Diantenjeom JIS` with any CJK text font, mix and
        # match per design preference. See notes/punctuation-positioning-
        # history.md for why standards-based naming was chosen.
        return f"Diantenjeom {self.style.title()} {self.punct.upper()}"


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
        # If the source didn't have this ID at all, seed Windows only.
        # Previously also seeded (1, 0, 0) Macintosh, but the subsetter
        # already stripped platform=1 records via name_legacy=False, and
        # re-adding them here would defeat that optimization.
        existing = slots.get(nid) or {(3, 1, 0x409)}
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
        slots = {(3, 1, 0x409)}

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

    # Drop Source Han's old per-instance name records (IDs 266-279).
    # fvar.instances no longer points at them (now uses 300+), and STAT
    # references only 256-265 (axis name + axis values + elided
    # fallback). 266-279 are orphans that the subsetter retained as
    # potential fvar dependencies — safe to remove post-canonicalisation.
    name.names = [r for r in name.names if not (266 <= r.nameID <= 279)]


def subset_one(variant: Variant) -> tuple[list[Path], tuple[int, int]]:
    font = TTFont(variant.source)

    opts = Options()
    opts.layout_features = list(variant.layout_features) if variant.layout_features else KEEP_FEATURES
    # Name table whitelist — was `["*"]` which retained every record
    # including Source Han's 266-279 per-instance pairs that we later
    # supersede with 300-317 via `_canonicalize_instances`. Drop those
    # orphans, plus all Macintosh-platform (legacy) records and non-
    # English localized records.
    #   0-21    : standard family/style/copyright/credits + OFL required
    #   256-265 : STAT references these (axis name + 7 axis-value names
    #             + ElidedFallbackNameID) — must keep
    #   300-317 : our canonical CSS-standard instance names — added
    #             post-subset by _canonicalize_instances; allowlisted
    #             here so the subsetter doesn't strip them if present
    opts.name_IDs = (
        list(range(0, 22))
        + list(range(256, 266))
        + list(range(300, 318))
    )
    opts.name_legacy = False           # drop Macintosh (platform=1) records
    # name_languages must stay "*" — fontTools' subsetter doesn't
    # recognize ISO 639 tags like "en" here; passing them silently
    # drops every record. The langID filter happens implicitly when
    # name_legacy=False trims to platforms 0/3.
    opts.name_languages = ["*"]
    opts.glyph_names = True
    opts.legacy_kern = True
    opts.notdef_outline = True
    opts.recommended_glyphs = True
    opts.recalc_bounds = True
    opts.recalc_timestamp = False
    opts.canonical_order = True
    # DSIG (digital signature) is empty-padding leftover from Adobe's
    # build pipeline — not used by any modern renderer. Default
    # drop_tables already includes it; let it be dropped.
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
        font, variant.upright_cps,
        variant.pin_to_locale, variant.pin_locl_to,
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
    rotate_quotes.install(
        font, variant.rotate_configs,
        clear_locl_for_cps=variant.rotate_clear_locl_cps,
    )
    vert_nudge.install(font, variant.vert_nudges)
    dash_center.install(font)
    ellipsis_pair.install(font)
    # Brute-force horizontal shift on ! : ; ? to compensate for the
    # Chrome/Safari ~10% cross-axis right offset on these glyphs (see
    # README TODO / docs/vertical-text.md).
    center_punct.install(font, variant.center_punct_cps)

    # Unify U+00B7 (Latin `·`) with U+30FB (katakana `・`) by re-routing
    # the Latin codepoint's cmap entry to the katakana glyph. Both then
    # render as the same full-width CJK middle dot across all 4 variants
    # and all document langs. See middle_dot.py for the trade-off.
    middle_dot.install(font)

    # Hand-drawn U+25CF for CSS `text-emphasis: circle`. Replaces
    # Noto's oversize disc (~0.85 em) with a tasteful 0.50 em circle
    # positioned slightly above em centre. No-op if the variant's
    # codepoint set excludes U+25CF (won't happen with current BASE,
    # but the guard keeps the call cheap and safe).
    if 0x25CF in variant.unicodes:
        circle.install(font)

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


def _css_blocks(
    entries: list[tuple[Variant, tuple[int, int]]],
    weight_by_stem: dict[str, tuple[int, int]],
) -> list[str]:
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
    return blocks


def write_css(entries: list[tuple[Variant, tuple[int, int]]]) -> list[Path]:
    """Emit the combined stylesheet plus one per punctuation standard.

    `diantenjeom.css` carries every variant; `{punct}.css` (jis / moe / gb /
    kv) carries only that standard's faces, for callers who need a single
    convention and don't want to ship the others' @font-face rules. The
    weight-range map is built from the *full* entry list so a per-file
    delegated face can still resolve its donor's font-weight range even when
    the donor lives in another standard's group.
    """
    weight_by_stem = {v.stem: wr for v, wr in entries}

    def _emit(path: Path, group: list[tuple[Variant, tuple[int, int]]]) -> Path:
        path.write_text(
            "\n\n".join(_css_blocks(group, weight_by_stem)) + "\n",
            encoding="utf-8",
        )
        return path

    written = [_emit(DIST / "diantenjeom.css", entries)]

    by_punct: dict[str, list[tuple[Variant, tuple[int, int]]]] = {}
    for entry in entries:
        by_punct.setdefault(entry[0].punct, []).append(entry)
    for punct, group in by_punct.items():
        written.append(_emit(DIST / f"{punct}.css", group))

    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Build diantenjeom punctuation fonts.")
    parser.add_argument(
        "--sources",
        type=Path,
        default=ROOT / "sources",
        help="Directory containing Noto CJK source fonts.",
    )
    args = parser.parse_args()

    # Three punctuation variants per style — naming follows the
    # authoritative regional standards: JIS X 4051 (Japan), 教育部
    # 重訂標點符號手冊 / MoE (Taiwan & 港澳), and GB/T 15834 (Mainland).
    # Standards-based naming decouples punctuation style from text
    # locale so callers can mix-and-match (e.g. Japanese text with
    # MoE punctuation, TC text with JIS punctuation). See
    # notes/punctuation-positioning-history.md for the rationale.
    variants: list[Variant] = [
        Variant(
            punct="jis",
            style="sans",
            source=args.sources / "NotoSansCJKjp-VF.otf",
            unicodes=codepoints.JP,
            vert_nudges=vert_nudge.JP,
        ),
        Variant(
            punct="jis",
            style="serif",
            source=args.sources / "NotoSerifCJKjp-VF.otf",
            unicodes=codepoints.JP,
            vert_nudges=vert_nudge.JP_SERIF,
        ),
        # Centered: TW MOE-style punctuation positioning. For now the only
        # divergence from JP is ：(U+FF1A) staying upright in vertical mode
        # (Chinese convention) instead of rotating 90° (JP convention).
        # 、，。centring and other Centered-specific adjustments to follow.
        # Centered: TC-style centred 、，。 (grafted from Noto TC source),
        # ：upright in vertical. Keep ALL layout features — Chrome's
        # text-spacing-trim requires the source's `locl` feature to be
        # present AND its mappings + target glyph outlines untouched, or
        # pair-squeeze disables across the whole font. The side effect
        # is ZHT locl swaps under lang="zh-Hant" (．/！/？/：/；/etc.).
        # See docs/chrome-pair-squeeze.md.
        Variant(
            punct="moe",
            style="sans",
            source=args.sources / "NotoSansCJKjp-VF.otf",
            unicodes=codepoints.JP,
            vert_nudges={},
            upright_cps=(0xFF1A, 0x3001, 0xFF0C, 0x3002),
            # Pin locl to ZHT so the TC-grafted design stays stable
            # across document lang. Without this, lang="ja" swaps the
            # four dots back to JP-corner (breaking trim's four-dot
            # consistency check), and lang="zh-Hans" / "ko" substitutes
            # ？！：； to SC corner-aligned presentation forms.
            pin_locl_to="ZHT",
            layout_features=("*",),
            grafts=(
                (args.sources / "NotoSansCJKtc-VF.otf", (0x3001, 0xFF0C, 0x3002)),
            ),
            # ．(FF0E) delegated to the JP-default sans woff2 via the
            # @font-face unicode-range split — keeps ．JP-corner without
            # tripping Chrome's han_kerning four-dot consistency gate.
            css_delegate_donor_stem="diantenjeom-sans-jis",
            css_delegate_cps=(0xFF0E,),
            rotate_clear_locl_cps=(0x2018, 0x2019, 0x201C, 0x201D),
        ),
        Variant(
            punct="moe",
            style="serif",
            source=args.sources / "NotoSerifCJKjp-VF.otf",
            unicodes=codepoints.JP,
            vert_nudges={},
            upright_cps=(0xFF1A, 0x3001, 0xFF0C, 0x3002),
            # Pin locl to ZHT so the TC-grafted design stays stable
            # across document lang. Without this, lang="ja" swaps the
            # four dots back to JP-corner (breaking trim's four-dot
            # consistency check), and lang="zh-Hans" / "ko" substitutes
            # ？！：； to SC corner-aligned presentation forms.
            pin_locl_to="ZHT",
            layout_features=("*",),
            grafts=(
                (args.sources / "NotoSerifCJKtc-VF.otf", (0x3001, 0xFF0C, 0x3002)),
            ),
            css_delegate_donor_stem="diantenjeom-serif-jis",
            css_delegate_cps=(0xFF0E,),
            rotate_clear_locl_cps=(0x2018, 0x2019, 0x201C, 0x201D),
        ),
        # SC (mainland GB) — three locale-specific behaviours layered on JP
        # base:
        #   1. ！：；？ — graft cmap outlines from Noto SC (SC bakes
        #      corner-aligned positioning into outline x_min). Pin vert
        #      to ZHS so JP source's L52 (FF01/FF1A/FF1B/FF1F → FE15-FE13/14/16
        #      presentation forms, designed upper-right for SC vertical) fires.
        #   2. ‘’“” — graft cmap outlines AND hmtx from Noto SC (SC uses
        #      full-width 1000-em curly quotes; JP uses ~0.23-0.37 em
        #      proportional). Graft FE41-FE44 glyphs, then install an
        #      explicit vert substitution 2018/2019/201C/201D → FE41-FE44
        #      so vertical layout renders 「」『』 corner brackets in place
        #      of curly quotes (Chinese vertical convention; mirrors Noto
        #      SC's default ZHS lookup chain via cmap→vert).
        # 、，。．are identical between SC and JP, so they stay JP-sourced.
        Variant(
            punct="gb",
            style="sans",
            source=args.sources / "NotoSansCJKjp-VF.otf",
            unicodes=codepoints.GB,
            # FE15 / FE16 (the vert presentation forms for ！？) sit too tight
            # to the top in SC vertical layout; nudge down 5 % of em. ：；
            # (FE13 / FE14) stay at source position.
            vert_nudges={**vert_nudge.JP, 0xFF01: -50, 0xFF1F: -50},
            pin_to_locale="ZHS",
            pin_locl_to="ZHS",
            # Retain every source feature (incl. locl). Required for Chrome's
            # text-spacing-trim gate — `locl` absent => trim disabled font-wide
            # (see docs/chrome-pair-squeeze.md). Side effect: under lang="ja"
            # JAN locl substitutes our grafted SC glyphs to JP forms; benign
            # given SC font under ja is unusual usage.
            layout_features=("*",),
            grafts=(
                (args.sources / "NotoSansCJKsc-VF.otf",
                 (0xFF01, 0xFF1A, 0xFF1B, 0xFF1F,
                  0x2018, 0x2019, 0x201C, 0x201D,
                  0xFE41, 0xFE42, 0xFE43, 0xFE44)),
            ),
            hmtx_graft_cps=(0x2018, 0x2019, 0x201C, 0x201D),
            vert_substitutions={
                0x2018: 0xFE41,
                0x2019: 0xFE42,
                0x201C: 0xFE43,
                0x201D: 0xFE44,
            },
            gpos_squeeze_cps=(0x2018, 0x2019, 0x201C, 0x201D),
            center_punct_cps=(),
        ),
        Variant(
            punct="gb",
            style="serif",
            source=args.sources / "NotoSerifCJKjp-VF.otf",
            unicodes=codepoints.GB,
            vert_nudges={**vert_nudge.JP_SERIF, 0xFF01: -50, 0xFF1F: -50},
            pin_to_locale="ZHS",
            pin_locl_to="ZHS",
            layout_features=("*",),
            grafts=(
                (args.sources / "NotoSerifCJKsc-VF.otf",
                 (0xFF01, 0xFF1A, 0xFF1B, 0xFF1F,
                  0x2018, 0x2019, 0x201C, 0x201D,
                  0xFE41, 0xFE42, 0xFE43, 0xFE44)),
            ),
            hmtx_graft_cps=(0x2018, 0x2019, 0x201C, 0x201D),
            vert_substitutions={
                0x2018: 0xFE41,
                0x2019: 0xFE42,
                0x201C: 0xFE43,
                0x201D: 0xFE44,
            },
            gpos_squeeze_cps=(0x2018, 0x2019, 0x201C, 0x201D),
            center_punct_cps=(),
        ),

        # KV (Korean Vertical) — JP-based glyph design with `：` upright
        # so vertical Korean reads naturally. No standardised regional
        # punctuation standard exists for Korean (한글맞춤법 dropped the
        # vertical chapter in 2015; W3C KLReq is a draft) — the "KV"
        # name is descriptive rather than an authority reference.
        # Horizontal Korean works fine with system Western punctuation,
        # so KV is intended for vertical contexts (signage, calligraphy,
        # mixed Hangul–Hanja prose, traditional layouts). See
        # docs/notes/korean-vertical-punctuation.md.
        Variant(
            punct="kv",
            style="sans",
            source=args.sources / "NotoSansCJKjp-VF.otf",
            unicodes=codepoints.BASE,
            vert_nudges=vert_nudge.JP,
            upright_cps=(0xFF1A,),  # ：直排不旋轉（韓文 KLReq cl7 慣例）
        ),
        Variant(
            punct="kv",
            style="serif",
            source=args.sources / "NotoSerifCJKjp-VF.otf",
            unicodes=codepoints.BASE,
            vert_nudges=vert_nudge.JP_SERIF,
            upright_cps=(0xFF1A,),
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

    for css in write_css(entries):
        print(f"wrote {css.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
