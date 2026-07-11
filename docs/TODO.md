# TODO

- **File the Chromium bug.** `docs/chromium-bug-report-draft.md` has a
  ready-to-paste draft. Findings to land:
  - `text-spacing-trim` is **not** a Noto-fingerprint check. It's
    `han_kerning.cc:CharTypeFromBounds()` running a type-consistency
    check across the four "dot" characters in `kChars`:
    `、 (U+3001)`, `。 (U+3002)`, `，(U+FF0C)`, `．(U+FF0E)`. After
    shaping (locl applied), the four glyphs' bboxes must classify to
    the same `CharType` (`kClose` / `kMiddle` / `kOpen` / `kOther`).
    If they don't, `has_alternative_spacing = false` and trim is
    disabled **font-wide** (not just for the disagreeing glyph).
  - A from-scratch custom font is unaffected, **provided the four
    dots are designed consistently** — all corner-attached or all
    centred. Mixed-design subsets (Diantenjeom MOE's case: TC
    centred `、/。/，` + JP corner `．`) trigger the gate.
  - Suggested fixes in the draft, in order of effort: surface the
    gate to DevTools → downgrade per-group instead of font-wide →
    replace bbox classification with Unicode-property-based
    classification (which matches the spec) → opt-in OpenType feature
    tag for designer self-certification.
  - When filing, swap the placeholder repo URL in the draft for the
    actual GitHub URL of this project. Target component:
    `Blink>Fonts>Shaping`.

- **縱排彎引號不參與 pair-squeeze。** `rotate_quotes` 建的四個 vert 形（glyph00186-189）墨水都在 em 中央（ink center ≈ 38% from top），Chrome `CharTypeFromBounds` 無法分類為 open 或 close，故 `'〈` 等配對不擠壓。修法：vert 形需把開引號 ink 下移至 em 底（TSB ≈ 600–750，比照 `〈`），閉引號 ink 上移至 em 頂（TSB ≈ 50–200）。此為既有限制，非 glyf 轉換退化。

- **MOE pair-squeeze drops `(Close, Open)` under `lang="ja"`.** Specifically
  `。「` (U+3002 + U+300C) doesn't squeeze under `lang="ja"`, but the same
  pair squeezes under `lang="zh-Hant" / "zh-Hans" / "ko"`. `。『`
  (U+3002 + U+300E) squeezes under all four langs. Confirmed still broken
  (2026-05-26). Root cause: Chromium `text-spacing-trim` heuristic classifies
  `「` differently from `『` under `ja`. To file as a Chromium bug — needs
  minimal repro.

- **Collapse per-style files into one shared subset.** The Noto CJK source
  carries `locl` GSUB rules that map the same Unicode punctuation to different
  glyph forms per OT language tag (JAN / ZHT / ZHS / KOR), so a single subset
  could serve every punctuation convention if downstream pages set `lang` or
  [`font-language-override`][fla] correctly. We currently ship one file per
  style and strip `locl` at build time, because **Safari does not yet
  implement `font-language-override`** and Chrome has precedence bugs when an
  HTML `lang` attribute is already set. Revisit once browser support
  stabilises — flip `locl` back on in `KEEP_FEATURES` (`src/diantenjeom/build.py`)
  and the alternate glyphs will be retained automatically.

[fla]: https://developer.mozilla.org/en-US/docs/Web/CSS/font-language-override

- **Latin-low ellipsis (`…`) sits slightly above the Latin baseline in
  Firefox inside a rotated Latin run.** Chrome and Safari place it on
  the baseline; Firefox places it ~50–80 font units higher (close
  enough but not perfect). Horizontal mode is identical across all
  three browsers, so this is a vertical-rotated-Latin-run-specific
  baseline-alignment quirk Firefox applies to U+2026 specifically. We
  picked `_LATIN_LOW_DY = -360` (vs the ideal -330 for Chrome / Safari)
  as the least-wrong compromise; revisit if Firefox's vertical text
  baseline handling for Common-script changes. See
  `docs/vertical-text.md` § "Ellipsis in Firefox vertical Latin runs"
  for the diagnostic timeline.

- **`! : ; ?` need a -50 unit outline pre-shift to look centred in
  Chrome / Safari, which leaves Firefox ~5 % off to the left.** Source
  Noto Sans CJK JP renders these glyphs ~10 % of em right of the CJK
  centre axis in Chrome / Safari (Firefox is fine). We couldn't find a
  font-side knob that nudges Chrome / Safari alone, so `center_punct`
  brute-forces the outlines (and matching hmtx LSB) left by 50 units
  — half the observed C/S offset — so C/S land on centre and Firefox
  lands ~5 % left. Both within visual tolerance. Revisit if a more
  precise fix surfaces (e.g. shipping per-glyph proportional `palt` /
  `vpal` values matching Hiragino's). See `docs/vertical-text.md`
  § "`! : ; ?` offset in Chrome / Safari vertical".

- **Square-stroke punctuation variant (、，。：；).** Noto CJK's comma /
  colon / semicolon use round curves; a Hiragino-style square-stroke
  design would pair better with gothic/黑體 body text. The build
  pipeline (`graft.py`) can splice any CFF2 VF outline, but the square
  outlines need to be drawn first — full VF designspace (wght 100–900
  for Sans, 200–900 for Serif). Hiragino outlines cannot be used
  (proprietary). Provide a `.glyphs` or `.designspace` source with the
  new drawings; integration into the build is straightforward.

- ~~**Align em-dash and 2-em-dash with the line's centre axis in vertical
  mode.**~~ ✅ Resolved 2026-05-14 by `dash_center.py`: shift the cmap
  `emdash` / `uni2E3A` outlines up by +105 units so the ink y-centre
  aligns with the CJK character body centre (matches `中`'s y_center=381).
  Both horizontal and vertical modes pick this up because the change is
  to the source outline itself rather than via GSUB — engines can ignore
  `vert` substitutions for UTR50 R-class codepoints, but they can't
  ignore the outline of the glyph they're rendering. See
  `docs/vertical-text.md` § "Dash alignment" → "Update (2026-05-14)".

## CFF2 → glyf conversion (2026-06-17)

- **GB ：/；lose right-side squeeze in glyf path.** After the CFF2→glyf
  conversion, `gb/sans/h` and `gb/serif/h` no longer squeeze ：/；pairs
  such as `：〉`, `：）`, `：，`. Root cause: Chrome's CoreText/DirectWrite
  glyph-type detection (in `han_kerning.cc`) differs from FreeType for
  left-aligned glyphs. GB ：(xMin≈194) is SC-sourced and left-aligned;
  JIS ：(xMin≈394) has `center_punct` applied so it's centred — Chrome
  squeezes centred ：but not left-aligned ：in the native path. Applying
  `center_punct` to GB ：would visually move the ink to centre, which
  contradicts GB/mainland style. Net outcome: gb/sans/h went from 804 →
  900 (+96, from curly quotes now squeezing), gb/serif/h went 804 → 760
  (-44). Deferred; slight-bracket is the lesser evil (see plan).
  Note: Chrome uses **hmtx LSB** (not glyf xMin) for horizontal
  pair-squeeze classification; syncing LSB to xMin restored GB ：；squeeze
  (+44 pairs) but cost MOE 。、，138 pairs — net worse, reverted.

## Tooling / CI (added 2026-06-14)

- ~~**Wire the pair-squeeze regression into CI.**~~ ✅ Done 2026-06-14:
  `ci.yml` runs `python scripts/check_squeeze.py` after the structural tests
  (ubuntu-latest ships `google-chrome`). Watch for cross-platform snapshot
  drift — the snapshot was generated on macOS Chrome; pair-squeeze is advance-
  based so it *should* be platform-stable, but a Chrome-version bump could
  shift amounts. If CI flags spurious diffs, re-`--update` on the runner.
- ~~**Tighten fontbakery once triaged.**~~ ✅ Done 2026-06-14: the CI step is
  now a hard gate (no `|| true`), running **per-file** (each `.otf` is its own
  family) with eight triaged `--exclude-checkid`s. Rationale for each exclude
  is inline in `ci.yml`. Triaged against fontbakery 1.1.0 — re-triage if a
  version bump adds/renames checks.
- **Deferred genuine font fixes (surfaced by the fontbakery triage).** Two
  excluded FAILs are real metadata nits, not subsetting noise — excluded only
  because fixing them is a build-pipeline change (rebuild + retest) out of
  scope for the CI wiring. Fix in `_canonicalize_instances`
  (`src/diantenjeom/build.py`) then drop the matching `-x` from `ci.yml`:
  - `opentype/varfont/valid_default_instance_nameids` — the instance whose
    coords equal the fvar default (Thin) should carry the bare PostScript name
    (`DiantenjeomSansJIS`), not the `-Thin`-suffixed form.
  - `opentype/fsselection` — the default instance's OS/2.fsSelection Regular
    bit (bit 6) isn't set. Likely shares a root cause with the above: the fvar
    default sits at Thin rather than a Regular (400) location.
- **New files under `docs/` need `git add -f`.** A global gitignore
  (`~/.gitignore_global`) ignores `docs/`; already-tracked docs are fine,
  but newly created ones are silently skipped unless force-added.
