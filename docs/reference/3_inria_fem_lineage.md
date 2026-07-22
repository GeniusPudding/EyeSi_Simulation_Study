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

## 研究脈絡:四個瓶頸 → 四組解法(接力賽)

整條線不是散論文,而是「把 FEM 從 2006 跑不動、推到 2013 完整即時系統」的接力。
**Weber 因『FEM 太慢』放棄的四件事(真變形/真材料/真撕裂/真接觸),被一件件救回來:**

| 2006 遺留瓶頸 | INRIA 解法 | 篇 |
|---|---|---|
| ①變形太慢 | GPU TLED 顯式(見 [`4_inria_fem_realtime.md`](4_inria_fem_realtime.md)) | Comas 08 |
| ②材料不真 | 各向異性黏-超彈性(visco-hyperelastic) | Taylor 08 (961) |
| ③撕裂靠手調 | 纖維斷裂準則(argmax c) | Allard 09 |
| ④接觸/觸覺/穩定做不到即時 | **非同步預條件子** | Courtecuisse 10-11 (730) |
| (整合) | 統一系統 | Dequidt 13 |

**分期接力**:
```
2007 SOFA ─────────── 平台(讓一切可組合,後續都是它的 component)
2008 Comas GPU TLED ─ ①變形即時(比 CPU 快 16×)
2008 Taylor(961) ─── ②各向異性黏超彈性 → 材料像真組織
2009 Allard ───────── ③纖維斷裂 → 撕痕方向從物理算出(取代手調 drift)
2010-11 Courtecuisse ─ ④非同步預條件子 → 接觸/觸覺/穩定即時 ★最硬的一關
2010 Jung(727) ───── 拓樸改變時的高擬真觸覺(~1kHz)
2008-10 723/724/Comas2010 ─ 眼科零件:粗↔細網格 mapping / IOL 注入 / 薄殼
2013 Dequidt ──────── 集大成:撕囊+phaco+IOL 完整系統 ⭐
2014 Courtecuisse(MedIA) ─ 一般化定稿:即時接觸+切割異質組織(眼/肝/腦)
InSimo(2013)→ HelpMeSee ─ 商用產品(閉源)
```

**Phase 3 為何最硬(非同步預條件子的巧思)**:接觸/撕裂需要**隱式積分**(穩定、大 dt、能處理約束),
但隱式每步要解線性系統,CG 對**異質組織(軟硬不均)收斂很慢** → 又回到「慢」。
解法:好的**預條件子**能讓 CG 快速收斂但算它很貴 → 把它丟到**背景執行緒非同步計算**,
主迴圈**重複用「稍微過期」的預條件子**(組織變形夠慢,稍舊仍好用),在 GPU 上快速解 CG。
→ 隱式穩定 + 收斂快 + 即時,這才讓 Dequidt 的**接觸 + 器械互動**成立(摩擦接觸;器械 = IR 光學追蹤,**無力回饋裝置**)。

---

## 三篇關鍵精讀(貢獻定位;機制正本見指向)

> 本頁是**血緣定位**,不重述機制/公式。argmax c 準則的完整推導與三層邏輯在 [`ccc_method/4 INRIA 纖維FEM`](../ccc_method/4_inria_fiber_fracture.md);TLED/gather/matrix-free 引擎原理在 [`engines/6 FEM如何即時`](../engines/6_realtime_fem_pillars.md) 與 [`reference/4`](4_inria_fem_realtime.md);Dequidt 系統細節在 [`reference/5`](5_dequidt2013_vs_demo.md)。

- **Comas 2008** — *Efficient Nonlinear FEM…GPU…SOFA*(底層引擎)。**貢獻**:用 TLED 讓非線性 FEM 上 GPU、比 CPU 快 1–2 個數量級、數萬四面體即時 → 突破「FEM 即時用不了」([`engines/4 FEM`](../engines/4_fem.md))。這是 INRIA 敢用 FEM 做撕囊的底氣。
- **Allard, Marchal & Cotin 2009** — *Fiber-based Fracture Model*(撕裂核心)。**貢獻**:橫向同性 FEM + 每元素同心圓纖維 + **argmax c 斷裂準則**,取代 Weber 手調 drift;等向時退化成最大主應力準則。1500 三角形即時。→ 公式/邏輯正本見 `ccc_method/4`。
- **Dequidt / Courtecuisse 2013** — *Computer-Based Training System*(集大成 ⭐)。**貢獻**:囊膜三角 FEM + 水晶體四面體 FEM + 同心圓纖維 + 應力特徵值超門檻→可斷 + 歷史方向防回折 + two-level 網格 + GPU 即時 + 摩擦接觸(器械 IR 追蹤、無力回饋),組成撕囊+phaco+IOL 完整系統,直接點名超越 Weber 的 mass-spring。→ 系統細節見 `reference/5`。

---

## Weber 2006 → INRIA 怎麼「更進一步」(逐項對照)

| 面向 | Weber 2006(描述式) | INRIA 路線(2008–2013) |
|---|---|---|
| 組織引擎 | mass-spring + 特殊彈簧 | **GPU 非線性 FEM(TLED, Comas 2008)** |
| 各向異性來源 | 手調 DriftDir + 放射/同心彈簧 | **材料的纖維方向(Allard 2009),不依賴網格拓樸** |
| 「往哪撕」 | 手調 CurrDir+Drift+Pull 旋轉角 | **應力特徵值 + 纖維閾值內插 + 歷史方向** |
| 「何時撕」 | 應力超門檻觸發 | **最大應力特徵值超門檻** |
| remesh | Delaunay split/collapse/flip | 沿邊 or 任意方向切分(同源) |
| 框架 | vrmDesign(私有) | **SOFA(開源)** |
| 範圍 | 撕囊模組 | **完整三步驟系統** |

> **核心進步點**:Weber 用「手調規則」假裝懸韌帶張力造成的周邊漂移(DriftDir);
> INRIA 改用**囊膜真實的同心圓纖維結構 + 各向異性 FEM**,讓「撕痕往哪走」**從物理(纖維+應變)自然算出**,而非手調。
> 加上 Comas 2008 的 **GPU TLED** 讓 FEM 即時,整條路線在「物理真實 + 即時 + 開源可用」三點上同時超越 Weber。

## 對 CCC 實作的建議
- **理解原理** → Weber 2006(描述式,最好懂,見 [`ccc_method/1 描述式撕裂`](../ccc_method/1_tearing_descriptive.md))。
- **實際實作** → **INRIA 路線**:SOFA + Allard 2009 纖維斷裂 + Comas 2008 GPU FEM;**Dequidt 2013 = 現成完整參考架構**。
- 兩線互補:Weber 教「撕囊邏輯」,INRIA 給「能跑的現代實作」。

## 2013「系統」vs 2014「方法」——兩篇的分工(最常被混為一談)

**不是續作,是同組、幾乎同時、分工不同的姊妹作**(2014 *Medical Image Analysis* 線上是 2013/12,作者群與 Dequidt 2013 大幅重疊)。

| 軸向 | **Dequidt 2013(系統)** | **Courtecuisse 2014(方法)** |
|---|---|---|
| 性質 | 完整訓練系統(撕囊+phaco+IOL)+ IR 追蹤 + 硬體 | 異質軟組織 **接觸+切割** 的數值求解器 |
| 器官 demo | 白內障(整台模擬器) | 白內障 **+ 肝切 + 腦瘤**(顯示方法通用) |
| 線性解 | matrix-free GPU-CG(**引用** Courtecuisse 的解算) | GPU-CG + **非同步預條件子 + Sherman-Morrison 增量更新** |
| 拓樸改變 | 撕痕鄰域 remesh;matrix-free 免重組 K | **正面解決「切割→預條件子/分解失效」** |
| 發表領域 | SIMULATION(偏系統) | Medical Image Analysis(偏方法/數值) |

→ 核心差:2013 撕囊靠 **remesh + matrix-free CG**,**沒有**非同步 Sherman-Morrison 預條件子(只引用 Courtecuisse 的 GPU-CG);2014 補上的正是這塊(切割下仍穩又即時的關鍵)。**機制正本見 [`reference/8 §1.6`](8_inria_implementation_deepread.md)**,本頁只做血緣定位。

**預條件子演進(2010 → 2014)**:
- **2010(Prog. Biophys. Mol. Biol.)**:GPU 即時變形 + **切割 + 觸覺**,把「GPU 隱式解 + 預條件子」這條路建起來(= 你 EndNote 的白內障預條件子那群的源頭)。
- **2014(MedIA)**:加上 **Sherman-Morrison 增量更新**——切割只是低秩擾動,只更新被切到的節點、免整體重分解 → **切割專門的成熟版**。

---

## 2014 之後:INRIA 這條線分四路長出去

1. **切割免重網格(CutFEM / XFEM 化)**:Bui, Courtecuisse, Bordas 等《Corotational Cut Finite Element Method for real-time surgical simulation》(~2018, CMAME)——針插入**不 remesh**(承 Bordas 的 XFEM;呼應 [`1_lineage_map`](1_lineage_map.md) 的 XFEM 分支)。
2. **大規模 / 機器人約束解**:Zeng et al. 2022(*Computer Graphics Forum*)預條件子接觸 + isolated-DOF 約束;Adagolodjo / Courtecuisse 機器人針的即時**逆 FEM**。
3. **商用化**:**InSimo**(2013 Strasbourg spin-off)→ **HelpMeSee** MSICS 模擬器(閉源;物理引擎承本線,+ Moog 力回饋 + SenseGraphics 渲染)。
4. **AI / RL**:Peter et al. 2024(ICRA)在 **SOFA**(= 本線 FEM 框架)環境上做 **RL 自主/輔助撕囊**(見 [`references.md`](../../references.md)、[`2_weber2006_citations`](2_weber2006_citations.md))。

---

## 如何全面理解 INRIA 白內障 CCC 模擬系統(閱讀路徑)

分六層、由淺入深——**「為什麼 → 怎麼即時 → 撕裂準則 → 完整系統 → 切割數值 → 之後」**:

1. **為什麼走 FEM 不走描述式**:[`engines/1 框架`](../engines/1_framework.md)(物理式 vs 描述式)→ 本頁「Weber 2006 → INRIA 逐項對照」。
2. **FEM 為何能即時(四支柱)**:[`engines/6 即時FEM支柱`](../engines/6_realtime_fem_pillars.md) + [`reference/4`](4_inria_fem_realtime.md)(TLED / co-rotational / matrix-free / GPU);想看**具體怎麼寫**→ [`reference/8 §1`](8_inria_implementation_deepread.md)。
3. **撕裂準則(往哪撕/何時撕)**:[`ccc_method/4 纖維FEM`](../ccc_method/4_inria_fiber_fracture.md) 的 **argmax c** 三層邏輯(正本)。
4. **完整系統怎麼兜**:[`reference/5 Dequidt 系統細節`](5_dequidt2013_vs_demo.md) + [`reference/8`](8_inria_implementation_deepread.md)(SofaCUDA 元件對映、效能總表)。
5. **切割/接觸的數值核心**:本頁「2013 vs 2014」+ [`reference/8 §1.6`](8_inria_implementation_deepread.md)(非同步 + Sherman-Morrison)。
6. **之後往哪走**:本頁「2014 之後」四路。

> **一句話心法**:**Comas(讓 FEM 即時)→ Allard(讓撕裂有物理)→ Courtecuisse 2010–2014(讓切割/接觸穩且即時)→ Dequidt 2013(把三者兜成系統)→ InSimo/HelpMeSee(商用)/ Peter 2024(AI)**。

---

## 來源
- Comas et al. 2008, *Efficient Nonlinear FEM for Soft Tissue Modelling and its GPU Implementation within SOFA*, ISBMS / Springer.
- Allard, Marchal, Cotin 2009, *Fiber-based Fracture Model for Simulating Soft Tissue Tearing*, MMVR / Stud Health Technol Inform.
- **Courtecuisse, Jung, Allard, Duriez, Lee, Cotin 2010**, *GPU-based real-time soft tissue deformation with cutting and haptic feedback*, Prog. Biophys. Mol. Biol. 103(2–3):159–168 (HAL hal-00686056). → 非同步預條件子這條線的奠基。
- **Dequidt, Courtecuisse, Comas, Allard, Duriez, Cotin, Dumortier, Wavreille, Rouland 2013**, *Computer-based training system for cataract surgery*, SIMULATION (HAL hal-00855821). → 集大成完整系統。
- **Courtecuisse, Allard, Kerfriden, Bordas, Cotin, Duriez 2014**, *Real-time simulation of contact and cutting of heterogeneous soft-tissues*, Medical Image Analysis 18(2):394–410 (HAL hal-01097108). → 切割/接觸數值定稿(Sherman-Morrison 增量預條件子)。
- Allard et al. 2007, *SOFA – an Open Source Framework for Medical Simulation*; Faure et al. 2012, *SOFA: A Multi-Model Framework*.
- PDFs(本機 papers/):Comas_2008、Marchal_2009、Dequidt_2013。
