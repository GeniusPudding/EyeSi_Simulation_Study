# EyeSi_Simulation_Study

軟組織即時變形與**白內障撕囊(CCC, Continuous Curvilinear Capsulorhexis)模擬**的演算法學習筆記。
從 Schill (2001) 的 EyeSi 博士論文出發,整理出**數學/物理公式 ↔ 虛擬碼 ↔ 真實度**的對照,
作為實作白內障手術模擬器(及 AR 訓練系統)的技術參考。

> 研究脈絡:本筆記服務於「**從 EyeSi 系列論文理解 CCC 模擬該如何實作**」這個目標。
> 器械追蹤(tracking)不在本筆記範圍內;重點是**組織變形引擎**與**撕裂(tearing)演算法**。

---

## 核心結論先講(TL;DR)

1. **即時手術模擬器必須走「描述式(descriptive)」方法**——純物理 FEM 太慢。
   見 [`docs/01_modeling_framework.md`](docs/01_modeling_framework.md)。
2. **CCC 模擬的關鍵設計 = 把「撕裂傳播」和「囊膜變形」解耦成兩層**:
   - Layer A 囊膜變形 = **mass-spring**(或 ECM)
   - Layer B 撕裂傳播 = **Indicator 描述式演算法**(shearing/ripping)
   見 [`docs/06_ccc_tearing.md`](docs/06_ccc_tearing.md)、[`docs/08_architecture.md`](docs/08_architecture.md)。
3. **三大引擎的取捨**:FEM(準·慢)→ mass-spring(中間)→ ECM(快·穩·可非均質)。
   見 [`docs/05_comparison.md`](docs/05_comparison.md)。

---

## 目錄

| 文件 | 內容 |
|---|---|
| [docs/00_overview.md](docs/00_overview.md) | EyeSi 論文系列脈絡、CCC 醫學背景、本筆記地圖 |
| [docs/01_modeling_framework.md](docs/01_modeling_framework.md) | 物理式 vs 描述式、建模金字塔、彈性理論(E、ν) |
| [docs/02_mass_spring.md](docs/02_mass_spring.md) | **mass-spring**:數學 → 虛擬碼 → 真實度 |
| [docs/03_chainmail_ecm.md](docs/03_chainmail_ecm.md) | **ChainMail / Enhanced ChainMail**:數學 → 虛擬碼 → 真實度 |
| [docs/04_fem.md](docs/04_fem.md) | **FEM**:概念、KU=F、為何即時用不了 |
| [docs/05_comparison.md](docs/05_comparison.md) | FEM / mass-spring / ECM **核心差異 + 真實度對照表** |
| [docs/06_ccc_tearing.md](docs/06_ccc_tearing.md) | **CCC Indicator 撕裂演算法**(shearing/ripping) |
| [docs/07_topological_changes.md](docs/07_topological_changes.md) | **拓樸改變**:remeshing(collapse/split/Delaunay)、Attached 旗標 |
| [docs/08_architecture.md](docs/08_architecture.md) | 兩層架構、Node+Connector、vrmDesign → SOFA |
| [docs/09_lineage_map.md](docs/09_lineage_map.md) | **文獻關係圖 + 方法演進表**(含 2006 後 PBD / XFEM / FEM 斷裂) |
| [docs/10_clarifications.md](docs/10_clarifications.md) | **釐清 FAQ**:element 定義、ECM 夾什麼、兩層解耦、應力觸發 |
| [references.md](references.md) | 對應論文清單 |

## 虛擬碼

| 檔案 | 對應 |
|---|---|
| [pseudocode/mass_spring.py](pseudocode/mass_spring.py) | mass-spring 引擎 |
| [pseudocode/chainmail_ecm.py](pseudocode/chainmail_ecm.py) | Enhanced ChainMail |
| [pseudocode/ccc_tearing.py](pseudocode/ccc_tearing.py) | CCC Indicator 撕裂 + 兩層整合 |

> 虛擬碼以「**可讀、對應公式**」為目標,非可直接執行的最佳化實作。實務建議建在 [SOFA](https://www.sofa-framework.org/) 上。

## 互動 Demo

| 檔案 | 內容 |
|---|---|
| [docs/demo_shearing_ripping.html](docs/demo_shearing_ripping.html) | **3D 互動**:拖曳旋轉 + 滑桿改變瓣膜對折角度,看 shearing/ripping 時「外表面法線」如何翻轉、Indicator 如何切換。直接用瀏覽器開即可(需連網載入 three.js)。 |
| [docs/demo_decoupling_tear.html](docs/demo_decoupling_tear.html) | **解耦互動**:用滑鼠當器械拉瓣膜,同時看 **Layer A mass-spring 變形**(藍色節點/彈簧)與 **Layer B descriptive 撕裂**(黃線)各自運作;切換 shearing/ripping 觀察撕痕跟隨 vs 跑向周邊(runs downhill)。純 canvas,**離線可用**。 |

> 重點觀念:**ripping = 瓣膜沒翻面(法線與晶體面法線同向);shearing = 瓣膜對折翻面(法線反向)**。
> 「法線朝不朝向晶體」會隨你釘在內/外表面而顛倒,所以真正穩健的判準是「瓣膜法線 vs 旁邊還黏著囊膜法線:同向=ripping,反向=shearing」。見 [`docs/06_ccc_tearing.md`](docs/06_ccc_tearing.md)。
