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

Four variants — three named after the authoritative regional standard whose
punctuation positioning they follow (JIS / MOE / GB), plus KV for Korean
vertical typesetting. Naming is intentionally decoupled from text locale,
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
| `Diantenjeom Sans KV`           | Sans     | Korean vertical — JP-based, `：` upright; no standards body |
| `Diantenjeom Serif KV`          | Serif    | 同上                                                  |

Each variant exposes the full `wght` axis (Sans 100–900, Serif 200–900) with
named instances on the CSS-standard grid: Thin / ExtraLight / Light / Regular
/ Medium / SemiBold / Bold / ExtraBold / Black.

**KV** is descriptive, not an authority reference — Korean has no standardised
vertical-punctuation spec (한글 맞춤법 dropped its vertical chapter in 2015). It
reuses the JP design with `：` kept upright, and is meant for vertical contexts
(signage, calligraphy, mixed Hangul–Hanja prose). See
[docs/notes/korean-vertical-punctuation.md](docs/notes/korean-vertical-punctuation.md).

## Usage

Install:

```sh
npm install @han.css/diantenjeom
```

Load the stylesheet — it ships the `@font-face` blocks:

```css
@import "@han.css/diantenjeom/css";
```

or, with a bundler:

```js
import "@han.css/diantenjeom";
```

Then put a Diantenjeom family **before** your CJK text font in the
`font-family` fallback chain:

```css
body {
  font-family:
    "Helvetica Neue",        /* Latin body                              */
    "Diantenjeom Sans MOE",  /* punctuation — must precede the CJK font */
    "Noto Sans TC",          /* CJK body                                */
    sans-serif;
}
```

Each `@font-face` carries a `unicode-range` covering only the ~30 punctuation
codepoints, so the browser pulls Diantenjeom **only** for those characters and
falls through to the next font for everything else (Han, kana, Hangul, Latin).
That's why it has to sit ahead of the CJK font — otherwise the CJK font's own
punctuation wins. Pick the convention independently of your text language: pair
`Diantenjeom Sans MOE` with Japanese text, `Diantenjeom Serif JIS` with
Traditional Chinese, and so on.

> **Markup caveat.** Browser pair-squeezing (`text-spacing-trim`) only collapses
> adjacent punctuation that share an inline formatting context. Splitting two
> glyphs across separate *atomic-inline* boxes — `display: inline-block` /
> `inline-flex` / `inline-grid`, as some frameworks emit when wrapping
> characters — silently disables the squeeze; plain inline `<span>`s are fine.
> See [docs/pair-squeeze-and-markup.md](docs/pair-squeeze-and-markup.md).

### Without a build step

Copy `dist/diantenjeom.css` and `dist/fonts/` to your site and link the CSS
directly. The `@font-face` `src` URLs are relative to the stylesheet, so keep
`fonts/` next to it.

### Desktop apps (InDesign, etc.)

Install the OTFs from `dist/fonts/` and add a Diantenjeom family ahead of your
CJK font in a composite-font / fallback list — the same ordering rule applies.

## Status

Early. APIs, file names, and the punctuation codepoint set are all subject to
change. More docs to come.

## TODO

See [docs/TODO.md](docs/TODO.md).

## License

SIL Open Font License 1.1, inherited from Noto CJK.
