# Plan: 修 DTJ SC 在 Chrome 的對成擠壓不 fire

## 觀測

`demo-sc-quotes.html` 直接讀 `sources/NotoSans/SerifCJKsc-VF.otf`：
- `text-spacing-trim: normal` + 任何 lang ⇒ `“‘`、`」「`、`”「`、`」“` 全部擠壓 ✓

我們 build 的 `dist/fonts/diantenjeom-sans-sc.otf` 加上同樣 CSS：
- 全沒擠壓（不只彎引號 — 括號、`」「` 也沒）

→ 證明 Chrome 規範與 source 字體都是對的，問題在我們 pipeline。

## 根因（已 pin）

跑 GSUB feature 對照：

| feature | Noto Sans CJK SC raw | DTJ Sans SC |
|---|---|---|
| `locl` | 有，JAN 下對 6 個 kChar substitute (`‘’“”：；`) | **完全沒有** |
| `calt` | 有 | 沒 (subset 後無 entry，prune 掉) |
| `aalt`/`dlig`/`hist`/`liga`/`ruby`/`*jmo` | 有 | 沒 |
| 其它 (`ccmp`/`fwid`/`hwid`/`pwid`/`vert`/`vrt2`) | 有 | 有 |

GPOS：`halt`/`palt` 都有，coverage 也覆蓋 4 個 quote（我們的 gpos_graft 工作的）。

`docs/chrome-pair-squeeze.md` 已多次驗過：**`locl` 缺席 → Chrome `text-spacing-trim` font-wide 關閉**。這是 gate-level 的硬條件。Centered variant 用 `layout_features=("*",)` 保住 locl，所以擠壓 OK；SC variant 用預設 `KEEP_FEATURES`（其中沒有 `locl`），就掉進同一個坑。

## 改善計畫

### Step 1（核心修正）— SC variant 改用 `layout_features=("*",)`

`src/diantenjeom/build.py` SC sans / serif 兩個 `Variant(...)` row 加一行：

```python
layout_features=("*",),
```

跟 Centered 一致。副作用：原本被 subset prune 的 calt / aalt / liga / dlig / hist / ruby / *jmo / **locl** 全保留。預期：locl 回來 → Chrome gate 過 → 擠壓 fire。

### Step 2 — 評估 locl 副作用

Noto SC source 的 locl 在 kChar 上的 substitute 分布（從 raw font dump）：
- `‘` (2018) → `uni02BB` — **JAN only**
- `’` (2019) → `glyph00726` — **JAN only**
- `“` (201C) → `glyph00728` — **JAN only**
- `”` (201D) → `glyph00729` — **JAN only**
- `：` (FF1A) → `glyph59072` — **JAN only**
- `；` (FF1B) → `glyph59073` — **JAN only**

對應的情境：

| 頁面 `lang` | locl 觸發 | 我們 grafted 的 SC 視覺保留？ |
|---|---|---|
| `zh-Hans` | 無 (ZHS langsys 對這 6 個無 locl entry) | ✓ |
| `zh-Hant` | 無 (ZHT 同上) | ✓ |
| 未設 / `en` / 其它 | 無 (DFLT 走 fallback，這 6 個對應 JAN，但 DFLT 不觸發 JAN entry) | ✓ |
| **`ja`** | **JAN locl fires** → 6 字 substitute 成 JP-proportional/corner glyph | ✗ |

→ 只有 `lang="ja"` 把 SC font 拉進來會破視覺。Diantenjeom Sans SC 字面就是「給中文用」，被拉進 ja 頁是極邊緣情境。**建議 Step 1 即可，不必處理 ja 情境**；只在 README / @font-face comment 註明。

### Step 3（選做，不建議現在做）— 屏蔽 JAN locl 對我們 grafted codepoints 的 substitute

如果 Step 2 的 ja 情境真的成問題，三種應對：

A. **改 JAN locl mapping**：在 build pipeline 加一步，刪除 JAN locl SingleSubst 裡對應我們 8 個 grafted 碼點的 entry。  
   - 風險：`docs/chrome-pair-squeeze.md` 已驗過「修改 locl mapping 內容（增、刪、改）」會關掉 Chrome trim。**這條路 90% 會打破我們剛修好的 gate**。不要走。

B. **Graft locl target 的 outline**：找出 6 個 locl target glyph（subset 後會被 rename 成 `glyph00XXX`），把它們的 outline 也從 SC source graft 過來（其實是想要它們等於 SC cmap glyph 的 outline）。  
   - 風險：docs 也驗過「修改 locl target glyph outline」會關掉 trim gate。**同樣 90% 失效**。不要走。

C. **新增 cmap reroute**：給我們的 grafted 碼點新增 `uniXXXX_sc` glyph，cmap 改指過去，locl 看不到新 glyph 不會 fire。  
   - 風險：docs 第 6 條已實作完整版並驗證**會破 gate**。不要走。

→ Step 3 三條路 **都已被 docs 證明會破 gate**。所以接受 `lang="ja"` 下的視覺退化，只做 Step 1。

### Step 4 — 驗證

1. Rebuild：`pnpm build`
2. 確認 `dist/fonts/diantenjeom-sans-sc.otf` 的 GSUB feature 列表含 `locl`、`mark`、`calt` 等
3. 開 `article.html`（`<html lang="zh-Hant">`），CSS 暫時改 `text-spacing-trim: normal`（或在 `&.sc` 內加 override），到 Chrome 看 SC 段的 `“‘點’的政治⸺` 是否擠壓
4. 對照 demo-sc-quotes.html 應有同樣行為
5. 順便驗：`lang="ja"` 切換時 SC 段的視覺退化是否在可接受範圍（不在的話再評估 Step 3）

### Step 5（連帶事項）— `main.css` 的 `text-spacing-trim`

目前是 `trim-start`，只 trim 行首。要中段對成擠壓必須 `normal`。Centered variant 也受影響（它本來就應該擠壓但 CSS 限制了）。

建議改成 `normal`（spec default）；trim-start 行為其實就是 normal 的子集，沒理由特意限制。

## 預期變動範圍

- `src/diantenjeom/build.py`：SC sans / serif 兩個 Variant 各加 `layout_features=("*",)`
- `main.css`：`text-spacing-trim: trim-start` → `normal`（或拿掉，UA default 就是 normal）
- 視 README 是否要記 `lang="ja"` 注意事項

## 風險清單

| 風險 | 評估 |
|---|---|
| pin_locale alias vert 到 ZHS（不是 JAN）會不會踩 gate | docs 沒測過 ZHS pin，但 alias 機制與 JAN 相同，理論安全。Step 4 用 demo / article 雙確認 |
| graft 改了 cmap glyph outline（`！：；？‘'"’` 8 個）會不會破 gate | docs 嚴格說「改 locl target glyph outline 會破 gate」。我們改的是 **cmap glyph 自己**，不是 locl target（後者是被 locl 替換到的另一個 glyph）。理論上不衝突，但要驗 |
| 新增 vert_subst / gpos_graft 的 lookup 會不會破 gate | docs 第 6 條測過「**新增 glyph**」破 gate；新增 lookup（不增 glyph）沒測過，理論上 gate 只看 glyph 與 locl，新 lookup 不影響 |
| `layout_features=("*",)` 額外保留的 features（liga / dlig / aalt / ruby / *jmo）會不會在某個 lang 下觸發奇怪 substitute | 對我們 codepoint set 應該無感（這些 features 主要對 Latin / Korean Jamo）。Step 4 看視覺 |

## 為何當初 SC variant 沒像 Centered 一樣設 `("*",)`

當時的設計思路（`docs/plans/gb-sc.md` plan 步驟 2 寫的）：

> `unicodes` 直接沿用 `codepoints.JP`；GB 的標點集合與 JP 相同，只是其中四個外觀換源。
> [...] 預設 KEEP_FEATURES 沒 `locl`，這裡也不用 `("*",)`。

當時假設 SC 跟 JP-default 一樣不需要 `("*",)`，沒注意到 Centered 用 `("*",)` 是為了 Chrome trim gate（而 JP-default 之所以 OK 是因為 KEEP_FEATURES 預設就沒打破 gate — JP-default 沒 graft，原本 vanilla Noto JP 的 cmap outline 與 fallback 行為自然通過 gate）。

SC variant 因為做了 graft（改了 outline）+ 沒保 locl，兩個條件疊加才會打破 gate。修法是補 locl，graft 不必動。
