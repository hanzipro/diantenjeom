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

## Open issue: ellipsis in Firefox vertical Latin runs

After splitting `…` (U+2026) into Latin-low (single) and CJK-centred
(paired), Chrome and Safari render both cases correctly in horizontal
**and** vertical writing mode. Firefox renders the horizontal case
correctly, but in a **rotated Latin run inside `writing-mode:
vertical-rl`** the single ellipsis floats noticeably higher than the
adjacent period or the run's Latin baseline.

**Current state (good enough across all three):**
- `cmap[U+2026]` → `ellipsis` with the outline shifted down by
  `_LATIN_LOW_DY = -360` (dots end up at y=-30 to +70). This is the
  least-wrong compromise:
  - Chrome / Safari render dots ~30 units below the Latin baseline
    (visually fine — barely noticeable).
  - Firefox renders them ~30 units above the Latin baseline (also
    visually fine).
  - The ideal value for Chrome / Safari alone would be -330; for
    Firefox alone roughly -400. -360 splits the difference.
- HVAR / VVAR entries for the modified `ellipsis` glyph cleared to
  "no variation" (0xFFFFFFFF) — the source's varStore deltas were
  calibrated for the unmodified outline and shifted position at
  non-default weights.
- Existing `vert` substitution retargeted from `ellipsis → glyph00042`
  onto a sibling `ellipsis.cjk` so single ellipsis in vertical does
  not become the CJK vertical stack.
- GSUB Chain Context Substitution under `ccmp` (every engine applies
  it in every writing mode — calt / liga were observed flaky in
  Firefox vertical-rl CJK runs) with separate Coverage objects per
  input position (CoreText silently ignores chain contexts whose
  input positions share a Coverage reference).

**Diagnostic timeline — what we tried, why most didn't help:**

1. Setting OS/2 `ulUnicodeRange1` bit 31 (General Punctuation) so the
   font advertises coverage of U+2026. **No effect.** (Kept anyway —
   it's the right thing to do for a font that covers this range.)
2. A `vert` sentinel self-substitution (`ellipsis → ellipsis`), the
   same trick that fixed `;` UTR50-rotation in Firefox. **No effect.**
3. Modifying the outline in place rather than creating a new glyph and
   re-pointing cmap. The hypothesis was that fontTools renaming new
   glyphs to `ellipsis` on save under post format 3.0 broke VVAR / HVAR
   index linking. In-place modification keeps the ID stable. **No
   visible effect on Firefox**, but kept as the cleaner design anyway.
4. Updating `vmtx` tsb to match the new bbox y_max (vs. leaving the
   source value). **No effect** either way.
5. Clearing HVAR / VVAR variation entries to "no variation". **No
   visible effect at default weight**, but kept (correctness).
6. Moving the chain context lookup between `calt`, `liga`, `ccmp` and
   combinations of those. **No visible difference for the single-glyph
   case**, settled on `ccmp` for engine-wide reliability.
7. Extreme outline shift (`_LATIN_LOW_DY = -1000`) as a diagnostic to
   verify Firefox actually uses our glyph. **Confirmed**: all three
   browsers showed dots at extreme low. Firefox does read the outline,
   it just adds a small constant vertical offset relative to the rest
   of the Latin run.

**Observations against Helvetica / ArialHB**, both of which render
this case correctly:

- Helvetica and ArialHB have **no** `BASE`, `vmtx`, or `VORG` tables.
  Our font has all three (required for CJK vertical typesetting).
  The hypothesis was that Firefox uses these tables for cross-axis
  baseline alignment of Common-script characters in rotated Latin
  runs. We couldn't drop them — they're load-bearing for the rest of
  the font. Tested neutralising specific entries on the ellipsis glyph
  to no effect.
- ArialHB's `ellipsis` bbox `(117, 0, 883, 100)` is **identical** to
  ours after the shift. Same em (1000). The only structural difference
  is the presence of the vertical-mode tables. The actual Firefox
  fix likely involves some metric we haven't isolated.

**Worth trying next** if revisiting:

- Build a debug font that drops `BASE` entirely and see whether
  Firefox falls back to outline-based positioning that matches
  Chrome / Safari.
- Provide a per-glyph `BASE` override (if such a thing exists in
  OpenType) for U+2026 declaring it Latin / `romn` baseline.
- Inspect Firefox source for the specific code path that positions
  Common-script glyphs in rotated Latin runs.

## Open issue: `! : ; ?` offset in Chrome / Safari vertical

In vertical writing mode `！` (U+FF01), `：` (U+FF1A), `；` (U+FF1B) and
`？` (U+FF1F) appear ~10 % of em to the right of where adjacent CJK
characters sit, in Chrome and Safari. Firefox renders them precisely
on the line's centre axis. Hiragino Sans — another full CJK font —
doesn't exhibit this in any browser. **Original unsubsetted Noto Sans
CJK JP also exhibits the offset** when shipped as a webfont, so it's
not introduced by our build pipeline; it's something Chrome / Safari
do downstream that we couldn't pin to any specific font metadata.

### Current state

`center_punct.install()` translates each affected glyph's CFF2 outline
left by **50 font units** (5 % em) and updates hmtx LSB to match. This
splits the visible delta:

- Chrome / Safari: now precisely on centre (was ~10 % right; -50 cancels
  half of it).
- Firefox: now ~5 % left of centre (was on centre; -50 shifts it that
  much).

Both are within visual tolerance. The trade-off is documented in the
README TODO.

### What we tested, all no-effect on Chrome / Safari

1. Shifting the source outline horizontally so each glyph's bbox is
   exactly em-centred — without an additional uniform shift this only
   moves Firefox, not C/S. Same with matching hmtx LSB to new x_min.
2. Zero-ing the GPOS `halt` SinglePos values (`XPlacement=-250,
   XAdvance=-500`) that source Noto Sans CJK JP ships for `! : ;`.
3. Zero-ing the GPOS `vhal` SinglePos values for the colon vert
   target.
4. Testing at `font-weight: 100` (= default-instance, no CFF2
   variation blending). Offset persists; not a blend issue.
5. Disabling every post-subset transform (pin_locale, rotate_quotes,
   vert_nudge, ellipsis_pair) and rebuilding with only fontTools'
   Subsetter. Offset still there. So the issue is introduced by the
   Subsetter (or by something earlier in the pipeline), not by any of
   our additions.
6. Keeping the source name `Noto Sans CJK JP` instead of renaming to
   `Diantenjeom Sans JP`. No effect — not a name-based heuristic.
7. Forcing `head.xMin/xMax` to match source values. fontTools'
   serialiser recomputes head bbox from outlines on save, so the
   override doesn't survive; we never got a clean test of whether
   head bbox influences the offset.

### Hiragino vs our font, what's structurally different

- Hiragino is CFF (non-variable); ours is CFF2 (variable wght axis).
  HVAR / VVAR / fvar / gvar / STAT exist only in ours.
- vhea ascent / descent: **same** (500 / −500).
- BASE table tags + coords: **virtually identical** (icfb=53/52,
  icft=947/948, ideo=0, romn=120).
- bbox centres of these glyphs: **virtually identical** (`?` is at
  ~494 in both fonts).
- GPOS positioning entries: Hiragino ships **both** `halt` AND `palt`
  SinglePos entries for these glyphs, with per-glyph proportional
  values in `palt` (e.g. `?`: XPlacement=−118, XAdvance=−244). Our
  subset has only `halt` (uniform −250 / −500), no `palt` for these
  glyphs. Hiragino additionally has `vpal` entries for `?` and `!`.

### Worth trying next

- Add `palt` (and `vpal`) SinglePos entries matching Hiragino's
  per-glyph proportional values for `! : ; ?` to our font. Risk: this
  changes the explicit-opt-in behaviour for callers who set
  `font-feature-settings: "palt"` themselves, but might let us drop
  the brute-force outline shift in favour of a cross-browser-correct
  positioning feature.
- Build a non-variable instance of our font (drop variation tables) and
  compare. If a non-variable version renders correctly in C/S, the
  bug is specifically in Chrome / Safari's CFF2 variable vertical
  pipeline.
- Find the exact Blink / WebKit code path that aligns Common-script
  CJK punctuation cross-axis in vertical mode and diff against the
  CFF (non-variable) path.

## Open issue: dash alignment

`—` (U+2014, em-dash) and `⸺` (U+2E3A, two-em dash) render slightly
off-centre relative to the ellipsis (`…`) in vertical mode in all three
browsers — and also in bare Hiragino Sans, so it's not unique to our
subset. Reproducing in plain HTML with `writing-mode: vertical-rl`:

    語料庫……
    ────
    待命中——

The dashes sit clearly left of the column's centre axis, while the
ellipsis sits dead-centre.

**Root cause.** UTR50 classifies both codepoints as `R` (always rotate
90° CW in vertical text). For `R`-class, browsers are expected to
auto-rotate the source glyph and **ignore** any `vert` substitution.
Three engines, three slightly different interpretations:

- **Chrome / Firefox** strictly follow UTR50 R — they rotate the source
  outline themselves, ignoring our `vert` lookup. The rotation pivot
  isn't (0, 0); empirically it appears to be advance-relative, so the
  rotated bar ends up offset from em/2 by an amount that depends on the
  glyph's horizontal advance.
- **Safari (CoreText)** applies `vert` for `—` but **not** for `⸺` —
  so even with a centred pre-rotated alternate in the font, the
  two-em-dash stays mis-aligned, and the em-dash version renders our
  alternate but with its own positioning quirks (we saw a visible gap
  in the middle of `——`).

**What we tried, didn't work.**

1. **Add a `vert` substitution with a pre-rotated, centred alternate**
   (the same trick that works for curly quotes). Safari respected it
   for `—` but ignored it for `⸺`; Chrome / Firefox ignored it for
   both. Code lived in `rotate_quotes.py`'s `ROTATE_CONFIGS`.

2. **Shift the source outline up so its y-centre sits at em/2** —
   intended to pre-compensate for the auto-rotation pivot. Result:
   Chrome / Firefox over-shot to the right (the pivot model was
   wrong), Safari `⸺` still untouched, Safari `——` showed
   "too right + middle gap". The shift also affected horizontal
   rendering of em-dashes (they'd appear at em/2 instead of around
   the baseline).

Both changes were reverted; `rotate_quotes.ROTATE_CONFIGS` no longer
includes `0x2014` / `0x2E3A`. The font now ships the dashes as-is from
Noto CJK, matching Hiragino's (also off-centre) behaviour.

### Update (2026-05-14): resolved by raw cmap-outline shift

The earlier attempts all went through GSUB (`vert` substitution to a
pre-rotated alternate, or `rotate_quotes`-style ROTATE_CONFIGS). They
hit UTR50 R-class semantics: Chrome and Firefox ignore `vert` /
`vrt2` for R-class codepoints and rotate the source glyph themselves;
Safari applies the substitution inconsistently. As long as we expected
the engine to honour our substitution, we couldn't move the dash.

We sidestepped the entire GSUB layer by **modifying the cmap glyph's
outline directly** — `dash_center.py` prepends an `0 dy rmoveto` to
the CharString of both `emdash` and `uni2E3A` (`dy = +105`), then
clears their HVAR / VVAR variation entries so wght-axis interpolation
doesn't re-drift the position. Effect:

- **Horizontal**: ink y_center moves from 275 (Latin x-height middle,
  inherited from Noto's Latin design) to 380 — matches a CJK character's
  body centre (`中` y_center = 381). The dashes now align with the
  surrounding character line.
- **Vertical**: UTR50 R-class browsers still auto-rotate the source
  outline, but because the source outline is itself shifted, the
  rotated position lands at the corresponding new centre axis. The
  off-centre / mid-`——`-gap symptoms from the earlier rotate_quotes
  attempt don't recur because we're not introducing a separate rotated
  alternate glyph — engines get exactly the cmap outline they expect,
  just at a different y.

Why this works where GSUB approaches didn't: an engine can ignore an
alternate-glyph substitution, but it cannot ignore the outline of the
glyph it's already chosen to render.

Ellipsis (`…`) is intentionally left alone — `ellipsis_pair.py`'s
"single Latin-low, paired CJK-centred" design is correct per
Latin / CJK typesetting conventions, and the single case sitting on
the Latin baseline is what the user wants for mixed-script paragraphs.

## Per-style vert nudges: Sans and Serif need different `，`/`、` offsets

The `vert_nudge.JP` dict (`{0x3001: -120, 0xFF0C: -120}`) was tuned
visually against Noto Sans CJK JP, where the vert-form comma
(`glyph00035`) ships with `vmtx` tsb = -28. After our -120 nudge it
lands at tsb = 92 — visually near the top of the 1000-unit vertical
slot, matching JP body-text convention.

Noto Serif CJK JP's source places the same vert form at **tsb = 102
already** (130 units lower than Sans). Applying the same -120 nudge
pushes Serif's comma to tsb = 222 — visually around mid-slot, well
past the "top-attached句讀" position.

The position itself was acceptable visually, but it broke browser
**`text-spacing-trim` squeeze detection on `〕，` pairs** (and likely
others). In all three browsers tested, vertical-mode `〕` followed by
`，` rendered with a full em of gap in Serif, whereas Sans rendered
the same pair tightly squeezed. `」，` / `』，` continued to squeeze
in both styles — the browser appears to allow-list "typical" CJK
quotes/brackets for pairwise trim regardless of comma position, but
fall back to a heuristic check for less-common closers like `〕`.
When the comma is too far from the slot top, that heuristic rejects
the pair.

**Fix.** Ship a separate `vert_nudge.JP_SERIF = {}` (empty) and wire
Serif to it in `build.py`. Serif's source position is already close
enough to where Sans's nudged version ends up — no transform needed.
Sans keeps its -120 nudge (different source baseline, still needs the
push).

The general rule that fell out: **vert nudges are per-style, not
per-locale** — the source font's default vert-form metrics differ
enough between Sans and Serif (and likely between locales' Noto CJK
sources too) that any locale-wide nudge dict needs splitting per
style as new variants come online.

**To pick this up again**, things worth trying next:

- Bypass `vert` entirely: emit a `ccmp` (always-on GSUB) substitution
  to a pre-rotated alternate. `ccmp` fires before UTR50 orientation
  logic, so browsers may apply it even for R-class codepoints. Risk:
  it would also affect horizontal mode, where the rotated alternate
  is the wrong shape.
- Find each browser's actual rotation pivot empirically (with a debug
  glyph at known coordinates) and pre-compensate per-engine.
- Replace the cmap mapping to point at a centred pre-rotated glyph,
  and add a horizontal-mode `ccmp` (or similar) substitution back to
  a horizontal alternate. Two glyphs per codepoint; might be worth it
  if shipping vertical-first.
