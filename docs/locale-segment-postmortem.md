# 為什麼 Diantenjeom 的 Locale + Segment family 一直修不對

## 摘要

從加 SC variant 開始，到把 split family 重命名為 Segment 並穩定下來，
中間經歷一系列「修好一個又壞另一個」的 bug 追逐。所有問題的根都不複雜，
但每次都因為**對 Chrome `han_kerning` gate 行為的錯誤假設**而選錯方案。
這份報告把所有踩過的坑與真正的修法都寫一遍，避免下次再走。

主要結論：

1. **Chrome gate 讀 face 的 cmap，不看 CSS `unicode-range`**。`css_delegate`
   只是 render-time route，對 gate 沒幫助。
2. **`pin_locl_to` 會 silent fail**：subsetter 把目標 langsys 的 locl FR
   prune 掉就找不到目標，alias 被 skip 但沒報錯。
3. **`align_locl` 必須跑在 outline 變動之後**（graft / shift），否則 locl
   target 會被同步成「未變動前的 outline」。
4. **跨 face pair 的 trim 取決於「後字所在 face」的 font_data**——前一個
   face 的 gate 過不過跟這個 pair 是否擠壓**無直接關係**，但前一個 face
   提供的 glyph 進到本 face 的 `type_for_*` 路徑時會 mat 上去；可以斷
   trim 鏈。

---

## 時間軸與每次踩坑

### 1. SC variant 初步建立

問題：JP source 的 ZHT locl 會把 `、 。 ， ．` 替換成 ZHT 居中
glyph，所以在 `lang="zh-Hant"` 頁面下，SC variant 的 dots 跟著被改成
居中——破壞了 SC「全 corner」的設計意圖。

**錯誤假設**：「subsetter 留下 GSUB feature 就會用我希望的 langsys 路徑」。
**現實**：browser 用 document `lang` 決定 langsys，可能跑到任何 langsys
的 locl。

**正解**：用 `pin_locl_to="ZHS"` 把所有 langsys 的 locl FR 都 alias
到 ZHS 的 lookup list。ZHS locl 不替換 dots，所以跨 lang 都保持 cmap
設計。

### 2. `pin_locl_to` 對 Segment 變體 silent fail

問題：把 `pin_locl_to="JAN"` 套到 Dot Anchored 上，預期讓 4 個 dot
跨 lang 都維持 JP corner 設計。實際 `lang=zh-Hant` 還是被 ZHT locl
替換成居中。

**根因**：Segment 的 Dot face cmap 只有 4 個 dot 碼點。JP source 的
JAN locl 對這 4 個碼點沒有任何 mapping（JAN locl 動的是 quotes /
marks，不動 dots）。所以 **subsetter 認為 JAN langsys 的 locl 對這個
face 是 empty，prune 掉**。當 `_alias_locl_to_locale(gsub, "JAN")`
跑時，`_locale_feature_lookups(gsub, "JAN", "locl")` 找不到 JAN locl
FR，回傳 `None`，alias 邏輯 skip。但 ZHT/ZHH locl 沒被 prune（它們
真的替換 dots），原本就在 GSUB 裡照常 fire。

**教訓**：**pin 的目標 langsys 必須在這個 face 的 subset 裡仍有實際
locl entry，pin 才會生效**。否則沒任何錯誤，也沒任何效果。

**正解**：改用 `align_locl_cps` 機制——不動 locl mapping、不動
langsys 結構，而是**直接把 locl 替換到的目標 glyph 的 outline 覆寫成
cmap source 的 outline**。Locl 還是 fire（Chrome gate 看得到 locl 活
動，gate 過），但替換結果視覺上跟 cmap 一致。

### 3. `align_locl` 對 Dot Centered 的 `．`

問題：Dot Centered 用了 `align_locl_cps=DOT` 之後，4 個 dot 的 locl
target 都被同步到 cmap。3 個 dot（、。，）已經 graft 過 TC 居中，
所以 cmap 是 kMiddle；但 `．` 沒 graft（TC 也是 corner），cmap 是
JP corner kClose。Locl target 被同步成 cmap → 也變 kClose。最後 4 個
dot 的分類混合：3 kMiddle + 1 kClose → **Chrome 4-dot consistency gate
失敗 → 整個 face 的 trim disabled**。

**錯誤假設**：「TC 的 `．` 也是 corner，所以 `．` 留在 cmap 不動就好」。
**現實**：「不動」就違反 4-dot consistency。整個 face 為了 1 個 dot
不一致就掛了。

**第一次嘗試**：用 `css_delegate_cps=(0xFF0E,)` 把 FF0E 在 CSS 層級
路由到 Dot Anchored face。**Chrome render 看 unicode-range，會去 Dot
Anchored 拿 FF0E；但 Chrome gate 不看 unicode-range，gate test shape
FF0E 還是走這個 face 的 cmap，看到 JP corner**。4-dot 仍然 mixed。
chrome-pair-squeeze.md 之前寫的「unicode-range 切割可以救」根本不成立
——doc 對 integrated Centered 的觀察很可能也是錯的（integrated
Centered 在 ja / zh-Hans 下本來就不擠壓，只是在 zh-Hant 下 ZHT locl
fire 後巧合過了 gate）。

**第二次嘗試**：把 FF0E 從 face 的 `unicodes` 列表移除，subset 不放
這個碼點。預期 Chrome gate test shape FF0E 找不到 → 變 `.notdef` →
跳過 4-dot 一致性檢查。**現實**：`.notdef` 還是有 bbox（一個 placeholder
矩形），bbox 分類為 kOther。4-dot 變 3 kMiddle + 1 kOther → 仍然
mixed → 仍然失敗。

**正解（第三次）**：**保留 FF0E 在 cmap，但用 `_outline.shift_in_place`
程式化把 FF0E 的 outline 從 JP-corner 位置平移到 em-centre**。Shift
amount 算出來剛好讓 ink 中心對齊到跟 TC graft `、` 一樣的位置
(500, 380)。4 個 dot cmap 全部 kMiddle，一致。**而且** outline_shifts 要
跑在 align_locl 之前，這樣 shifted outline 才會傳播到 locl target。

### 4. 「老的整套亂掉了」的誤診

問題：使用者報告「老的 Locale variant 也壞掉」，列了 SC / Centered /
Sans 一堆。實證 harfbuzz shape 結果：

- Sans (JP-default): 跨 lang 完全一致、gate 過 ✓
- Sans Centered: zh-Hant 過、ja / zh-Hans **本來就 fail**（FF0E 在
  非 ZHT-locl-fire 環境下是 kClose、其他 3 dot 是 kMiddle）
- Sans SC: zh-Hant / zh-Hans 過、ja 下 quote pair 不擠壓（is_qfw=false）

「老的亂了」其實是**之前一直存在但沒注意到的舊架構限制**，這次混雜
看 integrated + split 變體才被發現。**沒有新 regression**，只是真相
浮現。

不過確實有一個真 regression 是這次造成的：**SC variant 在 zh-Hant
下 dots 變居中**——根因是 §1 的 ZHT locl 替換。修法是加
`pin_locl_to="ZHS"`，已修。

### 5. Mark Centered 的 `:` 旋轉問題

JP convention 直排 `:` 旋 90° 變 ︰；TW MOE / SC 不旋。Mark Centered
（JP 源頭 + 居中設計）預設**會旋**（走 JAN vert path L50 substitution）。
使用者想要 TW MOE 風（不旋）作為 Mark Centered 預設，把旋轉版另開一個
變體。

**正解**：Mark Centered 加 `upright_cps=(0xFF1A,)` 強制 `:` 直立。
新增 Mark Centered Rotated（無 upright_cps）保留 JP 旋轉行為。
最終 3 個 mark variant：
- Mark Centered：JP 居中設計、`:` 直立（TW MOE 風）
- Mark Centered Rotated：JP 居中設計、`:` 旋轉（JP 風）
- Mark Anchored：SC 倚角設計、`:` 直立

---

## 拆 build 腳本

最後一個結構性決定：把 `build_fonts.py` 拆成 `build_locale.py` +
`build_segment.py`。原本擔心「拆腳本太麻煩、共用 helper 抽不乾淨」，
實際做完後**確實乾淨很多**：

- `src/diantenjeom/build.py` 變成純 library（`Variant` + `subset_one`
  + `write_css` + `run_build`），沒有 main()。
- `src/diantenjeom/locale_variants.py` 與 `src/diantenjeom/segment_variants.py`
  各自定義自己的 variant 列表。
- Segment 用 `SegmentVariant(Variant)` subclass 加自己的欄位
  (`align_locl_cps`、`outline_shifts`)。Locale 直接用 `Variant`，這
  些欄位用 `getattr(v, ..., default)` fallback 取。

最大好處：兩個腳本互不影響。動 Segment 不會 rebuild 一堆 Locale font
也不會誤觸 Locale 邏輯，反之亦然。

---

## 給未來自己（與下次踩坑的人）的 takeaways

### Chrome `han_kerning` gate 真實行為（與 doc 錯誤之處）

1. **Gate 讀 face 的 cmap**，不看 CSS `unicode-range`。所以「用
   unicode-range 排除某個 codepoint 讓 gate 看不到它」**這條路是錯的**。
   chrome-pair-squeeze.md 之前的描述要修正。
2. Gate 是 **per-`SimpleFontData`**，也就是 per-@font-face × per-face-
   file 的組合。每個 face 獨立檢查。
3. **跨 face pair 的 trim**：在 run boundary，Chrome 用「current char
   face」的 `font_data` 解析前一個 char 的型別。所以如果前一個 face
   的 gate 過，但這個 face（current char's face）的 gate 沒過，trim
   也不 fire。如果前一個 face gate 沒過，倒不直接影響——只要 current
   face 自己 gate 過，trim 仍可能 fire。

### `pin_locl_to` 用法的隱形要求

只有當「目標 langsys 的 locl 對這個 face 的 cmap 有實際 entry」時，
pin 才有效。Subsetter 會 prune 掉沒實際 entry 的 locl FR。所以：

- **大 face**（如 integrated SC，含完整 codepoints.JP）：pin 到 ZHS
  OK，ZHS locl 對 quote/mark 有 entry，被 subsetter 保留。
- **小 face**（如 Segment Dot Anchored，只有 4 個 dot 碼點）：pin 到
  JAN 沒用，JAN locl 不動 dots，FR 被 prune，pin 找不到目標 silent fail。

對小 face，改用 `align_locl_cps`（不靠 langsys aliasing，直接 overwrite
locl target outline）。

### `align_locl` 的 ordering 要求

`align_locl` 是 **複製 cmap source → locl target**。任何會改 cmap source
outline 的步驟（graft、outline_shifts）**必須跑在 align_locl 之前**。
否則 align 同步的是「未改動前的 outline」，最後 locl target 跟 cmap
不一致。

### Chrome 4-dot 一致性是 `、 。 ， ．` 全組同型

不分 kClose / kMiddle / kOpen / kOther 中哪一型，**4 個必須完全相同**。
任何 mixed（3+1 也算 mixed）→ gate fail → font-wide trim disabled。

對策三選一：

- **graft**：所有 4 個 dot 從同一個 source graft 過來（如 integrated
  Centered 想做但 TC 的 `．`也是 corner，graft 沒用）
- **shift**：程式化把不同設計的 dot 平移到一致 ink 區域（Dot Centered 的 `．` 用這條）
- **delete**：把不一致的那個從 cmap 移除（但 `.notdef` 替代會變 kOther
  仍然 mixed，**這條路也沒用**）

### Curly quote pair 是 2 + 2 不是 4 一致

Chromium 對 curly quote 的檢查是「前 2 (`""'`)`'` 必須 kOpen，後 2
(`'""'`) 必須 kClose」，不是 4 個同型。所以 SC 的全寬 curly quote
（2 kOpen + 2 kClose）能 pass `is_quote_fullwidth = true`。JP 的窄
curly quote（全 kClose）pass false（quote 走 kCloseNarrow path）——
那就不擠壓，**設計使然不算 bug**。

### 「老的好像也壞了」的 debug 第一步

先跑 harfbuzz shape test 比對「現在 vs git checkout f1df5c4」的結果，
別憑感覺說「老的也亂了」。實證後常常發現：

- 真的 regression：哪裡的 outline / mapping 動到了
- 舊有限制被首次發現：本來就有，只是換 lang / 換 variant 才暴露

兩種完全不同的處理路徑。把這個 step 寫進 debug checklist。

---

## 影響範圍與後續

修完後當前狀態：

- **Locale family**（6 face）：SC dots 跨 lang 穩定 ✓；Centered ja /
  zh-Hans 的 4-dot mixed 限制**保留**（out of scope）；JP-default 任
  何 lang ✓。
- **Segment family**（16 face）：5 個 group × Sans/Serif 全 lang 穩定，
  含新加的 Mark Centered Rotated。Dot Centered 用 outline_shift 修
  FF0E。

doc 待更新：

- `docs/chrome-pair-squeeze.md` 那節「unicode-range 切割救 4-dot」要
  加註：對 split face 不成立，只在 integrated Centered + 特定 lang
  下湊巧 work。
- `README.md` 加 Locale / Segment 兩 family 並列的 fallback chain 範
  例（plan 已寫好範例）。

---

*Written after the dust settled. Future-self: read this before adding
the next punctuation variant.*
