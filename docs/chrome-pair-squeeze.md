# Chrome 的 text-spacing-trim 觸發條件（踩坑記錄）

## TL;DR

Chrome 的 `text-spacing-trim` 對 CJK 標點配對擠壓是否啟動，**整個 font 範圍**地依賴下列條件全部成立。任何一個被破壞，全 font 的 pair-squeeze 都會關掉 — 不只是被你動過的那個 codepoint：

1. **GSUB 的 `ScriptList.LangSysRecord` 必須完整**。砍掉非 Default 的 LangSys（例如為了強迫 fallback 到 JAN）會關掉擠壓。
2. **GSUB 的 `locl` feature 必須存在且其 SingleSubst lookups 有真實 mapping**。把 `locl` 從 KEEP_FEATURES 拿掉、清空 mapping、或把目標 entry 改成 identity (`X → X`) 都會關掉擠壓。
3. **`locl` 的目標 glyphs 的 outline 不能被覆寫**。即使 mapping table 一字未改，把 locl target glyph（例如 `glyph00097`）的 CharString 換成 cmap source glyph 的 outline，也會關掉擠壓。

換句話說：Chrome 在判斷是否擠壓時，似乎對 `(LangSys 結構 → locl FeatureRecord → SingleSubst 來源/目標 glyph → 目標 glyph 的 outline)` 整條鍊都做了某種指紋檢查。任一節點被改動，整個 font 失去擠壓資格。

## 怎麼發現的

長 bisect 紀錄（針對 Diantenjeom Sans Centered，TC graft 後 `〕，` 在 Chrome 橫排不擠壓）：

| 嘗試 | 結果 |
|---|---|
| 把 `KEEP_FEATURES` 從 curated list 換成 `["*"]` | 仍不擠壓 |
| 完全跳過 `pin_locale.install` | 擠壓恢復 |
| 跳過 GPOS LangSysRecord strip（只動 GSUB） | 仍不擠壓 |
| 跳過 `_empty_orphan_lookups` | 仍不擠壓 |
| 跳過 `_alias_vert_to_jan` | 仍不擠壓 |
| 跳過 GSUB LangSysRecord strip | **擠壓恢復** |
| 保留 LangSys，把 `locl` 從 KEEP_FEATURES 拿掉 | 不擠壓 |
| 保留 LangSys，`locl` 仍在，但清空所有 mapping | 不擠壓 |
| 保留 LangSys，`locl` 仍在，只把 `FF0E` 改成 identity (`uniFF0E → uniFF0E`) | 不擠壓 |
| 保留 LangSys + locl mapping 完全不動，但把 `glyph00097`（locl 目標）的 outline 改成 JP 樣式 | **連 `〕，` 也不擠壓** |

最後一個發現特別關鍵 — locl mapping table 完全不動的情況下，光是改了 locl target glyph 的 outline 就會 font-wide 失效。這推翻了「Chrome 只是在 pair detection 時看 post-locl glyph 的 ink 位置」這個假設，指向 font-wide gate。

## 對我們的影響

「完全去除地區配置（locl）」這個原始計畫**跟 Chrome 橫排擠壓互斥**。我們選了擠壓：

- **Centered**：保留 `locl`（透過 `layout_features=("*",)`），代價是在 `lang="zh-Hant"` / `lang="zh-Hans"` 環境下，下列 codepoint 會被替換成 ZHT 在地化字形：
  - `．` (FF0E) → ZHT 置中點
  - `！` (FF01) → ZHT 全形驚嘆號
  - `？` (FF1F) → ZHT 全形問號
  - `：` (FF1A) → ZHT 全形冒號
  - `；` (FF1B) → ZHT 全形分號
  - `·` (00B7) → `・` (30FB)
  - 彎引號 `‘’ “”` → ZHT alternate forms

  之前希望這些保 JP 樣式但已知**目前做不到**。

- **JP-default**：sans / serif 沒受影響，因為它們 codepoint set 跟 Centered 一樣，subsetter 同樣保留 locl，document 用 `lang="ja"` 時 ZHT locl 不會 fire。

## 試過但都失敗的解法

放在這裡避免下次再走一遍。

### 1. 砍 locl

`KEEP_FEATURES` 拿掉 `locl`，讓 subsetter 直接 strip 整個 locl feature。

**為何失敗**：Chrome 沒有 locl 就不擠壓。

### 2. 清空 locl mapping

保留 locl feature 結構，但把 SingleSubst lookups 的 mapping dict 清空。

**為何失敗**：Chrome 似乎判斷 locl 必須「有實際內容」才算 enabled。

### 3. 把 FF0E 從 locl mapping 移除（其他保留）

只刪掉 `uniFF0E → glyph00097` 這一條，其他 locl entries（3001、FF0C 等）保留。

**為何失敗**：Chrome 的檢查不只看「有沒有 locl entry」，連 FF0E 這條被改動也會 trigger font-wide 失效。

### 4. 把 FF0E 改成 identity self-subst

`uniFF0E → uniFF0E`。Chrome 看到 locl 對 FF0E「有動作」但實際是 no-op。

**為何失敗**：Chrome 知道 identity 不算數，pair-squeeze 仍失效。

### 5. 不動 mapping，把 locl target 的 outline 替換成 source outline

`glyph00097` 的 CharString 改成跟 `uniFF0E` 一樣。locl mapping 一字未改，但渲染結果視覺上是 JP 樣式。

**為何失敗**：這是最反直覺的一個 — Chrome 連 locl target glyph 的 outline 都檢查。改了就 font-wide 失效。

（2026-05-13 retry 確認：再做一次同樣的 alias，視覺上 `．` 確實變回 JP corner，但 `〕，` 跟 `，「` 也同步失去擠壓。Gate 真實存在，現象可重現。）

### 6. cmap reroute（add new glyph + 改 cmap target）

新增 `uniFF0E_jp` glyph（copy `uniFF0E` outline），改 cmap 讓 `U+FF0E → uniFF0E_jp`。locl 看不到 `uniFF0E_jp`，不會 fire。其他 locl 完整保留。

**最後實作完整版**（2026-05-13）：
- `cmap_reroute.add_cmap_alias()` 正確處理 CFF2 add-glyph：append 到 `charStringsIndex.items` + 註冊 `charStrings[name]` + `topDict.charset.append` + `FDSelect.gidArray.append` + 補 HVAR/VVAR `VarIdxMap` 條目 + 更新所有 cmap subtable。
- Build 成功、新 glyph 在 font 裡、cmap 正確 reroute。視覺上 `．` 橫排確實變回 JP corner。
- 但：(a) Chrome 橫排 pair-squeeze **掛了**（連 `〕，` 也不擠壓）。(b) 直排 `．` 沒走 vert 替代（新 glyph 不在 vert lookup coverage 內），顯示成橫排形。

**結論**：Chrome 的 gate 比想像更嚴 — 它不只看 locl 表的 mapping 與 target outline，連 glyph 數、cmap-source 是否與 locl-source 是同一個 glyph、font 整體結構是否「乾淨」都可能在檢查。**任何結構偏離 vanilla Noto CJK 都會關閉 gate**。

實作放棄了（commit 前刪除了 `src/diantenjeom/cmap_reroute.py`），但 fontTools CFF2 add-glyph 機制研究成果記在這裡：

```python
# Add a glyph to a CFF2 font (works for save/reload):
cff2 = font["CFF2"].cff.topDictIndex[0]
cs = cff2.CharStrings
new_idx = len(cs.charStringsIndex.items)
cs.charStringsIndex.items.append(new_charstring)
cs.charStrings[new_name] = new_idx
cff2.charset.append(new_name)
cff2.FDSelect.gidArray.append(src_fd_index)
font.glyphOrder = list(cff2.charset)
# Also: hmtx/vmtx/VORG entries, HVAR/VVAR VarIdxMap entries for every map
# (AdvWidthMap, LsbMap, AdvHeightMap, TsbMap, VOrgMap, ...) where the map exists
```

## 哲學

我們的初衷是「subset 出純 punctuation font，跨語言環境一致呈現 JP 樣式」 — 但 Chrome 的 text-spacing-trim 實作明顯是針對「完整的 Noto CJK 拿來當 web font」設計的，它把 `locl` + LangSys + locl-target-outline 整套當作「這是 Noto 系字體」的指紋。我們做了 surgical subset 並重寫部分結構，從 Chrome 的角度看就「不像 Noto」，於是降級到不擠壓。

要改變這個只有兩條路：

1. **Chrome 改實作**：text-spacing-trim 應該基於 Unicode 屬性（East Asian Width、line break class），不該綁特定 GSUB 結構。可向 Chromium 提 bug。
2. **我們的 subset 完全模仿 Noto 結構**：保留所有 locl、所有 LangSys、不動任何 locl target glyph。這就是目前的妥協 — 代價是上述 codepoint 被 ZHT locl 替換。

## 後記：不是 Noto 指紋，是 halt coverage 要求（2026-05-13 調査）

之前說「Noto fingerprint」其實不對。查了 W3C / Chrome / MDN 文件後修正：

- **Chrome 的明確規範**：text-spacing-trim 要 fire 必須字體有 `halt`（或 `chws`） OpenType feature。沒有就整個 disabled。這是 spec 層級的字體層級檢查，不是 Noto 衍生檢查。
- **真正的隱含要求（推測）**：Chrome 的 halt 套用發生在 **GSUB shaping 之後** — 對 post-locl 的 glyph 找 halt coverage。Noto CJK 的 halt coverage 既包含原 cmap glyph（`uniFF0C`）又包含 locl 替代後的 glyph（`glyph00096`），所以無論 locl 有沒 fire 都能順利套 halt。我們動 locl mapping、換 locl target outline、或加新 glyph 改 cmap，會讓 post-shape 的某些 glyph 落在 halt coverage 外，Chrome 似乎是 **all-or-nothing**（偵測到任何關鍵 codepoint 的 post-shape glyph 缺 halt 就整個 font 關掉 trim）。

這個假設**部分驗證、部分被推翻**（2026-05-13 實驗）：

- ✅ Dump vanilla Noto JP halt coverage 確認包含 10 個 locl target 中的 9 個
- ✅ Subset 後我們的 Centered build halt coverage 也仍包含 9/10 locl targets
- ❌ cmap-reroute 加新 glyph + **同步把新 clone 加進 halt coverage**（含 Format 2 SubTable 的 per-glyph value 處理）→ Chrome 橫排 trim **仍然不 fire**

所以 gate **不只是 halt coverage**。深挖 Chromium source 後找到真正的 gate（見下節）。

## 確診：Chromium `han_kerning.cc` 的型別一致性檢查（2026-05-13）

Chromium source: `third_party/blink/renderer/platform/fonts/shaping/han_kerning.cc`

關鍵流程：

1. Chrome shape 一個固定的 10-codepoint 序列（`kChars`）：

   ```cpp
   const UChar kChars[] = {
       kIdeographicComma,        // 、 (U+3001)
       kIdeographicFullStop,     // 。 (U+3002)
       kFullwidthComma,          // ， (U+FF0C)
       kFullwidthFullStop,       // ． (U+FF0E)
       kFullwidthColon,          // ： (U+FF1A)
       kFullwidthSemicolon,      // ； (U+FF1B)
       kLeftDoubleQuotationMark, // " (U+201C)
       kLeftSingleQuotationMark, // ' (U+2018)
       kRightDoubleQuotationMark,// " (U+201D)
       kRightSingleQuotationMark // ' (U+2019)
   };
   ```

   shape 用真實的 locale（文件 lang）— 所以 `locl` 會 fire。

2. 把 shape 結果分組分類：
   - **dots group** (4 個): 、 。 ， ．
   - **colon** (1 個): ：
   - **semicolon** (1 個): ；
   - **quotes** (4 個): " ' " '

3. 對每組用 `CharTypeFromBounds()` 算 glyph 的 type：

   ```cpp
   if (bound.right() <= half_em) return kClose;   // ink 在左半（JP 倚角）
   if (bound.left() >= half_em) return kOpen;     // ink 在右半
   if (bound.width() <= half_em && bound.left() >= half_em / 2)
       return kMiddle;                            // 細小、置中
   return kOther;
   ```

4. **關鍵**：dots group 4 個字符要 shape 完都產生**同型別**的 glyph，才能跑 trim。若任一個型別跟其他不同 → 整組變 `kOther` → `has_alternative_spacing = false` → **全 font 不 trim**。

### 為什麼 Centered + `．` JP 化必然失敗

| codepoint | baseline (work) post-locl glyph | cmap-reroute (broken) post-locl |
|---|---|---|
| 、 | ZHT centered → kMiddle | ZHT centered → kMiddle |
| 。 | ZHT centered → kMiddle | ZHT centered → kMiddle |
| ， | ZHT centered → kMiddle | ZHT centered → kMiddle |
| ． | ZHT centered → kMiddle | JP corner (locl 抓不到 clone) → **kClose** |

baseline 四 dot 全 kMiddle（一致），trim work。任何讓 `．` 變成跟其他 3 個不同型別的修改 — alias outline / cmap reroute / remove FF0E from locl / identity self-subst — 都會讓 dots group 變成 kOther。

### 設計層面的意涵

- Chrome 的 trim 設計**假設字體設計者把 4 個 dot 視為一組**：要嘛全 JP 倚角，要嘛全 ZHT 置中，不能混。
- 自己拉曲線的字體完全沒問題，只要 4 個 dot（跟 colons / quotes 各組內部）**設計上一致**即可。
- Noto CJK 的 ZHT locl 把 4 個 dot 全替換成置中版，所以 `lang="zh-Hant"` 環境下 4 個 dot 都是 kMiddle。
- 我們的 Centered：graft 把 `、/。/，` 換成 TC 置中，但 `．` 沒 graft、locl 仍替換成 ZHT 置中 — 4 個還是一致。視覺上 `．` 是 ZHT 置中，**這是 Chrome trim 強制的設計約束**。

### 對其他組的影響

`：;` 在 Centered 經 center_punct 平移 -50 後 bbox (-50, 0, 506, 684)：
- bound.right() = 506 > 500 → 不是 kClose
- bound.left() = -50 < 500 → 不是 kOpen
- width = 556 > 500 → 不是 kMiddle
- → **kOther**

也就是說 `：` / `；` 在我們的 build 本來就是 kOther — Chrome 對這兩個的 pair-squeeze 行為很可能也跟 vanilla Noto 不同。實測中使用者報告 `：「` 有擠壓，可能是因為 colon / semicolon 是「per-char group」而非「dots group」— 即使它自己 kOther 也只影響它一個，不會 cascade 關掉整個 font 的 trim。

### 結論

**4 個 dot 必須同型別**。要 `．` JP 倚角，唯一辦法是另外 3 個 dot 也撤回 JP 倚角（放棄 Centered 的視覺）。或者向 Chromium 提 bug，主張這個檢查太嚴格。

### 參考資料

- [Chromium han_kerning.cc](https://chromium.googlesource.com/chromium/src/+/HEAD/third_party/blink/renderer/platform/fonts/shaping/han_kerning.cc)
- [Chromium text_spacing_trim.h](https://chromium.googlesource.com/chromium/src/+/HEAD/third_party/blink/renderer/platform/fonts/shaping/text_spacing_trim.h)

**對自己從零設計的字體：** 完全沒有 Noto-specific 的問題。只要字體有 halt 且對所有需要 trim 的 codepoint（更精確：post-GSUB-shaping 的目標 glyph）有 halt coverage，就會 work。

### 參考資料

- [Chrome Intent to Ship: text-spacing-trim](https://groups.google.com/a/chromium.org/g/blink-dev/c/jVUR2ebE3e0)
- [W3C csswg-drafts #8293 — halt/vhal/chws/vchw discussion](https://github.com/w3c/csswg-drafts/issues/8293)
- [W3C csswg-drafts #9504 — closing punctuation classes](https://github.com/w3c/csswg-drafts/issues/9504)
- [MDN text-spacing-trim](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/text-spacing-trim)
- [Chrome blog: CSS i18n features](https://developer.chrome.com/blog/css-i18n-features)

## 不要再嘗試以下

- 從 KEEP_FEATURES 移除 locl
- 修改 locl SingleSubst 的 mapping 內容（增、刪、改）
- 修改 locl target glyph 的 CharString / hmtx / vmtx / VORG
- 在 font 裡新增 glyph（即使只是 cmap 重指過去、原 glyph 保留也算）

任何一個都會關掉 Chrome 橫排的 CJK 標點擠壓，且無預警 — Chrome devtools 不會告訴你 trim 為什麼沒 fire。Chrome 的 gate 看起來是「font 必須結構性等價於某種 vanilla Noto CJK fingerprint」。

## 相關 commit / branch

- bisect 紀錄：`centered` branch，commit `2c52004` 之後一系列嘗試
- 最後決議：保留現狀（`locl` 完整、LangSys 完整、locl target outline 不動）
