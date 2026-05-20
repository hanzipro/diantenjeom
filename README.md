# diantenjeom

**點 · 点 · 점** — /ti̯ɛn˨˩˦ teɴ tɕʌm/

A set of punctuation-only CJK fonts, extracted from
Noto Sans CJK +
Noto Serif CJK, shipped as variable fonts.

The name strings together the readings of **點** ("dot") in Mandarin (*diǎn*),
Japanese (*ten*), and Korean (*jeom*) — the three reading traditions whose
punctuation conventions the project sets out to disentangle.

## Why

CJK text routinely mixes a Latin body font with a CJK fallback. That fallback
also has to render the punctuation — and different conventions render the
*same* Unicode punctuation differently (the position of `。`, the shape of
`「」`, the width of `、`, where `〕，` should squeeze). Bundling punctuation
with whichever CJK font happens to be loaded forces one convention onto
everyone.

**diantenjeom** pulls just the punctuation glyphs out of Noto CJK and ships
them as small variable fonts you drop into a font fallback chain — CSS
`font-family`, InDesign composite fonts, app text styles, anywhere fallback
is supported — and pick the punctuation style independently from the body
face.

## Variants

Each style ships as a separate variable font; pick by punctuation positioning
convention, not by language tag.

Three punctuation conventions, each named after the authoritative
regional standard. Naming is intentionally decoupled from text locale,
so you can pair any variant with any CJK text font (e.g. Japanese text
with MOE punctuation, TC text with JIS punctuation).

| Family                          | Style    | Punctuation convention                                |
|---------------------------------|----------|-------------------------------------------------------|
| `Diantenjeom Sans JIS`          | Sans     | JIS X 4051 — 、，。 hug the top-left corner of the em |
| `Diantenjeom Serif JIS`         | Serif    | JIS X 4051                                            |
| `Diantenjeom Sans MOE`          | Sans     | 教育部《重訂標點符號手冊》— 、，。 centred             |
| `Diantenjeom Serif MOE`         | Serif    | 同上                                                  |
| `Diantenjeom Sans GB`           | Sans     | GB/T 15834 — 、，。：；！？ side-aligned              |
| `Diantenjeom Serif GB`          | Serif    | 同上                                                  |

Each variant exposes the full `wght` axis (Sans 100–900, Serif 200–900) with
named instances on the CSS-standard grid: Thin / ExtraLight / Light / Regular
/ Medium / SemiBold / Bold / ExtraBold / Black.

## Status

Early. APIs, file names, and the punctuation codepoint set are all subject to
change. More docs and examples to come.

## TODO

- **File the Chromium bug.** `docs/chromium-bug-report-draft.md` has a
  ready-to-paste draft. Findings to land:
  - `text-spacing-trim` is **not** a Noto-fingerprint check. It's
    `han_kerning.cc:CharTypeFromBounds()` running a type-consistency
    check across the four "dot" characters in `kChars`:
    `、 (U+3001)`, `。 (U+3002)`, `，(U+FF0C)`, `．(U+FF0E)`. After
    shaping (locl applied), the four glyphs' bboxes must classify to
    the same `CharType` (`kClose` / `kMiddle` / `kOpen` / `kOther`).
    If they don't, `has_alternative_spacing = false` and trim is
    disabled **font-wide** (not just for the disagreeing glyph).
  - A from-scratch custom font is unaffected, **provided the four
    dots are designed consistently** — all corner-attached or all
    centred. Mixed-design subsets (Diantenjeom MOE's case: TC
    centred `、/。/，` + JP corner `．`) trigger the gate.
  - Suggested fixes in the draft, in order of effort: surface the
    gate to DevTools → downgrade per-group instead of font-wide →
    replace bbox classification with Unicode-property-based
    classification (which matches the spec) → opt-in OpenType feature
    tag for designer self-certification.
  - When filing, swap the placeholder repo URL in the draft for the
    actual GitHub URL of this project. Target component:
    `Blink>Fonts>Shaping`.


- **Collapse per-style files into one shared subset.** The Noto CJK source
  carries `locl` GSUB rules that map the same Unicode punctuation to different
  glyph forms per OT language tag (JAN / ZHT / ZHS / KOR), so a single subset
  could serve every punctuation convention if downstream pages set `lang` or
  [`font-language-override`][fla] correctly. We currently ship one file per
  style and strip `locl` at build time, because **Safari does not yet
  implement `font-language-override`** and Chrome has precedence bugs when an
  HTML `lang` attribute is already set. Revisit once browser support
  stabilises — flip `locl` back on in `KEEP_FEATURES` (`src/diantenjeom/build.py`)
  and the alternate glyphs will be retained automatically.

[fla]: https://developer.mozilla.org/en-US/docs/Web/CSS/font-language-override

- **Latin-low ellipsis (`…`) sits slightly above the Latin baseline in
  Firefox inside a rotated Latin run.** Chrome and Safari place it on
  the baseline; Firefox places it ~50–80 font units higher (close
  enough but not perfect). Horizontal mode is identical across all
  three browsers, so this is a vertical-rotated-Latin-run-specific
  baseline-alignment quirk Firefox applies to U+2026 specifically. We
  picked `_LATIN_LOW_DY = -360` (vs the ideal -330 for Chrome / Safari)
  as the least-wrong compromise; revisit if Firefox's vertical text
  baseline handling for Common-script changes. See
  `docs/vertical-text.md` § "Ellipsis in Firefox vertical Latin runs"
  for the diagnostic timeline.

- **`! : ; ?` need a -50 unit outline pre-shift to look centred in
  Chrome / Safari, which leaves Firefox ~5 % off to the left.** Source
  Noto Sans CJK JP renders these glyphs ~10 % of em right of the CJK
  centre axis in Chrome / Safari (Firefox is fine). We couldn't find a
  font-side knob that nudges Chrome / Safari alone, so `center_punct`
  brute-forces the outlines (and matching hmtx LSB) left by 50 units
  — half the observed C/S offset — so C/S land on centre and Firefox
  lands ~5 % left. Both within visual tolerance. Revisit if a more
  precise fix surfaces (e.g. shipping per-glyph proportional `palt` /
  `vpal` values matching Hiragino's). See `docs/vertical-text.md`
  § "`! : ; ?` offset in Chrome / Safari vertical".

- ~~**Align em-dash and 2-em-dash with the line's centre axis in vertical
  mode.**~~ ✅ Resolved 2026-05-14 by `dash_center.py`: shift the cmap
  `emdash` / `uni2E3A` outlines up by +105 units so the ink y-centre
  aligns with the CJK character body centre (matches `中`'s y_center=381).
  Both horizontal and vertical modes pick this up because the change is
  to the source outline itself rather than via GSUB — engines can ignore
  `vert` substitutions for UTR50 R-class codepoints, but they can't
  ignore the outline of the glyph they're rendering. See
  `docs/vertical-text.md` § "Dash alignment" → "Update (2026-05-14)".

## License

SIL Open Font License 1.1, inherited from Noto CJK.
