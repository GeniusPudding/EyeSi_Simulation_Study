# 總覽:EyeSi 論文系列脈絡與 CCC 背景

## 🧭 START HERE — 怎麼讀這個 repo(三層)

文件分三層,先看清「哪些按序讀、哪些用查的」:

**① 主幹 Spine(按序讀一遍 = 最高效路徑)**
```
變形引擎  engines/1 框架 → 2 mass-spring → 3 ECM → 4 FEM → 5 選型 → 6 FEM如何即時
撕裂演算法 ccc_method/1 兩層+描述式 → 2 remesh → 3 Weber09物理 → 4 INRIA纖維FEM → 5 免重網格切割(XFEM/CutFEM)
實作      implementation/1 架構(SOFA) → 2 demo → 3 架構決策 → 4 stock-SOFA 撕裂 demo(實測能耐 + 模型極限 vs EyeSi/INRIA)
對照(選讀) compare_eyesi_vs_inria.html · compare_2006_vs_2009.html
前沿(獨立) reference/6_modern_ai_ccc
```

**② 參考 Reference(查閱,不必按序)**:`reference/`——論文血緣、貢獻定位、引用。
血緣正本 = [`reference/1_lineage_map`](reference/1_lineage_map.md);其餘每篇 = 「貢獻一句話 + 指向主幹正本」。商用化端(InSimo/HelpMeSee)= [`reference/9`](reference/9_inria_commercial_helpmesee.md)。

**③ 隨查 Lookup(需要時翻)**:[`clarifications`](clarifications.md)(FAQ)、[`weber2009_reading_guide`](weber2009_reading_guide.md)(逐章導讀)、`reference/{4,5,7}`(引擎/系統/力學深讀附錄)。

> 各方法的**唯一正本**:E/ν-vs-k 與引擎基礎→`engines/`;撕裂準則(argmax c)→`ccc_method/4`;SOFA 實作骨架→`implementation/1`。`reference/` 不重述機制,只指過去。

---

## 🗺️ 概念地圖(知識圖譜):物理機制怎麼串起來

從最底層概念往上長,每塊標「在哪個檔詳講」。每個檔在講什麼的一句話索引見 [`README`](../README.md) 目錄表。

```
【數值地基】
  自由度 DOF(每節點 x,y,z)──堆成向量 U──► 靜力平衡 KU=F(內彈力=外力,K 稀疏耦合)
    engines/7 §0.5,§B                          engines/4, engines/7 §B
                                                   │「怎麼解這個系統?」
                                 ┌─────────────────┴──────────────────┐
                           顯式(不解方程,逐節點推)             隱式(解耦合系統)
                           = TLED  engines/6 §1                 解法:matrix-free CG
                                                                engines/6 §3, engines/7 §F
【變形怎麼量:連續體力學】
  位移 u → 位移梯度 ∇u ──(F=I+∇u)──► 變形梯度 F ──極分解──► R(旋轉)·U(拉伸)
                                        │ C=FᵀF                   engines/7 §E
                                        ▼
  應變:E=½(C−I) 精確 ┃ ε=∇u 對稱部分(=E 砍二次項,小變形近似)   engines/7 §B.5,§C
                                        │ 材料律 S=f(C)
                                        ▼
  應力 S(各向異性纖維剛度矩陣 K11–K33)   ccc_method/4

【三支柱:讓真 FEM 即時】  engines/6(速查)+ engines/7(深入)
  TLED 顯式 · co-rotational(修大旋轉:ε 丟二次項→cosθ−1 假應變) · matrix-free
                                        ▼
【撕裂(疊在變形上)】  ccc_method/4
  應力 σ → argmax c 準則 → remesh 改拓樸(matrix-free 讓改拓樸免重組矩陣)
                                        ▼
【器械(疊在撕裂上)】  reference/8, inria_ccc_roadmap.html
  IR 光學追蹤→器械位置→接觸/夾持→產生組織力→觸發撕裂(無力回饋,手感靠視覺)
```

> **兩條路線**:EyeSi(描述式:mass-spring + 手調規則)vs INRIA(物理式:上面整套 FEM)——對照見 [`compare_eyesi_vs_inria.html`](compare_eyesi_vs_inria.html)、INRIA 整套端到端見 [`inria_ccc_roadmap.html`](inria_ccc_roadmap.html)。
> **INRIA 兩套引擎**:純變形 = TLED 顯式(Comas);要撕裂/接觸 = co-rotational 隱式 matrix-free(Allard/Dequidt)。整合正本 [`reference/8`](reference/8_inria_implementation_deepread.md)。

---

## EyeSi 是什麼

EyeSi 是德國 Mannheim 大學 Reinhard Männer 教授的 **ViPA(Virtuelle Patienten Analyse)** 研究組
於 1996 年起開發的眼科手術虛擬實境模擬器,後 spin-off 成商用產品 **VRmagic / EyeSi**。
住院醫師在一個機械眼模型中操作真實器械,系統即時模擬組織變形並以立體顯微鏡畫面回饋。

## 論文系列(技術血緣)

| 論文 | 年 | 角色 | 對 CCC 模擬的關係 |
|---|---|---|---|
| **Schill** — Biomechanical Soft Tissue Modeling | 2001 | 組織變形引擎(ECM)+ vrmDesign 架構 | **底層引擎(Layer A 的根)** |
| Wagner — Virtuelle Realitäten für surgical training | 2003 | VR 系統架構 + 繪圖 + 碰撞偵測 | 外殼 |
| Jakubik — Simulation der Phakoemulsifikation | 2009 | phaco 機器物理(灌注/抽吸/超音波/前房壓力) | 白內障術式模組 |
| Köpfle — Modulares optisches Trackingsystem (MOSCOT) | 2012 | 光學追蹤平台 | (本筆記範圍外) |
| **Webster** — A Haptic Surgical Simulator for CCC | 2004 | CCC 模擬開山(mass-spring 囊膜 + 撕裂概念) | **Layer B 概念起點** |
| Webster et al. — Simulating CCC on EYESI | 2005 | mass-spring 撕裂 + 訓練指標 | Layer B 概念 |
| **Weber, Wagner, Männer** — Simulation of the CCC Procedure | 2006 | **最完整的 CCC 撕裂演算法** | **Layer B 實作主藍圖** |
| Karim — Novel capsulorhexis technique (shearing) | 2010 | 臨床撕囊技巧 | 驗證手法 |
| McCannel — Simulator training improves CCC in OR | 2013 | 臨床成效(降併發症 68%) | 驗證訓練有效 |

---

## 逐篇統整(每篇在說什麼 + 脈絡)

### 群組一:`1_Dissertation EyeSi` — EyeSi 的技術族譜(Mannheim / ViPA 組)
全來自 Männer 教授的 ViPA 研究組,是「打造 EyeSi 需要的四塊技術積木」,從底層引擎往上長。

- **① Schill 2001 — Biomechanical Soft Tissue Modeling ⭐ 地基**
  即時手術模擬最難的是「組織被碰到要即時變形」;純物理(FEM)太慢,故發明 **Enhanced ChainMail (ECM)**——用「夾位置」的幾何規則取代「算力」,一個 pass 定形、可模非均質、3D 穩定。再設計 **vrmDesign**(Node+Connector,可換引擎),組裝成 EyeSi。
  → **整個系列的根**:組織變形引擎 + 系統架構。

- **② Wagner 2003 — Virtuelle Realitäten für surgical training**
  把 Schill 的變形引擎**包成能跑的 VR 系統**(VR 架構、繪圖、碰撞偵測、第一個眼球模型)。
  → **外殼**。(掃描檔無法抽文字,內容靠 Schill 序言補。)

- **③ Jakubik 2009 — Simulation der Phakoemulsifikation**
  把真實 **phaco 機器**(超音波乳化 + 灌注/抽吸/泵浦 + 前房壓力/體積模型 + 組織破壞)整台搬進 VR,做成白內障模組。核心是**流體驅動的前房壓力模型 + 阻塞動力學**。
  → **白內障術式模組**;對 CCC 的價值在「前房穩定性」與「Ch3 拓樸/可變形物體基礎」。

- **④ Köpfle 2012 — MOSCOT 模組化光學追蹤**
  把 EyeSi 的器械追蹤升級成通用平台(標記偵測→三角測量→姿態→Kalman/RANSAC 濾波)。
  → **追蹤模組**(本筆記範圍外)。

```
Schill 引擎 ──► Wagner 外殼 ──► Jakubik 白內障模組
              └─► Köpfle 追蹤模組
```

### 群組二:`3_CCC` — 撕囊的實作演進(概念 → 演算法 → 臨床驗證)

- **① Webster 2004 — A Haptic Surgical Simulator for the CCC ⭐ 開山**
  第一個專門模擬撕囊的系統。囊膜 = **mass-spring 網格**;提出核心難點「沒重抓就往周邊跑(runs downhill)」;PHANToM 觸覺 + 訓練指標。
  → **Layer A(mass-spring 囊膜)+ 撕裂概念的起點**。

- **② Webster 2005 — Simulating the CCC on the EYESI System**
  把同一套搬到 **EYESI 平台**(立體顯微鏡)上跑;mass-spring 囊膜 + 撕裂 + 動作錄製重播。
  → Webster 路線移植到 EyeSi。

- **③ Weber, Wagner & Männer 2006 — Simulation of the CCC Procedure ⭐⭐ 主藍圖**
  撕囊最完整的演算法。關鍵設計=**解耦兩層**:囊膜變形(mass-spring,次要)⊥ 撕裂傳播(描述式,核心)。撕痕方向在**切平面**上由 CurrDir+PullDir+DriftDir 合成,**Indicator** 區分 shearing/ripping;拓樸用 **Delaunay remesh**(split/collapse/flip)+ **Attached 旗標**讓膜瓣長大。
  → **你 CCC 實作的主要範本**(Mannheim 團隊,接上群組一血脈)。見 [`ccc_method/1 描述式撕裂`](ccc_method/1_tearing_descriptive.md)。

- **④ Karim 2010 — Novel Capsulorhexis Technique Using Shearing Forces**
  臨床醫師在 EyeSi 模擬器 + 真人眼上示範截囊針剪切力撕囊技巧。
  → **驗證手法真實性**(擬真到能練複雜技巧)。

- **⑤ McCannel 2013 — Simulator Training Improves CCC in the OR**
  1037 台手術回溯研究:導入 EyeSi 撕囊密集課程後,錯誤撕囊率**降 68%**。
  → **驗證訓練有效**。

```
Webster 04 開山 ──► Webster 05 移到 EYESI ──► Weber 06 完整演算法 ⭐
                                                  │
                        Karim 10(驗證手法)+ McCannel 13(驗證成效)
```

### 兩群組怎麼合起來(全局脈絡)
> 群組一(Schill 引擎 + 架構)提供「組織怎麼即時變形」的底層;群組二(Webster→Weber)在其上做出「撕囊怎麼撕」的演算法,再用臨床研究驗證有效。
> **你的 CCC 模擬 = Schill 的 mass-spring/ECM 引擎(Layer A)+ Weber 2006 描述式撕裂(Layer B)+ Delaunay remesh + Attached 旗標。**

## CCC(撕囊)醫學背景

- **CCC = Continuous Curvilinear Capsulorhexis**(連續環形撕囊),白內障 phaco 手術**最關鍵、最難**的一步。
- 在水晶體**前囊**撕出一個完美圓形開口,以便取出混濁水晶體、置入人工水晶體。
- **難在哪**:水晶體赤道有**懸韌帶(zonular fibers)**持續張力,使撕痕**傾向往周邊跑(peripheral drift)**,
  而非跟著拉的方向。撕歪 → 延伸到後囊 → 玻璃體脫出 → 嚴重併發症。
- 兩種控制手法(來自 Seibel《Phacodynamics》):**shearing(剪切)** 與 **ripping(撕扯)**。
  見 [`ccc_method/1 描述式撕裂`](ccc_method/1_tearing_descriptive.md)。

## 本筆記的兩條主線

```
組織變形引擎(怎麼讓組織變形)          撕裂演算法(撕痕往哪走)
  FEM ───────────┐                     Indicator 描述式
  mass-spring ───┤── engines/2–5        (shearing/ripping)
  ECM ───────────┘                       + 拓樸改變(remeshing)
                                          ccc_method/1–2
        ╲                               ╱
         ╲                             ╱
          兩層架構整合(implementation/1) → CCC 模擬器
```
