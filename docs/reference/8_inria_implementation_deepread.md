# INRIA CCC 系列:技術原理 × 實作方法 × 系統架構(完整脈絡深讀)

> **這是 INRIA 內容的整合正本**——把散在 [`ccc_method/4`](../ccc_method/4_inria_fiber_fracture.md)、[`reference/3`](3_inria_fem_lineage.md)、[`reference/4`](4_inria_fem_realtime.md)、[`reference/5`](5_dequidt2013_vs_demo.md)、[`engines/6`](../engines/6_realtime_fem_pillars.md) 的片段,合成一份「原理→實作→架構」的完整深讀。
> **來源**:三篇一手 PDF 逐頁精讀——Comas 2008(GPU 引擎)、Marchal/Allard/Cotin 2009(撕裂)、Dequidt/Courtecuisse 2013(完整系統),存 `papers/`。
> **標註慣例**:凡「原文明述」直接寫;涉及推論處標 **[推論]**。

---

## 0. 最關鍵的框架:INRIA 不是「單一引擎」

常見誤解是「INRIA = TLED」。實際上這系列有**兩套不同的 solver stack**,克服運算量的手法完全不同:

| 論文 | 角色 | 引擎 | 積分 | 克服運算量靠 |
|---|---|---|---|---|
| **Comas 2008** | GPU 引擎 | **TLED**(Total Lagrangian Explicit) | 顯式中央差分 | 不解方程 + GPU 兩 kernel |
| **Marchal 2009** | 撕裂準則 | **co-rotational** | 隱式 | matrix-free CG |
| **Dequidt 2013** | 完整系統 | **co-rotational 線彈性** | 隱式,dt=0.01s | matrix-free GPU-CG |

> 🔑 **撕裂與完整系統走的是 co-rotational + 隱式 + matrix-free CG,不是 TLED 顯式。** TLED 只在 Comas 那篇。讀下面每一節都要記得「哪套引擎」。

### 脈絡:四瓶頸 → 四解法(接力)
Weber 2006 因「FEM 太慢」放棄的四件事,被 INRIA 一件件救回:

| 2006 瓶頸 | INRIA 解法 | 篇 |
|---|---|---|
| ①變形太慢 | GPU TLED 顯式 | Comas 08 |
| ②材料不真 | 各向異性 visco-hyperelastic | Comas 08 |
| ③撕裂靠手調 | 纖維斷裂 argmax c 準則 | Allard 09 |
| ④接觸/穩定做不到即時 | 隱式 + matrix-free GPU-CG(+ 非同步預條件子) | Courtecuisse 10 → Dequidt 13 |

---

## 1. 核心技術完整講解(用途導向)

每個技術用「**是什麼 / 解決什麼(用途) / 怎麼運作 / 誰用**」講清楚。

### 1.1 TLED(Total Lagrangian Explicit Dynamics)
- **是什麼**:顯式動力學 FEM,一切量相對**原始構型 t=0**(Total Lagrangian)計算。
- **解決什麼(用途)**:讓「真非線性 FEM」快到能即時 + 能上 GPU。攻的是「解全域 K 太慢」與「每步重算幾何量太貴」兩個成本。
- **怎麼運作**:
  - **Total Lagrangian**:形狀函數空間導數相對永不變的原始構型 → **常數,預算一次**(SOFA `init()` 上傳 GPU)、每步查表。(對比 Updated Lagrangian 每步重算。)
  - **Explicit(顯式中央差分)+ 集中質量 M**:`uₙ₊₁ = 2uₙ − uₙ₋₁ + Δt²·M⁻¹·(F_ext − F_int(uₙ))`;M 對角化 → M⁻¹ 只是逐節點縮放,**無線性解、逐節點獨立 → 天生平行**。
  - 代價:顯式條件穩定,Δt 受元素尺寸/波速限制(軟組織剛度低 → 臨界 Δt 較大 → 不太痛)。
- **誰用**:Comas 2008(唯一)。**撕裂/完整系統不用 TLED**。

### 1.2 co-rotational
- **是什麼**:線性彈性 + 每元素扣掉剛體旋轉的幾何非線性法。
- **解決什麼(用途)**:線性彈性便宜,但**分不清旋轉與拉伸**——元素純旋轉會被誤判成拉長 → 憑空生假力、膨脹。膜瓣對折、IOL 折疊都大幅旋轉,必崩。co-rotational 用便宜的線性成本換到「大旋轉不失真」。
- **怎麼運作**:每元素每步 → 抽出剛體旋轉 R → 用 R⁻¹ 轉回靜止方位(只剩真拉伸,線性才成立)→ 線性算力 → 用 R 把力轉回世界座標。座標框架跟著元素轉。
- **誰用**:Marchal 2009、Dequidt 2013(囊膜三角、水晶體四面體、IOL 殼全用)。

### 1.3 matrix-free(免組裝共軛梯度)
- **是什麼**:隱式求解時,全域剛度矩陣 K **從不成形**,用迭代 CG 只算 `K·v`。
- **解決什麼(用途)**:隱式直接解要把 K 分解(O(N³)),而**撕裂/移除元素一直改拓樸 → 分解失效 → 重分解 → 死**。matrix-free 讓拓樸改變幾乎零成本。
- **怎麼運作**:CG 只需 `K·v`,而 `K·v = Σ_e (Ke·v_e)` **逐元素即時算**(co-rotational)、加總。撕裂改拓樸 = 只增刪 loop 裡的元素,**不重組、不重分解**。Marchal 原文:「因為會撕裂改拓樸,所以不做矩陣組裝,用專用 CG 解」。
- **誰用**:Marchal 2009、Dequidt 2013(GPU-CG)。

### 1.4 scatter→gather(GPU 力累加,Comas 專屬)
- **是什麼**:GPU 上把「元素力累加到共用節點」改成兩階段。
- **解決什麼(用途)**:多個元素 thread 同時寫同一節點 = 寫衝突(race);CUDA 不管衝突、加 atomic 嚴重拖慢。
- **怎麼運作**:**兩個 kernel**——Kernel1(每 thread=元素)算力貢獻、寫**各自獨佔格子**;Kernel2(每 thread=節點)**讀回鄰元素貢獻 gather 加總**。共用只發生在讀,寫各自私有 → 衝突消失。需 element→node 連結表。
- **誰用**:Comas 2008。

### 1.5 各向異性 visco-hyperelastic(Comas 材料)
- **是什麼**:橫向同性 + 超彈性 + 黏彈性材料(宣稱首個 GPU 實作)。
- **解決什麼(用途)**:比線性/co-rotational 更真的軟組織行為(大變形非線性 + 時間相依鬆弛 + 纖維方向)。TLED 顯式「應力直接由應變算、不組 K」→ 複雜本構才塞得進去。
- **怎麼運作**(符號因 PDF 抽取掉字,結構可靠、參數名 [推論]):
  ```
  Ψ_iso = (μ/2)(Ī₁−3) + (γ/2)(Ī₄−1)²    # 中性氏等容 + 纖維增強
  Ψ_vol = (κ/2)(J−1)²
    C̄ = J^(−2/3)FᵀF,  Ī₁=tr(C̄),  Ī₄=a·C̄a(纖維 a 耦合),  J=det F
  黏彈遞迴(不必存應變史):
    Qₙ = [2Δt/(Δt+τ)]·(∂Ψ_iso/∂C)ₙ + [τ/(Δt+τ)]·Qₙ₋₁
    Sₙ = 2(∂Ψ_iso/∂C)ₙ + 2(∂Ψ_vol/∂C)ₙ − Qₙ
  ```
  只等容項有黏彈;單一鬆弛支。
- **誰用**:Comas 2008。(Dequidt 反而用更簡單的 co-rotational 線彈性。)

### 1.6 非同步預條件子(Courtecuisse — 正名)
- **是什麼**:把 CG 的預條件子丟背景執行緒算、主迴圈用「稍過期」版本。
- **解決什麼(用途)**:CG 在**軟硬不均組織**(囊膜軟、核硬)收斂很慢 → 隱式又「慢回去」。好預條件子加速收斂但算它貴、拓樸一變又要重算。
- **怎麼運作**:背景執行緒做 LDLᵀ 分解當預條件子,主迴圈重複用稍舊版本(組織變形夠慢,稍舊仍好用)→ 隱式穩定 + 收斂快 + 即時。
- **誰用**:**Courtecuisse et al. 2010(Prog. Biophys. Mol. Biol.)及其後續**。⚠️ **不是 Dequidt 2013**——Dequidt 只引 Courtecuisse [14] 的 GPU-CG,本身沒描述非同步預條件子。引用時請歸給 Courtecuisse。
- **切割專門的成熟版(Courtecuisse et al. 2014, Medical Image Analysis)**:切割改拓樸 → K/M/C 改變 → 預條件子的 **LDLᵀ 分解與真實系統脫節** → 接觸/自碰撞不穩。解法 = **Sherman-Morrison 公式,只更新被切到的節點**(切割視為低秩擾動 N):
  ```
  P̃⁻¹ = P⁻¹ − P⁻¹Gᵀ (N⁻¹ + G P⁻¹ Gᵀ)⁻¹ G P⁻¹
  ```
  免整體重分解;GPU 上做稀疏三角解(兩層平行);新分解隱式吸收先前切割、免誤差累積。**這是 2010(非同步)→ 2014(切割增量更新)的成熟版**。→ 與 Dequidt 2013 的分工見 [`reference/3`](3_inria_fem_lineage.md)「2013 系統 vs 2014 方法」。

### 1.7 顯式 vs 隱式:何時用哪個(INRIA 的實際選擇)
- **顯式(TLED)**:便宜、逐節點平行、無線性解;但條件穩定(小 Δt)、對接觸力**較不穩**(Comas 明述)。用於「大量元素、純變形、要 GPU」。
- **隱式**:大 Δt、穩健、能處理接觸約束;但每步要解線性系統。用於「要接觸/觸覺/撕裂穩定」。
- **Dequidt 的混搭**:水晶體/囊膜用**隱式 + GPU-CG**(matrix-free);**IOL 例外用直接稀疏解**——因為 IOL **高剛度+低質量**,直接解較準較穩(較慢,見 §8)。

---

## 2. 怎麼建 MESH

**元素型別(Comas 貢獻)**:支援**四面體與六面體**。
- 四面體(4 節點)易 **volumetric locking**;**8 節點六面體(reduced integration)** 較準、**同 DOF 下元素數少很多** → 顯式每元素成本主導,總算量少。
- 六面體有 **hourglass 零能量模式**,加 Flanagan-Belytschko 控制(存額外每元素變數);GPU occupancy 8%(四面體 25%),但「元素少」勝出。

**Dequidt 三種 mesh**:
- 水晶體體 = **四面體 FEM,3000 顆**;前囊 = **三角 FEM 橫向同性**(demo 方形 1500 三角);IOL = **三角殼,743 三角/473 節點**(腳袢交界加密)。

**兩層網格(phaco)**:
```
1 粗四面體 ──1→8 tessellation──> 8 細四面體
  粗 = 力學(保效能)   細 = 渲染 + 器械/碰撞
  8 顆細元素全移除 → 粗四面體也移除(反映失去物質)
```
[推論] SOFA 對映 = `BarycentricMapping` + 動態 `TetrahedronSetTopologyContainer`。

**同心圓纖維初始化**:Dequidt 明述**每 0.5 mm 一圈同心**、逐三角給方向。逐三角公式 [推論]:中心 x_c、圓心 O,徑向 r=(x_c−O)/|·|,纖維 F=N×r(圓周切線⊥r),θ=F 對局部 x 軸夾角。

---

## 3. 模擬的物理機制

**Comas(TLED + visco-hyperelastic)**:每元素每步——變形梯度 F → 右 Cauchy-Green C 與第二 Piola-Kirchhoff S → strain-displacement → 元素節點力;每節點中央差分。材料見 §1.5。

**Dequidt(co-rotational 線彈性 + 隱式)**:全部從虎克定律經 co-rotational 得幾何非線性 + 隱式(dt=0.01s)。
- 水晶體剛度 **1 kPa(20 歲)→5 kPa(>60 歲)**(可依年齡調);IOL **E=1 MPa, ν=0.42, ρ=1.2 g/cm³**。
- 囊膜各向異性剛度矩陣(c=cosθ, s=sinθ;Marchal Eq.1 = Dequidt 同式):
```
K11 = c⁴E_F + s⁴E_T + 2c²s²(ν_T E_F + 2G_F)
K22 = s⁴E_F + c⁴E_T + 2c²s²(ν_T E_F + 2G_F)
K33 = c²s²(E_F+E_T−2ν_T E_F) + (c²−s²)²G_F
K12 = c²s²(E_F+E_T−4G_F) + (c⁴+s⁴)ν_T E_F
K13 = −cs[c²E_F − s²E_T − (c²−s²)(ν_T E_F+2G_F)]
K23 = −cs[s²E_F − c²E_T + (c²−s²)(ν_T E_F+2G_F)]
  G_F = E_F/(1+ν_F),  約束 ν_T/E_T = ν_F/E_F
```
= 旋轉後的正交異向平面應力本構矩陣直接當元素剛度;各向異性從 E_F(纖維強)vs E_T(橫向弱)進來。

---

## 4. 怎麼克服運算量

**路線 A(Comas,顯式)**:TLED 預算導數 + 集中質量(無解)+ scatter→gather 兩 kernel + texture 綁 **linear memory**(非結構化隨機存取最快)+ shared memory coalesced 搬出。**53.6× CPU、3× 舊 OpenGL**;3993–177957 DOF。**無絕對 FPS,且不做撕裂/接觸/觸覺**。

**路線 B(Marchal/Dequidt,隱式)**:**matrix-free**(K 從不成形,逐元素 `K·v`)+ **GPU-CG**(Courtecuisse 2010)+ **非同步預條件子**(§1.6,Courtecuisse)。撕裂/移除只改元素清單,免重組/重分解。

⚠️ **效能真相(修正「INRIA 慢」誤讀)**——全在 2.4 GHz + 一般顯卡:

| 步驟 | FPS | 解法 |
|---|---|---|
| **水晶體 phaco(3000 tetra)** | **80 fps** | 隱式 + GPU-CG |
| 囊膜撕囊(1500 tri demo) | 即時(未給 fps) | matrix-free CG |
| **IOL 完整** | **~5 fps** | **直接稀疏解**(非 CG) |
| IOL 僅變形 | ~10 fps | 直接稀疏解 |

> 「~5 fps」**只是 IOL 那步**(高剛度低質量、刻意用直接解換準與穩)。**撕囊與 phaco 其實很快(phaco 80 fps)。**

---

## 5. 怎麼處理撕裂

**準則(Marchal Eq.3–6,Dequidt 沿用)**:對裂尖每個候選方向 d 算分數,`c>1` 就撕,取 argmax。
```
c(d,σ,f,p) = σ_{d⊥} / σ̄_{d⊥} · H((d·p) − cosθ_P),   d⊥ = d×n            (Eq.4)
σ_u = cos²θ_u·σx + sin²θ_u·σy + 2 sinθ_u cosθ_u·τxy                        (Eq.5, Mohr 投影)
σ̄_u = σ̄_T + (σ̄_F − σ̄_T)·[1 − (2/π)·acos(|u·f|)]^α                        (Eq.6, 方向強度內插)
d_fracture = argmax_d c
```
- **σ_{d⊥}**:垂直撕痕的張應力(撐開裂縫的 Mode-I 分量,不是沿 d 的力)。
- **σ̄_{d⊥}**:方向強度,u∥f→σ̄_F(纖維強)、u⊥f→σ̄_T(橫向弱),α 控陡度。
- **H((d·p)−cosθ_P)**:只允許與上一步 p 夾角 ≤ θ_P 的候選(防回折);p 消歧(應力/纖維無方向性)。
- **等向退化**:σ̄_F=σ̄_T 且角限 90° → argmax σ_{d⊥} = 應力張量特徵分解、垂直最大主應力裂 = **經典最大主應力準則**(Marchal 明證)。

**何時/何處**:裂尖或潛在裂元素中心;粗網格單元素應力不準 → **鄰域加權平均**平滑;**不做 substepping**(大 Δt 下取 argmax)。
**remesh(每步)**:沿既有邊(便宜、mesh-dependent)或任意方向切分(mesh-independent,**須避免退化細三角形**否則病態,引 Federl)。matrix-free 讓拓樸改變免重組。

⚠️ **修正**:Dequidt 正文用 **stress 張量特徵值**(intro 寫 "strain" 是鬆散);門檻**依外科醫師回饋調**。
⚠️ **phaco 的「移除」不是撕裂**——是直接刪四面體(40 kHz 探針建模成元素刪除)。

---

## 6. 怎麼模擬器械操作

⚠️ **沒有 kHz 力回饋觸覺裝置**。Dequidt 明確否決觸覺筆/機械臂(無法處理多器械、不像真器械)。互動全靠**紅外光學追蹤**:
- **6 台 IR 相機**(抗遮擋)、每器械 **4 反光標記**(標記簽章區分多器械)、OptiTrack 剛體追蹤、**VRPN** 傳輸、**雙電腦**(追蹤 PC + SOFA GPU PC)。
- 器械 = **尼龍快速原型複製品**(真金屬漫反射毀 IR 追蹤):phaco chopper、乳化手把、撕囊鑷。
- 文中 "haptics" 多指 **IOL 彈性腳袢**,非力回饋。

**Phaco**:抽吸(尖端球形體積把粒子加人工力拉向尖端)+ 乳化(移除四面體)+ **Projected Tetrahedra** GPU 體積渲染(算光沿深度衰減;移除物質→更多光透出 = 避免推太深穿破後囊的視覺線索)。

**IOL 置入(最複雜接觸)**:[校正] shell 模型是 **Dequidt 2013 §5 自家的** shell FEM(平面應力+彎曲能疊加、建在 co-rotational [Felippa] 上);原文未把它歸給「Comas 2010」,此處先前的歸屬存疑。
- **殼元素** = 平面應力(膜)能 + 彎曲能疊加 + co-rotational。彎曲用 **9 DOF 三次多項式板**:
```
uz = c1 + c2x + c3y + c4x² + c5xy + c6y² + c7x³ + c8xy² + c9y³           (Eq.5)
  9 DOF = 3 角點各(撓度+2 斜率); Ke = ∫ bᵀκb dV, b = D·C⁻¹
```
- **折疊**離線(固定鏡體、折腳袢、捲進注射器);**注射**含**自我碰撞 + 鏡片vs注射器 + 鏡片vs囊袋 + 摩擦**。
- **曲面碰撞巧思**:每三角**遞迴細分 1→4**、用**同一條三次形狀函數 Eq.5** 算新頂點撓度 → 曲面三角給平面碰撞器用。
- **接觸力回分配**:「反演殼 FEM 公式」把曲面法向力分配成 3 角節點各力+力矩。→ **三次形狀函數身兼三職:內部彎曲力、碰撞幾何、接觸力分配。**
- **摩擦接觸回應**:Saupin **contact-warping**(為 co-rotational 設計、含摩擦)。

---

## 7. 系統架構(SofaCUDA 元件對映)

SOFA 多模型:每物件拆成 **Behaviour / Collision / Collision-Response / Visual / Haptic Model**,用 **mapping** 連接;scene-graph 遍歷 = 模擬迴圈;換演算法 = 改 XML,不重編譯。Behaviour 內含 `DoF`(= MechanicalObject 狀態)、`Mass`、`ForceField`(內外力)、`Solver`(積分)。

**TLED 怎麼插進 SOFA**:寫一個新 `ForceField` C++ 類——`init()` 做預算並配置 GPU 記憶體/綁 texture;`Solver`(中央差分)請求算力時,ForceField **啟動 CUDA kernels**。CPU↔GPU 用 **page-locked(pinned)記憶體**傳(輸入互動位移、輸出反力)。

**[推論] Dequidt 系統的 SOFA 元件對映**(原文未點名類別):
```
MechanicalObject                     # 自由度
TetrahedronFEMForceField(co-rot)     # 水晶體
TriangleFEMForceField(transv-iso)    # 囊膜(+ 自訂纖維各向異性)
自訂 shell ForceField                # IOL(膜+彎曲三次板)
動態 Tetra/Triangle SetTopologyContainer + 修改器  # 撕裂/移除
自訂 FractureComponent               # argmax c 準則
CGLinearSolver(GPU, matrix-free)     # 隱式解(水晶體/囊膜)
直接稀疏 Solver                       # IOL(高剛度低質量)
FrictionContact + Saupin contact-warping  # 接觸+摩擦
Projected-Tetrahedra Visual          # phaco 體積渲染
BarycentricMapping                   # 粗↔細兩層網格
```
非 SOFA 工具:VRPN(追蹤傳輸)、NaturalPoint Tracking Tools(IR 剛體追蹤)。

---

## 8. 效能數字總表(全部原文明述)

| 量 | 值 |
|---|---|
| 水晶體 tetra | 3000 |
| 水晶體 phaco | **80 fps** @ dt=0.01s, 2.4 GHz |
| tessellation | 1 粗 → 8 細 tetra |
| phaco 探針頻率 | 40,000 cycles/s |
| 水晶體剛度 | 1 kPa(20 歲)→5 kPa(>60 歲) |
| 囊膜 demo 網 | 1500 三角 |
| 同心纖維間距 | 每 0.5 mm |
| IOL 網 | 743 三角/473 節點 |
| IOL E/ν/ρ | 1 MPa / 0.42 / 1.2 g/cm³ |
| IOL 完整/僅變形 | ~5 fps / ~10 fps(直接稀疏解) |
| Comas GPU 加速 | 53.6× CPU、3× OpenGL |
| Comas DOF 範圍 | 3993–177957 |
| IR 相機/標記 | 6 台 / 每器械 4 顆 |

---

## 9. 對 repo 舊敘述的 6 點修正(本篇已採正確版)

1. **非同步預條件子 ≠ Dequidt 2013**,是 Courtecuisse 2010/後續(§1.6)。
2. **「5 fps」只是 IOL 步(直接解)**;水晶體 phaco 其實 **80 fps** → 「INRIA 慢」是誤讀(§4、§8)。
3. **沒有 kHz 力回饋觸覺裝置**,是 IR 光學追蹤;"haptics" 多指 IOL 腳袢(§6)。
4. **Dequidt 撕裂用 stress 特徵值**(非 strain)(§5)。
5. **引擎不是單一**:Comas=TLED 顯式 GPU;Marchal/Dequidt=co-rotational 隱式 GPU-CG(§0)。
6. **Comas 也支援六面體**(reduced-integration + hourglass),非只四面體(§2)。

> 這些修正**已回填**到 `reference/3,4,5`、`ccc_method/4`、`compare_eyesi_vs_inria.html`(#2 效能、#3 器械無力回饋、#4 stress 特徵值、#5 兩套引擎、#6 六面體)。`engines/6` 的 TLED/co-rot 用途原本即正確,無需改。全 repo INRIA 敘述已一致。

## 來源
Comas et al. 2008 · Allard/Marchal/Cotin 2009 · Courtecuisse et al. 2010(PBMB,非同步預條件子/GPU-CG)· Courtecuisse/…/Dequidt 2013(本機 `papers/`)。相關:[`ccc_method/4`](../ccc_method/4_inria_fiber_fracture.md)、[`engines/6`](../engines/6_realtime_fem_pillars.md)、[`reference/3`](3_inria_fem_lineage.md)、[`reference/4`](4_inria_fem_realtime.md)、[`reference/5`](5_dequidt2013_vs_demo.md)。
