# diantenjeom

**點 · 点 · 점** — /ti̯ɛn˨˩˦ teɴ tɕʌm/

A set of punctuation-only CJK fonts, extracted from
Noto Sans CJK +
Noto Serif CJK.

The name strings together the readings of **點** ("dot") in Mandarin (*diǎn*),
Japanese (*ten*), and Korean (*jeom*) — the three locales this project
supports as first-class targets.

## Why

CJK text routinely mixes a Latin body font with a CJK fallback. That fallback
also has to render the punctuation — and different locales render the *same*
Unicode punctuation differently (the position of `。`, the shape of `「」`, the
width of `、`). Bundling punctuation with whichever CJK font happens to be
loaded forces a single locale's convention onto everyone.

**diantenjeom** pulls just the punctuation glyphs out of Noto CJK, per locale
and weight, so you can drop them into a font fallback chain — CSS
`font-family`, InDesign composite fonts, app text styles, anywhere fallback is
supported — and pick the punctuation style independently from the body face.

## Status

Early. APIs, file names, and the punctuation codepoint set are all subject to
change. More docs and examples to come.

## TODO

- **Collapse per-locale files into one shared subset.** The Noto CJK source
  carries `locl` GSUB rules that map the same Unicode punctuation to different
  glyph forms per OT language tag (JAN / ZHT / ZHS / KOR), so a single subset
  could serve every locale if downstream pages set `lang` or
  [`font-language-override`][fla] correctly. We currently ship one file per
  locale and strip `locl` at build time, because **Safari does not yet
  implement `font-language-override`** and Chrome has precedence bugs when an
  HTML `lang` attribute is already set. Revisit once browser support
  stabilises — flip `locl` back on in `KEEP_FEATURES` (`src/diantenjeom/build.py`)
  and the alternate glyphs will be retained automatically.

[fla]: https://developer.mozilla.org/en-US/docs/Web/CSS/font-language-override

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
