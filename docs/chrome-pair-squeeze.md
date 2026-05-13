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

## 不要再嘗試以下

- 從 KEEP_FEATURES 移除 locl
- 修改 locl SingleSubst 的 mapping 內容（增、刪、改）
- 修改 locl target glyph 的 CharString / hmtx / vmtx / VORG
- 在 font 裡新增 glyph（即使只是 cmap 重指過去、原 glyph 保留也算）

任何一個都會關掉 Chrome 橫排的 CJK 標點擠壓，且無預警 — Chrome devtools 不會告訴你 trim 為什麼沒 fire。Chrome 的 gate 看起來是「font 必須結構性等價於某種 vanilla Noto CJK fingerprint」。

## 相關 commit / branch

- bisect 紀錄：`centered` branch，commit `2c52004` 之後一系列嘗試
- 最後決議：保留現狀（`locl` 完整、LangSys 完整、locl target outline 不動）
