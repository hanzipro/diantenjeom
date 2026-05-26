# diantenjeom

**點 · 点 · 점** — /ti̯ɛn˨˩˦ teɴ tɕʌm/, or, as you might say in English, /ˈdiː.æn.tɛn.dʒəm/

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

See [docs/TODO.md](docs/TODO.md).

## License

SIL Open Font License 1.1, inherited from Noto CJK.
