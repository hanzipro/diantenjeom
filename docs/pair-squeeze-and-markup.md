# text-spacing-trim 與 markup 邊界（標點擠壓何時失效）

## TL;DR

瀏覽器的標點配對擠壓（`text-spacing-trim`）只會收合**處於同一個 inline
formatting context（同一排版 run）**的相鄰全形標點。把任一個標點單獨關進一個
**atomic inline 盒子**就會破壞收合，寬度回到未擠壓的全形。

關鍵不是「`inline-block` 這個值」，也不是「拆成不同元素」，而是「**跨越 atomic
inline 邊界**」：

- ✅ **不影響**：純 `display: inline` 的 `<span>`，不論巢狀多深 —— 兩字仍在同一
  IFC。
- ✅ **不影響**：兩個字放在**同一個** atomic 盒子裡（它們在盒內共享 IFC）。
- ❌ **失效**：兩個字**各自**一個 atomic inline 盒子 —— `inline-block` /
  `inline-flex` / `inline-grid` / `inline-table`、replaced element（`<img>` 等）
  全都一樣。

## 實測

`demo/pair-span-squeeze.html` 會自行量測並判定（並含本表所有情況）。
環境：Chrome 149.0.7827.103，48px 字級，`text-spacing-trim: trim-start`，以
`text-spacing-trim: space-all` 為「未擠壓」基準。測 `》。`（U+300B U+3002）：

| markup | 寬度 | 擠壓 |
|---|---:|---|
| 同一文字節點 `》。` | 72 | ✅ |
| 兩個純 inline `<span>` | 72 | ✅ |
| 深層巢狀的純 inline `<span>` | 72 | ✅ |
| 兩個字放在**同一個** `inline-block` | 72 | ✅ |
| 兩個 `inline-block` `<span>` | 96 | ❌ |
| 兩個 `inline-flex` `<span>` | 96 | ❌ |
| 兩個 `inline-grid` `<span>` | 96 | ❌ |

未擠壓 = 96px（2×48，各保留全形 advance）；擠壓 = 72px（收掉 0.5em 內側空白）。

> 量測陷阱：基準別用 `text-spacing-trim: normal` —— 依 CSS Text 4，`normal`
> 本身就會 trim（行為近似 `space-first`），不是「不擠壓」。真正的未擠壓基準是
> `space-all`。

## 為什麼

相鄰全形標點的收合發生在 line layout 的 inline 文字 run 內。atomic inline
（`inline-block` 等）會自成一個獨立 layout 盒子 / 獨立 IFC，兩個標點落在不同
run，引擎找不到「相鄰的另一個全形標點」可收合，於是各自保留全形。純 inline
元素不會切斷 run，所以無影響。

## 對使用者的影響

- 一般 HTML / CSS 直接用沒問題。
- 風險在**框架產生的 DOM**：逐字 wrap 做動畫 / 高亮 / 計數時，若每個字是
  `inline-block` 之類的 atomic inline，標點擠壓會悄悄失效。建議標點不要單獨包進
  atomic inline；要包就連同相鄰字一起包進同一個盒子，或維持純 inline。
- 另需「**真正相鄰**」：兩個標點中間夾空白或其他字元一樣不會擠 —— 這與盒子無關。
- 這是**作者端 markup** 的條件，跟字型建置端的 font-wide gate
  （見 [chrome-pair-squeeze.md](chrome-pair-squeeze.md)）是兩回事；兩者都成立才會擠壓。

## 瀏覽器

僅在 Chrome 149 實測。Safari 的 `text-spacing-trim` 實作不同，Firefox 目前尚未
實作（預期三種情況全 96，完全不擠壓）。`demo/pair-span-squeeze.html` 會自行量測
並判定，可直接在各瀏覽器開啟對照。
