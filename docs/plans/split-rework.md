# Plan: 拆分 build 為 Locale / Segment 兩個獨立腳本

## 決議（已對齊）

1. **命名**：採用 **Locale / Segment**（取代 Group / Old-New）
   - Integrated 整套地區風 family → **Locale**：JP-default、Centered、SC
   - Per-group 分組 family → **Segment**：Joiner、Curly、Dot、Bracket、Mark

2. **腳本拆乾淨**：兩個獨立 build 腳本，共用底層 helper
   - `scripts/build_locale.py` → Locale family（6 face）
   - `scripts/build_segment.py` → Segment family（16 face 含新增 Mark Centered Rotated）
   - `package.json` build 串兩個

3. **回退到「前一個正常狀態」**：意思是把當前 `src/diantenjeom/build.py` 與
   `scripts/build_fonts.py` 從「整套 + 分組混在一起」清乾淨，回到只負責 Locale，
   再另起一個獨立檔給 Segment。已加進 Locale 但對 Locale 沒幫助的欄位（如
   `align_locl_cps`、`css_bundle`）拿掉；對 Locale 有用的欄位（`pin_locl_to`、
   `circle.install`、`pin_to_locale`）留下。

4. **Locale SC 修跨 lang 問題**：給 SC variant 加 `pin_locl_to="ZHS"`，
   讓 zh-Hant 下不被 ZHT locl 把 `、 。 ， ．` 換成 ZHT 居中。ZHS locl L7
   對 dots 沒 entry，所以 dots 永遠保持 cmap 設計（= JP corner，SC 自己
   也用同設計）。quote/mark 仍走 ZHS substitution（=我們要的 SC alt）。

5. **Colon 旋轉**：新增 `Mark Centered Rotated` 變體，不改 `Mark Centered`
   行為。最終 Mark 三個變體：
   - `Mark Centered`：JP 居中設計、`:` **不**旋轉（TW MOE 風）
     - 改 `upright_cps=(0xFF1A,)` 強制 upright
   - `Mark Centered Rotated`：JP 居中設計、`:` **會**旋轉（JP 風）
     - 不設 upright_cps，走 JAN vert 預設的旋轉 L50
   - `Mark Anchored`：SC 倚角設計、`:` 不旋轉（SC 風，已 OK）

6. **不在 scope**：
   - 不修 integrated Centered 在 ja/zh-Hans 下 4-dot mixed 的舊問題
   - 不修 integrated SC 在 ja 下 quote 不擠的舊問題
   - 不動其他 helper module 的內部邏輯

## 目標文件結構

```
src/diantenjeom/
  build.py              # 共用：Variant + subset_one + write_css(path) + helpers
                        #       (移除 main()、css_bundle 欄位、align_locl_cps 欄位)
  locale_variants.py    # 新：variants(sources) → 6 個 Locale Variant
  segment_variants.py   # 新：variants(sources) → 16 個 Segment Variant
                        #       含 align_locl_cps、Mark Centered Rotated

  align_locl.py         # 留：Segment 才用
  circle.py             # 留：兩家都用
  pin_locale.py         # 留：含 pin_locl_to 機制（兩家都用）
  其他 helper           # 不動

scripts/
  build_locale.py       # 新：呼 locale_variants + subset_one + write_css → dist/diantenjeom.css
  build_segment.py      # 新：呼 segment_variants + subset_one + write_css → dist/diantenjeom-segment.css
  fetch_sources.py      # 不動
  build_binomoto.py     # 不動

# 刪除：
  scripts/build_fonts.py
  dist/diantenjeom-split.css  # rebuild 後會被 diantenjeom-segment.css 取代

# 改名：
  demo-split.html → demo-segment.html （內部 CSS link 改 diantenjeom-segment.css）
```

`package.json`：
```json
"scripts": {
  "build": "python scripts/build_locale.py && python scripts/build_segment.py",
  ...
}
```

## TODO list（按執行順序）

- [ ] **1. 改 `src/diantenjeom/build.py`**
  - 移除 `Variant.css_bundle` 欄位
  - 移除 `Variant.align_locl_cps` 欄位
  - `write_css` 改 signature 成 `write_css(entries, output_path: Path)`，
    寫單檔 CSS（不再 multi-bundle）。`css_delegate_*` 邏輯保留。
  - 移除 `main()` 與 `if __name__` block
  - `subset_one` 內判斷 `align_locl` 用 `getattr(variant, "align_locl_cps", ())` 而非欄位
    （這樣兩種 Variant 共用一個 subset_one，不必拆）
  - 註解更新 — 說明這檔是純 library，main() 在 scripts 下

- [ ] **2. 新 `src/diantenjeom/locale_variants.py`**
  - `def variants(sources: Path) -> list[Variant]`：6 個 Locale variant
  - JP-default Sans / Serif（無 graft、預設 pipeline）
  - Centered Sans / Serif（TC graft 3 dots + css_delegate FF0E → diantenjeom-sans/serif）
  - **SC Sans / Serif** 加 `pin_locl_to="ZHS"`（修跨 lang dots 變居中問題）
  - 不裝 `align_locl_cps`、`css_bundle`

- [ ] **3. 新 `src/diantenjeom/segment_variants.py`**
  - `def variants(sources: Path) -> list[Variant]`：16 個 Segment variant
  - Joiner / Curly / Bracket × Sans/Serif（各無特殊處理）
  - Dot Anchored × Sans/Serif（align_locl_cps=DOT）
  - Dot Centered × Sans/Serif（TC graft + align_locl_cps=DOT + css_delegate FF0E → dot-anchored）
  - **Mark Centered × Sans/Serif**：`upright_cps=(0xFF1A,)` + `align_locl_cps=MARK`（: 不轉）
  - **Mark Centered Rotated × Sans/Serif (新)**：無 `upright_cps` + `align_locl_cps=MARK`（: 轉）
  - Mark Anchored × Sans/Serif（pin_to_locale=ZHS + pin_locl_to=ZHS + graft SC）

- [ ] **4. 新 `scripts/build_locale.py`**
  - argparse `--sources`
  - 呼 `locale_variants.variants(args.sources)`
  - For each: `subset_one(v)` → `entries`
  - `write_css(entries, DIST / "diantenjeom.css")`
  - 印 build log

- [ ] **5. 新 `scripts/build_segment.py`**
  - 同上，但呼 `segment_variants.variants`
  - 寫到 `DIST / "diantenjeom-segment.css"`

- [ ] **6. 刪 `scripts/build_fonts.py`**

- [ ] **7. `package.json`**
  - `"build"` 改為 `"python scripts/build_locale.py && python scripts/build_segment.py"`

- [ ] **8. Demo**
  - `mv demo-split.html demo-segment.html`
  - 內部 `<link>` 從 `diantenjeom-split.css` 改 `diantenjeom-segment.css`
  - JS 裡的 face names 不變（family 名沒變）

- [ ] **9. dist 清理**
  - `rm dist/diantenjeom-split.css`（rebuild 後 segment 路徑會產生 diantenjeom-segment.css）
  - `rm dist/fonts/dtjx-*` 已清（早先做過）

- [ ] **10. Rebuild + 驗證**
  - `pnpm build` 跑兩個腳本，產出乾淨
  - harfbuzz shape test 跨 lang × Locale + Segment 全變體
  - 重點驗：
    - Locale SC dots：跨 lang 都 JP corner ✓
    - Locale Centered：zh-Hant work、ja/zh-Hans 維持舊行為（不是 regression）
    - Segment Dot Centered：3-dot consistent（透過 css_delegate FF0E）
    - Mark Centered：: 直排不轉
    - Mark Centered Rotated：: 直排會轉
    - Mark Anchored：: 不轉、SC 倚角

## 改造後 face / file 清單

### Locale family（6 face × 2 file = 12 file，寫到 `dist/diantenjeom.css`）

```
diantenjeom-sans.{otf,woff2}              Diantenjeom Sans
diantenjeom-serif.{otf,woff2}             Diantenjeom Serif
diantenjeom-sans-centered.{otf,woff2}     Diantenjeom Sans Centered
diantenjeom-serif-centered.{otf,woff2}    Diantenjeom Serif Centered
diantenjeom-sans-sc.{otf,woff2}           Diantenjeom Sans SC
diantenjeom-serif-sc.{otf,woff2}          Diantenjeom Serif SC
```

### Segment family（16 face × 2 file = 32 file，寫到 `dist/diantenjeom-segment.css`）

```
diantenjeom-sans-joiner.{otf,woff2}                 Diantenjeom Sans Joiner
diantenjeom-serif-joiner.{otf,woff2}                Diantenjeom Serif Joiner
diantenjeom-sans-curly.{otf,woff2}                  Diantenjeom Sans Curly
diantenjeom-serif-curly.{otf,woff2}                 Diantenjeom Serif Curly
diantenjeom-sans-dot-anchored.{otf,woff2}           Diantenjeom Sans Dot Anchored
diantenjeom-serif-dot-anchored.{otf,woff2}          Diantenjeom Serif Dot Anchored
diantenjeom-sans-dot-centered.{otf,woff2}           Diantenjeom Sans Dot Centered
diantenjeom-serif-dot-centered.{otf,woff2}          Diantenjeom Serif Dot Centered
diantenjeom-sans-bracket.{otf,woff2}                Diantenjeom Sans Bracket
diantenjeom-serif-bracket.{otf,woff2}               Diantenjeom Serif Bracket
diantenjeom-sans-mark-centered.{otf,woff2}          Diantenjeom Sans Mark Centered
diantenjeom-serif-mark-centered.{otf,woff2}         Diantenjeom Serif Mark Centered
diantenjeom-sans-mark-centered-rotated.{otf,woff2}  Diantenjeom Sans Mark Centered Rotated  *(new)*
diantenjeom-serif-mark-centered-rotated.{otf,woff2} Diantenjeom Serif Mark Centered Rotated  *(new)*
diantenjeom-sans-mark-anchored.{otf,woff2}          Diantenjeom Sans Mark Anchored
diantenjeom-serif-mark-anchored.{otf,woff2}         Diantenjeom Serif Mark Anchored
```

### 兩個 family 在 CSS 引用上完全獨立

- 用戶想要某個地區整體風 → `<link href="dist/diantenjeom.css">` + 引用 `Diantenjeom Sans` / `Sans Centered` / `Sans SC`
- 用戶想要分組 mix-and-match → `<link href="dist/diantenjeom-segment.css">` + 用 fallback chain 拼 Joiner/Curly/Dot/Bracket/Mark
- 兩個都要 → 兩個 `<link>` 都加

## 風險與已知不確定

1. **單一 `Variant` dataclass 同時服務兩個 family** — 用 `getattr(v, "align_locl_cps", ())` fallback 處理 segment-only 欄位，避免基類有 segment-only 欄位的污染。Locale variants 不會用到 align_locl 邏輯（cps=()）就 no-op。

2. **`write_css` 不再 multi-bundle** — 兩個 script 各自 call `write_css(entries, output_path)` 寫各自的檔。`css_delegate_donor_stem` 跨 bundle 不會發生（Locale Centered delegates `．` 給 Diantenjeom Sans，同 bundle；Dot Centered delegates 給 Dot Anchored，同 bundle）。OK。

3. **SC variant 加 pin_locl_to="ZHS" 會不會破 gate** — 之前已驗過 SC 在 zh-Hant 下 ZHS-pinned locl 仍 fire 真實 substitution（quotes/marks 替換）→ gate 過。dots 不被 ZHS 觸及，跨 lang 都保持 JP corner（kClose）→ 4-dot 一致 → gate 過。

4. **Mark Centered upright + Mark Centered Rotated 兩個變體**：Sans + Serif 共 4 file 新增。
   寫到 dist。

5. **demo-segment.html 還有 ` ／ ` 分隔符** — 之前已 sed 換成 `<br>`，OK。

6. **Locale Centered 在 ja/zh-Hans 下 4-dot mixed 的舊問題** — 不在本次 scope 內。
   若日後要修，建議路徑同 Dot Centered：把 cmap 的 `．` 移除（subset 不放）+ 用
   `unicode-range` 委派給 JP-default。但會 break 既有 `Diantenjeom Sans Centered`
   下 `．` 永遠可用的契約，需要單獨 plan。

## Definition of Done

- `scripts/build_locale.py` 與 `scripts/build_segment.py` 都能單獨成功 build
- `dist/diantenjeom.css` 與 `dist/diantenjeom-segment.css` 各自獨立、不相互覆蓋
- `dist/fonts/` 有完整 12 + 32 = 44 個 .otf + .woff2 檔案
- `demo-segment.html` 可用，所有 face on/off + Dot/Mark variant 切換正常
- Locale SC dots 跨 lang 都 JP corner
- Segment Mark Centered: 不轉、Mark Centered Rotated: 旋轉、Mark Anchored: 不轉
- `pnpm build` 一次跑完兩個腳本
