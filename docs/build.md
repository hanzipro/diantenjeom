# Build pipeline

How `npm run build` (i.e. `scripts/build_fonts.py` →
`src/diantenjeom/build.py`) turns a Noto CJK source font into a
punctuation-only subset.

## What gets built

Current scope: **Noto Sans JP only**. One variant:

| Locale | Style | Source                              | Output stem                  |
| ------ | ----- | ----------------------------------- | ---------------------------- |
| `jp`   | sans  | `sources/NotoSansCJKjp-VF.otf`      | `diantenjeom-sans-jp`        |

Outputs land in `dist/`:
- `dist/fonts/diantenjeom-sans-jp.otf` — desktop (InDesign, app text styles)
- `dist/fonts/diantenjeom-sans-jp.woff2` — web
- `dist/diantenjeom.css` — sample `@font-face` block

Other locales (`tc`, `sc`, `kr`) and the serif family are intentionally
not wired up yet — add `Variant(...)` rows in `build.py` when ready.

## Codepoint set

`src/diantenjeom/codepoints.py` holds the per-locale lists. `JP` mirrors
the table rows in `ja.html`, one entry per cell, in table order. **The
demo HTML is the source of truth** — if you change a row there, update
the list here.

Today's `JP` set has 25 codepoints covering 句號 / 逗號 / 頓號 /
引號 / 書名號 / 括號 / 破折號 / 刪節號 / 連接號 / 斜線 etc.

## Layout features (and why we keep them)

The previous `build.py` dropped `GSUB`/`GPOS` outright. That can't stand:
vertical typesetting and CSS punctuation-squeezing both live in those
tables. The current build keeps these tags:

| Feature       | Why                                                        |
| ------------- | ---------------------------------------------------------- |
| `vert`, `vrt2`| Vertical glyph alternates — required for `writing-mode: vertical-rl`. Without these, `。「」` etc. don't rotate/reposition. |
| `palt`, `vpal`| Proportional alternate metrics. This is the feature CSS `font-feature-settings: "palt"` (and the upcoming `text-spacing-trim`) target to squeeze full-width punctuation. |
| `halt`, `vhal`| Half-width alternate metrics — same idea, half-width track. |
| `fwid`, `hwid`, `pwid` | Explicit full/half/proportional width switches. |
| `kern`, `vkrn`| Pair kerning (horizontal / vertical).                      |
| `ccmp`, `locl`, `calt`, `rlig`, `mark`, `mkmk` | Standard shaping/positioning; harmless to keep. |

The subsetter follows GSUB closure under these tags, so the alternate
glyphs they reference (vertical forms, half-width forms) are pulled in
even though their codepoints aren't in our base set.

Vertical metric tables (`VORG`, `vhea`, `vmtx`, `VVAR`) are also kept
— the subsetter retains them by default; we just don't drop them.

The `wght` variable axis (100–900) is preserved end-to-end. The CSS
emits `format('woff2-variations')` and `font-weight: 100 900;`.

## Name table

The subset overwrites name IDs **1 / 4 / 6 / 16 / 21** so the OTF
identifies itself as `Diantenjeom Sans JP` instead of the original
`Noto Sans CJK JP`. Without this, installing the desktop OTF would
collide with an existing Noto install at OS level. We only write into
(platform, encoding, language) slots the source already had — no
inventing records for platforms the font never targeted.

## Running it

```sh
npm run build       # or: python3 scripts/build_fonts.py
```

Requires the source fonts under `sources/` (see `npm run fetch:sources`
and `sources/sources.lock.json`).

## Verifying a build

```sh
python3 -c "
from fontTools.ttLib import TTFont
f = TTFont('dist/fonts/diantenjeom-sans-jp.otf')
print('tables:', sorted(f.keys()))
print('GSUB:', sorted({r.FeatureTag for r in f['GSUB'].table.FeatureList.FeatureRecord}))
print('GPOS:', sorted({r.FeatureTag for r in f['GPOS'].table.FeatureList.FeatureRecord}))
print('cmap:', len(f.getBestCmap()), 'codepoints')
print('name1:', f['name'].getDebugName(1))
"
```

Expect to see `vert`, `vrt2` in GSUB; `palt`, `vpal`, `halt`, `vhal`,
`kern` in GPOS; `VORG`/`vhea`/`vmtx`/`VVAR` in the tables list; and
`Diantenjeom Sans JP` as name ID 1.

## Visual smoke test

Drop the woff2 into a page, set CSS to vertical, and toggle `palt`:

```html
<style>
@import url('./dist/diantenjeom.css');
.v {
  writing-mode: vertical-rl;
  font-family: 'Diantenjeom Sans JP', sans-serif;
  font-feature-settings: "palt";
}
</style>
<p class="v">「日本語」、句読点。《書名》〈篇〉……</p>
```

If `palt` collapses adjacent fullwidth punctuation and the brackets
rotate correctly in vertical mode, the build is healthy.

## Adding a new locale

1. Add the codepoint list to `src/diantenjeom/codepoints.py`, keyed by
   locale. Mirror whichever demo HTML defines that locale's table.
2. Append a `Variant(...)` row in `build.py`'s `variants` list,
   pointing at the right source `.otf`.
3. `npm run build`; verify with the snippet above.
