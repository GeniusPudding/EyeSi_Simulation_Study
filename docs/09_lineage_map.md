# 09 — 文獻關係圖 + 方法演進表

把整個 repo 的論文串成一條故事線:**醫學術式 → 變形引擎 → CCC 撕裂建模 → 臨床驗證**,
以及 2006(Weber)之後的後續發展(PBD / XFEM / FEM 斷裂)。

---

## 1. 文獻關係圖(技術血緣)

```
                       醫學術式根源
   Gimbel & Neuhann 1990 ── 發明 CCC 環形撕囊
   Seibel《Phacodynamics》 ── 定義 shearing / ripping 兩種手法
                       │ (提供「該模擬什麼行為」)
                       ▼
 變形引擎根源                          CCC 撕裂模擬主線
 Gibson 1997  3D ChainMail            Webster 2004  開山(Phantom 力回饋)
        │                                   │  mass-spring 囊膜 + 撕裂概念
        ▼                                   ▼
 Schill 2001  Enhanced ChainMail      Webster 2005  移植到 EYESI
   ECM 引擎 + vrmDesign 架構                │
        │  (Layer A 的根)                   ▼
        └───────────┐               ★ Weber/Wagner/Männer 2006
                    │                  最完整 CCC 撕裂演算法(Layer B 主藍圖)
 拓樸/切割           │                  = 解耦 + Indicator 描述式 + Delaunay 重網格
 Nienhuys & van der │                        │
 Stappen 2002/03 ───┘  (提供 remeshing)       │
                                             ▼
                                   臨床驗證(這條線的收尾)
                                   Karim 2010   shearing 撕囊手法(力學細緻化)
                                   McCannel 2013 模擬訓練→OR,降錯誤撕囊 ~68%
                                             │
                                             ▼
                              後續發展(2006 之後,本 repo 範圍邊緣)
                              即時變形 : mass-spring → PBD(≈ ECM 同源)
                              裂縫拓樸 : Delaunay 重網格 → XFEM / cohesive zone
                              離線物理 : 非線性 FEM 斷裂(2021 撕囊力學)
```

> 關鍵人物 **Wagner**:2003 博論(VR 系統)、2002 CACM、2006 CCC 撕裂——是 Mannheim/EyeSi 原廠這條線的核心。
> Webster(Millersville/Penn State)是外部團隊,把模組接上 EyeSi 開放 API;Weber 2006 即在其基礎上做出原廠精緻版。

---

## 2. 方法演進表

| 階段 | 年代 | 變形引擎 (Layer A) | 撕裂 / 拓樸 (Layer B) | 物理↔描述 | 即時? | 代表文獻 |
|---|---|---|---|---|---|---|
| 體積變形引擎 | 1997–2001 | ChainMail → **ECM** | (未處理撕裂) | 描述式 + 物理鬆弛 | ✅ | Gibson 97 / Schill 01 |
| CCC 開山 | 2004–2005 | mass-spring | 力向量 **heuristic** 定方向 | 偏描述 | ✅(beta) | Webster 04/05 |
| **CCC 成熟藍圖** | **2006** | mass-spring(次要) | **Indicator 描述式**(shearing/ripping)+ **Delaunay 重網格** | **純描述式** | ✅ 上線 | **Weber 2006** |
| 臨床驗證 | 2010–2013 | — | — | — | — | Karim 10 / McCannel 13 |
| 即時變形演進 | 2007→ | **PBD**(位置基,無條件穩定;≈ ECM 位移驅動) | 約束投影 | 描述式 | ✅ | Müller 2007 |
| 免重網格裂縫 | 1999→ | FEM | **XFEM**(富集函數,裂縫穿元素免 remesh)/ cohesive zone | 物理式 | ⚠️ 偏離線 | Belytschko 99 / Moës 99 |
| 物理真相(離線) | 2009–2021 | 非線性 FEM | **斷裂力學**(內聚介面律 + 破壞準則) | 物理式 | ❌ 離線 | INRIA 09 / FEM 撕囊 21 |

---

## 3. 三個典範定位(放進演進脈絡)

```
準確度:  FEM / XFEM  >  mass-spring  >  ECM/PBD
即時性:  ECM/PBD  ≳  mass-spring  >>  FEM/XFEM
```

- **即時訓練端**:走 mass-spring → **PBD**(穩定、快、可控)。EyeSi 走的是 ECM/描述式路線。
- **裂縫拓樸端**:Weber 2006 的 **Delaunay 重網格** ↔ 現代 **XFEM**(免重網格)是同一問題的兩種答案。
- **物理理解端**:2006 為即時「放棄物理、改描述式」;2009–2021 的 FEM 斷裂研究則「不求即時、回頭把斷裂力學算清楚」——
  目的不同(訓練 vs 力學理解),且 2021 FEM 結論(剪/拉力主導、特定方向撕裂力最小)反過來**驗證了 2006 shearing/ripping 的直覺**。

---

## 4. 這條線的一句話總結

> **Schill (引擎) → Webster (CCC 概念) → Weber 2006 (解耦+描述式+Delaunay 三件套的成熟藍圖) → McCannel (臨床買單)**;
> 之後即時端長出 **PBD**、裂縫端長出 **XFEM**、離線端長出 **FEM 斷裂力學**。
> 本 repo 聚焦 2001–2006 的可即時實作藍圖(docs 01–08),本頁提供其上下游全景。

→ 相關:[`00_overview.md`](00_overview.md)(脈絡)、[`05_comparison.md`](05_comparison.md)(引擎對照)、[`06_ccc_tearing.md`](06_ccc_tearing.md)(撕裂)、[`07_topological_changes.md`](07_topological_changes.md)(remeshing)
