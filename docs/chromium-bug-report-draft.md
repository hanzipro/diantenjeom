# Chromium bug report draft

Target tracker: https://issues.chromium.org/ → component `Blink>Fonts>Shaping`

Suggested title:
> `text-spacing-trim` silently disabled font-wide when the four "dot"
> punctuation glyphs (U+3001 / U+3002 / U+FF0C / U+FF0E) don't share an
> identical bbox-derived `CharType`

---

## Summary

`HanKerning::FontData` in
[`han_kerning.cc`][han_kerning] shapes ten fixed test characters
(`kChars`) at construction time and classifies their resulting glyphs
into `kClose` / `kOpen` / `kMiddle` / `kOther` using
`CharTypeFromBounds()`. If the four "dot" characters
`、 (U+3001)`, `。 (U+3002)`, `，ｱU+FF0C)`, `．(U+FF0E)` do not all
classify to the same type, the dot group is reduced to `kOther` and
`has_alternative_spacing` is set to `false`. That flag gates
`text-spacing-trim` **for the entire font**, not just for the dot
characters — so a single inconsistent glyph (e.g. one corner-attached
dot among three centred dots, or vice versa) silently disables CJK
pair-squeeze for **every** punctuation pair in the document, including
pairs whose participating glyphs (e.g. `〕，`, `」。`, `：「`) have no
relationship to the disagreeing glyph.

This makes any of the following authoring patterns silently break
trim across the document:

- Subsetting Noto CJK and mixing TC + JP glyphs in the dot group
  (e.g. ZHT-centred `、/。/，` + JP-corner `．`)
- Font-fallback chains where one designer's punctuation font supplies
  only some of the dots and the next-fallback font supplies the rest
- Composite fonts (InDesign-style) used for typesetting that route
  individual punctuation glyphs to different physical font files

There is no developer signal — DevTools doesn't report which check
failed, the rendered text just doesn't trim. The disable is also
font-wide, not pair-wide.

## Repro

1. Build a subset Noto CJK web font where `U+FF0E` retains the
   JP-corner outline and `U+3001 / U+3002 / U+FF0C` are replaced with
   their ZHT-centred forms (e.g. via OpenType `locl` substitution
   chains in JP source for the first three but not for `．`).
2. Serve the font with `font-display: swap` and apply
   `text-spacing-trim: trim-start` on the document `<html lang="zh-Hant">`.
3. Type a paragraph containing `〕，` and observe whether `〕` half-trims.

Expected: `〕` half-trims against the following `，` (pair-squeeze fires;
this is what the spec
[CSS Text Module Level 4 § 7][css-text-4] describes for adjacent
fullwidth punctuation).

Actual: No trim. Devtools shows no warning. The same font with
`．` also swapped to ZHT-centred (so all four dots agree) trims
correctly.

A minimal repro font and HTML can be derived from
[diantenjeom][diantenjeom-repo] commit `842ee37`: `dist/fonts/
diantenjeom-sans-centered.woff2` ships the four dots all kMiddle and
trims; any commit-level modification that flips `．` to kClose
(e.g. `_strip_locl_for`, `cmap_reroute`, `_alias_locl_target_outline`)
disables font-wide trim. The repo's `docs/chrome-pair-squeeze.md`
records the full bisect.

## Root cause (from source)

In [`han_kerning.cc`][han_kerning], the `FontData` constructor:

```cpp
const UChar kChars[] = {
    kIdeographicComma,         // 、 (U+3001)
    kIdeographicFullStop,      // 。 (U+3002)
    kFullwidthComma,           // ， (U+FF0C)
    kFullwidthFullStop,        // ． (U+FF0E)
    kFullwidthColon,           // ： (U+FF1A)
    kFullwidthSemicolon,       // ； (U+FF1B)
    kLeftDoubleQuotationMark,  // " (U+201C)
    kLeftSingleQuotationMark,  // ' (U+2018)
    kRightDoubleQuotationMark, // " (U+201D)
    kRightSingleQuotationMark  // ' (U+2019)
};
```

shapes `kChars` against the font with the document locale,
classifies each result via:

```cpp
HanKerning::CharType CharTypeFromBounds(float half_em,
                                        const SkRect& bound,
                                        bool is_horizontal) {
  if (is_horizontal) {
    if (bound.right() <= half_em) return kClose;
    if (bound.left() >= half_em)  return kOpen;
    if (bound.width() <= half_em && bound.left() >= half_em / 2)
      return kMiddle;
  }
  // ...
  return kOther;
}
```

and aggregates per group:

```cpp
type_for_dot = CharTypeFromBounds(
    glyph_data_span.first(kDotSize),  // first 4 of kChars
    bounds_span.first(kDotSize), is_horizontal);
```

The span-based overload returns `kOther` if *any* glyph in the span
has a different type from the first. `type_for_dot == kOther`
then propagates to `has_alternative_spacing = false`, which gates the
entire trim feature application in
`HarfBuzzShaper::AppendFontFeatures()`.

## Why this is questionable

1. **The spec is glyph-agnostic.** [CSS Text 4 § 7][css-text-4]
   defines trim eligibility based on Unicode line-break class and
   East Asian Width, not on glyph bbox geometry. The bbox-derived
   type-consistency check is an undocumented implementation choice
   that web authors have no way to discover.

2. **Mixed-design fonts are legitimate.** OFL-licensed CJK fonts are
   often subset, merged, or composed. There is no spec-level
   requirement that the four dot glyphs share a visual design.
   Penalising mixed designs by silently disabling the feature
   conflates "designer chose to mix" with "font is broken".

3. **The disable cascade is over-broad.** If the four dots are
   inconsistent, trim is disabled for every pair in the font —
   including pairs like `〕，` that don't involve the disagreeing
   `．`, and including pairs in the colon / semicolon / quote groups
   that are checked independently. A pair-level (or group-level)
   downgrade would surface the same conservatism without breaking
   unrelated pairs.

4. **No developer feedback.** DevTools doesn't expose
   `has_alternative_spacing` or its inputs. There's no console
   warning, no inspector panel hint, no way to bisect the cause
   short of reading Blink source.

## Suggested fixes (in order of effort)

1. **Surface the gate to DevTools.** Add a console warning / Layout
   inspector hint when `has_alternative_spacing` is set to `false`,
   identifying which `kChars` codepoint caused the type
   inconsistency.

2. **Downgrade per-group instead of font-wide.** If the dots group
   is inconsistent, disable trim only for pairs involving the dot
   characters. Leave colon / semicolon / quotes / bracket-bracket
   pairs eligible.

3. **Replace bbox classification with Unicode-property-based
   classification** (the spec model). Use line-break / EAW class
   for pair eligibility; use `halt` / `chws` outputs verbatim for
   the actual offset. This matches the spec text and removes the
   designer-intent inference.

4. **Allow opt-in via OpenType feature tag.** If a font intentionally
   mixes designs, expose a feature tag (e.g. a future `tspc`) that
   confirms the designer has self-certified trim eligibility, so
   Chrome doesn't need to infer.

## Related work

- W3C csswg-drafts [#8293][csswg-8293] — discusses how
  text-spacing-trim should relate to halt / vhal / chws / vchw
- W3C csswg-drafts [#9504][csswg-9504] — `Pf` (final punctuation)
  classification
- Blink-dev intent-to-ship: ["CJK punctuation kerning: the CSS
  text-spacing-trim property"][i2s]

[han_kerning]: https://chromium.googlesource.com/chromium/src/+/HEAD/third_party/blink/renderer/platform/fonts/shaping/han_kerning.cc
[css-text-4]: https://www.w3.org/TR/css-text-4/#text-spacing-trim-property
[csswg-8293]: https://github.com/w3c/csswg-drafts/issues/8293
[csswg-9504]: https://github.com/w3c/csswg-drafts/issues/9504
[i2s]: https://groups.google.com/a/chromium.org/g/blink-dev/c/jVUR2ebE3e0
[diantenjeom-repo]: https://github.com/han-css/diantenjeom
