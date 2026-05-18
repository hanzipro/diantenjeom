# Plan: 大陸標點變體 `Diantenjeom Sans/Serif SC`

## Goal

JP-base 子集再加一層 graft：把 `：；！？` 四個標點的 cmap 字形（CFF2
CharString + vmtx + VORG）改從 Noto Sans/Serif CJK **SC** 拿，模仿
大陸/GB 直式排版的「四號偏前」習慣。

family name：`Diantenjeom Sans SC` / `Diantenjeom Serif SC`，
file stem：`diantenjeom-sans-sc` / `diantenjeom-serif-sc`。
（`punct="sc"`，沿用既有 Variant 欄位。）

## 大陸 SC 的設計約定 (要點)

要驗證 / 兼顧的事情（先用 fontTools dump SC 源、比對 JP 同字
形再進實作）：

1. **四號都不旋轉。** 橫排當然不轉；直排時 JP 的 JAN `vert` 會把
   `：` 轉 90°（這是日文慣例），SC/中文則保持直立。`；！？` 在 JP
   源頭已經保持直立（pin_locale 的 `_TR_UPRIGHT_CODEPOINTS` 加上
   JAN vert lookup 本來就沒收這三個的 vert subst）；需要新增的只是
   `：` 強制直立。
2. **偏前方向（橫直不同）：**
   - 橫排：dot/ink 緊貼 em 盒**左上**（行內方向上的字前）。
   - 直排：dot/ink 緊貼 em 盒**上方**（直書方向上的字前）。
3. **Noto 怎麼實作的：** 不是靠 GPOS palt/vpal，而是 SC 源頭直接
   把 cmap glyph 的 outline 畫在 em 盒對應角落 + 配 vmtx tsb 把直
   排原點往上推。Grafting CharString + vmtx + VORG 就把這個位置
   一起搬過來。橫排 hmtx (advance / LSB) **不複製**（沿用 JP 的）
   ——和 Centered 一樣，保留 Chrome 的 pair-squeeze 訊號完整。
   要在 graft 前確認 SC 的 charstring 是「outline 已內含位移」，
   而不是「outline 居中、靠 GPOS 推」；後者 graft 完不會有視覺變化。

## Implementation steps

1. **Source 比對（先不寫 code）**
   - Dump SC Sans + Serif 的 `：；！？` `cmap` glyph：CharString
     program、bbox、hmtx、vmtx、VORG。
   - 對照同四個碼點在 JP Sans/Serif 的同名 glyph。
   - 確認 bbox x_min/y_max 偏移確實落在 SC outline 內（驗證 §「大陸
     SC 的設計約定」#3 的假設）。
   - 用 `_check_compatible` 跑一下 SC↔JP 的 fvar / VarStore region
     簽章一致，graft 才會合法。
   - 時間盒 10 min。

2. **build.py 加兩個 SC Variant**

   參考 Centered 的 row 寫法，差別在 `grafts=` 換成 SC source 加四
   個碼點，並改 `upright_cps`：
   ```python
   Variant(
       punct="sc",
       style="sans",
       source=args.sources / "NotoSansCJKjp-VF.otf",
       unicodes=codepoints.JP,
       vert_nudges={},                                  # 不要 nudge ，、
       upright_cps=(0xFF1A,),                           # 只強制 ：直立
       layout_features=("*",),                          # 保 locl 給 Chrome trim
       grafts=(
           (args.sources / "NotoSansCJKsc-VF.otf",
            (0xFF01, 0xFF1A, 0xFF1B, 0xFF1F)),
       ),
   ),
   ```
   Serif 同理對 `NotoSerifCJK{jp,sc}-VF.otf`。

   - 不重用 Centered 的 `．` delegate 機制 —— 那是 four-dot 一致性檢
     查（U+3001/3002/FF0C/FF0E），這次只動 `：；！？`，與那組無關。
   - `unicodes` 直接沿用 `codepoints.JP`；GB 的標點集合與 JP 相同，
     只是其中四個外觀換源。
   - `vert_nudges={}` —— JP 的 `-120 ，、` nudge 是 JP corner-top 風
     格；GB / SC 的 `、，。` 依然是 JP-default corner-top（這次沒
     graft 它們），nudge 可保留或關掉，先以保留為主，第 4 步觀察
     決定。**待第 4 步再 confirm。**

3. **center_punct 對 SC 不該再 −50。**
   `center_punct.py` 把 `! : ; ?` outline 整體左移 50 來補 Chrome/Safari
   約 10 % 的右偏。那校正是在 **JP-centre 設計**前提下做的；SC graft
   進來的 outline 已經貼左上，再 −50 會破掉「貼左」的視覺。
   - 做法：`center_punct.install` 加一個可選 `codepoints` 參數
     （已經有了，預設 `JP`），在 `subset_one` 裡依 variant 決定是否
     呼叫 / 傳空 tuple。最乾淨：在 `Variant` 加 `center_punct_cps`
     欄位（default `center_punct.JP`），SC variant 設成 `()`。
   - 要先在第 4 步用 Chrome/Safari 視覺驗證：SC outline 在 C/S 下
     會不會也有那個 ~10 % 右偏？若會，再調整為「左移較小量」或
     在 SC graft 完後重做一次平移計算。

4. **Build + 視覺驗證（article.html）**
   - `pnpm build` 後檢 `dist/fonts/diantenjeom-{sans,serif}-sc.{otf,woff2}`
     + `dist/diantenjeom.css` 多兩塊 `@font-face`。
   - 在 `article.html` 加一組切換（or 暫時硬接 CSS 試）切到 SC family。
   - 測試矩陣 — Chrome / Safari / Firefox 各一輪：
     - 橫排：`：；！？` 視覺貼左上、不被 center_punct 拉偏；前後文連
       接看起來像 SC 排版；`、，。` 仍是 JP-corner（這版不改）。
     - 直排：`：` 直立不旋；`；！？` 直立不旋；四號 ink 都靠上半邊；
       行間 `、，。` 仍 JP-style。
     - 三家瀏覽器一致；Chrome `text-spacing-trim` 不被打掉
       （`docs/chrome-pair-squeeze.md` 提到的 4-dot 一致性檢查
       這次不會被觸發，因為沒動 `、 。 ， ．`）。
     - `font-weight` 由 100/200 → 900 全段拉一次：CFF2 blend 在
       graft 過後仍然要正常插值（這是 `_check_compatible` 把守的
       前提）。

5. **修只需要修的。**
   - 若 vert_nudge `、，` 在 SC 視覺底下偏低/偏高，調或拿掉。
   - 若 SC outline 在 C/S 仍有右偏，加回一個較小的 `center_punct`
     位移、或在 SC source-side 量測後設新 `_SHIFT_DX_SC`。

## 直橫排「偏前」具體機制（要寫進 commit / 註解）

- 橫排「字前 = 左」：SC charstring 的 ink x-range 集中在 em 盒左半。
  graft 後 hmtx 不動 → advance/LSB 仍是 JP 值 → 視覺上 dot 在格子
  左半 + 右半留白，這就是大陸標點橫排的「擠前」感。
- 直排「字前 = 上」：SC vmtx 的 tsb (top side bearing) 與 VORG 把
  glyph 原點推到 em 盒上半 → ink 集中在格子上半。`vert` 對這四個
  字不作旋轉 subst，因此最終仍由 cmap glyph 直立繪製在那個位置。

JP 那邊則是把這四個畫在格子中央、然後 `：` 用 vert lookup 轉 90°
變成左右對稱的「︰」——我們要的 SC 行為完全不要那個 subst，所以
`upright_cps=(0xFF1A,)` 透過 `_force_upright` 把 JAN vert lookup
裡的 `：→︰` mapping 改成 self-subst。

## Out of scope

- TC / KR locale 版的標點集（不開新 `codepoints.*`）。
- `、，。．` 不必動：陸 / 日這四個 corner 字形相同，沿用 JP 即可。
- 對 article.html / demo.html 的 UI 重設計；先有可切的 family 就夠。
- chws/vchw bake-in（另案 `docs/plans/chws-feature.md`）。

## Risks

- **SC charstring 用 GPOS palt/vpal 而非 outline 位移：** 若如此，
  graft CharString 不會搬到位移，hmtx 也沒動，視覺=JP。第 1 步驗
  證；若中招，要改為同時 graft 一個對應的 GPOS subset 或者放棄
  graft 改走 outline-shift（自己算 dx/dy）。
- **center_punct 殘留位移：** SC outline + −50 dx 會破視覺，務必第
  3 步處理。
- **Chrome `text-spacing-trim` 一致性檢查：** 本次只動 `：；！？`，
  與 four-dot group (`、。，．`) 完全脫鉤，理論不觸發；仍要在第 4
  步 Chrome 觀察 trim 是否照常運作。
- **Sans vs Serif 不對稱：** SC Serif 的「靠左/靠上」實作幅度可能與
  Sans 不同（Serif 字身設計更保守）。視覺驗證兩個 style 都要做。

## Definition of done

- `dist/fonts/diantenjeom-{sans,serif}-sc.{otf,woff2}` 乾淨產出。
- `dist/diantenjeom.css` 多兩塊 `@font-face`，family =
  `Diantenjeom {Sans,Serif} SC`。
- Chrome / Safari / Firefox × 橫直 × 兩個 style 視覺通過：四號都
  直立、都靠字前；其餘字符與 JP-default 一致。
- 不需要新增模組；改動限於 `build.py`（兩個 Variant row + 可能加
  `center_punct_cps` 欄位 + `subset_one` 改一行）。
