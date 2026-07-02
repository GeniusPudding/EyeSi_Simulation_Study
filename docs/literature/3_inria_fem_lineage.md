# INRIA FEM 路線:從 Weber 2006 描述式 → GPU 即時 FEM 撕裂

2006 之後 CCC 撕裂演算法的主要進展,來自 **INRIA(Alcove / Shacra 組:Cotin, Duriez, Allard, Courtecuisse, Comas…)**。
他們把白內障手術模擬**從 mass-spring + 描述式,換成「GPU 即時非線性 FEM + 纖維各向異性斷裂」**,並全部建在開源框架 **SOFA** 上。

> 對照:Mannheim(Schill/Weber)= mass-spring/ECM + 描述式(私有 vrmDesign);
> INRIA = FEM + GPU + 纖維斷裂(開源 SOFA)。**你能實際使用的是 INRIA 這條。**

---

## 脈絡圖(對應你 EndNote 的 `2013 INRIA` + `SOFA` 群組)

```
【底層即時引擎】
  Comas 2008 — GPU 非線性 FEM(TLED)        ← 讓 FEM 即時的關鍵突破
  961 2008 — 各向異性黏彈性即時組織
  729 2011 — GPU 隱式 FEM + 流體耦合
  730 2011 — 預條件子接觸響應(應用白內障)
        │
【撕裂演算法核心】
  Allard/Marchal/Cotin 2009 — 纖維式斷裂模型   ← 把 Weber 描述式「物理化」
        │
【眼科專用組件】
  723 2008 粗↔細網格對映 · 724 2009 IOL 注入 · 725/728 2010 薄殼模型 · 727 2010 拓樸觸覺
        │
【集大成完整系統】
  Dequidt / Courtecuisse 2013 — 完整白內障訓練系統(rhexis + phaco + IOL)⭐
  726 2010 — 白內障模擬教學平台
```

SOFA 框架本身:733 (2007 SOFA 開源框架)、734 (2012 SOFA 多模型框架)。

---

## 三篇關鍵精讀

### Comas 2008 — Efficient Nonlinear FEM ... GPU ... SOFA(底層引擎)
作者:Comas, Taylor, Allard, Ourselin, Cotin, Passenger(INRIA + UCL + 澳洲 e-Health)。
- **問題**:即時組織模擬需要 FEM,但 FEM 慢(要解全域大矩陣)。
- **方法**:用 Taylor 的 **TLED(Total Lagrangian Explicit Dynamics)**——顯式、節點間無相依 → 天生適合 GPU 平行;再加入 **黏-超彈性(visco-hyperelastic)** 行為。
- **結果**:GPU 比 CPU **快 1–2 個數量級**,**數萬四面體即時**。
- **意義**:直接突破「FEM 即時用不了」(見 [`04_fem.md`](../engines/4_fem.md))——用 GPU 顯式公式繞過全域矩陣瓶頸。這是 INRIA 敢用 FEM 做撕囊的底氣。

### Allard, Marchal & Cotin 2009 — Fiber-based Fracture Model(撕裂核心)
- **問題**:Weber 用 mass-spring + 特殊彈簧結構(放射/同心)假裝囊膜各向異性;撕囊 remesh 時維持該結構很麻煩。
- **方法**:**橫向同性(transversely isotropic)FEM**,每元素定義**纖維方向 θ**(囊膜用**同心圓纖維**=真實結構);
  撕裂準則用**沿纖維/橫向兩個應力閾值**,任意方向依夾角內插;撕裂方向 = 讓準則最大者,並用 θ_P 限制與上一步方向的夾角(避免回折)。
- **退化性質**:設等向(σ̄_F = σ̄_T)→ 退化成經典「最大主應力準則」。是老方法的一般化。
- **即時化**:鄰域加權平均應力 + 不做 substepping(直接選準則最大方向)。1500 三角形即時。

**斷裂準則數學(式 2–6 精簡)**:每三角形有纖維方向 f、兩個強度門檻 σ̄_F(沿纖維)/σ̄_T(橫向)。
- 式2 何時撕:`σ_F > σ̄_F 或 σ_T > σ̄_T`。
- 式5 任意方向 u 的應力 = 應力張量投影到 u(Mohr 轉換):`σ_u = cos²θ·σx + sin²θ·σy + 2sinθcosθ·τxy`。
- 式6 任意方向 u 的門檻 = 依「u 與 f 夾角」在 σ̄_F、σ̄_T 間內插(u∥f→σ̄_F,u⊥f→σ̄_T;α 控尖銳度)。
- 式4 準則:`c = (σ_{d⊥}/σ̄_{d⊥}) × H((d·p) − cos θ_P)`,`>1` 就撕。
  - `σ_{d⊥}` = 垂直於撕痕方向 d 的張應力(把裂縫撐開的那個);÷ 該方向強度 → 比值>1 = 應力超過強度。
  - `H(...)` 階躍:只允許與上一步方向 p 夾角 ≤ θ_P 的候選(**防回折**)。
- 撕裂方向 = `argmax_d c`(受 θ_P 約束下,最超過強度的方向)。GPU 引擎原理見 [`4_inria_fem_realtime.md`](4_inria_fem_realtime.md)。

### Dequidt / Courtecuisse 2013 — Computer-Based Training System(集大成)⭐
作者:Courtecuisse, Allard, Kerfriden, Bordas, Cotin, Duriez。完整白內障三步驟即時訓練系統。
- **囊膜 = 三角 FEM(幾何非線性);水晶體 = 四面體 FEM**(不再 mass-spring)。
- **各向異性 = 同心圓纖維**(用 Allard 2009)。
- **撕裂判定**:每元素**應變張量特徵值分解**,**最大特徵值超門檻 → 標記「可斷 breakable」**(門檻依外科醫師回饋調)。
- **撕裂方向**:考慮**撕裂歷史(上一步方向)**(= Allard 的 p 參數),避免回折;**每 time step 做拓樸改變**。
- **two-level 拓樸**:粗模擬網格 + 細視覺網格(= 723 的粗↔細對映)。
- **GPU 即時 + 觸覺**。直接點名超越 Weber [2] 的 mass-spring。

---

## Weber 2006 → INRIA 怎麼「更進一步」(逐項對照)

| 面向 | Weber 2006(描述式) | INRIA 路線(2008–2013) |
|---|---|---|
| 組織引擎 | mass-spring + 特殊彈簧 | **GPU 非線性 FEM(TLED, Comas 2008)** |
| 各向異性來源 | 手調 DriftDir + 放射/同心彈簧 | **材料的纖維方向(Allard 2009),不依賴網格拓樸** |
| 「往哪撕」 | 手調 CurrDir+Drift+Pull 旋轉角 | **應變特徵值 + 纖維閾值內插 + 歷史方向** |
| 「何時撕」 | 應力超門檻觸發 | **最大應變特徵值超門檻** |
| remesh | Delaunay split/collapse/flip | 沿邊 or 任意方向切分(同源) |
| 框架 | vrmDesign(私有) | **SOFA(開源)** |
| 範圍 | 撕囊模組 | **完整三步驟系統** |

> **核心進步點**:Weber 用「手調規則」假裝懸韌帶張力造成的周邊漂移(DriftDir);
> INRIA 改用**囊膜真實的同心圓纖維結構 + 各向異性 FEM**,讓「撕痕往哪走」**從物理(纖維+應變)自然算出**,而非手調。
> 加上 Comas 2008 的 **GPU TLED** 讓 FEM 即時,整條路線在「物理真實 + 即時 + 開源可用」三點上同時超越 Weber。

## 對 CCC 實作的建議
- **理解原理** → Weber 2006(描述式,最好懂,見 [`06_ccc_tearing.md`](../ccc_method/1_tearing_descriptive.md))。
- **實際實作** → **INRIA 路線**:SOFA + Allard 2009 纖維斷裂 + Comas 2008 GPU FEM;**Dequidt 2013 = 現成完整參考架構**。
- 兩線互補:Weber 教「撕囊邏輯」,INRIA 給「能跑的現代實作」。

## 來源
- Comas et al. 2008, *Efficient Nonlinear FEM for Soft Tissue Modelling and its GPU Implementation within SOFA*, MICCAI workshop / Springer.
- Allard, Marchal, Cotin 2009, *Fiber-based Fracture Model for Simulating Soft Tissue Tearing*, MMVR / Stud Health Technol Inform.
- Courtecuisse, Allard, Kerfriden, Bordas, Cotin, Duriez 2013, *Computer-based training system for cataract surgery* (HAL hal-00855821).
- Allard et al. 2007, *SOFA – an Open Source Framework for Medical Simulation*; Faure et al. 2012, *SOFA: A Multi-Model Framework*.
- PDFs(本機 papers/):Comas_2008、Marchal_2009、Dequidt_2013。
