# Vertical CJK rendering across browsers

Browsers disagree wildly about how to render vertical CJK text from a
CFF2 variable font. This doc records the divergences we hit while
shipping the JP subset, and what the build does to mask them so all
three majors (Chrome, Safari, Firefox) render the same.

If you're touching `pin_locale.py`, `vert_nudge.py`, or `rotate_quotes.py`
and something breaks, start here.

## TL;DR cheat sheet

| Behaviour                                  | Chrome   | Safari   | Firefox  | Fix                       |
| ------------------------------------------ | -------- | -------- | -------- | ------------------------- |
| Honours `vert` GSUB substitution           | ✓        | ✓ (via vrt2) | ✓    | universal                 |
| Honours `vrt2` over `vert`                 | =        | prefers vrt2 | =    | alias both to JAN lookups |
| Reads VORG for vertical glyph position     | ✗        | ✓        | ✓ (HB)   | also write vmtx tsb + GPOS|
| Reads vmtx tsb for vertical glyph position | ✓        | =        | ✓        | (Chrome's main signal)    |
| Reaches orphan feature records by tag      | ✗        | ✓ (CoreText) | ✓     | alias every record to JAN |
| Applies orphan lookups by tag-walk         | ✗        | ✗        | ✓        | empty orphan mappings     |
| Strictly applies UTR50 Tr → rotate         | ✗ (lax)  | ✗ (lax)  | ✓ (strict) | sentinel self-subst     |

## The five quirks

### 1. CFF2 vertical positioning: Chrome ≠ Safari ≠ Firefox

We wanted to nudge `、`(U+3001) and `，`(U+FF0C) a bit down in vertical
mode because Noto JP's vert glyphs sit very tight to the top. Three font
metadata knobs exist for this and **each browser listens to a different
one**:

- **vmtx `tsb`** (top side bearing) — Chrome's main signal for CFF2
  vertical position. Raising tsb pushes the glyph down in the slot.
- **VORG** (per-glyph vertical origin) — Safari / CoreText. Raising
  VORG_y pushes the rendered glyph down.
- **GPOS `SinglePos` under `vkrn`** — Firefox / HarfBuzz. Negative
  yPlacement pushes the glyph down.

No single knob worked everywhere. `vert_nudge.install()` writes all
three (consistent direction, sign-flipped where the OpenType convention
disagrees with screen "down").

### 2. Safari prefers `vrt2` over `vert`

Noto Sans CJK JP ships separate `vert` and `vrt2` feature records with
different lookup lists. JAN's `vert` includes lookup #5 (which rotates
`：`); `vrt2` doesn't. Chrome / Firefox apply `vert`, Safari prefers
`vrt2` → on Safari the colon stayed stacked.

`pin_locale._alias_vert_to_jan()` pins both `vert` and `vrt2` to
JAN's lookup list. Now Chrome (vert) and Safari (vrt2) compute the
same substitutions.

### 3. Locale-tagged feature records: stripping LangSys isn't enough

Noto CJK encodes per-locale vertical layout in TWO ways:

1. `locl` GSUB feature — we already drop this (see `KEEP_FEATURES`).
2. **Multiple `vert`/`vrt2` feature records, one per OT LangSys** —
   `DefaultLangSys` (JAN), `KOR`, `ZHT/ZHH`, `ZHS`. Each points at a
   different lookup list, so a page with `lang="zh-Hant"` resolves to
   the ZHT record, which omits some JP-style substitutions (e.g. the
   colon rotation).

The naive fix is to strip every non-default `LangSysRecord` so every
OT language falls back to `DefaultLangSys`. That fixes Chrome.

**But Safari/CoreText still picked the wrong record** — it walks the
FeatureList by tag and reaches into now-orphaned records (the ZHT vert
record still exists in the table, just no LangSys points at it).
`_alias_vert_to_jan()` rewrites **every** `vert`/`vrt2` record's lookup
list to JAN's, so even if CoreText finds an orphan record, it executes
JAN's lookups.

### 4. Firefox applies orphan lookups by tag-walking

After fixing (3), one regression appeared: Firefox started rotating
`；`. Cause: lookup #7 (originally KOR-specific, mapping `;!?` to their
rotated forms) was no longer referenced by any feature, but Firefox
tag-walked the lookup list and applied it anyway. Chrome / Safari
respect the reference graph.

`_empty_orphan_lookups()` wipes the `mapping` of every unreferenced
GSUB lookup. The lookup objects stay (avoids index reshuffles) but do
nothing when invoked.

### 5. Firefox strictly applies UTR50; Chrome / Safari are lax

UTR50 (Unicode Vertical Orientation) classifies each codepoint as:

- **U** — always upright
- **R** — always rotate 90° CW
- **Tu** — upright by default, replaced by `vert` substitute if present
- **Tr** — **rotate by default**, replaced by `vert` substitute (and
  then rendered upright with the substitute) if present

Firefox implements this faithfully. Chrome and Safari are lax: even for
Tr-class codepoints without any `vert` subst, they don't rotate.

`；` (U+FF1B) is Tr-class. JAN convention keeps it upright (Noto's JAN
`vert` lookup has no rule for it). Result: Firefox rotated it, Chrome
/ Safari didn't — matching the same problem with bare Hiragino, so
not unique to our subset.

`_add_upright_self_substs()` registers `uniFF1B → uniFF1B` (identity
substitution) under JAN's vert lookup. Firefox reads it as "vert
handles this glyph — render upright with the substituted (= same)
glyph", which is the UTR50-defined override for Tr. The substituted
glyph is identical, so visually nothing changes; the substitution
exists only to flip Firefox out of the Tr-default rotate branch.

This pattern — substituting a glyph with itself purely to flip
UTR50/shaping behaviour — is sometimes called a **sentinel
substitution** or **identity vert subst**.

## Cache busting during iteration

`pnpm dev` won't always serve fresh bytes when you rebuild:

- **`serve` (the package)** holds an in-memory copy. Stop and restart
  if the served WOFF2 hash doesn't match `dist/`.
- **Chrome font cache** is separate from HTTP cache; DevTools "Disable
  cache" doesn't always touch it. Hard refresh (⌘+Shift+R) usually
  evicts; quit and reopen Chrome if it doesn't.
- **Safari + macOS system font cache** is the worst. Even Private
  windows can serve stale parsed fonts because macOS's `fontd` caches
  at the OS level. Full ⌘+Q and reopen Safari; if still stale,
  `sudo atsutil databases -remove`.

A quick sanity check we used repeatedly:

```sh
shasum -a 256 dist/fonts/diantenjeom-sans-jp.woff2
curl -s http://localhost:3000/dist/fonts/diantenjeom-sans-jp.woff2 | shasum -a 256
```

If those two hashes differ, fix the server before chasing rendering
ghosts.
