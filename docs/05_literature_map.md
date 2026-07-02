# 05 — 文獻地圖:演進、Weber 2006 引用、INRIA FEM 路線、現代 AI

## 1. 演進線(technical lineage)
```
Gimbel&Neuhann 1990 發明 CCC   ·   Seibel《Phacodynamics》shearing/ripping
        │
Gibson 1997 ChainMail → Schill 2001 ECM(EyeSi 引擎/vrmDesign)
        │
Webster 2004/2005  CCC 模擬開山(mass-spring + 描述式)→ 移植 EyeSi
        │
★ Weber, Wagner & Männer 2006  描述式撕裂 + mass-spring + Delaunay(= 本 repo demo)
        ├─ Weber 2009 博論      同作者升級:描述式 → 物理式(應變/應力)        [見 04]
        ├─ INRIA 物理路線       Comas08 → Allard09(纖維斷裂)→ Dequidt13(SOFA-FEM 系統)
        ├─ 離線 FEM 力學        2020 IOL 偏位 / 2021 裂縫豬眼驗證
        └─ AI / 自主手術        Peter 2024 ICRA(FEM 撕裂 + RL);影片分析 2023–26
方法演進:mass-spring→PBD/ECM(即時);Delaunay 重網格→XFEM(免重網格);離線非線性 FEM 斷裂(最準)
```

## 2. Weber 2006 引用地圖(誰引用、屬哪種延伸)
- **直接方法延伸**:**Weber 2009**(唯一「直接改進其方法」;描述式→物理式,無英文版,PDF 在 `papers/`)、**Allard/Marchal/Cotin 2009**(纖維斷裂,物理對照)、**Dequidt/Courtecuisse/Comas 2013**(SOFA-FEM 系統)、**Duriez 2013**(SOFA haptic habilitation)、**Peter et al. 2024 ICRA**(FEM 撕裂 + RL,KIT)。
- **綜述(脈絡)**:Lam, Sundaraj, Sulaiman(2013×2, 2014)。
- **同家族撕裂**:Le Gouis/Marchal 2017(FEM 撕裂 + haptic)。
- **離線 FEM 力學**:2021《FE lens capsule tearing》(四層晶體 + 內聚裂縫,豬眼驗證)、2020《IOL decentering》。
> **結論**:引用者中**唯一直接改進 Weber 方法的是 Weber 2009 自己**;其餘走別的典範(FEM / RL)。

## 3. INRIA 物理路線(三篇分工)
| 看什麼 | 貢獻 | 提供 |
|---|---|---|
| **撕囊怎麼撕** | **Allard 2009** | 纖維各向異性 + `argmax c` 撕裂準則 + remesh |
| **怎麼即時** | **Comas 2008** | SofaCUDA 上的 **GPU TLED FEM** 引擎 |
| **完整系統** | **Dequidt 2013** | 撕囊+phaco+IOL + 接觸/觸覺 + 兩層網格 |

### 纖維斷裂準則為何對(`c = (σ_{d⊥}/σ̄_{d⊥})·H((d·p)−cosθ_P)`,c>1 即撕)
1. **撕痕往周邊 = 纖維的物理必然**:囊膜纖維呈**同心圓**(每三角形纖維 = 該點到圓心連線的**垂直方向/圓周切線**,建網時指定)→ 徑向弱、圓周強 → 徑向最省力 → **drift 自己湧現**(Weber 是手調 drift 模仿現象;Allard 把因果建進材料)。
2. **每塊都是標準斷裂力學**:σ_{d⊥}=撐開裂縫的垂直張力;÷σ̄=負載/強度(各向異性在此進來,徑向易 >1);H(·)=防回折(裂縫平滑);argmax=最脆弱方向先裂。
3. **等向時退化成「最大主應力準則」**(公認脆性斷裂判據)→ 不是新 heuristic,是其**各向異性升級版**。

### 為何 FEM 能即時(對照「FEM 太慢」)
不是完整非線性 FEM;而是 **TLED(Total Lagrangian Explicit Dynamics,相對原始構型、免每步重組剛度)+ co-rotational(去除大旋轉的幻影力)+ matrix-free 顯式 + GPU(SofaCUDA)**。撕裂改拓樸時,顯式/TLED 比隱式好(隱式的預算矩陣會失效)。

### Dequidt 2013 vs 本 demo(差距)
Dequidt:3D 四面體 FEM、纖維斷裂物理判定、GPU、力回饋、ERM/晶體兩層網格。本 demo:2D 描述式、無觸覺、無真 FEM。升級路徑見 [`02 §4`](02_ccc_tearing_method.md)。

### SOFA 對 FEM 領域的意義:標準化了「怎麼組裝物理模擬」
SOFA 之前每個手術模擬(如 Schill 的 vrmDesign)都私有地把 FEM+碰撞+觸覺+求解硬寫在一起,不可重用。
SOFA 把「物理模擬」拆成**正交、可互換的標準組件**(之於即時 FEM ≈ ROS 之於機器人)。標準化了 4 件事:
1. **組件化場景圖**:狀態 `MechanicalObject`、幾何 `Topology`、力 `ForceField`、時間 `Solver`、線性 `LinearSolver`、互動 `Constraint/Collision` 各為插槽 → **換 ForceField(FEM↔mass-spring)其餘不動** → 研究者發表新組件即可 drop 進所有人管線(可累積、可比較)。
2. **Mapping(多模型)**:把位置從父層(粗力學網格)傳到子層(細視覺/碰撞網格),用 Jacobian 轉置把力傳回 → **標準化「粗力學+細視覺」多分辨率**(= Dequidt 兩層網格)。
3. **統一約束**:接觸/觸覺/抓取用 Lagrange 乘子統一處理,與變形模型解耦。
4. **GPU 模板容器**:組件加 `Cuda` 模板即可跑 GPU(Comas 2008 的 GPU FEM 就這樣進 SOFA)。

> 意義:讓即時 FEM 從「私有重造」變「開源可累積」——INRIA 那條線(Comas→Allard→Courtecuisse→Dequidt)**能接力,正因每篇都是一個 SOFA 組件可組合**。

### 基於 SOFA 開發 CCC 撕囊:只需自寫 2 個組件,其餘用現成插槽
```
Node "capsule"
├─ EulerImplicit + CGLinearSolver(+預條件子)     ← 現成(求解)
├─ MechanicalObject                               ← 現成(節點自由度)
├─ TriangleSetTopology(動態)                     ← 現成(幾何,撕裂要它可變)
├─ CudaTriangleFEMForceField(method="large")     ← 現成 = Comas 2008 引擎(co-rotational GPU FEM)
├─ ★FiberAnisotropy   (自寫)                      ← 每三角形 θ=同心圓切線 + σ̄_F/σ̄_T
├─ ★FractureController(自寫)                      ← 每步讀應力→argmax c→標記 breakable→觸發 remesh
├─ TopologyModifier(split/flip)                  ← 半現成(SofaCarving/topology 為基礎)
└─ Collision + Mapping(鑷子拉、立體繪圖)         ← 現成(統一約束+多模型)
```
**開發流程**:① 拿內建 FEM 薄膜範例(現成能跑)→ ② ForceField 換 CudaFEM(即時)→ ③ 加 FiberAnisotropy → ④ 加 FractureController → ⑤ 接 TopologyModifier 做 remesh → ⑥ 接器械 Constraint。

**自寫組件 1 — FiberAnisotropy**(囊膜專屬,通用 FEM 不含):
- `init()`:對每三角形算 `r = normalize(中心 − 圓心)`、`f = rotate90(r)`(圓周切線)、存 `θ` + 兩方向模量 `E_F/E_T`、強度 `σ̄_F/σ̄_T`。Total Lagrangian → 只算一次。
- 提供給 FEM ForceField:各向異性剛度矩陣(把等向 D 換成含 θ 的橫向同性 D)。實作 = 擴充/包裝 `TriangleFEMForceField`,讓它每元素用自己的 θ 建 D。

**自寫組件 2 — FractureController**(Allard/Dequidt 的研究/商用碼,不在公開 SOFA):
- 每個 time step(在 solver 之後):
  1. 從 ForceField 讀各元素應力張量 σ(或應變特徵值);
  2. 對候選方向 d 算 `c=(σ_{d⊥}/σ̄_{d⊥})·H((d·p)−cosθ_P)`,`σ̄` 依 θ 內插(式6);
  3. `max c > 1` → 標記該元素 breakable,方向 = `argmax_d c`;
  4. 呼叫 `TriangleSetTopologyModifier`:沿方向 split 三角形(策略:網格夠細→沿邊;要精確圓→任意方向切,並避免退化三角形);
  5. 更新撕裂前緣、把掃過節點 `Attached: True→False`(=交給 mass-spring/自由節點,見 [`03`](03_implementation_demos.md))。
- 資料:每元素存「is_breakable、上一步方向 p、fracture tip」。應力用鄰域加權平均(粗網格下單元素應力不準)。

> 🔑 **標準化的回報**:變形/求解/幾何改變/器械互動都是 SOFA 標準插槽,你**只寫 CCC 特有的「纖維 + argmax c 撕裂」兩塊**。沒有 SOFA 就得五樣全自己寫(= 回 Schill 時代)。

## 4. 現代 AI 撕囊(2023–26,不同典範:分析而非模擬)
影片分析 / 技能評估 / 自主手術方向:**Cataract-LMM**、Meta Surgery、meta-analysis 等資料集與模型;**Peter 2024 ICRA** 把 FEM 撕裂模擬當環境訓練 **RL**,是「物理模擬 → AI」的橋。缺口:標註、即時性、真實器械資料。

> 詳細論文出處見 [`references.md`](references.md)。
