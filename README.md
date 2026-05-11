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

## License

SIL Open Font License 1.1, inherited from Noto CJK.
