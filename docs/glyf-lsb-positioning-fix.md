# glyf 轉換的 LSB 定位 bug（MOE 標點失中）

**狀態：** 根因已確認、修法已實作並驗證。**實測確認無 pair-squeeze 損失**（見下）。
剩測試衛生與 commit（見末節）。
**發現：** 2026-07-11 由 og:image 渲染察覺；2026-07-12 系統性除錯定位根因。
**影響檔案：** `src/diantenjeom/to_glyf.py`（修法所在）。

---

## 症狀

CFF2→glyf 轉換後，MOE 的置中標點（、。，）被渲染到 em 框的**左下角**，
而非置中。JIS／GB／KV 不受影響。這是 7 月 og:image 上抓到的錯。

## 根因（與舊 TODO 的推測相反）

損失**不在** `instantiateVariableFont`，也**不在** TTGlyphPen 之前。逐邊界量測
MOE serif `uni3002`（。）的墨界 xMin..xMax：

| 階段 | xMin..xMax | 判定 |
|---|---|---|
| CFF2 VF 預設實例 | 361..640 | ✅ 居中 |
| `instantiateVariableFont` 後 | 361..640 | ✅ 居中 |
| `_convert_glyph` 產出的 glyph 物件 | 361..640 | ✅ 居中 |
| 經 `getGlyphSet().draw()` 讀出（＝rasterizer 實際定位） | **43..322** | ❌ 偏移 −318 |

glyf 裡**儲存的 outline 座標是正確的**（361..640）。錯的是 **`hmtx.leftSideBearing = 43`**，
而 361 − 43 = **318**，正是位移量。

**機制：**

- **CFF2 定位純看 charstring 座標，無視 `hmtx.lsb`。**
- **glyf 定位由 `lsb` 驅動**——rasterizer 把 outline 的 xMin 座到離原點 `lsb` 處；
  規範要求 `lsb == xMin`。

`graft.py` 當初**刻意**保留 JP base 的 `lsb=43` 當作 Chrome pair-squeeze 的分類訊號
（見該檔 docstring）。在 CFF2 世界裡，這個「假的 lsb」和居中的 outline 脫鉤共存、無事；
一旦轉 glyf，兩者耦合，rasterizer 信了那個 43，把整個字拉回角落。

`to_glyf.py` 原註解明言「hmtx 保持不動」——正是病灶。波及範圍不只 MOE 。：
MOE 的 、。，與 GB 的 ！：；？ 全中招（8 個字體、數十個 glyph 的 `lsb ≠ xMin`）。

## 修法

轉換末段（`cff2_to_glyf`，建完 glyf 表後）把每個實心 glyph 的 `hmtx.lsb`
重新同步到其（cu2qu 量化後的）`xMin`，advance 不動：

```python
hmtx = font["hmtx"].metrics
for gname, g in glyphs_def.items():
    if g is not None and getattr(g, "numberOfContours", 0) > 0:
        advance, _lsb = hmtx.get(gname, (0, 0))
        hmtx[gname] = (advance, g.xMin)
```

這同時也是 glyf 格式的正確性要求（`lsb == xMin`）。

## 驗證

- MOE serif 。 回到 361..640（居中）；全 8 字體重建後 `lsb ≠ xMin` mismatch = **0**。
- `pytest`：48 passed。
- `fontbakery check-opentype`：僅剩 2 個**既有且已在 CI 排除**的 metadata nit
  （`fsselection` Regular bit、ExtraLight-同預設座標；皆因 fvar 預設落在 Thin，與本次無關）。
  **無新增 FAIL，尤其無 metrics/lsb 類問題** → 修法乾淨。

## 連帶影響：pair-squeeze（實測無損失）

> **⚠️ 修正紀錄。** 本節初稿曾據 `scripts/check_squeeze.py`（squeeze-matrix）的
> 輸出，宣稱本修法讓 MOE「損失 138 對擠壓、屬 glyf 本質限制的取捨」。**那個結論是錯的**，
> 起因是量測方式不具代表性。以下為訂正。

**如何驗證：** 直接量 `demo/article.html` 的真實渲染情境——把標點對放進**單一文字節點**、
夾在 Han 之間（如 `音檔」，語料`），以 `text-spacing-trim: normal`（article.html 未設，
吃瀏覽器預設）對比 `space-all` 基線，用 `Range` 量該對的 inline 寬度。在**修好的 glyf 字體**上，
MOE serif：

| 擠壓 ✅（本該擠、量到 0.5em） | 不擠 ✅（MOE 慣例本就不該擠） |
|---|---|
| `」，` `》，` `〉，` `』，`（結束括號＋點） | `。」`（點＋結束引號） |
| `」。`（結束引號＋句號） | `。。` `，，` `，。`（點對點） |
| `。「`（點＋開引號） | |
| `：「` `」「`（括號相關） | |

`。、，` 後接**結束**引號、或點與點相鄰，本就不該擠（台灣排版慣例），量到「不擠」是**正確**。
該擠的（結束括號／點在前、點接開括號）全數照擠，與置中的 outline 並存無礙。**置中位置與正確
擠壓兩者兼得**；GB `：；` 靠角標點也因 lsb 修正而正確地開始擠壓（正面）。先前以為的「居中 vs
擠壓不可兼得」是量測假象。

**關於 squeeze-matrix 回歸測試：** `scripts/check_squeeze.py` 驅動的 `squeeze-matrix.html`
對 MOE 報出較低的擠壓數（serif/h 622），這是**該 harness 的量測產物、非真實文章行為**。
已排除的嫌疑：trim 模式（`normal` 與 `trim-start` 同結果）、把對包進獨立 `<span>`、
Han fallback 字型——三者單獨複刻該量法都能正確測到擠壓，故分歧源自其**全頁環境**中某個尚未
定位的因素。快照已依修好的字體重生（仍能守住非預期的 drift）；**把 harness 改為「Range／正文
情境」量法**列為後續改善，不阻擋本修法。

## 當前樹狀態

程式已改、`dist/` 已重建、`demo/fonts` 已解除 rc.0 釘版並同步修好的字體、
`tests/squeeze-snapshot.json` 已重生。連同本文件與 `docs/TODO.md` 一併 commit。
