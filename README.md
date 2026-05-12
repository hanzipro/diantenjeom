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

| Family                          | Style    | Punctuation convention                              |
|---------------------------------|----------|-----------------------------------------------------|
| `Diantenjeom Sans`              | Sans     | JP-style — recommended default. 、，。 hug the top   |
| `Diantenjeom Serif`             | Serif    | JP-style — recommended default                       |
| *(Planned)* `… Centered`        | both     | TW MOE — 、，。 centred                              |
| *(Planned)* `… GB`              | both     | Mainland — 、，。：；！？ all side-aligned             |

Each variant exposes the full `wght` axis (Sans 100–900, Serif 200–900) with
named instances on the CSS-standard grid: Thin / ExtraLight / Light / Regular
/ Medium / SemiBold / Bold / ExtraBold / Black.

## Status

Early. APIs, file names, and the punctuation codepoint set are all subject to
change. More docs and examples to come.

## TODO

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

- **Align em-dash and 2-em-dash with the line's centre axis in vertical
  mode.** Both `—` (U+2014) and `⸺` (U+2E3A) currently render slightly
  off-centre relative to other CJK punctuation because UTR50 marks them
  `R` (always rotate) — Chrome and Firefox auto-rotate the source glyph
  and ignore `vert` substitutions, while Safari applies `vert`
  inconsistently between the two codepoints. This matches Hiragino's
  behaviour out of the box, so it's not unique to our subset, but it
  still looks off compared to the ellipsis. See
  `docs/vertical-text.md` § "Dash alignment" for the full investigation
  and the attempted fixes that didn't pan out.

## License

SIL Open Font License 1.1, inherited from Noto CJK.
