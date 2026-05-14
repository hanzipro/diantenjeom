# Plan: bake `chws` / `vchw` feature into our subset

## Why

CSS Text 4 spec：「如果字體有 `chws` (Contextual Half-width Spacing) 或
`vchw`，瀏覽器的 `text-spacing-trim` 邏輯應該 **defer 給字體**」 —— 即不
再用瀏覽器內部那套配對判斷，照字體裡 chws 規則描述的 pair 來套 halt。

對我們的影響：Chrome 的 `han_kerning.cc` consistency gate（4 個 dot 必須
同 type 否則 trim 全 font 關掉）是 Chrome 自己內部判斷的一部分。**如果
字體有 chws，這個 gate 整段路徑都不會跑** — Chrome 直接交給 chws GPOS
chained context lookup 處理 pair-squeeze。

如果這個推測成立，下列限制都解開：
- Centered 可以讓 `．` 維持 JP corner（直接動 cmap glyph outline 或 locl
  target outline），不需要 CSS `@font-face unicode-range` split。
- 4 個 dot 內部 type 可以混（部分 TC 置中、部分 JP corner），不會 trigger
  font-wide trim disabled。

**但**：這個推測**未驗證**。Chrome 實作行為跟 spec 不一定 1:1，有 chws
也可能 Chrome 還是先跑自己的 gate 再 fall through chws。要實測才知道。

## 工具

[`chws_tool`](https://github.com/adobe-fonts/chws_tool) —— Adobe 維護的
Python script，輸入字體 + spec，輸出加好 chws/vchw GPOS chained context
lookup 的字體。

Install:
```bash
pip install east-asian-spacing  # 套件名是 east-asian-spacing
```

預設規則基於 JLREQ / CLREQ —— 適合中日文標點配對。

## 步驟

### 1. 工具驗證
- `pip install east-asian-spacing` (需 Python ≥3.10)
- 拿 vanilla `NotoSansCJKjp-VF.otf` 測試一次 round-trip：跑 chws_tool 加
  chws，看 output font 有沒有 chws GPOS feature，glyph 數 / metric 有
  沒有意外變化
- 驗證 CFF2 + variable wght axis 沒被破壞（chws_tool 可能對 CFF1 比較
  完整）

### 2. 套到我們的 build
位置：在 `subset_one` 結束（font.save 之前）插一個 `chws.install(font)`。

- 寫個薄 wrapper module `src/diantenjeom/chws.py`，呼叫
  east-asian-spacing 的 API（不要 shell out，避免 subprocess 依賴）
- 在 build pipeline 加進去（位置：所有現有 modules 之後，rename_family
  之前）

### 3. 對所有 4 個 variant 套用
- Sans / Serif / Sans Centered / Serif Centered 都加 chws
- 預期：每個 variant 的 chws lookup 內容應該都對它自己的 codepoint set
  正確（chws_tool 會自動 inspect cmap）

### 4. 測試 matrix
| 場景 | 預期 | 重點驗證 |
|---|---|---|
| Sans default zh-Hant 橫排 `〕，` | 擠壓 | regression test |
| Sans default zh-Hant 直排 `〕，` | 擠壓 | regression test |
| Centered Sans zh-Hant 橫排 `〕，` | 擠壓 | regression test |
| Centered Sans zh-Hant 橫排 `〕．` | 擠壓 | regression test |
| Serif default 橫排 `〕，` | 擠壓 | regression test |
| Serif Centered 橫排 `〕，` | 擠壓 | regression test |
| **Centered ．JP corner**（撤掉 CSS unicode-range split） | `．` JP corner + 擠壓正常 | **核心目標** |
| **Centered 4 dot 混型別**（dots 不一致） | 擠壓不掛 | 核心目標 |

### 5. 決策點

A. **chws 對 Centered 的 trim 行為**：
   - **目標達成**（Chrome 真的 defer 給 chws、gate 不跑）：移除 CSS
     unicode-range split，把 `．` 改回直接動 locl target outline 拿到
     JP corner。
   - **目標未達**（Chrome 仍跑 gate 或 chws 沒用）：保留 CSS split 跟
     現狀。chws 可能還是有意義（更精準的 pair 規則），但不一定值得多
     一個 dependency。

B. **chws_tool 對 variable font 的相容**：
   - 如果 CFF2 + variable wght 被破壞，先 try TTF 變體（drop variation
     軸→ 多重 weight files）做為 workaround
   - 或 patch chws_tool 上游

C. **chws 規則自定**：
   - chws_tool 預設規則應該夠用，但如果發現特定 pair 行為不符預期，
     可以提供自定 spec 檔覆寫

### 6. Rollback plan
- 把 chws step 從 build pipeline 拿掉就是 revert
- chws_tool 預設**不修改 cmap / 不增刪 glyph**，只加 GPOS lookup —— 拿
  掉就乾淨

## Risks

1. **chws_tool 對 CFF2 variable font 不完全支援**
   - 上游主要測試對象是 CFF1 + static / TTF + gvar
   - CFF2 可能會炸或產出壞 lookup
   - 緩解：先用 vanilla Noto 測，failure 早發現

2. **Chrome 行為跟 spec 不符**
   - spec 說「有 chws 就 defer」，但 Chrome 實作可能：
     - 先跑自己的 gate（4-dot consistency check）才 fall through chws
     - 同時跑兩個 path 結果 chaos
     - chws 跟 halt 同時 fire 變成擠壓兩次
   - 緩解：用 article.html 多 sample 看實際行為

3. **chws 跟我們現有的 halt 衝突**
   - 現在 font 裡的 halt 是 SinglePos（單 glyph 套 halt）；chws 是
     Contextual（pair 觸發套 halt）
   - 兩個同時存在時，CSS Text 4 spec 規定 Chrome 應該優先 chws、
     skip halt。但實作可能不 skip → 變成 pair 套兩次。
   - 緩解：實測比對 advance 看有沒有 double-compression

4. **Safari / Firefox 還沒實作 text-spacing-trim**
   - 加 chws 對它們**完全沒影響**（要嘛 ignore chws，要嘛 user 沒 opt-in）
   - 反過來說，這個改動只在 Chrome 看得到效果

5. **chws_tool 邏輯跟 JLREQ / CLREQ 對 ZHT/JP 慣例的詮釋**
   - 我們的 Centered 是 TW MOE 風格（、，。 置中），跟 JLREQ 的 JP 風格、
     一般 ZHT 風格都不完全一致
   - chws_tool 的預設 pair 規則對 TW MOE 不一定理想
   - 緩解：需要時自定 spec

## 大概工時

- 工具驗證 + wrapper module：半天
- Build 整合 + 4 variants 套用：兩三小時
- 測試 matrix 跑一輪：一個下午
- 如果踩 risk 1-3 任一個，debug 不確定，估 1-2 天

## 建議啟動條件

不急。目前的妥協（Centered `．` ZHT 置中 + CSS unicode-range split 把
JP donor 拼進去）已經 work，視覺正確。chws 是「拆掉 Chrome gate 整個
迷宮」的工程，值得做但不緊急。

啟動時機：
- 想做新 variant（例如 GB style 大陸標點），又踩到 dots-group 一致性
  gate → 那時候做 chws 比再走一次 CSS unicode-range split 划算
- 或想跟 Chromium 提 bug 之前，先用 chws 自證「字體側方案已盡力」
