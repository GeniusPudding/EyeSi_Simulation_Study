# 總覽:EyeSi 論文系列脈絡與 CCC 背景

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
  → **你 CCC 實作的主要範本**(Mannheim 團隊,接上群組一血脈)。見 [`06_ccc_tearing.md`](ccc_method/1_tearing_descriptive.md)。

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
  見 [`06_ccc_tearing.md`](ccc_method/1_tearing_descriptive.md)。

## 本筆記的兩條主線

```
組織變形引擎(怎麼讓組織變形)          撕裂演算法(撕痕往哪走)
  FEM ───────────┐                     Indicator 描述式
  mass-spring ───┤── docs 02/03/04/05    (shearing/ripping)
  ECM ───────────┘                       + 拓樸改變(remeshing)
                                          docs 06/07
        ╲                               ╱
         ╲                             ╱
          兩層架構整合(docs 08) → CCC 模擬器
```
