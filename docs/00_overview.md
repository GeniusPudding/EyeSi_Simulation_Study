# 00 — 總覽:EyeSi 論文系列脈絡與 CCC 背景

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

## CCC(撕囊)醫學背景

- **CCC = Continuous Curvilinear Capsulorhexis**(連續環形撕囊),白內障 phaco 手術**最關鍵、最難**的一步。
- 在水晶體**前囊**撕出一個完美圓形開口,以便取出混濁水晶體、置入人工水晶體。
- **難在哪**:水晶體赤道有**懸韌帶(zonular fibers)**持續張力,使撕痕**傾向往周邊跑(peripheral drift)**,
  而非跟著拉的方向。撕歪 → 延伸到後囊 → 玻璃體脫出 → 嚴重併發症。
- 兩種控制手法(來自 Seibel《Phacodynamics》):**shearing(剪切)** 與 **ripping(撕扯)**。
  見 [`06_ccc_tearing.md`](06_ccc_tearing.md)。

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
