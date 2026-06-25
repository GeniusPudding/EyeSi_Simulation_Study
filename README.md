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
| [references.md](references.md) | 對應論文清單 |

## 虛擬碼

| 檔案 | 對應 |
|---|---|
| [pseudocode/mass_spring.py](pseudocode/mass_spring.py) | mass-spring 引擎 |
| [pseudocode/chainmail_ecm.py](pseudocode/chainmail_ecm.py) | Enhanced ChainMail |
| [pseudocode/ccc_tearing.py](pseudocode/ccc_tearing.py) | CCC Indicator 撕裂 + 兩層整合 |

> 虛擬碼以「**可讀、對應公式**」為目標,非可直接執行的最佳化實作。實務建議建在 [SOFA](https://www.sofa-framework.org/) 上。
