# 免重網格裂縫:XFEM / CutFEM(vs Weber/Dequidt 的重網格)

「撕痕/切口前進」= 拓樸改變。即時 FEM 面對它有**兩大類對策**:

- **A. 重網格(conforming remesh)**:把網格**實際切開**去貼合裂縫。Weber 2006 / Dequidt 2013 走這條 → 機制正本見 [`ccc_method/2 拓樸改變`](2_topological_remesh.md)。
- **B. 免重網格(non-conforming)**:網格**固定不動**,裂縫「穿過元素」,用**數學**表示不連續。= XFEM / CutFEM。**本頁講 B。**

> ⚠️ 本頁多為**通用 FEM 方法教學**,不出自 EyeSi/INRIA 一手撕囊論文;方法細節一律標 **[補充]**。
> 一手來源:Belytschko & Black 1999 / Moës 1999(XFEM);Burman & Hansbo 2010–2015(CutFEM / ghost penalty);Bui, Courtecuisse, Bordas 2019(即時手術 CutFEM)。

---

## 1. 為什麼要免重網格?[補充]

重網格的痛點(承 [`ccc_method/2`](2_topological_remesh.md) 與 [`reference/8 §1.6`](../reference/8_inria_implementation_deepread.md)):

- 一直改拓樸 → 隱式解的 **K 分解/預條件子失效** → 要重分解(貴)。
- 要小心**退化細三角形**(Dequidt「唯一要求:避免過小三角形」,否則病態)。
- 網格解析度綁死撕痕平滑度(太粗露出多邊形痕跡)。

**免重網格**把裂縫幾何從「網格拓樸」抽離成「數學富集/嵌入」→ 網格結構穩定 → 更適合即時 + 隱式。

## 2. XFEM(eXtended FEM,Belytschko & Black 1999)[補充]

核心:標準 FEM 位移場 `u(x) = Σ Nᵢ(x)·uᵢ`,**再加富集項**:

```
u(x) =  Σ Nᵢ·uᵢ   +   Σ Nⱼ·H(x)·aⱼ   +   Σ Nₖ·(Σ Fₗ(x)·bₖₗ)
        標準 FEM       Heaviside 跳斷        裂尖漸近函數
```

- **H(x)** = Heaviside 階梯:描述「裂縫兩側位移可**跳斷**」——被裂縫貫穿的元素,節點加富集 DOF `aⱼ`。
- **Fₗ(x)** = 裂尖漸近解函數(如 √r·sin(θ/2) 家族):描述尖端應力奇異性——裂尖元素加 DOF `bₖₗ`。
- 效果:裂縫可**從元素中間穿過、甚至終止在元素內部**,**網格完全不動**;裂縫推進 = 增刪富集 DOF,不動幾何。

## 3. CutFEM(Burman & Hansbo;ghost penalty)[補充]

XFEM 的近親,走**嵌入式 / 虛擬域(fictitious domain)**:

- 把界面/切口**嵌進一個固定背景網格**(背景網格**不需貼合**幾何)。
- 只在「被切到的元素」上做**特殊(子單元)積分**來表示真實幾何。
- 難點:元素可能被切得**極畸形**(只有一小角落在域內)→ 系統病態、條件數爆。
- 解法:**ghost penalty(Burman 2010)** 穩定化——對「跨界面相鄰元素」的高階導數加懲罰項,讓畸形切割元素「借」相鄰健康元素的資訊 → 條件數受控。
- **Corotational Cut FEM(Bui, Courtecuisse, Bordas 2019, CMAME 345:183–211)**:把 CutFEM 用到**即時手術**(針插入)——使用者只給**不貼合的背景網格**,cut 元素用**多層嵌入(multilevel embedding)**處理;co-rotational 撐大旋轉。= INRIA 這條線 **2014 之後的「免重網格切割」分支**([`reference/3` 2014 之後](../reference/3_inria_fem_lineage.md))。

## 4. 三種切割對策的定位(同一問題三種答案)

| 對策 | 網格 | 拓樸/分解怎麼扛 | 代表 | 本 repo 正本 |
|---|---|---|---|---|
| **重網格(conforming)** | 實際切開貼合裂縫 | 改拓樸 → matrix-free 免重組 K(或被迫重分解) | Weber 06 / Dequidt 13 | [`ccc_method/2`](2_topological_remesh.md) |
| **免重網格 XFEM/CutFEM** | 固定,裂縫穿元素 | 網格不動 → 系統結構穩定 | Belytschko 99 / Bui-Courtecuisse 19 | **本頁** |
| **增量修預條件子** | 仍重網格,但不重分解 | Sherman-Morrison 只更新被切節點 | Courtecuisse 14 | [`reference/8 §1.6`](../reference/8_inria_implementation_deepread.md) |

> 三者非取代關係,而是「即時 FEM 遇拓樸改變」的三種工程答案:
> **切了重組但避免重分解(重網格 + matrix-free)／ 切了增量修分解(Sherman-Morrison)／ 乾脆不切網格(XFEM/CutFEM)。**

## 5. 與 EyeSi / 描述式的關係

- Weber/EyeSi 走**描述式 + 重網格**(教學最好懂);XFEM/CutFEM 屬**物理式**且免重網格,偏 INRIA / 離線力學那端。
- `1_lineage_map` 早已標「Delaunay 重網格 ↔ XFEM 免重網格 = 同問題兩答案」——本頁補上其**技術機制**與**三方定位**。

## 來源

- Belytschko, T.; Black, T. (1999). *Elastic crack growth in finite elements with minimal remeshing.* Int. J. Numer. Methods Eng. 45(5). / Moës, N.; Dolbow, J.; Belytschko, T. (1999). *A finite element method for crack growth without remeshing.* Int. J. Numer. Methods Eng. 46.
- Burman, E. (2010). *Ghost penalty.* C. R. Math. 348:1217–1220. / Burman, Claus, Hansbo, Larson, Massing (2015). *CutFEM: Discretizing geometry and partial differential equations.* Int. J. Numer. Methods Eng. 104(7).
- Bui, H. P.; Tomar, S.; Courtecuisse, H.; Cotin, S.; Bordas, S. P. A. (2019). *Corotational cut finite element method for real-time surgical simulation: application to needle insertion simulation.* Comput. Methods Appl. Mech. Engrg. 345:183–211. [arXiv 1712.03052](https://arxiv.org/abs/1712.03052) · [HAL hal-01717155](https://hal.science/hal-01717155)
