# EyeSi_Simulation_Study

軟組織即時變形與**白內障撕囊(CCC, Continuous Curvilinear Capsulorhexis)模擬**的演算法學習筆記。
從 Schill (2001) 的 EyeSi 博士論文出發,整理出**數學/物理公式 ↔ 虛擬碼 ↔ 真實度**的對照,
作為實作白內障手術模擬器(及 AR 訓練系統)的技術參考。

> 研究脈絡:本筆記服務於「**從 EyeSi 系列論文理解 CCC 模擬該如何實作**」這個目標。
> 器械追蹤(tracking)不在本筆記範圍內;重點是**組織變形引擎**與**撕裂(tearing)演算法**。

---

## 🧭 怎麼讀(閱讀順序)

先看 [`docs/overview.md`](docs/overview.md) 頂端的 **START HERE 主幹圖**——它給出「按序讀一遍」的最高效路徑(變形引擎 → 撕裂演算法 → 實作),並標明哪些是**查閱層**(`reference/`:論文血緣)與**隨查層**(FAQ / 逐章導讀)。機制正本只在主幹寫一次,`reference/` 只指過去、不重述。

---

## 核心結論先講(TL;DR)

1. **即時手術模擬器必須走「描述式(descriptive)」方法**——純物理 FEM 太慢。
   見 [`docs/engines/1_framework.md`](docs/engines/1_framework.md)。
2. **CCC 模擬的關鍵設計 = 把「撕裂傳播」和「囊膜變形」解耦成兩層**:
   - Layer A 囊膜變形 = **mass-spring**(或 ECM)
   - Layer B 撕裂傳播 = **Indicator 描述式演算法**(shearing/ripping)
   見 [`docs/ccc_method/1_tearing_descriptive.md`](docs/ccc_method/1_tearing_descriptive.md)、[`docs/implementation/1_architecture.md`](docs/implementation/1_architecture.md)。
3. **三大引擎的取捨**:FEM(準·慢)→ mass-spring(中間)→ ECM(快·穩·可非均質)。
   見 [`docs/engines/5_comparison.md`](docs/engines/5_comparison.md)。

---

## 快速閱覽:本機文件瀏覽器(Docs Viewer)

文件分散在多個子資料夾,用 VS Code 逐一切換很慢。附了一個**零安裝、可即時刷新**的本機瀏覽器
(純 Python 標準庫),一行指令啟動,在瀏覽器裡就能折疊樹狀切換、跨全文搜尋、內嵌看 PDF/HTML、直接編輯存回硬碟:

```bash
python scripts/serve_docs.py          # 啟動後自動開瀏覽器 (預設 http://127.0.0.1:8777)
```

Windows 也可用 `./scripts/serve_docs.ps1`。旗標:`--port 9000` 換埠、`--no-browser` 不自動開。

功能:

| 功能 | 說明 |
|---|---|
| **即時刷新** | 硬碟上的檔案一存,viewer **自動更新**目前開的檔案 + 檔案樹,不用手動 F5(保留展開狀態與捲動位置)。正在編輯且未存檔時會保護你的修改。右上「刷新」鈕可開關 |
| **折疊樹** | 左側依子資料夾展開/收合;md 內嵌閱讀,PDF/HTML demo/圖片也內嵌顯示 |
| **內嵌 PDF** | 論文 PDF 用 PDF.js 直接畫在頁內(不跳下載、不受瀏覽器 PDF 設定影響);PDF.js 快取在 `~/.docs_viewer/`,下載一次、跨專案共用 |
| **HTML 報告** | `docs/*.html` 統整報告/互動 demo 內嵌開啟;報告內連到別的報告或 md 的連結會**在 viewer 內無縫切換**(md 直接渲染、報告互跳、左樹同步) |
| **渲染閱讀** | 支援 GFM 表格、程式碼區塊、ASCII 圖、blockquote、Unicode 數學符號 |
| **全文搜尋** | `Ctrl+K` 聚焦搜尋框,跨全部 **md + HTML 報告**找檔名+內文(HTML 去標籤),點結果跳到該處並高亮 |
| **編輯存檔** | `Ctrl+E`(或 ✏️)切編輯,左改右即時預覽,`Ctrl+S` 存回實際 `.md`(僅限 `.md`) |
| **深/淺色** | 跟隨系統,右上 ◐ 可手動切換 |

> 實作:瀏覽器本體是一個**獨立、與專案無關的工具**,放在 [`docs-viewer/`](docs-viewer/)(`docs_viewer.py` + `viewer.html`,自寫 Markdown 渲染器,無外部相依)。
> `scripts/serve_docs.py` 只是把它指向本 repo 的薄轉呼叫;要瀏覽其他專案:`python docs-viewer/docs_viewer.py <目錄>`。整包可複製到任何專案使用,詳見 [`docs-viewer/README.md`](docs-viewer/README.md)。存檔限定 repo 內的 `.md`,路徑逃逸會被拒。

---

## 目錄(依主題分子目錄)

**入口**
| 文件 | 內容 |
|---|---|
| [docs/overview.md](docs/overview.md) | EyeSi 論文系列脈絡、CCC 醫學背景、本筆記地圖 |
| [docs/clarifications.md](docs/clarifications.md) | **釐清 FAQ**:element 定義、ECM 夾什麼、兩層解耦、應力觸發 |
| [docs/weber2009_reading_guide.md](docs/weber2009_reading_guide.md) | **Weber 2009 博論逐章導讀**(中德對照 + 教學,隨進度累積;目前 §1 導論、§2 EYESi) |

**`engines/` — 變形引擎基礎**
| 文件 | 內容 |
|---|---|
| [1_framework](docs/engines/1_framework.md) | 物理式 vs 描述式、建模金字塔、彈性理論(E、ν) |
| [2_mass_spring](docs/engines/2_mass_spring.md) | **mass-spring**:數學 → 虛擬碼 → 真實度 |
| [3_chainmail_ecm](docs/engines/3_chainmail_ecm.md) | **ChainMail / Enhanced ChainMail** |
| [4_fem](docs/engines/4_fem.md) | **FEM**:概念、KU=F、為何即時用不了 |
| [5_comparison](docs/engines/5_comparison.md) | FEM / mass-spring / ECM **核心差異 + 真實度對照** |
| [6_realtime_fem_pillars](docs/engines/6_realtime_fem_pillars.md) | **FEM 如何變即時**(承 5):TLED / co-rotational / matrix-free 三支柱速查 + E/ν vs k 地基 + DOF/大旋轉根因/各向異性 |
| [7_fem_deep_dive](docs/engines/7_fem_deep_dive.md) | **FEM 深入原理**(機制細節):KU=F 為何耦合、線性應變的旋轉假象(θ=90°→−100% 假應變算例)、非線性 FEM + Newton、CG 每步在做什麼、co-rotational 如何抽 R(polar 分解) |

**`ccc_method/` — CCC 撕裂方法(核心)**
| 文件 | 內容 |
|---|---|
| [1_tearing_descriptive](docs/ccc_method/1_tearing_descriptive.md) | **Indicator 描述式撕裂**(shearing/ripping)= 2006 |
| [2_topological_remesh](docs/ccc_method/2_topological_remesh.md) | **拓樸改變**:remeshing(collapse/split/Delaunay)、Attached 旗標 |
| [3_weber2009_physical](docs/ccc_method/3_weber2009_physical.md) | **Weber 2009 物理版**(應力→位置/應變→方向)+ 逐圖走查 + 與 2006 差異 + 術語表 |
| [4_inria_fiber_fracture](docs/ccc_method/4_inria_fiber_fracture.md) | **INRIA 纖維 FEM 撕囊**:為何 argmax c 準則是對的(三層邏輯)+ Allard/Comas/Dequidt 三篇實作分工 + SofaCUDA 實現流程 |
| [5_meshfree_cutting](docs/ccc_method/5_meshfree_cutting.md) | **免重網格裂縫:XFEM / CutFEM**(vs 重網格):XFEM 富集(Heaviside+裂尖)、CutFEM 嵌入+ghost penalty、Bui/Courtecuisse 即時手術 CutFEM;**重網格／免重網格／增量修預條件子**三種切割對策定位 |

**`implementation/` — 架構與 demo 實作**
| 文件 | 內容 |
|---|---|
| [1_architecture](docs/implementation/1_architecture.md) | 兩層架構、Node+Connector、vrmDesign → SOFA |
| [2_freetear_demo](docs/implementation/2_freetear_demo.md) | **自由撕囊 demo 實作拆解**:Layer B →(Attached/切斷)→ Layer A → remesh |

**`reference/` — 文獻演進、引用、後續發展**
| 文件 | 內容 |
|---|---|
| [1_lineage_map](docs/reference/1_lineage_map.md) | **文獻關係圖 + 方法演進表**(含 PBD / XFEM / FEM 斷裂) |
| [2_weber2006_citations](docs/reference/2_weber2006_citations.md) | **Weber 2006 引用地圖 + 後續延伸**(Weber 2009、Peter 2024…) |
| [3_inria_fem_lineage](docs/reference/3_inria_fem_lineage.md) | **INRIA FEM 路線**(Comas 08 → Allard 09 → Courtecuisse 10/14 → Dequidt 13)+ **2013 系統 vs 2014 方法** + **如何全面理解 INRIA CCC** 閱讀路徑 + 2014 之後四路 |
| [4_inria_fem_realtime](docs/reference/4_inria_fem_realtime.md) | **「FEM 為何能即時」**:TLED / co-rotational / matrix-free / SofaCUDA |
| [5_dequidt2013_vs_demo](docs/reference/5_dequidt2013_vs_demo.md) | Dequidt 2013 系統細節 + 本專案 demo 差距分析 |
| [6_modern_ai_ccc](docs/reference/6_modern_ai_ccc.md) | **現代 AI 撕囊影片分析(2023–26)** |
| [7_han2021_fem_tearing](docs/reference/7_han2021_fem_tearing.md) | **Han 2021 離線 FEM 撕囊力學精讀**(四層水晶體 + Von Mises + 雙線性內聚律 + 豬眼驗證;符號全解;最省力撕裂方向 θ₁=0°/θ₂=30°;含對 repo 舊敘述的判據修正) |
| [8_inria_implementation_deepread](docs/reference/8_inria_implementation_deepread.md) | **⭐ INRIA 整合正本**:三篇一手 PDF 深讀 —— 兩套引擎(TLED 顯式 vs co-rotational 隱式)、核心技術用途完整講解(TLED/co-rot/matrix-free/gather/visco-hyperelastic/非同步預條件子)、建 mesh/物理/克運算量/撕裂(argmax c 全式)/器械、SofaCUDA 元件對映、效能總表、對舊敘述 6 點修正 |
| [9_inria_commercial_helpmesee](docs/reference/9_inria_commercial_helpmesee.md) | **INRIA → 商用化**:InSimo(2013 spin-off,Cotin/Allard/Duriez 創辦)/ HelpMeSee(Ueltschi 航空訓練哲學)/ Moog 力回饋;論文分「臨床效度 vs 引擎技術」兩層;補上 Dequidt 2013 沒有的力回饋 |
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
| [docs/demo_remesh_attached.html](docs/demo_remesh_attached.html) | **自由撕囊完整實作(Weber 2006 描述式)**:按住自由拉撕痕(你拉+drift,shearing/ripping 自動判定)→ 撕痕圍出的內側整片 **Attached→FALSE 脫離** → **PBD 整片掀起/折皺** → 撕裂邊即時 **flip/split/collapse**;雙擊換位撕第二條。實作拆解見 [`implementation/2_freetear_demo`](docs/implementation/2_freetear_demo.md)。純 canvas,**離線可用**。 |
| [docs/demo_strain_field_2009.html](docs/demo_strain_field_2009.html) | **Weber 2009 物理版**:同一 mass-spring 底層,但 **Layer B 裂向改讀應變場**——尖端鄰域組應變張量、取「與最大拉伸垂直=應變最小」方向裂(Rankine 離散近似)。**兩種器械分工**:**針(cystotome)**= 圈圈就是尖端,方向鍵/游標**直接帶著尖端切**(切到哪裂到哪,方向仍受應變場微彎),可在不同位置各切一條;**鑷子(forceps)**= 移到某條裂痕的瓣膜上往外拉,**只有那一片**漸漸被拉開/掀起(每個脫離節點標記所屬裂痕,拉一片不牽動其他切口)。可開**應變場熱圖**看演算法讀的東西。鍵盤全操作:**方向鍵**移動、**空白鍵**操作、**T** 開切口、**F/N** 器械、**R** 重置、**S/V** 開關。技術精讀見 [`ccc_method/3_weber2009_physical`](docs/ccc_method/3_weber2009_physical.md)。純 canvas,**離線可用**。 |
| [docs/compare_2006_vs_2009.html](docs/compare_2006_vs_2009.html) | **一頁對照視覺化**:2006 描述式 vs 2009 物理式的方向決策流程、Layer A/B/Remesh「什麼變了/什麼沒變」、逐項差異總表、核心洞見;內含直接開兩個 demo 的連結。純 HTML/CSS,**離線可用**。 |
| [docs/compare_eyesi_vs_inria.html](docs/compare_eyesi_vs_inria.html) | **一頁對照視覺化**:EyeSi(Weber 描述式)vs INRIA(Comas/Allard/Dequidt 物理 FEM)兩條路線 —— 哲學、團隊血緣、四個子問題(變形/撕裂判定/拓樸/即時)正面對照、argmax c 準則為何更對(三層邏輯)、逐項差異總表、「不是競爭是兩個答案」的核心洞見。純 HTML/CSS,**離線可用**。 |
| [docs/inria_ccc_roadmap.html](docs/inria_ccc_roadmap.html) | **INRIA 完整技術路線圖**:建 mesh → 物理引擎(兩套:TLED 顯式/co-rot 隱式)→ 克服運算量 → 撕裂+remesh(argmax c 全式)→ 器械操作。含 volumetric locking 解釋、真實實作範例血緣(SOFA→Dequidt→Courtecuisse→InSimo/HelpMeSee)、端到端每幀迴圈流程圖、**器械力正確流程(位置驅動接觸,非力回饋也非速度推算)**、效能真相(80fps vs 5fps)。純 HTML/CSS,**離線可用**。 |
| [docs/demo_corot_cg.html](docs/demo_corot_cg.html) | **互動手算視覺化**:①拖 slider 轉動/拉伸一個囊膜三角形,即時看**線性應變的假應變**(θ=90°→−100%)vs **co-rotational / Green 修正**(疊四個三角形:靜止/當前/線性以為的/co-rot 轉回);②**CG 逐步迭代**在碗形等高線上兩步走到解(2×2 迷你系統,顯示 r/α/β/殘差)。對應 [`engines/7_fem_deep_dive`](docs/engines/7_fem_deep_dive.md) §C/§F/§G。純 canvas,**離線可用**。 |

> 重點觀念:**ripping = 瓣膜沒翻面(法線與晶體面法線同向);shearing = 瓣膜對折翻面(法線反向)**。
> 「法線朝不朝向晶體」會隨你釘在內/外表面而顛倒,所以真正穩健的判準是「瓣膜法線 vs 旁邊還黏著囊膜法線:同向=ripping,反向=shearing」。見 [`docs/ccc_method/1_tearing_descriptive.md`](docs/ccc_method/1_tearing_descriptive.md)。
