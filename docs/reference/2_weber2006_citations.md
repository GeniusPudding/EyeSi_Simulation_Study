# Weber 2006 引用關係圖 + 後續延伸

追蹤「**引用 Weber, Wagner & Männer (2006)** *Simulation of the Continuous Curvilinear Capsulorhexis Procedure*(見 [`ccc_method/1 描述式撕裂`](../ccc_method/1_tearing_descriptive.md))且**方法屬於相關延伸**」的論文。
資料來源:OpenAlex(id `W1553707737`)+ Semantic Scholar 引用清單 + 網搜補齊(兩 API 對老 LNCS 章節都漏記,已交叉比對)。

---

## 1. 引用關係圖(演進線)

```
Gimbel & Neuhann 1990   CCC 術式發明
Seibel《Phacodynamics》  shearing / ripping 手法
        │
        ▼
Webster 2004/2005   CCC 模擬開山(mass-spring + 描述式,由 mesh 受力啟發)
        │  移植到 EYESi 開放 API
        ▼
★ Weber, Wagner & Männer 2006   描述式撕裂(shearing/ripping)+ mass-spring + Delaunay remesh
        │                        ＝ 本 repo demo_remesh_attached 實作的版本
        │
        ├─ Weber 2009 博論 ★★     同作者直接升級:描述式 → 物理式(應變/應力),見 §2
        │
        ├─ INRIA 物理路線         Allard/Marchal/Cotin 2009 纖維斷裂
        │                        → Dequidt/Courtecuisse/Comas 2013 SOFA-FEM 白內障訓練
        │                        → (Le Gouis/Marchal 2017 FEM 撕裂 + haptic)          [reference/3_inria_fem_lineage]
        │
        ├─ 離線 FEM 力學          2020 IOL 偏位 / 2021 裂縫豬眼驗證                      [reference/1_lineage_map]
        │
        └─ AI / 自主手術          Peter et al. 2024 ICRA:FEM 撕裂 + 強化學習           [reference/6_modern_ai_ccc]
```

---

## 2. ⭐ 焦點:Weber 2009 博論(2006 的直接完整版)

**Weber, K. (2009).** *Interaktive Echtzeitsimulation deformierbarer Oberflächen für Trainingssysteme in der Augenchirurgie.* PhD thesis, Univ. Mannheim.
[MADOC](https://madoc.bib.uni-mannheim.de/2816/) · 原文 PDF 已存 `papers/Weber_2009_PhD_DeformableSurfaces_EyeSurgery.pdf`(161 頁德文)。
> **不在** EndNote 收集裡(需另存)。

### 最關鍵的一句(§7.1.3,作者自述)
2006 那版撕痕方向是「**rein deskriptiv(純描述式)**」;但作者發現「**找不到一個描述式模型能對所有器械–膜互動都產生物理上合理的裂縫**」→ 因此 2009 版改成「**撕痕方向原則上是物理計算的,只有特殊情況才交給描述式**」。

### 2006 vs 2009 方法差異 + 2009 撕囊模組工程(§7.1.4)
> 這兩塊的**完整內容是方法正本,不在本頁重述**——逐項差異表(方向/位置/drift/拓樸/範圍/器械)與撕囊模組工程(晶體/囊膜/貼合/張力/迴圈/評分/難度)見 [`ccc_method/3 Weber09 物理版`](../ccc_method/3_weber2009_physical.md) §3、§5。本頁只做**引用定位**。

### Fig 7.1 實拍步驟(印證 shearing/ripping 直覺)
(c) 針往周邊 → 直的**徑向裂**;**(d) 動作由「徑向」轉「垂直於裂痕」→ 把裂邊往前推、尾端生張力,將裂痕導向「與虹膜相切」的圓弧**;(e) 器械前方膜**立起、被折過去 (umgelegt)**。
→ 正是「ripping 先垂直展開 → 折起 → 沿切線走」的機制。

---

## 3. 其他引用且方法相關的論文

### A. 直接引用 + 方法延伸
| 論文 | 關係 / 方法 |
|---|---|
| **Allard, Marchal, Cotin 2009** — Fiber-based Fracture Model for Simulating Soft Tissue Tearing [PDF](https://people.rennes.inria.fr/Maud.Marchal/Publications/AMC09.pdf) | 引 Weber 當描述式對照,提**物理式**纖維斷裂(INRIA)[reference/3_inria_fem_lineage] |
| **Dequidt, Courtecuisse, Comas 2013** — Computer-based training system for cataract surgery | SOFA + GPU 即時 FEM 白內障訓練 [reference/3_inria_fem_lineage] |
| **Duriez 2013** — Real-time haptic simulation of medical procedures involving deformations…(habilitation) | SOFA 變形/切割/haptic 總整理,收錄撕囊 |
| **Peter, Peikert, Haide, …, Mathis-Ullrich 2024** — Lens Capsule Tearing in Cataract Surgery using Reinforcement Learning,**ICRA 2024** pp.15501–15508 [IEEE](https://ieeexplore.ieee.org/document/10611714/) · [code](https://github.com/maystroh/RL_cataract) | ⭐ FEM 撕裂當環境 + **RL** 自主/輔助撕囊(KIT)[reference/6_modern_ai_ccc 橋] |

### B. 引用它的綜述(脈絡,非方法延伸)
- Lam, Sundaraj, Sulaiman (2013) *A Systematic Review of Phacoemulsification Cataract Surgery in VR Simulators*
- Lam et al. (2013) *A Review of Computer-Generated Simulation in the Pedagogy of Cataract Surgery Training and Assessment*
- Lam et al. (2014) *Computer-based VR simulator for phacoemulsification cataract surgery training*

### C. 同「撕裂模擬」家族(方法相關,未必直接引 Weber)
- **Le Gouis, Marchal, Arnaldi, Gouranton 2017** — *Haptic Rendering of FEM-based Tearing Simulation using Clusterized Collision Detection*,IEEE World Haptics [HAL](https://inria.hal.science/hal-01675134)(Allard/Marchal 纖維斷裂續作)

### D. 離線 FEM 晶體囊力學(相鄰分支)
- *A study for lens capsule tearing during capsulotomy by FE simulation* (2021) [PubMed](https://pubmed.ncbi.nlm.nih.gov/33714899/) [reference/1_lineage_map]
- *A numerical model of capsulorhexis to assess … IOL decentering and tilt* (2020) [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S1751616120307128)

---

## 4. 對本 repo 的意義
- 我們的 `demo_remesh_attached` = **Weber 2006 的「描述式」版本**(Layer B 描述式 + Delaunay + Attached)。
- **Weber 2009 是它的直接物理式後繼**:方向改由「應變最小」物理計算,drift 降為 fallback。若要做「進階版 demo」,可把 Layer B 換成 2009 的**應變場方向**(需要從 mass-spring 算每個三角形的變形應變)。
- 演進全景見 [`reference/1 血緣圖`](1_lineage_map.md)、INRIA 物理路線 [`reference/3 INRIA 血緣`](3_inria_fem_lineage.md)、AI 路線 [`reference/6 現代 AI`](6_modern_ai_ccc.md)。
