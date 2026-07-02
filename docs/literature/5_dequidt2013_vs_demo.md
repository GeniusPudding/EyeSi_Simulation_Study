# Dequidt 2013 完整系統細節 + 本專案 demo 差距分析

Dequidt/Courtecuisse 2013《Computer-Based Training System for Cataract Surgery》是 INRIA 路線的**集大成**
(見 [`12_inria_fem_lineage.md`](3_inria_fem_lineage.md))。本篇拆解其技術細節,並對照本 repo 的互動 demo,
評估「教學級 Weber 路線 demo」離「SOTA 即時模擬器」還差多遠。

---

## 一、Dequidt 2013 系統細節

### 系統全貌
白內障三步驟完整即時訓練系統(撕囊 + phaco + IOL 置入):
- **囊膜 = 三角形 FEM**(幾何非線性);**水晶體 = 四面體 FEM**。
- 真實器械 replica + 即時追蹤 + 觸覺回饋。
- 效能:**完整模擬 ~5 FPS,僅變形 ~10 FPS**(2010 年代硬體;隱式積分求穩健)。

### 撕囊演算法(§4,最詳細)
1. **各向異性 FEM**:橫向同性,每三角形定義**纖維方向 θ**(囊膜用同心圓纖維);
   刚度矩陣 K11~K33 由 cosθ/sinθ、E_F/E_T 組成(= Allard 2009)。
2. **不組裝全域矩陣**:撕裂一直改拓樸,改用**共軛梯度迭代解**(省去重組 K)。
3. **撕裂判定**:每元素做**應變張量特徵值分解**,**最大特徵值 > 門檻 → 標記 "breakable"**
   (門檻依外科醫師回饋調);撕裂方向 = 該特徵值的**主應變方向(特徵向量)**。
4. **歷史方向**:撕痕傾向從已裂處延續 → 把**上一步撕裂位置與方向**納入當前方向計算(防回折)。
5. **每 time step 拓樸改變**:撕痕鄰域中應變超門檻的三角形被 **remesh(細分)**;
   唯一要求 = **避免過小三角形**(否則系統病態)。
6. **隱式積分**保證變形穩健。

### Phaco
- **Projected Tetrahedra** 體積渲染;移除組織 = **移除四面體**;
- 粗四面體的 8 個細元素都移除時,粗四面體也移除(力學上反映失去的水晶體物質)。

### IOL 置入(用 Comas 2010 Shell Model)
- 複雜接觸:鏡片自我碰撞 + 鏡片vs注射器 + 鏡片vs囊袋;脚袢折疊處高應力;
- 接觸含**摩擦**(鏡片與組織沾黏);
- **殼元素曲面碰撞偵測**(細分法算曲面,非平面三角形)。

---

## 二、本專案 demo 現況

`docs/demo_remesh_attached.html`(Canvas 2D)實作 **Weber 2006 路線**:

| 組件 | demo 實作 |
|---|---|
| Layer A 變形 | **PBD / 速度 Verlet** + 整片往鑷子折皺 |
| Layer B 撕裂 | **Weber §3.1 角度規則**:CurrDir 被 PullDir + DriftDir 旋轉 |
| shearing/ripping | ✅ 依拉力與撕痕夾角自動切換 |
| 撕痕切斷 / 整片脫離 | ✅ severed edge set + point-in-polygon |
| remesh | ✅ **Delaunay flip + split + collapse**(inCircle 判定) |
| Attached 旗標 | ✅ freed/dead 節點 |

→ demo 已**完整實現 Weber 2006 兩層解耦 + Delaunay remesh**,是扎實的教學級撕囊模擬。

---

## 三、差距分析(demo → Dequidt 2013)

| 面向 | demo | Dequidt 2013 | 差距 |
|---|---|---|---|
| 變形引擎 | PBD/Verlet(描述式,位置約束) | **幾何非線性 FEM(應力/應變)** | 🔴 大 |
| 撕裂判定 | 角度規則(幾何) | **應變特徵值 > 門檻(物理)** | 🔴 大 |
| 各向異性 | DriftDir(手調漂移) | **纖維方向 + 各向異性剛度矩陣** | 🟡 中 |
| 維度 | 2D 平面圓盤 | **3D**(囊膜三角 + 水晶體四面體) | 🔴 大 |
| remesh | ✅ Delaunay flip/split/collapse | ✅ 應變觸發局部細分 | 🟢 接近 |
| 歷史方向防回折 | 部分(curr 延續) | ✅ 明確納入 | 🟢 接近 |
| 觸覺/接觸 | ❌ | ✅ 摩擦接觸 + 觸覺 | 🔴 大 |
| 完整術式 | 只有撕囊 | 撕囊 + phaco + IOL | 🔴 大 |

---

## 四、要不要追平?

**取決於目標:**
- demo 目前是**教學 / 概念驗證**——理解撕囊力學已足夠,**不需 3D FEM**。
- Dequidt 是「即時訓練模擬器」等級,追平 = 3D + FEM + 觸覺 + 完整術式,屬博士級工程。

**建議**:
1. demo **已完成它該做的事**(教學級 Weber 撕囊),不必手刻 3D FEM 去追 Dequidt。
2. 若要「物理更真」,**正確做法是直接用 SOFA**(Dequidt 系統就建在 SOFA 上),而非手刻 FEM。
3. 若想讓 demo 更物理但保持輕量,**最高投報率的單步升級 = 撕裂判定「角度規則 → 應變門檻」**
   (仍可在 2D 做,把撕裂從幾何規則變成物理準則),其次是**同心圓纖維各向異性**取代手調 drift。

## 升級路徑(可選,按投報率)
```
1. 撕裂判定:角度規則 → 應變張量特徵值門檻   (2D 可做,撕裂物理化)★最值得
2. 加纖維各向異性(同心圓)→ 撕痕自然沿圓,取代手調 drift
3. 2D → 3D(three.js,工程量大)
4. PBD → FEM(最大工程,通常直接改用 SOFA)
```

## 來源
- Courtecuisse, Allard, Kerfriden, Bordas, Cotin, Duriez 2013, *Computer-based training system for cataract surgery*(HAL hal-00855821,本機 papers/Dequidt_2013_INRIA_CataractTrainingSystem.pdf)。
- 相關:Comas 2008(GPU FEM)、Allard 2009(纖維斷裂)、Comas 2010(Shell/IOL)—見 [`12_inria_fem_lineage.md`](3_inria_fem_lineage.md)。
