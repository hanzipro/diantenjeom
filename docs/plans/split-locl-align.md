# Plan: split-family Dot / Mark 變體跨 lang 不變

## Goal

`Diantenjeom Sans/Serif Dot Anchored / Dot Centered / Mark Centered /
Mark Anchored` 四種變體在 `lang={ja, zh-Hant, zh-Hans}` 任一下都
產生**完全相同**的：
- 字形設計（cmap-level outline）
- 對成擠壓行為（halt/palt 觸發 + Chrome `text-spacing-trim` gate 過）

換句話說：使用者選 Dot Anchored 就是要 JP 倚角，不管網頁 `lang` 是
什麼；選 Centered 就是 TW 居中。**locl 替換不可以在這些 face 內 fire**。

## 當前狀態（已 build）

實測 harfbuzz shape：

| 變體 | lang=ja | lang=zh-Hant | lang=zh-Hans |
|---|---|---|---|
| Dot Anchored | uni3001 ✓ | **glyph00012 ZHT 居中** ✗ | uni3001 ✓ |
| Dot Centered | TC graft ✓ | **glyph00012** ✗ (覆寫 TC graft) | TC graft ✓ |
| Mark Centered | uniFF1A ✓ | uniFF1A ✓ | **glyph00026 SC 倚角** ✗ |
| Mark Anchored | glyph00026 ✓ | glyph00026 ✓ | glyph00026 ✓ |

## 根因

`pin_locl_to="JAN"` 對 Dot 變體**沒有 take effect**。原因：subsetter
把 face cmap 不參與的 locl FR / lookups prune 掉了：

- Dot face cmap = {uni3001, uni3002, uniFF0C, uniFF0E}
- JAN locl 的 L11 entries（emdash, curly quotes, etc.）不碰這 4 字 → subsetter 視同空 → JAN locl FR 被 prune
- ZHS locl 的 L7 也不碰 dots → 同樣被 prune
- ZHT 的 L8 把 4 dots 全替換成 ZHT 居中 → 對 Dot cmap 有實際 entry → 保留
- ZHH 同 ZHT → 保留
- KOR 的 L12 entry chain 牽涉到 pwid forms（間接），保留了少數 entries → 4 個無關 entry → 保留

當 `_alias_locl_to_locale(gsub, "JAN")` 跑的時候，`_locale_feature_lookups(gsub, "JAN", "locl")` 找不到 JAN 的 locl 路徑（已 prune），回傳 None，alias 直接 skip。結果：原本的 ZHT/ZHH locl 還在原 langsys，照常 fire。

Mark Centered 同理：JAN locl 沒 entry 動 marks → JAN locl FR 被 prune
→ pin 失效 → ZHS locl L7（替換 marks 成 SC 倚角）在 zh-Hans 下 fire。

## 為什麼 SC integrated variant 之前的 pin 沒踩這個坑

SC variant 是「整套 JP source + 全 codepoints.JP」，layout_features=("*",)。
ZHS locl 對 SC cmap 內的 quotes/marks 有真實 entries → subsetter 保
留 → `pin_locl_to="ZHS"` 找得到 → alias 成功。

split 變體 cmap 只有 4-12 個碼點，多數 langsys 的 locl 對這個小 cmap
都「無事可做」→ 被 prune → pin 找不到目標。

## 改造方案 — 三條路評估

### 方案 A：屏蔽 locl entries（surgical strip）

對每個 split variant，build 後遍歷所有 locl lookups，把對 face cmap
碼點的替換 entry **從 mapping 移除**：

```python
def strip_locl_for_cmap(font, protect_cps):
    # 移除 locl 替換來源在 protect_cps 集合內的 entries
    cmap = font.getBestCmap()
    protect_glyphs = {cmap[cp] for cp in protect_cps if cp in cmap}
    for fr in font['GSUB'].table.FeatureList.FeatureRecord:
        if fr.FeatureTag != 'locl': continue
        for li in fr.Feature.LookupListIndex:
            lk = font['GSUB'].table.LookupList.Lookup[li]
            for st in lk.SubTable:
                while hasattr(st,'ExtSubTable'): st=st.ExtSubTable
                if hasattr(st,'mapping'):
                    for g in protect_glyphs:
                        st.mapping.pop(g, None)
```

**優點**：直接，code 短，無視角度依賴。
**風險**：`docs/chrome-pair-squeeze.md` 嘗試 3 明確記錄「從 locl mapping
移除特定 entry」會關 Chrome trim gate（FF0E 移除實驗）。**這條路高機率
讓 trim 失效**。

### 方案 B：對齊 locl targets（align）

不動 locl mapping。但**把 locl 替換到的目標 glyph 的 outline 改成
與 cmap source glyph 一樣**。視覺上 locl fire 與不 fire 結果相同：

對 Dot Anchored：locl L4 mapping `uni3001 → glyph00012` 保留不動，
但把 glyph00012 的 CharString 改成 uni3001 的 CharString（JP 倚角）。
hmtx / vmtx / VORG 也同步。

對 Dot Centered：把 glyph00012 改成 TC-grafted uni3001 的 outline
（TC 居中）。

**優點**：locl 仍 fire 真實替換 → Chrome gate 看到 locl 活動 → gate
過。視覺與 cmap 一致 → 跨 lang 不變。
**docs 風險**：嘗試 5「修改 locl target outline」失敗。但那是「**只
改 FF0E 一個**，其他 3 個 dot locl target 保持 TC 居中」造成 4-dot
不一致（FF0E=kClose、其他=kMiddle）→ group 失敗。

本方案**統一改全部 4 個 dots / 4 個 marks 的 locl targets**，所以
post-locl 4 個 dots 同型（Anchored 全 kClose、Centered 全 kMiddle）→
group 一致 → gate 應該過。docs 警告針對的是「混改」場景。

**唯一未知**：halt / palt SinglePos 條目也得跟著對齊（locl-target glyph
的 halt 條目可能與 cmap source 不同）。如果不對齊，pair 擠壓行為跨
lang 可能略有差異。

### 方案 C：fallback 到 empty locl

`_alias_locl_to_locale` 在找不到目標 langsys locl 時，把所有 locl FR
的 LookupListIndex 設為 `[]`（清空）。

**優點**：實作最簡單。視覺絕對乾淨（locl 完全不 fire）。
**風險**：docs 嘗試 1「`KEEP_FEATURES` 拿掉 locl」與嘗試 2「清空 locl
mapping」都驗過會關 gate。**幾乎肯定破 gate**。Dot face 之前 gate 過
是因為 ZHT/ZHH locl 還在 fire；清空後沒 locl fire → 推測 gate 失敗。

## 推薦：方案 B

理由：
1. 唯一能**同時滿足「視覺穩定」+「gate 過」**的路。
2. docs 失敗案例是「混改」，我們統一改 → 預期不踩同坑。
3. 實作可控：寫一個 `align_locl_targets(font, cps)` helper，對指定碼點把
   locl target outline 同步成 cmap source outline。
4. 已有現成基礎設施可改造：`graft.py` 的 CharString 複製能力。

## 實作步驟

### Step 1 — 新 helper module `align_locl.py`

```python
def install(font, codepoints):
    """For each cmap codepoint in `codepoints`, find every locl
    SingleSubst entry that takes its cmap glyph as the source, and
    copy the cmap glyph's CharString / hmtx / vmtx / VORG into the
    target glyph. Effect: locl fires but renders visually identical
    to the cmap glyph."""
    cmap = font.getBestCmap()
    for cp in codepoints:
        src = cmap.get(cp)
        if src is None: continue
        targets = _collect_locl_targets(font, src)
        for tgt in targets:
            _copy_charstring(font, src, tgt)
            _copy_metrics(font, src, tgt)
```

GPOS 部分（halt / palt 條目）也視需要對齊：

```python
def _align_gpos_single_pos(font, src, tgt, feature_tags=("halt","palt","vhal","vpal")):
    # 如果 src 在 feature 的 SinglePos coverage 內、tgt 不在，把 tgt 也加進去
    # 共用同一個 ValueRecord
    ...
```

### Step 2 — `Variant` 加 `align_locl_cps` 欄位

`tuple[int, ...] = ()`。subset_one 跑完 graft 之後跑 `align_locl.install`。

### Step 3 — 套用到 4 個 split 變體

```python
# Dot Anchored / Centered: 對齊 4 個 dots 的 locl target 為 cmap
align_locl_cps=tuple(codepoints.DOT),

# Mark Centered / Anchored: 對齊 4 個 marks
align_locl_cps=tuple(codepoints.MARK),
```

Mark Anchored 也對齊？是的——這樣連 lang=ja 下也不會走 JAN locl 的
quote subs（雖然 Mark face 沒 quote，但保險起見）。其實 Mark Anchored
*想要* locl fire 到 SC alt，所以**不要**對齊（保持原本 pin_locl_to=ZHS）。
等等，重新想：

- Mark Anchored：我們*要*locl fire 到 SC alt（這就是我們要的 SC 視覺）。
  pin_locl_to="ZHS" 想做的是讓 lang=ja/hant 下 ZHS locl 也 fire（一致）。
  問題是 ZHS locl FR 在 Mark face 裡是否被保留？實測：ja/hant/hans 下都
  顯示 glyph00026/SC 倚角 → 表示 ZHS locl FR 真的在所有 lang 下 fire ✓。
  Mark Anchored 已經正常。不需要 align_locl_cps。

- Mark Centered：我們*不要*任何 locl fire。
  - pin_locl_to="JAN" 失敗（JAN locl FR 被 prune）
  - 換 align_locl_cps：對齊 4 個 marks 的 locl target glyphs → locl 仍 fire
    但 target 與 cmap 等價 → 視覺 = cmap = JP 居中
  - 改用 align_locl_cps=codepoints.MARK，移除 pin_locl_to

- Dot Anchored / Centered：同 Mark Centered 邏輯，align_locl_cps=codepoints.DOT。

### Step 4 — 驗證

1. Build 後再跑 harfbuzz shape test，三組 lang × 四變體，post-locl 結果
   應該與 cmap 完全相同。
2. Chrome 開 demo-split.html，逐 variant + lang 切換，驗：
   - 視覺：dots/marks 設計穩定
   - 擠壓：`、「` `」、` `：「` `」：` 等對成在所有 lang 都 fire halt
3. 如果某 face 的 gate 仍 fail（trim 不 fire），考慮：
   - 把 halt/palt 也 align（pages 內 face）
   - 或回退 pin_locl_to 加上 fallback strategy

## Risks

1. **halt/palt 不對齊**：locl target glyph 在 GPOS halt coverage 內可能有
   不同 ValueRecord。實測過 Mark Anchored 場景，locl target glyph 與 cmap
   bbox 相同且 halt entry 相同（earlier 調査結果）→ 對 Mark Anchored 應無
   問題。Dot 變體要看 locl target glyph 的 halt 是否與 cmap 一致；不一致
   要 align GPOS。

2. **VarStore 干擾**：locl target glyph 可能在 CFF2 VarStore 中有自己的
   variation（不同 wght 下形狀變化）。如果直接把 cmap CharString 蓋過去，
   variation 區域引用會錯位。緩解：copy 整個 `cs.program` 包含 blend 操作。
   `graft.py` 的 `_copy_charstring` 已驗過跨 source 工作的 case，這次 src
   與 tgt 同 font，相容性更好。

3. **HVAR / VVAR 不對齊**：locl target glyph 在 HVAR AdvWidthMap 有自己
   的 delta-set。複製 hmtx 不會改變 HVAR 的影響。但因為 src 與 tgt
   在同 font 共用相同 VarStore，HVAR 的 delta 應該也相容。

4. **docs Step 5 警告**：「修改 locl target outline」會關 gate。如同
   方案 B 的論述，docs 案例是混改 → group 不一致；統一改不踩同坑。
   **這條風險是本方案唯一真正未知**，要實測。

## Out of Scope

- Curly face：lang-switching 是設計意圖，不做對齊。
- Joiner / Bracket face：cmap 碼點不在任何 langsys 的 locl mapping 內，
  不需要做任何處理。
- 整套 family（Sans / Serif / Centered / SC）：行為已 OK，不動。

## Definition of Done

- `src/diantenjeom/align_locl.py` 實作完
- `Variant` 加 `align_locl_cps` 欄位
- 4 個 split 變體（Dot×2 + Mark Centered + Mark Anchored 可選）套用
- `pin_locl_to` 從 Dot×2 + Mark Centered 拿掉（不需要也不夠力）；
  Mark Anchored 保留 pin_locl_to="ZHS"
- Build 乾淨
- harfbuzz shape test：4 變體 × 3 lang 都 post-locl == cmap
- Chrome 視覺驗證：擠壓在所有 lang 都 fire
