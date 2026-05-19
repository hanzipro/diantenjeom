# Plan: Diantenjeom 按組別拆分發行（Joiner / Curly / Dot / Bracket / Mark）

## Goal

在保留現有 Diantenjeom family（`Sans`, `Serif`, `Sans/Serif Centered`,
`Sans/Serif SC`）的同時，新增**按 Chromium `han_kerning` 字符分組 +
排版風格變體**的獨立 face 系列，讓使用者按需在 CSS fallback chain
裡組裝出任何「地區 / 排版風格 / 字體」組合。

設計核心是兩條 must-have face 防護 Latin clobber，其他 3 組是 optional
排版風格選擇：

- **Joiner**（must-have）：抵擋西文字體蓋掉中點 / 破折號 / 刪節號等
  Latin-overlap 碼位（`·` 在 Latin-1 區，幾乎所有西文字體都有）。
- **Curly**（locale-switch）：U+2018-201D 沒有半/全寬碼位區隔，
  同碼位在 SC 要全形、在 JP/TC 要半形——必須獨立才能控制。
- **Dot / Mark / Bracket**（optional）：純 fullwidth CJK 碼位，
  Latin 字體無對應，自然 fallback 正確；分組純粹是給「想換 punct 風格」
  的設計者用。

**與已存在的 `DTJX Sans Dot/Bracket/Mark/Curly` 區隔**：DTJX 是
Sans-only 實驗包（最小 codepoint set，4 個核心 group，無 Centered/
Anchored 變體），用來測 Chrome trim gate 行為。**新的 Diantenjeom split
是 production**：Sans + Serif 對等、納入 `codepoints.JP` 全集 32 字、
Dot/Mark 進一步分 Centered + Anchored 兩種排版風格。

## 全部 codepoint 32 字逐字分組

| codepoint | char | Chrome class | 分組 |
|---|---|---|---|
| U+3001 | `、` | kDot | **Dot** |
| U+3002 | `。` | kDot | **Dot** |
| U+FF0C | `，` | kDot | **Dot** |
| U+FF0E | `．` | kDot | **Dot** |
| U+300C, 300D | `「」` | kOpen / kClose | **Bracket** |
| U+300E, 300F | `『』` | kOpen / kClose | **Bracket** |
| U+FF08, FF09 | `（）` | kOpen / kClose | **Bracket** |
| U+3008, 3009 | `〈〉` | kOpen / kClose | **Bracket** |
| U+300A, 300B | `《》` | kOpen / kClose | **Bracket** |
| U+3014, 3015 | `〔〕` | kOpen / kClose | **Bracket** |
| U+FF1A | `：` | kColon | **Mark** |
| U+FF1B | `；` | kSemicolon | **Mark** |
| U+FF1F | `？` | kClose | **Mark** |
| U+FF01 | `！` | kClose | **Mark** |
| U+2018, 2019 | `‘’` | kOpenQuote / kCloseQuote | **Curly** |
| U+201C, 201D | `“”` | kOpenQuote / kCloseQuote | **Curly** |
| U+00B7 | `·` | kMiddle | **Joiner**（Latin-1，會被西文蓋）|
| U+30FB | `・` | kMiddle | **Joiner** |
| U+2014 | `—` | kOther | **Joiner**（西文 em-dash 斷線、半寬）|
| U+2E3A | `⸺` | kOther | **Joiner** |
| U+2026 | `…` | kOther | **Joiner**（西文 ellipsis 沉底）|
| U+FF0D | `－` | kOther | **Joiner** |
| U+FF0F | `／` | kOther | **Joiner** |
| U+FF3C | `＼` | kOther | **Joiner** |

Invariant: `Dot(4) + Bracket(12) + Mark(4) + Curly(4) + Joiner(8) = 32 = len(codepoints.JP)`。
plan 實作時 `codepoints.py` 底部加 `assert`。

## Dot / Mark 的 Centered + Anchored 變體

`Dot` 與 `Mark` 兩組在 CJK 不同地區有兩套設計傳統：

| 組 | Centered（TW MOE 風）| Anchored（JP / mainland-GB 風）|
|---|---|---|
| Dot `、 。 ， ．` | ink 居中、寬度全 em | ink 倚角（lsb≈64-144、bbox 在左下）|
| Mark `： ； ？ ！` | ink 居中 em 高度 / 寬度 | ink 倚角（lsb≈194-460、bbox 在左半）|

Dot Centered = TC source 4 dots（已驗，與現有 `Centered` variant 同源）。
Dot Anchored = JP source 4 dots（與現有 `Sans` variant 同源）。
Mark Centered = JP source 4 marks（JP 本來就居中 — 與現有 `Sans` 同源）。
Mark Anchored = SC source 4 marks（已驗，與現有 `SC` variant 的 mark graft 同源）。

`Bracket` / `Curly` / `Joiner` 各只一版（無 Centered/Anchored 區分需要）：

- Bracket：CJK 括號設計上都是倚角，無中置變體。
- Curly：locale-switch（lang/locl 內部處理），不靠 face split。
- Joiner：中點、破折號、刪節號等都是中線設計，本來就「居中」，無 anchored 對手。

## 全部 face 列表（Sans + Serif 對等 = 14 faces × 2 file = 28 file）

每個 face 都產 `.otf` 與 `.woff2`，故 file 數 = face 數 ×2。

### Sans（7 faces）

| family | stem (base) | source | codepoints | 備註 |
|---|---|---|---|---|
| `Diantenjeom Sans Joiner` | `diantenjeom-sans-joiner` | JP | 8 (Joiner) | must-have |
| `Diantenjeom Sans Curly` | `diantenjeom-sans-curly` | JP | 4 (Curly) | locale-switch（locl + vert_subst）|
| `Diantenjeom Sans Dot Anchored` | `diantenjeom-sans-dot-anchored` | JP | 4 (Dot) | vert_nudge.JP |
| `Diantenjeom Sans Dot Centered` | `diantenjeom-sans-dot-centered` | JP + TC graft | 4 (Dot) | 4 dots grafted from Noto TC |
| `Diantenjeom Sans Bracket` | `diantenjeom-sans-bracket` | JP | 12 (Bracket) | |
| `Diantenjeom Sans Mark Centered` | `diantenjeom-sans-mark-centered` | JP | 4 (Mark) | JP 本來就居中 |
| `Diantenjeom Sans Mark Anchored` | `diantenjeom-sans-mark-anchored` | JP + SC graft | 4 (Mark) | 4 marks grafted from Noto SC，center_punct_cps=() |

### Serif（7 faces，命名平行）

| family | stem (base) | source | codepoints |
|---|---|---|---|
| `Diantenjeom Serif Joiner` | `diantenjeom-serif-joiner` | JP Serif | 8 |
| `Diantenjeom Serif Curly` | `diantenjeom-serif-curly` | JP Serif | 4 |
| `Diantenjeom Serif Dot Anchored` | `diantenjeom-serif-dot-anchored` | JP Serif | 4 |
| `Diantenjeom Serif Dot Centered` | `diantenjeom-serif-dot-centered` | JP Serif + TC Serif graft | 4 |
| `Diantenjeom Serif Bracket` | `diantenjeom-serif-bracket` | JP Serif | 12 |
| `Diantenjeom Serif Mark Centered` | `diantenjeom-serif-mark-centered` | JP Serif | 4 |
| `Diantenjeom Serif Mark Anchored` | `diantenjeom-serif-mark-anchored` | JP Serif + SC Serif graft | 4 |

### 全 build 後 dist 結構（含既存 + DTJX）

```
dist/fonts/
  # 既有「整套」family（保留不動）
  diantenjeom-sans.{otf,woff2}
  diantenjeom-serif.{otf,woff2}
  diantenjeom-sans-centered.{otf,woff2}
  diantenjeom-serif-centered.{otf,woff2}
  diantenjeom-sans-sc.{otf,woff2}
  diantenjeom-serif-sc.{otf,woff2}

  # DTJX 實驗（保留不動）
  dtjx-sans-dot.{otf,woff2}
  dtjx-sans-bracket.{otf,woff2}
  dtjx-sans-mark.{otf,woff2}
  dtjx-sans-curly.{otf,woff2}

  # NEW — Diantenjeom split family
  diantenjeom-sans-joiner.{otf,woff2}
  diantenjeom-sans-curly.{otf,woff2}
  diantenjeom-sans-dot-anchored.{otf,woff2}
  diantenjeom-sans-dot-centered.{otf,woff2}
  diantenjeom-sans-bracket.{otf,woff2}
  diantenjeom-sans-mark-centered.{otf,woff2}
  diantenjeom-sans-mark-anchored.{otf,woff2}
  diantenjeom-serif-joiner.{otf,woff2}
  diantenjeom-serif-curly.{otf,woff2}
  diantenjeom-serif-dot-anchored.{otf,woff2}
  diantenjeom-serif-dot-centered.{otf,woff2}
  diantenjeom-serif-bracket.{otf,woff2}
  diantenjeom-serif-mark-centered.{otf,woff2}
  diantenjeom-serif-mark-anchored.{otf,woff2}
```

| 段 | face 數 | file 數 |
|---|---|---|
| 既有 family | 6 | 12 |
| DTJX 實驗 | 4 | 8 |
| **NEW split** | **14** | **28** |
| Σ | 24 | 48 |

## CSS fallback chain 範式（README 要列）

四個方向的設計意圖示例：

### A. 最小防護（推薦預設）

只搶救容易被蓋的 Joiner + Curly，其他標點走系統字體 fallback：

```css
font-family:
  'Diantenjeom Sans Joiner',
  'Diantenjeom Sans Curly',
  'Hiragino Sans', system-ui, sans-serif;
```

### B. 混搭（Joiner + Curly 個別 + 整套兜底）

防 Latin clobber + 全套 Diantenjeom 風格：

```css
font-family:
  'Diantenjeom Sans Joiner',
  'Diantenjeom Sans Curly',
  'Diantenjeom Sans',          /* 兜底全套 */
  'Hiragino Sans', sans-serif;
```

### C. 全分組客製（按 TW MOE 風）

每組明確選風格：

```css
font-family:
  'Diantenjeom Sans Joiner',
  'Diantenjeom Sans Curly',
  'Diantenjeom Sans Dot Centered',
  'Diantenjeom Sans Bracket',
  'Diantenjeom Sans Mark Centered',
  'Hiragino Sans', sans-serif;
```

### D. 全分組客製（按 mainland-GB 風）

```css
font-family:
  'Diantenjeom Sans Joiner',
  'Diantenjeom Sans Curly',
  'Diantenjeom Sans Dot Anchored',
  'Diantenjeom Sans Bracket',
  'Diantenjeom Sans Mark Anchored',
  'Hiragino Sans', sans-serif;
```

## 實作步驟

### Step 1 — codepoints.py 加 5 組常數

```python
JOINER = [0x00B7, 0x30FB, 0x2014, 0x2E3A, 0x2026, 0xFF0D, 0xFF0F, 0xFF3C]
CURLY  = [0x2018, 0x2019, 0x201C, 0x201D]
DOT    = [0x3001, 0x3002, 0xFF0C, 0xFF0E]
BRACKET = [
    0x300C, 0x300D, 0x300E, 0x300F,  # 「」『』
    0xFF08, 0xFF09,                  # （）
    0x3008, 0x3009, 0x300A, 0x300B,  # 〈〉《》
    0x3014, 0x3015,                  # 〔〕
]
MARK   = [0xFF1A, 0xFF1B, 0xFF1F, 0xFF01]

assert sorted(JOINER + CURLY + DOT + BRACKET + MARK) == sorted(JP), \
    "split groups must partition codepoints.JP exactly"
```

DTJX 既存 `DTJX_DOT / DTJX_BRACKET / DTJX_MARK / DTJX_CURLY` 保留不動（給實驗用，核心字 set 不含 angle/書名/tortoise brackets，不含中點）。

### Step 2 — build.py 加 14 個 Variant row

7 個 Sans + 7 個 Serif：

```python
# Joiner — must-have
Variant(punct="joiner", style="sans",  source=JP_SANS,  unicodes=codepoints.JOINER,
        layout_features=("*",)),
Variant(punct="joiner", style="serif", source=JP_SERIF, unicodes=codepoints.JOINER,
        layout_features=("*",)),

# Curly — locale-switch (lang/locl handles narrow vs full)
Variant(punct="curly",  style="sans",  source=JP_SANS,  unicodes=codepoints.CURLY,
        layout_features=("*",)),
Variant(punct="curly",  style="serif", source=JP_SERIF, unicodes=codepoints.CURLY,
        layout_features=("*",)),

# Dot — Anchored (JP corner) + Centered (TC graft)
Variant(punct="dot-anchored", style="sans",  source=JP_SANS,  unicodes=codepoints.DOT,
        vert_nudges=vert_nudge.JP, layout_features=("*",)),
Variant(punct="dot-anchored", style="serif", source=JP_SERIF, unicodes=codepoints.DOT,
        vert_nudges=vert_nudge.JP_SERIF, layout_features=("*",)),
Variant(punct="dot-centered", style="sans",  source=JP_SANS,  unicodes=codepoints.DOT,
        layout_features=("*",),
        grafts=((TC_SANS, (0x3001, 0xFF0C, 0x3002)),)),
        # ．(FF0E) 不 graft；其餘 3 字 TC 居中
Variant(punct="dot-centered", style="serif", source=JP_SERIF, unicodes=codepoints.DOT,
        layout_features=("*",),
        grafts=((TC_SERIF, (0x3001, 0xFF0C, 0x3002)),)),

# Bracket
Variant(punct="bracket", style="sans",  source=JP_SANS,  unicodes=codepoints.BRACKET,
        layout_features=("*",)),
Variant(punct="bracket", style="serif", source=JP_SERIF, unicodes=codepoints.BRACKET,
        layout_features=("*",)),

# Mark — Centered (JP default) + Anchored (SC graft)
Variant(punct="mark-centered", style="sans",  source=JP_SANS,  unicodes=codepoints.MARK,
        layout_features=("*",)),
Variant(punct="mark-centered", style="serif", source=JP_SERIF, unicodes=codepoints.MARK,
        layout_features=("*",)),
Variant(punct="mark-anchored", style="sans",  source=JP_SANS,  unicodes=codepoints.MARK,
        pin_to_locale="ZHS", layout_features=("*",),
        grafts=((SC_SANS, (0xFF01, 0xFF1A, 0xFF1B, 0xFF1F)),),
        vert_nudges={0xFF01: -50, 0xFF1F: -50},
        center_punct_cps=()),
Variant(punct="mark-anchored", style="serif", source=JP_SERIF, unicodes=codepoints.MARK,
        pin_to_locale="ZHS", layout_features=("*",),
        grafts=((SC_SERIF, (0xFF01, 0xFF1A, 0xFF1B, 0xFF1F)),),
        vert_nudges={0xFF01: -50, 0xFF1F: -50},
        center_punct_cps=()),
```

`punct` 帶 `-` 連字號是新模式（`dot-anchored`, `mark-centered` 等）。
現有 family 屬性的 `.title()` 不會正確處理：`"dot-anchored".title()` → `"Dot-Anchored"`。
要動 `Variant.family`：把 `-` 替換成空格 + 各 title：

```python
@property
def family(self) -> str:
    if not self.punct:
        suffix = ""
    elif self.punct in {"sc", "tc", "jp", "kr"}:
        suffix = f" {self.punct.upper()}"
    else:
        # "dot-anchored" → " Dot Anchored"
        suffix = " " + " ".join(w.title() for w in self.punct.split("-"))
    return f"{self.family_prefix} {self.style.title()}{suffix}"
```

### Step 3 — Demo 頁 `demo-split.html`

跟 `demo-dtjx.html` 區隔，但結構相近：

- 14 個 face 載入
- Controls：
  - **Style**: Sans / Serif 切換
  - **Dot variant**: Centered / Anchored
  - **Mark variant**: Centered / Anchored
  - **face on/off**: 5 個（Joiner/Curly/Dot/Bracket/Mark）
  - **text-spacing-trim**: normal / trim-start / space-all
  - **explicit features**: halt / palt
  - **lang**: ja / zh-Hant / zh-Hans
- Test samples：
  - **內 face**: 各組內部 pair（dot+dot 等）
  - **跨 face**: 24 種 cross-face pair（demo-dtjx.html 已有相似結構）
  - **Joiner clobber 對比**：故意把 `Diantenjeom Joiner` 從 chain 拿掉，看 `…—·` 怎麼被系統字體蓋
  - **Centered vs Anchored 對比**: 同段落兩個版本並列
  - **lang 切換對 Curly**：同段在 ja / zh-Hans 下 quote 寬度差異
  - **直排**

### Step 4 — README

加一個「Split Family」段，列 fallback chain 範式（前述 A/B/C/D）。
DTJX 仍留實驗包標籤、註明非 production 入口。

## Risks / 不確定

1. **Chrome trim gate per face**：14 個 face 各跑 gate。風險點：
   - Bracket / Joiner face 自己 cmap 沒 colon/semi/quote/dot，gate 都
     用 `.notdef`。`.notdef` 分類 + locl 是否觸發未知。
   - Dot Centered face 用 TC source 設計，4 dots 都 kMiddle → 一致 ✓。
   - Mark Anchored face graft SC marks，bbox kClose → 一致 ✓。
   - 確認手段：build 後逐 face 跑 harfbuzz 模擬（demo-sc-quotes.html 用過的方法），列出 type_for_*。

2. **跨 face boundary pair**：例如 `，「`，前字 Dot face / 後字 Bracket face。
   Chrome 用「後字 face」的 font_data 解析前字的 kDot 分類，會去
   Bracket face 的 `type_for_dot`（從 Bracket 的 `.notdef` 算）。
   若 Bracket face 的 `type_for_dot` 跟 Dot face 真實 dots 分類不同，
   trim 可能不 fire 或 fire 錯。**Split 路線最大未知**。緩解：
   保留整套 `Diantenjeom Sans` 在 fallback chain 兜底（pattern B）。

3. **locl 滿足條件**：Bracket / Joiner face 自己 cmap 沒 locl substitute
   目標。docs/chrome-pair-squeeze.md 提過 locl 不 fire 會關 gate。
   但 `layout_features=("*",)` 保 locl 結構 + 其他 codepoint 仍有
   locl substitute（如 emdash → JAN locl，emdash 在 Joiner face cmap 內
   且有 locl substitute → Joiner face 的 locl 會 fire 在自己 cmap 內字）。
   Bracket face 可能 fail；實驗驗。

4. **檔案數膨脹**：48 個 file（OTF + WOFF2，含既有與 DTJX）。各 file
   平均 ~6-20 KB（小 subset）→ 全部 ~500 KB 量級，可接受。

5. **Variant `punct` 含 `-` 連字號**對既有 stem / family 邏輯影響：
   - stem: `diantenjeom-sans-dot-anchored` — 連字號是 stem 內合法。
   - family: 需 `.split("-")` + 各 word `.title()`（前面 code sketch 處理過）。
   - PostScript 名：`family.replace(" ", "")` → `DiantenjeomSansDotAnchored`，合法。

## Out of Scope

- SC 版的 Dot/Mark split：SC variant 已是整套，要再分 face 太碎，先不做。
- Centered 版的 Dot/Mark split：同上。
- Curly 拆 Narrow + Wide（不靠 locl 切）：先信任 locl 內部處理；
  若 lang switching 後續出問題再回頭加 Curly-Narrow / Curly-Wide。
- Joiner 與 Curly 的 Serif-only 微調（如 Joiner 在 Serif 下的中線位置）：
  先用 Serif source 預設。

## Definition of Done

- `codepoints.py` 5 個常數 + invariant assert
- `build.py` 14 個新 Variant row + `family` 屬性處理 `-` 連字號
- `pnpm build` 乾淨，`dist/diantenjeom.css` 多 14 個 face block
- 14 個新 `.otf` + 14 個 `.woff2` 在 `dist/fonts/`
- `demo-split.html` 可載入、5 face × variant 切換正常
- 各 face Chrome trim 行為驗證（內 face / 跨 face / Joiner clobber 對比）
- README 加 Split Family 段 + 4 種 fallback chain pattern
