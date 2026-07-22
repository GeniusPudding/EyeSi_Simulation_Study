# Han 2021 離線 FEM 撕囊力學:精讀筆記(符號全解)

> **論文**:Han, S., He, C., Ma, K., Yang, Y. (2021). *A study for lens capsule tearing during
> capsulotomy by finite element simulation.* **Computer Methods and Programs in Biomedicine**, 203, 106025.
> DOI [10.1016/j.cmpb.2021.106025](https://doi.org/10.1016/j.cmpb.2021.106025) · PMID
> [33714899](https://pubmed.ncbi.nlm.nih.gov/33714899/) · [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0169260721001000)
>
> **這份筆記在 repo 的定位**:文獻演進的「**離線物理真相**」端(見 [`1_lineage_map.md`](1_lineage_map.md) §2 最後一列)。
> 它**不是即時模擬器**,而是「不求即時、回頭把撕囊力學算清楚」的力學研究,用來**印證** EyeSi/INRIA
> 兩條即時路線塞進系統的行為假設是否有力學根據。與 Weber/INRIA 的關係見本篇 §6。

---

## ⚠️ 來源層級聲明(先講清楚可信度)

本 repo **沒有這篇的 PDF 全文**(Elsevier 付費牆,無法合法取得)。本筆記建立在:
- **PubMed 逐字摘要**(§1 引用的都是摘要原文,可信度最高);
- **書目記錄**(作者/期刊/卷期/DOI,已核對);
- **公開檢索摘要**(補充了「研究了哪些參數」「模擬力範圍」等,標為 [檢索補充],次一級可信)。

**因此**:凡「摘要原文」等級的敘述可直接引用;凡涉及**圖表級細節**(θ₁/θ₂ 的精確幾何定義、材料常數數值、網格、內聚律的具體參數值)本筆記**不杜撰**,一律標為「需查全文」。若日後取得 PDF 放進 `papers/`,再回填這些空缺。

---

## 1. 摘要原文拆解(摘要等級,可直接引用)

> *"The lens model consisted of four layers: the anterior and posterior lens capsule, the cortex, and the nucleus.
> **Distortion energy failure criterion combined with the bilinear interface law** was used to express the crack
> propagation process at the edge of the anterior lens capsule. At the clamping position, a **local coordinate
> system** was established to parameterize the capsule tearing. The simulation results were then validated by
> conducting a capsulorhexis experiment using **isolated porcine eyes with force-sensing forceps**."*

四個關鍵設計:
1. **四層 3D 水晶體模型**:前囊 + 後囊 + 皮質(cortex) + 核(nucleus)。注意是**整顆水晶體**分四層,不是「囊膜分四層」。
2. **撕裂判據 = 變形能失效準則(distortion energy = Von Mises)+ 雙線性介面律(bilinear cohesive)**。這是本篇的核心,§3 詳解。
3. **在夾持點(鑷子處)建局部座標系**,用角度 θ₁、θ₂ 參數化撕裂方向。
4. **豬眼 + 力感測鑷子**實驗驗證(不是純理論)。

---

## 2. 四層水晶體模型

```
      ┌─────────────────────────┐  ← 前囊 anterior capsule(撕囊發生在這層邊緣)
      │  皮質 cortex             │
      │      ┌───────────┐       │
      │      │ 核 nucleus │       │
      │      └───────────┘       │
      │  皮質 cortex             │
      └─────────────────────────┘  ← 後囊 posterior capsule
```
- **撕裂只發生在前囊邊緣**(clinical:撕囊撕的就是前囊)。
- 皮質/核/後囊提供**真實的力學支撐與邊界**(前囊不是懸空的膜,底下黏著皮質)——這正是為何需要「囊–皮質介面」的內聚律(§3B)。

---

## 3. 撕裂判據:Von Mises + 雙線性內聚律(本篇核心,符號全解)

判據拆兩塊:**A. 元素何時失效(Von Mises)** + **B. 裂縫怎麼在介面上長(bilinear cohesive)**。

### A. 變形能失效準則 = Von Mises 應力準則

**一句話**:材料的失效由「**形狀被扭曲的程度**」決定,而非「被壓縮的程度」。

- 一點的應力是**張量**(6 個分量),但可化簡成三個**主應力** σ₁ ≥ σ₂ ≥ σ₃(三個互相垂直方向上的純拉/壓,無剪切)。
- **Von Mises 應力 σ_vm**(把整個應力張量濃縮成一個純量):
  ```
  σ_vm = √( ½·[ (σ₁−σ₂)² + (σ₂−σ₃)² + (σ₃−σ₁)² ] )
  ```
  它只看主應力之間的**差**(= 剪切/扭曲部分),**與三者共同的靜水壓(σ₁=σ₂=σ₃ 的部分)無關**。
- **失效判據**:`σ_vm ≥ σ_y` 就失效(σ_y = 材料的降伏/失效應力)。物理意義 = 「使材料**改變形狀**所儲存的能量(distortion energy,變形能)達到臨界值就壞」。

**符號表(A)**:

| 符號 | 名稱 | 意義 |
|---|---|---|
| σ | 應力(stress) | 單位面積受力(Pa) |
| σ₁,σ₂,σ₃ | 主應力 | 三個互相垂直方向上的純拉/壓(無剪) |
| σ_vm | Von Mises 應力 | 把應力張量濃縮的純量,代表「扭曲/剪切」大小 |
| σ_y | 失效應力 | 材料撐得住的上限;σ_vm ≥ σ_y → 失效 |

### B. 雙線性內聚律(bilinear cohesive interface law)= 裂縫怎麼長

**內聚區模型(cohesive zone)** 是現代 FEM 模裂縫的標準法:在會裂開的介面(這裡是**前囊 ↔ 皮質**)之間放一層「虛擬的膠」,遵守一條 **牽引力 T vs 張開量 δ** 的曲線。「**雙線性(bilinear)**」= 這條曲線由**兩段直線**組成:

```
牽引力 T
  │        ╱‾‾╲            T_max = 介面能撐的最大抓力
T_max┤     ╱     ╲
  │      ╱        ╲          左段:彈性上升(膠被拉緊,越拉抓越緊)
  │     ╱           ╲        右段:損傷下降(膠開始壞,越拉抓越鬆)
  │    ╱              ╲
  └───┴────────┴──────→ 張開量 δ
      δ₀             δ_f
   (開始損傷)      (完全斷開)
   曲線下面積 = G_c(斷裂能,撕開單位面積要的能量)
```

- **δ < δ₀**:彈性段,還沒損傷(可復原)。
- **δ₀ ≤ δ < δ_f**:損傷段,抓力下滑(裂縫在長)。
- **δ ≥ δ_f**:牽引力歸零 = **完全撕開**。
- **曲線下的總面積 = G_c(斷裂能)**:這是內聚律**最重要**的物理量——它內建了「撕開需要多少能量」,決定裂縫何時開始、往哪長。

**符號表(B)**:

| 符號 | 名稱 | 意義 |
|---|---|---|
| T | 牽引力(traction) | 介面兩側之間的抓力(單位面積) |
| δ | 張開量(separation) | 介面被拉開的距離 |
| T_max | 峰值牽引力 | 介面能撐的最大抓力(= 介面強度) |
| δ₀ | 損傷起始張開量 | 超過就開始壞 |
| δ_f | 完全失效張開量 | 到此牽引力歸零 = 撕開 |
| G_c | 斷裂能 | T–δ 曲線下面積;撕開單位面積所需能量 |

> **A 與 B 怎麼合作**:Von Mises(A)判「前囊元素**何時**達到失效」→ 觸發前緣;bilinear cohesive(B)描述「介面**怎麼**一段段撕開、要花多少能量」。前者是**起裂判據**,後者是**擴展律**。

---

## 4. 撕裂方向的參數化:局部座標 + θ₁、θ₂

- 在**夾持點(鑷子夾住前囊處)** 建一個**局部座標系**,用兩個角度 **θ₁、θ₂** 描述「撕裂/拉扯的方向」。
- **θ₁、θ₂ 的精確幾何定義(哪個是面內、哪個是離面、相對什麼基準)需查全文的圖**——本筆記不杜撰。可先理解為「拉扯方向在鑷子局部座標下的兩個角度」。

---

## 5. 驗證與結果(摘要等級,可直接引用)

### 驗證
- **豬眼(離體)+ 力感測鑷子**做真實撕囊,量測撕開的力,與模擬對照。
- 與兩顆豬眼樣本(No. 6、No. 9)在**穩定撕裂階段**吻合良好:**p = 0.76、0.10**(p 大 = 兩者無顯著差異 = 吻合)。
- 平均力差:**3.10 ± 2.24 mN** 與 **2.14 ± 1.73 mN**。
- 模擬平均撕囊力範圍 **11.74–27.58 mN** [檢索補充]。

### 三個結論(摘要原文)
1. **撕裂力最小的方向 = θ₁ = 0°、θ₂ = 30°。** ← 本篇最重要、最可引用的結果:**存在一個「最省力」的撕裂方向**。
2. **撕裂速度對撕裂力無顯著影響**(velocity not significantly different)。
3. **合適的撕囊直徑有助於降低撕裂力**(capsulorhexis diameter 影響力)。

> [檢索補充] 公開摘要另提本篇掃過的參數包含:拉伸速度、撕囊直徑、**年齡**、retractor 寬度與形狀、rim 形態。這些的**逐項數值需查全文**。

**符號表(C)**:

| 符號 | 名稱 | 意義 |
|---|---|---|
| θ₁, θ₂ | 撕裂方向角 | 夾持點局部座標下描述拉扯方向的兩個角 |
| mN | 毫牛頓 | 力單位(10⁻³ N);撕囊力量級 ~10–30 mN |
| p-value | 顯著性 | 此處 p 大(0.76/0.10)= 模擬與實驗**無顯著差異** = 吻合 |

---

## 6. 與 Weber / INRIA 的關係(含對先前敘述的修正)

### 這篇如何「印證」即時路線的行為假設
- **「撕裂力最小的特定方向」(θ₁=0°, θ₂=30°)= 撕痕往最省力方向走的物理證據。** 這正是 Weber 2006
  用手調 `DriftDir`、INRIA 用 `argmax c` 各自要捕捉的「撕痕會被拉向某個偏好方向」。Han 2021 把這個
  「最省力方向」**從物理算/量出來**,而即時路線是**憑觀察/憑材料模型**把它放進去。三條獨立路徑指向同一件事
  → **收斂式驗證**(見 [`1_lineage_map.md`](1_lineage_map.md) §2、§3)。
- **「速度不影響、直徑有影響」** 也呼應臨床:撕囊成敗看方向與幾何,不是看撕多快。

### ⚠️ 對本 repo 先前敘述的兩點修正
1. **判據是 Von Mises(變形能),不是「最大主應力/Rankine」。** 兩者不同:
   - **Rankine(最大主應力)**:只看**最大那一拉** σ₁ 是否超標 → **脆性**材料(玻璃)。INRIA 的 `argmax c`
     在等向時退化成的是**這個**(見 [`../ccc_method/4_inria_fiber_fracture.md`](../ccc_method/4_inria_fiber_fracture.md) 第 3 層)。
   - **Von Mises(變形能)**:看**扭曲/剪切**綜合量 σ_vm → 偏**韌性**材料。Han 2021 把囊膜當成偏韌性的膜來模。
   - 所以 `argmax c → Rankine` 是講 **INRIA/Allard**;Han 2021 是**另一套**(Von Mises + cohesive),兩者
     不可混為一談。先前把兩者都籠統說成「斷裂力學印證」是**過度簡化**。
2. **repo 舊敘述「剪/拉力主導」需正名。** 摘要**沒有**逐字說「shear and tension dominate」;較準確的說法是:
   本篇用的 **distortion-energy(Von Mises)準則本身就是以「扭曲/剪切」為失效度量**,加上「最省力方向存在」的
   結果——這是「剪/拉力主導」這個**詮釋**的來源,而非論文原句。[`1_lineage_map.md`](1_lineage_map.md) §2 的
   該措辭宜理解為 repo 作者的**歸納**,非直接引用。

---

## 7. 一句話

> Han 2021 用**四層水晶體 FEM + Von Mises 失效準則 + 雙線性內聚律**,以**豬眼力感測**校準,離線算出撕囊的
> 撕裂力(~10–30 mN)與**最省力撕裂方向(θ₁=0°, θ₂=30°)**。它的價值不在即時,而在**用物理與實測,替
> Weber/INRIA 即時路線「撕痕有偏好方向」的行為假設提供了獨立的力學背書**——但其判據(Von Mises)與 INRIA
> 的 `argmax c`(退化為 Rankine)是**不同的斷裂框架**,不應混同。

## 來源
- Han, He, Ma, Yang (2021), *A study for lens capsule tearing during capsulotomy by FE simulation*,
  CMPB 203:106025 — [DOI](https://doi.org/10.1016/j.cmpb.2021.106025) · [PubMed 33714899](https://pubmed.ncbi.nlm.nih.gov/33714899/)。
  **全文付費牆,本筆記據 PubMed 摘要 + 書目 + 公開檢索摘要撰寫,圖表級細節待補。**
- 相關:[`1_lineage_map.md`](1_lineage_map.md)(演進定位)、[`../ccc_method/4_inria_fiber_fracture.md`](../ccc_method/4_inria_fiber_fracture.md)(INRIA argmax c / Rankine 對照)、[`../compare_eyesi_vs_inria.html`](../compare_eyesi_vs_inria.html)(兩路線總對照)。
