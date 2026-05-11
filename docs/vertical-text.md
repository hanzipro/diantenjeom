# Vertical CJK rendering across browsers

Browsers disagree wildly about how to render vertical CJK text from a
CFF2 variable font. This doc records the divergences we hit while
shipping the JP subset, and what the build does to mask them so all
three majors (Chrome, Safari, Firefox) render the same.

If you're touching `pin_locale.py`, `vert_nudge.py`, or `rotate_quotes.py`
and something breaks, start here.

## TL;DR cheat sheet

| Behaviour                                       | Chrome   | Safari   | Firefox    | Fix                          |
| ----------------------------------------------- | -------- | -------- | ---------- | ---------------------------- |
| Honours `vert` GSUB substitution                | ✓        | ✓ (via vrt2) | ✓      | universal                    |
| Honours `vrt2` over `vert`                      | =        | prefers vrt2 | =      | alias both to JAN lookups    |
| Reaches orphan feature records by tag           | ✗        | ✓ (CoreText) | ✓      | alias every record to JAN    |
| Applies orphan lookups by tag-walk              | ✗        | ✗        | ✓          | empty orphan mappings        |
| Strictly applies UTR50 Tr → rotate              | ✗ (lax)  | ✗ (lax)  | ✓ (strict) | sentinel self-subst          |
| **Vertical-glyph position: reads vmtx `tsb`**   | ✓ primary | ✗       | ✗          | Chrome's only signal         |
| **Vertical-glyph position: reads VORG**         | ✗        | ✓        | ✗          | Safari uses this — but compounds with outline (see below) |
| **Vertical-glyph position: reads outline bbox** | ✗        | ✓ (additive) | ✓ primary | Safari + Firefox             |
| Vertical font-side rotation: needs pre-rotated outline + `vert` subst | ✓ (vmtx for slot) | ✓ (VORG for slot) | ✓ (bbox for slot) | per-glyph VORG + vAdvance ≈ 0.4 em |

## The five quirks

### 1. CFF2 vertical positioning: Chrome ≠ Safari ≠ Firefox

We wanted to nudge `、`(U+3001) and `，`(U+FF0C) a bit down in vertical
mode because Noto JP's vert glyphs sit very tight to the top. After a
long iteration we landed on **`vmtx tsb` + outline translation** as the
combination that gives a single consistent shift across all three
engines:

- **Chrome** reads vmtx `tsb` (top side bearing). Raising tsb pushes the
  glyph down. Chrome ignores VORG and outline-y for vertical CJK; it's
  effectively a metric-only renderer.
- **Safari** (CoreText) reads VORG *and* outline bbox. Both contribute
  to position, so writing VORG **and** shifting the outline compounds
  to a 2× shift — we therefore write only the outline shift on Safari's
  behalf.
- **Firefox** reads only the outline bbox. Neither vmtx nor VORG nor
  GPOS SinglePos under `vkrn` had any effect during our tests.

So `vert_nudge.install()` does two things:

1. Bump `vmtx tsb` by `|dy|` on both the base cmap glyph (`uni3001` /
   `uniFF0C`) and the vert-substituted glyph (`glyph00036` /
   `glyph00035`) — covers Chrome.
2. Translate the vert-substituted glyph's CFF2 outline by `(0, dy)` —
   covers Safari and Firefox.

It deliberately does **NOT** write VORG or GPOS for these glyphs.
VORG would compound with the outline shift in Safari (we saw 2× shift
during iteration). GPOS yPlacement under `vkrn` had no observable
effect in any of the three browsers for this case.

**Sign convention exposed to callers:** a negative `dy` in
`vert_nudge.JP` means "move the rendered glyph DOWN". The mechanism
flips signs internally where the OpenType convention disagrees with
screen "down" (vmtx tsb grows positive going down; outline-y grows
negative going down — both end up consistent with the caller's sign).

### 1b. Rotated curly quotes: a similar three-way disagreement

The same browser split shows up for the pre-rotated Latin curly quotes
(`rotate_quotes.py`): Chrome positions them from `vmtx`, Safari from
VORG, Firefox from the outline bbox. We solve it by writing **both**
`vmtx` and a per-glyph VORG that agree with each other (VORG = bbox
y_max, tsb = 0), then setting `vAdvance ≈ 0.4 em` so Firefox's
bbox-derived slot height is large enough not to crowd the previous
character but small enough not to balloon the line spacing. The
outline is already where it needs to be (centred in its em), so we
don't translate it again.

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
