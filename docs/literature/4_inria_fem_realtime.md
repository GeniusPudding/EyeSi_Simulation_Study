# INRIA 引擎技術原理:FEM 為何能即時(KU=F / TLED / GPU)

速讀:FEM 從「太慢」變「即時」的核心原理。脈絡見 [`3_inria_fem_lineage.md`](3_inria_fem_lineage.md),Dequidt 細節見 [`5_dequidt2013_vs_demo.md`](5_dequidt2013_vs_demo.md)。

---

## 1. KU=F 是什麼、為何 2006 年慢

靜態 FEM 平衡方程,一次解出所有節點位移:
- **U** = 全部節點位移(未知),例 1000 節點×3 = 3000 未知數;**F** = 外力(已知);
- **K** = 全域剛度矩陣,`K[i][j]` = 節點 j 動一下、在節點 i 產生多少力。**K 把所有節點耦合 → 3000 條方程必須同時解。**

**為何難平行**:解聯立本身**順序相依**(高斯消去:消變數1改變其餘所有方程 → 消變數2用被改過的 → …),分解 O(n³)。
> 不是「節點耦合」奇怪,是「同時求解耦合系統」順序又貴。**2006「FEM 太慢」= 隱式 + 解全域 K。**

---

## 2. TLED 本體:其實跟 mass-spring 同骨架

**TLED = Total Lagrangian（總拉格朗日）+ Explicit（顯式）。** 關鍵:它的時間推進 = 你已懂的 mass-spring。

### Explicit:中央差分(central difference)
```
x(t+Δt) = 2·x(t) − x(t−Δt) + (Δt²/mᵢ)·Fᵢ(t)
逐節點:新位置 = 2×當前 − 上一步 + (Δt²/質量)×受力
```
每節點**只需自己的當前/上一步位置 + 受力 + 質量,不解任何聯立** → 跟 mass-spring 一樣可平行。

**與 mass-spring 唯一差別 = 力 F 怎麼算**(見 [`../engines/2_mass_spring.md`](../engines/2_mass_spring.md)):

| | mass-spring | TLED |
|---|---|---|
| 時間推進 | 顯式(各節點獨立) | **顯式,中央差分**(一樣) |
| 力 F 來源 | 彈簧(虎克,參數靠調) | **連續體力學:應變→應力→力**(真物理,E/ν 可量測) |

### Total Lagrangian:讓「算力」變便宜
算應變需要「形狀函數空間導數」。相對**原始(t=0,永不變)構型**算 → 導數是**常數 → 離線預算一次、每步查表**(相對「當前構型」則每步重算)。

> 🔑 **TLED = 顯式(各節點獨立→GPU)+ 總拉格朗日(導數預算好→算力便宜)。** 顯式要小 dt,但**軟組織低剛度 → 臨界 dt 較大 → 限制不痛**。三點互補 = GPU 即時。

---

## 3. GPU 實作(Comas 2008):兩個 kernel + scatter→gather

**kernel** = 一段 GPU 函式,同時在幾千 thread 上跑,每 thread 處理一個資料項(一個元素 or 一個節點)。

TLED 用**兩個 kernel**:
```
Kernel 1(每 thread = 一個元素):算元素應力 → 算「對自己角節點的力貢獻」→ 寫到「元素自己的格子」
Kernel 2(每 thread = 一個節點):讀「周圍元素的力貢獻」加總 → 中央差分更新此節點位置
```

**為何不用一個 kernel 直接把力寫到節點?**(scatter 的陷阱)
- 一個節點被多元素共用;多個元素 thread **同時寫同一節點** = **race condition**:
  ```
  節點=5,元素A想+2、元素B想+3(同時)→ A讀5寫7、B也讀5寫8 → 結果8(正確10,A的+2被吃掉)
  ```
- GPU 預設**不管寫入衝突**;加鎖(atomic)會嚴重拖慢。

**gather 解法**:規則 =「每 thread 只寫自己獨佔的位址;共用只發生在**讀**」。
- **讀可任意共用**(幾千 thread 讀同一塊記憶體沒問題);**寫同一位址才是災難**。
- 所以翻轉方向:不讓元素「推(scatter,寫共用)」,改讓節點「拉/收集(gather,讀共用+寫自己)」。
> 🔑 **scatter→gather = 把「共用的寫」換成「共用的讀 + 私有的寫」,衝突消失。** 代價多一個 kernel,遠比加鎖划算。這是 GPU 物理模擬的通用心法。

**結果**:比 CPU 快 16×、比舊 OpenGL GPGPU 快 3×,~3 萬節點即時。

---

## 4. 顯式/隱式 + 讓 FEM 即時的技術總表

| 技術 | 做什麼 | 為何快 |
|---|---|---|
| **TLED** | 總拉格朗日(導數預算)+ 顯式(中央差分) | 不組裝/不解 K;節點獨立→GPU;軟組織 dt 不痛 |
| **GPU/CUDA + gather** | 幾萬元素平行 + scatter→gather 避衝突 | 比 CPU 快 1–2 個數量級 |
| **Co-rotational** | 每元素扣剛體旋轉→線性算→轉回力 | 線性速度 + 大旋轉不失真 |
| **Matrix-free CG** | CG 只需 K·v,逐元素即時算,不組裝 K | 撕裂改拓樸也不用重組/重分解 |
| **兩層網格 + mapping** | 粗網格算力學、細網格做視覺/碰撞 | 減少昂貴的力學自由度 |

**撕裂即時的關鍵 = 不預組裝全域 K**:
- 直接解法(Cholesky/LU):組好 K 並分解 → 撕裂改拓樸 → 分解失效 → 重來(死)。
- 顯式/TLED:根本沒有 K → 撕裂只改元素清單(最活)。Matrix-free CG:K 從不成形 → 只改「loop 哪些元素」(活)。

---

## 5. 即時標準 & 開源現況

**FPS**:~10 = 沉浸最低門檻;**20–30 = 實用流暢**;觸覺 ~1kHz 獨立迴路。
Dequidt 5 FPS 是 2010 硬體 + 追求物理真實的代價;現代 GPU 快很多。描述式 demo 反在「流暢度」佔優。

**開源**:✅ SOFA/SofaCUDA(INRIA 自研,LGPL)——GPU FEM、co-rotational 現成;⚠️ 撕囊撕裂邏輯(Allard/Dequidt)需自己拼;❌ 完整成品 = InSimo 商用(HelpMeSee),閉源。

> **一句話**:Weber 在「FEM 太慢(隱式解全域 K)」的 2006 用手調 drift 換即時;INRIA 用 **TLED(顯式中央差分+預算導數)+ GPU(gather)+ co-rotational + matrix-free** 拆掉「解全域 K」瓶頸,讓真物理 FEM 即時,於是 Dequidt 2013 用真應變場取代手調 drift。引擎(SOFA)開源,成品(InSimo)閉源。

## 來源
Miller/Taylor 2007(TLED,NiftySim 為其開源實作)· Comas 2008(GPU FEM/SOFA)· Dequidt 2013 · SOFA: github.com/sofa-framework/sofa · InSimo: insimo.com/helpmesee(商用)。
