# FEM 如何變即時:TLED / co-rotational / matrix-free(速查)

FEM 準但即時用不了(見 [`engines/4 FEM`](4_fem.md)、[`engines/5 引擎對照`](5_comparison.md));INRIA 用三支柱把它救回即時。
本篇講清楚每支柱**解什麼、怎麼解**,並詳解相關物理概念:**節點自由度(DOF)、大旋轉為何失真、各向異性、matrix-free 是否還在解 KU=F**。
> **更深的機制細節**(旋轉假象 θ=90°→−100% 算例、非線性 FEM+Newton、CG 每步做什麼、如何抽旋轉 R):見 [`7_fem_deep_dive.md`](7_fem_deep_dive.md)。論文脈絡見 [`../reference/4_inria_fem_realtime.md`](../reference/4_inria_fem_realtime.md)、INRIA 整合正本見 [`../reference/8_inria_implementation_deepread.md`](../reference/8_inria_implementation_deepread.md)。

---

## 0. 地基:為何 E/ν 是真物理量、k 不是

- **FEM 的 E、ν**:材料性質,拉伸測試可量、與網格無關;細分網格會**收斂到連續體彈性 PDE 的真解**。
- **mass-spring 的 k**:沒有儀器可量、**隨網格而變**、不收斂到任何理論——是**手調旋鈕**,不是材料常數。

> 類比:FEM 像用 g=9.8(量得到)算落體;mass-spring 像對軌跡**硬擬合多項式**——擬得漂亮,但係數不對應任何可量的東西。
> 「k 不是真物理量」= 無可量測的材料對應物、且與網格糾纏(不是「假」)。多軸引擎對照見 [`5_comparison.md`](5_comparison.md)。

---

## 0.5 前置:節點自由度(DOF)—— KU=F 的 U 到底是什麼

**自由度(Degree of Freedom, DOF)= 一個節點「能獨立變動的數字」= 你要解的未知數。**
- 3D 軟組織節點:**3 個 DOF** = 位移的 (x, y, z)。N 個節點 → 共 **3N 個 DOF**;`KU=F` 的 **U 就是把全部節點的 DOF 疊成一個長 3N 的向量**,K 是 (3N)×(3N) 的矩陣。
- 2D 膜節點:2 個 DOF;殼/樑節點可到 6 個(3 平移 + 3 轉動)——例如 IOL 殼「每三角 9 DOF = 3 角點各(撓度 + 2 斜率)」,那些斜率就是**轉動 DOF**。

> 一句話:DOF = 「這節點能怎麼動」的獨立數目 = 求解的未知數。**解變形 = 解出每個 DOF 的值**;所有解法(顯式/隱式/matrix-free)都是在求這些 DOF。

---

## 1. TLED — 讓 FEM 顯式又便宜

**TLED = Total Lagrangian + Explicit Dynamics**,兩字各解一半:

- **Explicit(顯式)**:中央差分逐節點推進 `x(t+Δt) = 2x(t) − x(t−Δt) + (Δt²/mᵢ)·Fᵢ`,各節點獨立 → **GPU 平行**。骨架同 mass-spring,只差 F 用真應變場算。代價是小 Δt,但軟組織剛度低 → 臨界 Δt 大 → 不痛。
- **Total Lagrangian**:一切相對**永不變的原始構型**(t=0)算 → 形狀函數導數成**常數,預算一次、每步查表**(對比 Updated Lagrangian 每步重算)。註:此「Lagrangian」是連續體的**材料描述**,非 L=T−V。

---

## 2. co-rotational — 各向異性 + 大旋轉不失真

**問題**:線性彈性用線性(小)應變 `ε=½(∇u+∇uᵀ)`,**分不清旋轉與拉伸**——元素純剛體旋轉會被誤判成拉長 → 憑空生假力、膨脹(膜瓣對折、IOL 折疊即中招)。
**co-rotational = 便宜的修法**:每元素抽出剛體旋轉 R → 用 R⁻¹ 轉回靜止方位(只剩真拉伸,線性才成立)→ 線性算力 → 用 R 把力轉回。= 線性速度 + 大旋轉不失真。
**各向異性(anisotropic)** = 材料強度/剛度隨方向不同(纖維增強:順纖維強、橫向弱)。「co-rotational 各向異性 FEM」= co-rot 骨架裡,線性算力用「橫向同性纖維剛度矩陣」(K11–K33,見 [`../ccc_method/4_inria_fiber_fracture.md`](../ccc_method/4_inria_fiber_fracture.md))。co-rot 管大旋轉、各向異性管纖維方向 —— Allard/Dequidt 囊膜所用。

> **深入**(為何 ε 丟了二次項 → θ=90° 得 −100% 假應變的算例、如何用 polar 分解抽 R):見 [`7_fem_deep_dive.md`](7_fem_deep_dive.md) §C、§E。

---

## 3. matrix-free — 仍然解 KU=F,只是「不把矩陣組出來」

**澄清**:隱式每步**確實要解**一個 `KU=F` 型線性系統(精確說 `(M/Δt²+K)·Δu=殘差`)。matrix-free 不是跳過這個解,是換「不把矩陣存成實體」的解法。
- **直接解**:組裝 K → 分解(Cholesky/LU,O(N³))→ 回代。需要 K 實體。
- **迭代解(CG)**:反覆逼近,**每次只需 `K·v`,不需 K 本身**;而 `K·v = Σ_e (Ke·v_e)` 逐元素算 → **全域 K 從不成形**。

**為何對撕裂關鍵**:沒組 K、沒分解 → 撕裂改拓樸 = 只改「loop 哪些元素」,不必重組/重分解;直接解則分解作廢、重來(死)。顯式 TLED 更省(連線性系統都沒有)。異質組織 CG 收斂慢 → 非同步預條件子加速(見 [`../reference/3_inria_fem_lineage.md`](../reference/3_inria_fem_lineage.md))。

> 🔑 三層:顯式(TLED)= 不解方程;隱式直接解 = 解但要組+分解 K;隱式 matrix-free CG = 照樣解 KU=F 但 K 永不成形。
> **深入**(CG 每次迭代具體做什麼、碗形二次函數直覺):見 [`7_fem_deep_dive.md`](7_fem_deep_dive.md) §F。

---

## 4. 三支柱合作

| 支柱 | 解的問題 | 一句話 |
|---|---|---|
| **TLED** | FEM 太慢 + 導數每步重算 | 顯式(GPU)+ 總拉格朗日(導數預算) |
| **co-rotational** | 線性彈性大旋轉失真 | 扣旋轉 → 線性算 → 轉回 |
| **matrix-free** | 撕裂改拓樸讓分解失效 | 迭代 CG + 逐元素 K·v,K 不成形 |

⚠️ **重要:三支柱不是疊在同一顆 FEM 裡,而是分屬「兩套引擎」**——TLED 與 co-rotational 是**處理大旋轉的兩種替代做法**,不會同時用:
- **Comas 引擎 = TLED**(Total Lagrangian 顯式):用**非線性應變 F/C/S** 直接處理大旋轉,**不需要 co-rotational**;顯式所以**不解方程**(無 matrix-free 需求)。
- **Dequidt 引擎 = co-rotational + 隱式 + matrix-free CG**:用**扣旋轉**處理大旋轉,隱式所以要解方程 → matrix-free CG 上場。**不用 TLED**。

> 所以一顆 FEM 計算裡,你在「TLED 非線性應變」**或**「co-rotational 扣旋轉」擇一;matrix-free CG 只跟隱式(co-rot 那套)配。它們「合體」是在**系統層**——同一 SOFA 場景裡不同物件可掛不同引擎。深入見 [`../reference/8_inria_implementation_deepread.md`](../reference/8_inria_implementation_deepread.md) §0。
