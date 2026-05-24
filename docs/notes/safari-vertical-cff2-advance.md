# Lesson: Safari/CoreText ignores per-glyph vertical advance in CFF2

## What we tried to build

A "vertical pair-squeeze" — when an opening bracket follows `：；！？` in
vertical writing-mode, halve the bracket's vertical advance and lift its
ink into the top half of the slot. Visually equivalent to what Chrome's
`text-spacing-trim: trim-start` produces for the same pair, but driven
from the font side so it works in any browser.

Lived in `src/diantenjeom/vert_pair_squeeze.py` from 5bf12ec until this
revert.

## How it worked in Chrome

1. Clone every opening bracket's `vert`-substituted glyph. The clone has:
   - outline shifted up by +500 units,
   - `vmtx` advance = 500 (half em),
   - `vmtx` tsb decremented by 500 to compensate for the outline lift.

2. A GSUB `ChainContextSubst` under `ccmp`:
   - backtrack = `：；！？` (and their `vert` forms),
   - input = the opening bracket vert glyphs,
   - action = `SingleSubst` swapping bracket → clone.

3. `ccmp` is required-always-on in every shaping engine, so no CSS feature
   needed to be enabled.

Chrome rendered this exactly as designed: bracket lifted into the top
half, next character drops into the bottom half, no gap.

## Why Safari broke

Symptom: after the ccmp substitution fires, Safari draws the bracket in
the top half of the slot (so the outline shift is honoured) but then
advances by a **full em**, leaving a half-em gap before the next CJK
character.

That is, Safari/CoreText's CFF2 vertical pipeline does **not** read the
clone's per-glyph `vmtx` vertical advance. It used the font's em as the
advance for our newly-added glyph, defeating the entire squeeze.

We confirmed table integrity was not the issue:

- `maxp.numGlyphs` = `CFF2.numGlyphs` = `hmtx`/`vmtx` count =
  `glyphOrder` length = `vhea.numberOfVMetrics` — all 193, consistent.
- The clone was present in `vmtx.metrics` with `(500, ...)`.
- `hb-shape` / FreeType / Chrome all read the half advance correctly.

## Things we tried that did **not** fix Safari

### 1. Write a `VORG` entry for the clone

Hypothesis: Safari uses VORG for vertical origin, and an unrecorded clone
falls back to `defaultVertOriginY`, throwing the origin off. We wrote a
VORG record mirroring the src's value.

Result: no change. Inspection showed Safari was already getting the right
ink position — VORG wasn't the gap source.

### 2. Set `VVAR.AdvHeightMap[clone]` to the src's varIdx (instead of `0xFFFFFFFF`)

Hypothesis: every other glyph in the font points to varIdx `0` (the
zero-delta item). Our clone pointed to `0xFFFFFFFF` (the "no variation"
sentinel). Spec-wise that means "use the `vmtx` default value", but
Safari/CoreText may interpret it as "this glyph has no advance recorded"
and fall back to the font em advance.

We changed the clone's varIdx to inherit from the src (= `0` in
Diantenjeom, the zero-delta item).

Result: no change. Either Safari treats `0xFFFFFFFF` and `0` identically
(in which case the original hypothesis was wrong), or `VVAR` simply isn't
where Safari gets the per-glyph advance for CFF2 vertical.

### 3. Add a `vkrn` `SinglePos` `YAdvance = -500` targeting the clones

Hypothesis: if Safari isn't reading per-glyph `vmtx`, maybe it does
respect GPOS `YAdvance` (CoreText is generally OT-spec compliant). Chrome
is known to **ignore** GPOS `YAdvance` in its vertical pipeline (only
reads `vmtx` — see the original module docstring), so this wouldn't
double-squeeze Chrome.

Result: no change. Safari still rendered the half-em gap. Either CoreText
also skips GPOS `YAdvance` for CFF2 vertical text, or `vkrn` doesn't get
applied to glyphs that arrived via a `ccmp` substitution in this pipeline.

## The takeaway

> For CFF2 fonts in vertical writing-mode, **Safari/CoreText appears to
> use the font's em as the vertical advance for every glyph, ignoring
> both per-glyph `vmtx` and GPOS `YAdvance`.**

We could not find any OpenType table that lets us give a single CFF2 glyph
a non-em vertical advance and have Safari honour it. The font-side
pair-squeeze approach is a Chrome-only mechanism.

Open questions we did not resolve:

- Does Safari use `OS/2.sTypoAscender + sTypoDescender`, `vhea.ascent +
  vhea.descent`, or `head.unitsPerEm` for the vertical advance?
- Does the same limitation apply to TrueType (`glyf`) fonts, or only
  CFF2?
- Does enabling `vpal`/`halt`/`vhal` via CSS `font-feature-settings`
  shift this — i.e. does Safari read those per-glyph adjustments even
  when it ignores `vmtx`?

These are worth probing only if we decide to try again with a different
mechanism.

## What we kept

- `vert_nudge.py` still moves CJK punctuation in vertical layout — that
  uses GPOS `YPlacement` (not `YAdvance`), which Safari does respect.
- Source Han JP's own built-in vertical metrics (used by the JIS variant)
  continue to give the natural `：「` squeeze in vertical Japanese — that
  ships in the donor font's `palt`/`vpal` tables and was never something
  we added.
- Chrome's `text-spacing-trim: trim-start` (declared in `main.css`)
  continues to give a CSS-driven squeeze in Chromium-based browsers.

## What was reverted

- Deleted `src/diantenjeom/vert_pair_squeeze.py`.
- Removed its `install()` call and the three `Variant` config fields
  (`vert_pair_squeeze_extra_brackets`, `_extra_pair_chains`,
  `_extra_cascade_inputs`) from `src/diantenjeom/build.py`.
- Removed the four bracket pairs (`【】〖〗［］｛｝`) that 5bf12ec added
  to `BASE` in `src/diantenjeom/codepoints.py` — they were brought in
  only as squeeze inputs.
- Restored `demo.html` to its pre-1b98d09 state (removed the bracket
  pair-squeeze test cases).
