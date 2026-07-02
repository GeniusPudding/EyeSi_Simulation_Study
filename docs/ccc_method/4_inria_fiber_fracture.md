# INRIA 纖維 FEM 撕囊:準則邏輯 + 三篇實作分工

與 [`1_tearing_descriptive.md`](1_tearing_descriptive.md)(Weber 描述式)對稱:這是**物理式**撕囊的實作。
脈絡見 [`../literature/3_inria_fem_lineage.md`](../literature/3_inria_fem_lineage.md),引擎原理見 [`../literature/4_inria_fem_realtime.md`](../literature/4_inria_fem_realtime.md)。

---

## 0. 三篇分工(誰負責什麼)

| 看什麼 | 核心貢獻 | 提供 |
|---|---|---|
| **撕囊怎麼撕**(往哪/何時) | **Allard 2009** | 纖維各向異性 + argmax c 撕裂準則 + remesh |
| **怎麼即時** | **Comas 2008** | SofaCUDA 上的 GPU TLED FEM 引擎 |
| **組成完整系統** | **Dequidt 2013** | 撕囊+phaco+IOL + 接觸/觸覺 + 兩層網格 |

> 單看「撕囊邏輯」→ **Allard 2009**;單看「即時引擎」→ **Comas 2008**;單看「完整系統」→ **Dequidt 2013**。

---

## 1. 為什麼「纖維準則」是對的(三層邏輯)

`c = (σ_{d⊥} / σ̄_{d⊥}) · H((d·p) − cos θ_P)`,`c > 1` 就撕。

### 第 1 層:撕痕往周邊跑是「纖維造成的物理必然」
囊膜纖維呈**同心圓**(繞水晶體一圈圈)→ **徑向(往周邊)比圓周方向弱** → 撕痕天生易往周邊。
> Weber:觀察到「往周邊跑」現象 → 手調一個 DriftDir 模仿它(假)。
> Allard:把**造成現象的原因(同心圓纖維各向異性)建進材料** → 「往周邊跑」自己湧現(真)。
> 差別不在外觀,在**有沒有把因果建進去**。

### 第 2 層:準則每塊都是標準斷裂力學
- **σ_{d⊥}(垂直方向應力)**:撕痕沿 d 前進,但**把裂縫撐開的是垂直於 d 的張力**(裂縫面法線=d⊥)。所以看垂直張力,不是 d 方向的力。
- **÷ σ̄_{d⊥}(除以該方向強度)**:比值 = 負載/強度,`>1` = 應力超過材料強度 = 裂。**各向異性在此進來**:σ̄ 不同方向不同(纖維強、徑向弱)→ 徑向更易 >1 → 撕往周邊(= 第1層落成數學)。
- **H((d·p)−cos θ_P)(防回折)**:只允許與上一步方向 p 夾角 ≤ θ_P 的候選,其餘歸零 → 裂縫平滑連續(真實裂縫不會突然急轉)。
- **argmax c**:選「負載/強度」比值最大的方向 → 材料在最脆弱/最超載方向先裂。

### 第 3 層:等向時退化成公認正確的定律
關掉纖維(σ̄ 各方向相同、不防回折)→ argmax c **數學上等於「最大主應力準則」**(固體力學公認的脆性斷裂判據)。
> 🔑 所以它不是新 heuristic,而是**「最大主應力準則」的各向異性升級版**:等向=經典定律(已驗證),加纖維=描述囊膜。
> **能退化成公認正確定律,邏輯上就可信**——Weber 的手調 drift 沒有這個理論母體。

---

## 2. Allard 2009 實作(撕囊核心)

```
囊膜 = 三角 FEM,每三角形帶纖維方向 θ(同心圓);co-rotational(容許大位移)+ 隱式積分(穩健)

每一幀:
  A. 變形:解整個網格
     - 不組裝全域 K,用專用共軛梯度(CG)解(matrix-free)  ← 撕裂改拓樸也不用重組
  B. 撕裂判定:
     - 裂縫尖端應力 σ = 鄰域元素應力的加權平均(粗網格下單元素應力不準)
     - 對候選方向算 c;max c > 1 → 該元素可斷,方向 = argmax c(受 θ_P 約束)
     - 不做 substepping(不細分時間步抓精確斷裂時刻,保即時)
  C. remesh:沿 d_fracture 切分三角形
     - 兩策略:沿既有邊(簡單,撕痕被網格綁死)或 任意方向切分(mesh-independent,更真)
     - 小心避免退化三角形(否則 FEM 病態)
```
效能:1,500 三角形,變形+斷裂+remesh **即時**。

---

## 3. Comas 2008 實作(即時引擎,SofaCUDA)

```
GPU TLED(Total Lagrangian Explicit Dynamics):
  - 顯式中央差分:x(t+Δt)=2x(t)−x(t−Δt)+(Δt²/m)F  → 各節點獨立,可平行
  - Total Lagrangian:形狀函數導數相對原始構型=常數 → 預算一次
  - 材料:各向異性 visco-hyperelastic
兩個 CUDA kernel(scatter→gather 避寫入衝突):
  Kernel1(每 thread=元素):算應力→力貢獻,寫「自己的格子」
  Kernel2(每 thread=節點):收集鄰元素力貢獻加總→中央差分更新位置
```
效能:比 CPU 快 16×、比舊 OpenGL 快 3×,~3 萬節點即時。詳見 [`../literature/4_inria_fem_realtime.md`](../literature/4_inria_fem_realtime.md)。

---

## 4. Dequidt 2013 實作(完整系統集成)

把上兩者 + 眼科零件組成能跑的白內障系統:
- **撕囊**:三角 FEM + 同心圓纖維 + **應變張量特徵值超門檻→可斷**(門檻依外科醫師調)+ 歷史方向;每步 remesh。
- **phaco**:水晶體=四面體 FEM;**Projected Tetrahedra** 體積渲染;乳化=移除四面體;
  **兩層網格**——粗四面體(算力學,須夠粗保效能)+ 細元素(算移除),**粗四面體的 8 個細元素都移除時,粗的也移除**(力學上反映失去的物質)。
- **IOL**:薄鏡片=**Shell Model**(殼)+ co-rotational(大位移);注射含**自我碰撞 + 鏡片vs注射器vs囊袋 + 摩擦**。
  巧思:**FEM 的多項式形狀函數同時用於「算內力」與「算接觸」**(曲面接觸不必另建)。
- **接觸/觸覺**:隱式積分 + Courtecuisse 非同步預條件子;器械用 **4 個反光標記**(冗餘,追蹤更穩)。
- 效能:~5 FPS(完整)/ ~10 FPS(僅變形)。

---

## 5. 用 SOFA 自己做的實作對照

```
SOFA 場景:
├─ MechanicalObject              # 囊膜節點(自由度)          ← 開源現成
├─ TriangleSetTopology(動態)    # 可撕三角網格               ← 開源現成
├─ CudaTriangleFEMForceField     # Comas 2008 GPU FEM         ← 開源現成
├─ 自訂 FiberAnisotropy          # 每三角形同心圓纖維方向      ← 要自己寫
├─ 自訂 FractureComponent        # Allard argmax c 準則        ← 要自己寫
├─ 自訂 Remesher                 # 沿撕裂方向切分              ← SOFA 有 cutting 基礎
├─ CGLinearSolver / matrix-free  # 免組裝求解                 ← 開源現成
├─ CollisionModel + 鑷子約束     #                            ← 開源現成
└─ OglModel(立體)               #                            ← 開源現成
```
- **現成**:引擎、拓樸、求解器、碰撞、繪圖。
- **要自己拼**:纖維各向異性 + argmax c 撕裂準則 + remesh(= Allard/Dequidt 的邏輯,SOFA 未打包成插件)。

## 一句話
> CCC 撕囊在 SofaCUDA 的實現 = **Comas 2008 GPU TLED 引擎(即時變形)+ Allard 2009 纖維各向異性 argmax c 準則(往哪撕/何時撕,方向從真纖維物理算出)+ 顯式/matrix-free(撕裂改拓樸免重組矩陣)+ Dequidt 2013 集成**。準則「對」的根本:方向建立在真實纖維各向異性、每塊都是標準斷裂力學、等向時退化成公認的最大主應力準則。

## 來源
Comas 2008 · Allard/Marchal/Cotin 2009 · Dequidt/Courtecuisse 2013(本機 papers/)。
