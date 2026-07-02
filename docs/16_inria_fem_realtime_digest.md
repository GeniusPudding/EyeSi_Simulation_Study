# 16 — INRIA 眼科手術模擬:完整脈絡 + 「FEM 為何能即時」精簡版

一份速讀:INRIA 怎麼做白內障手術模擬,以及 FEM 從「太慢」變「即時」的關鍵原理。
細節見 [`12`](12_inria_fem_lineage.md)(脈絡)、[`14`](14_dequidt2013_vs_demo.md)(Dequidt 細節)。

---

## Part 1 — INRIA 發展脈絡(一條線)

```
2007 SOFA          開源模擬框架(Node+Component 場景圖)         [地基:平台]
2008 Comas         GPU 非線性 FEM(TLED)→ 讓 FEM 即時          [地基:引擎]
2009 Allard        纖維各向異性斷裂準則(取代手調 drift)        [撕囊組件]
2010 Comas         Shell Model(薄殼)→ IOL 薄片彎折展開         [IOL 組件]
2010-11 Courtecuisse 預條件子 + GPU 接觸響應                     [接觸/觸覺]
2013 Dequidt       統一框架 = 撕囊 + phaco + IOL 完整系統 ⭐     [集大成]
        │
        └─► 商用化:InSimo 公司(2013)→ HelpMeSee MSICS 白內障模擬器(閉源)
```

**INRIA 怎麼做眼科手術模擬(Dequidt 2013 三步驟)**:
- **撕囊**:囊膜=三角 FEM + 同心圓纖維各向異性;撕裂=**應變特徵值超門檻**,方向=主應變方向 + 歷史方向;每步 remesh。
- **phaco**:水晶體=四面體 FEM;乳化=**移除四面體**(兩層網格:粗算力學、細算移除)。
- **IOL**:薄鏡片=**Shell Model**(殼,算彎折);注射含自我碰撞 + 摩擦接觸。
- 全部在 **SOFA + GPU**;效能 ~5 FPS(完整)/ ~10 FPS(僅變形),2010 年代硬體;觸覺走獨立 ~1kHz 迴路。

---

## Part 2 — 從 KU=F 到「FEM 為何能即時」

### ① KU=F 是什麼
靜態 FEM 平衡方程,一次解出所有節點位移:
- **U** = 全部節點位移(未知),例 1000 節點×3 = 3000 個未知數。
- **F** = 每節點外力(已知)。
- **K** = 全域剛度矩陣(3000×3000),`K[i][j]` = 節點 j 動一下、在節點 i 產生多少力。
- 物理意義:找 U 使「內部彈性力 = 外力」。**K 把所有節點耦合 → 3000 條方程必須同時解。**

### ② 為何 KU=F 難平行(= 2006 FEM 慢的根源)
「解聯立」本身**順序相依**:高斯消去 → 消變數1會改變其餘所有方程 → 消變數2用被改過的 → …一條相依鏈,難平行,且稠密分解 O(n³)。
> 不是「節點耦合」奇怪,是「同時求解耦合系統」這件事順序又貴。

### ③ 顯式 vs 隱式(你的直覺 = 顯式)
| | 顯式(每節點各自從當前力算) | 隱式(解 KU=F) |
|---|---|---|
| 平行 | ✅ 可(只讀鄰居當前位置) | ❌ 難(新位置互相依賴) |
| 穩定 | dt 太大會爆炸 | 無條件穩定,可大 dt |
2006「FEM 太慢」主要指**隱式 + 解全域矩陣**慢。

### ④ 讓 FEM 即時的五個技術
| 技術 | 做什麼 | 為何快 |
|---|---|---|
| **TLED** | 總拉格朗日(導數預算好)+ 顯式積分 | 不組裝/不解 K;節點獨立→GPU;軟組織 dt 限制不痛 |
| **GPU/CUDA** | 幾萬元素丟幾千核心平行 | 比 CPU 快 1–2 個數量級 |
| **Co-rotational** | 每元素扣掉剛體旋轉→線性算→轉回力 | 線性速度 + 大旋轉不失真 |
| **Matrix-free CG** | CG 只需 K·v,逐元素即時算,不組裝 K | 撕裂改拓樸也不用重組/重分解 |
| **兩層網格 + mapping** | 粗網格算力學、細網格做視覺/碰撞 | 減少昂貴的力學自由度 |

**TLED 細節**:Total Lagrangian → 形狀函數導數為常數、可預算;Explicit → 節點獨立、可 GPU;軟組織低剛度 → 顯式臨界 dt 較大(限制不痛)。三者剛好互補。

### ⑤ 撕裂即時的關鍵:不預組裝全域 K
- 傳統直接解法(Cholesky/LU):必須組好 K 並分解 → 撕裂改拓樸 → 分解失效 → 重來(死)。
- **顯式/TLED**:根本沒有 K → 撕裂只改元素清單(最活)。
- **Matrix-free CG**:K 從不成形 → 撕裂只改「loop 哪些元素」(活)。

---

## Part 3 — 即時的標準 & 開源現況

**FPS**:~10 = 沉浸最低門檻;**20–30 = 實用流暢標準**;觸覺 ~1kHz 獨立迴路。
Dequidt 5 FPS 是 2010 年代硬體 + 追求物理真實的代價;現代 GPU 會快很多。描述式(本 repo demo)反而在「流暢度」佔優。

**開源**:
- ✅ **SOFA / SofaCUDA 開源**(INRIA 自研,LGPL,github.com/sofa-framework/sofa)——GPU FEM、co-rotational 現成。
- ⚠️ 撕囊撕裂邏輯(Allard/Dequidt)需**自己在 SOFA 上拼**。
- ❌ 完整白內障成品 = **InSimo 商用**(HelpMeSee),閉源。

## 一句話總結
> Weber 在「FEM 太慢(隱式解全域 K)」的 2006 用手調 drift 換即時;INRIA 用 **TLED(回到顯式+預算導數)+ GPU + co-rotational + matrix-free** 把「解全域 K」這個瓶頸拆掉,讓真物理 FEM 即時可跑,於是 Dequidt 2013 用真應變場取代手調 drift,做出撕囊+phaco+IOL 完整系統。引擎(SOFA/SofaCUDA)開源,成品(InSimo)閉源。

## 來源
- Miller, Taylor et al. 2007, *TLED FE algorithm for soft tissue deformation*(NiftySim 為其開源實作)。
- Comas 2008(GPU FEM/SOFA)、Allard 2009(纖維斷裂)、Comas 2010(Shell/IOL)、Courtecuisse 2010-11(預條件子)、Dequidt 2013(統一系統)。
- SOFA: github.com/sofa-framework/sofa · InSimo: insimo.com/helpmesee(商用)。
