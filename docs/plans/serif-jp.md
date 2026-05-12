# Plan: Noto Serif CJK JP variant (`diantenjeom-serif-jp`)

## Goal

Ship a Serif counterpart to the existing Sans JP build with **identical
behavior** — same codepoint set, same vert/vrt2 wiring, same rotated
quotes, same vert nudges, same ellipsis split, same `! : ; ?` shift,
same `font-weight: 100 900` axis exposure, same `@font-face` CSS block.

Source font already in tree: `sources/NotoSerifCJKjp-VF.otf`.

## Assumptions to verify before coding

The whole point of the plan is that 99 % of the pipeline is Sans-agnostic
and should just work on Serif. Things to confirm by introspection on
`NotoSerifCJKjp-VF.otf` first:

1. **Font format is CFF2 variable** with a `wght` axis 100–900 — same
   shape as Sans. (`_outline.shift_in_place` assumes `CFF2`.)
2. **`vert` GSUB lookups** exist for the same codepoints we transform
   (`、 ， ！ ： ； ？ … 「 」 『 』` …). If any are missing the build
   will silently skip them — check with a quick dump.
3. **Glyph names** follow the same `glyph#####` / `uniXXXX` scheme so
   `_find_vert_target` returns sensible names.
4. **LangSysRecord layout** is the same shape as Sans, so `pin_locale`
   strips them without surprises.
5. **`vmtx` / `VORG` / `vhea`** tables present (vertical metrics).
6. **fvar instance PS names** — likely `NotoSerifCJKjp-*`; need the same
   rename treatment as the Sans cleanup.

If any of these diverge, surface a focused diff before writing code —
don't paper over with conditionals.

## Implementation steps

The plan is *narrow on purpose*: add one Variant row, run, fix only
what actually breaks.

1. **Smoke-check the source** (no code yet)
   - Dump tables / fvar / a few representative GSUB lookups from
     `NotoSerifCJKjp-VF.otf` and confirm assumptions 1–6 above.
   - Time-box: 5 min.

2. **Add a Serif variant to `build.py`**
   - Append a second `Variant(locale="jp", style="serif", …)` to the
     `variants` list in `main()`.
   - Re-use `codepoints.JP`, `vert_nudge.JP`, default `rotate_configs`.
   - No changes to `Variant`, no per-variant feature switches —
     anything that differs between Sans and Serif belongs in the data
     dicts, not in branching logic.

3. **Run build, observe.**
   - `pnpm build` (or whichever script wraps `python -m diantenjeom.build`).
   - Expected outputs: `dist/fonts/diantenjeom-serif-jp.{otf,woff2}` and
     an updated `dist/diantenjeom.css` with a second `@font-face` block.

4. **Visual regression in `article.html`**
   - The existing `明體` checkbox in `article.html` already toggles a
     CSS family swap (per current markup). Wire it through to the new
     Serif `@font-face` family name (`Diantenjeom Serif JP`).
   - Test matrix per the existing Sans coverage:
     - Chrome / Safari / Firefox, latest
     - Horizontal + vertical
     - `font-weight` slider sweep 100 → 900 (verifies blend ops
       survived `center_punct` / `vert_nudge` / `ellipsis_pair` for
       Serif outlines too)
   - Spot-check the previously-fixed quirks:
     - Curly-quote rotation in vertical
     - 、 ，  vertical nudge
     - Single vs paired ellipsis
     - `! : ; ?` horizontal centering in C/S
     - Locale pinning (same glyph forms under `lang=zh-Hant` / `ja`)

5. **Fix only what breaks.**
   - Likely-zero scenario: pipeline just works because every transform
     is data-driven off codepoints, not glyph IDs.
   - Possible breakage: Serif's `vert` mapping points to differently-
     named glyphs and one of the heuristics in `rotate_quotes` /
     `ellipsis_pair` doesn't find them. Fix is local to that module,
     not the pipeline.

6. **Fix fvar instance PS-name leak** (bundled with this task since
   we're touching `build.py`)
   - Extend `_rename_family` to rewrite name IDs 25 (PS-name prefix
     for variations) and the per-instance PostScriptNameID strings
     (currently IDs 267 / 269 / … all read `NotoSansCJKjp-*` or
     `NotoSerifCJKjp-*`).
   - Map `NotoSansCJKjp-Foo` → `DiantenjeomSansJP-Foo` and the Serif
     equivalent. Preserve copyright (ID 0) and trademark (ID 7).
   - This applies retroactively to the Sans build too — desired.

## Out of scope

- TC / SC / KR locales (Serif or Sans) — those need their own
  `codepoints.*` / `vert_nudges` work that's not Serif-specific.
- Re-litigating any of the documented residual quirks
  (`docs/vertical-text.md`).
- A separate Serif demo page — `article.html` toggles family already.

## Risks

- **CFF2 differences**: if Serif glyphs use stylistic substitutions
  (e.g. some GSUB chain we don't keep), the wrong glyph might end up
  as the `vert` target. Mitigation: step 1 introspection.
- **Outline shift visual**: `_SHIFT_DX = -50` in `center_punct` was
  tuned against Sans bbox widths. Serif `! : ; ?` may have different
  bbox metrics and want a different shift. Mitigation: visual check in
  step 4 with all three browsers; tune per-style if needed (would
  promote `_SHIFT_DX` into a `Variant` field).
- **vert nudge amount**: `JP = {0x3001: -120, 0xFF0C: -120}` was set
  visually against Sans. Serif may want a slightly different value;
  same mitigation as above (data-driven, no code change).

## Definition of done

- `dist/fonts/diantenjeom-serif-jp.{otf,woff2}` builds clean.
- `dist/diantenjeom.css` has both Sans and Serif `@font-face` blocks.
- `article.html`'s 明體 checkbox swaps in the Serif family and renders
  correctly in Chrome / Safari / Firefox, horizontal + vertical, across
  the weight slider range.
- fvar instance PS names no longer contain `NotoSansCJKjp` /
  `NotoSerifCJKjp`.
- One commit per logical step (smoke + variant row + rename fix).
