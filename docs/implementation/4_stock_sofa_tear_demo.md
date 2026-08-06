# Stock-SOFA 撕裂 demo:機制、實測能耐、模型極限 vs EyeSi/INRIA

對應檔案:
- [`Capsulorhexis/scenes/cap_tear.py`](../../Capsulorhexis/scenes/cap_tear.py) — 主場景(彎曲囊膜 on 水晶體,滑鼠撕裂)
- [`Capsulorhexis/scenes/tear_stress.py`](../../Capsulorhexis/scenes/tear_stress.py) — 平面驗證台(同機制,先在平片上做對)
- 啟動:`./Capsulorhexis/scenes/run_cap.ps1`(預設就是 `cap_tear.py`;`-Scene cap_membrane.py` 才是舊的黏著剝離場景)

這份記錄**本 repo 用純 stock SOFA(免自編 dll)做出來的撕裂 demo**:它的機制、實測做得到什麼、
以及**做不到什麼、為什麼**——並對照 EyeSi(Weber)與 INRIA 兩條論文路線。定位是「實作經驗 +
模型極限」的收尾;論文機制正本仍在 [`ccc_method/3 Weber2009`](../ccc_method/3_weber2009_physical.md)、
[`ccc_method/4 INRIA 纖維斷裂`](../ccc_method/4_inria_fiber_fracture.md)、[`reference/8`](../reference/8_inria_implementation_deepread.md),本檔不重述、只指向。

> 慣例:凡「論文怎麼做」一律標 **[推論]**(依 repo 既有整理與記憶,未逐條回原文核對);凡「本 demo 怎麼做」
> 皆可回上面的程式碼行號查證。撕裂**判據是應力(stress)特徵值、非應變**,與 EyeSi 一致(見 CLAUDE.md 校正紀錄)。

---

## 1. 機制:三件事

一句話:**彈性薄膜 + 沿網格邊的離散裂縫,用主應力門檻觸發、沿 ⊥σ₁ 前進**。

### (a) 力學(純彈性)
- `TriangularFEMForceField method="large"`(線性共旋膜)+ `MeshSpringForceField`(每條邊一個線彈簧,抗伸長)
  + `TriangularBendingSprings`(抗彎)+ `DiagonalMass` + `UniformVelocityDampingForceField`。
- 幾何來自 [`generate_cap.py`](../../Capsulorhexis/scenes/generate_cap.py) 的扁橢球(oblate,A=7、C=1.5),
  囊膜是貼合其上緣的圓弧片;`EllipsoidForceField` 當水晶體的**解析障礙**(正剛度=向外推),外緣以
  `FixedProjectiveConstraint` 固定(懸韌帶錨,anatomical zonule)。
- **關鍵性質:純彈性**——放手就彈回原狀(§5 會說明這是最大的限制根源)。

### (b) 裂縫幾何:runtime 頂點分裂
裂縫是一條頂點路徑 `self.crack = [..., prev, tip]`,只有 `tip` 還連著。前進 = 把 `tip` 的三角形扇面
沿兩條裂邊(往 `prev`、往選定的 `next`)剖成兩片唇,一片保留原頂點、另一片改接一個**預留備用頂點**
(`_split_tip`,`cap_tear.py`)。備用點池在建網格時就配好(park 在網格內,避免撐大 bbox);分裂後
`fem/springs/mass.reinit()` 讓力學元件吃到新拓樸,並把新三角形清單**推給 OglModel**(否則畫面那層皮
不會跟著開)。

> 裂縫**只能沿現有網格邊**一格一格走 —— 這是與 INRIA「沿任意路徑重網格」最本質的差別(§5.2)。

### (c) 判據:σ₁ 門檻 + ⊥σ₁ 方向(Rankine)
每 `TEAR_CHECK_DT` 檢查一次(`onAnimateBeginEvent` / `_advance_once`):

```
每個三角形:F = Ds·Dm⁻¹              (Dm=靜止邊框, Ds=當前邊框, 逐三角形防呆 2×2 逆)
           ε = ½(FᵀF − I)          (Green 應變, 平面)
           σ = C:ε                 (平面應力, C = E/(1−ν²) 的各向同性矩陣)
           σ₁ = ½(σxx+σyy) + √(((σxx−σyy)/2)² + σxy²)   (主應力)
裂尖判定:  khot = argmax σ₁ (碰到 tip 的三角形中最燙的那個)
           若 σ₁(khot)·TIP_STRESS_GAIN < STRESS_THRESHOLD → 不前進(只是繃緊)
           否則 perp = normalize(n × σ₁方向)             (⊥σ₁, 落在裂尖切平面內)
                next = 與 perp 最對齊、且在環帶內的鄰居頂點(強制往前)
                _split_tip(tip, prev, next)
```

- **σ₁ 由幾何(靜止 vs 當前)算出**,與哪個元件在施力無關 → 判據不綁定特定力學模型。
- **⊥σ₁ 用裂尖的局部法線 `n`**(非寫死 z 軸),裂縫才會貼著彎曲的膜面走。
- **路徑不寫死**:同一條規則,平片均勻拉 → 直線;彎膜放射狀拉 → σ₁ 指向半徑 → ⊥σ₁ 是圓周 → **裂縫自然彎成圓**。

#### ⚠️ 已修正的 bug:主應力**方向**曾有一半是錯的(2026-07-23)

`cap_membrane.py` 的 `principal_stress()` 原本這樣算主應力方向:

```python
ang = 0.5 * np.arctan2(2*σxy, np.maximum(σxx − σyy, 1e-12))   # ← 錯
                               ~~~~~~~~~~~~~~~~~~~~~~~~~~~
```

`arctan2(y, x)` **靠 x 的正負號決定象限**。那個 `np.maximum(..., 1e-12)` 把分母**強制變正**,正好抹掉它唯一需要的資訊 —— 凡是 **σyy > σxx**(分母本該為負)的狀態,象限全錯。

而且該保護**根本不必要**:`arctan2` 是雙參數函式、**不做除法**,`x=0`(甚至 `x=y=0`)它自己就處理得正確。

**對照解析解的實測**:

| 應力狀態 | 解析解 | 正確式 | 舊程式碼 | 誤差 |
|---|---|---|---|---|
| 單軸拉伸沿 x | 0° | 0° | 0° | ✅ |
| **單軸拉伸沿 y** | 90° | 90° | **0°** | **90°** |
| 純剪切 | 45° | 45° | 45° | ✅ |
| σxx=0, σyy=2, σxy=1 | 67.5° | 67.5° | **45°** | **22.5°** |

端到端驗證(檢查「沿回傳方向的正向應力是否等於 σ₁」,20000 個隨機應力狀態):
**修正前 9990/20000 = 50.0% 錯誤;修正後 0/20000。** 隨機狀態恰有一半滿足 σxx < σyy,全數受害。

**為何這件事很嚴重**:Rankine 準則是「裂縫**垂直於** σ₁」。方向錯 90° → 裂縫方向**完全相反** → log 裡的
`crack CIRCUMFERENTIAL (good, curvilinear)` 與 `crack RADIAL (runs to the periphery!)` **會互換**。
那正是撕囊訓練最關心的指標(Argentinian-flag 逃逸),也是 `Capsulorhexis` plugin 的 argmax-c 準則
將來要吃的輸入 —— **用錯誤的方向做撕裂決策,會系統性地誤判**。

**修正**:移除該保護,`ang = 0.5 * np.arctan2(2*σxy, σxx − σyy)`。

**影響範圍**:此角度**只用於診斷輸出**(`sigma1_vs_radial` 分類、應力著色),**不回饋到力的計算**,
所以修正不改變任何動力學/手感;σ₁ 的**大小**(`½(σxx+σyy) + √(…)`)一直是正確的,錯的只有**方向**。

> **教訓**:對「除以零」的反射式防護,套在 `arctan2` 這種**不做除法**的函式上,會把正確性一起防掉。
> 診斷指標本身出錯最危險 —— 它不會讓模擬崩潰,只會讓你**根據錯的數字做判斷**。

---

## 2. 工程細節(得來不易的穩定性與收尾)

這些不是論文機制,是把上面三件事做成「不會崩、看得到」的必要防護,列成表備查(皆在 `cap_tear.py`):

| 機制 | 參數 | 為什麼 |
|---|---|---|
| **環帶約束** | `TEAR_R_MIN=3.0`、`TEAR_R_MAX=6.0` | 裂縫若捲進中央**極點**(自適應環收斂的奇異點),分裂會生退化細三角形 → FEM `Null determinant` → inf 爆掉。限制在 r∈[3,6] 環帶內;撕囊本來就是 r≈5 的環,路徑仍在環內自由湧現。 |
| **面積夾限** | `AREA_MIN_FRAC=0.30` | 三角形被拉到面積<30% 靜止面積(純剪切/翻面,邊長夾限抓不到)→ FEM 除以零。把過小三角形繞質心撐回去。實測:9000 力的暴力猛拉仍維持有限值。 |
| **回滾安全網** | `last_good_pos` | FEM 內部若仍炸出 inf(在夾限之前),下一步偵測到非有限值就**回滾上一個好狀態、速度歸零**。場景**再也不會永久消失**。 |
| **速度/應變夾限** | `MAX_SPEED=25`、`MAX_STRETCH=1.5` | 猛拉的大衝量、邊不得超過 1.5× 靜止長。 |
| **滑鼠力上限** | `MOUSE_STIFFNESS=250`(低) | 附著彈簧力 = 剛度 × 拖曳距離,**無上限**;高剛度把游標拖出畫面 = 巨大衝量 → 塌陷。壓低剛度封住遠拖的力。 |
| **裂尖應力集中** | `TIP_STRESS_GAIN=2.0` | 真實裂尖有應力奇異點,粗網格會低估 → 乘一個集中係數,手拉才拉得動(§5.3)。 |
| **起始缺口(穿囊針)** | `PRE_TEAR_DEG=100` | 開場沿圓周幾何預撕約 100°,給一片可抓的瓣(對應臨床:穿囊針先刺切口)。內部種子(非外緣),否則裂尖被固定住、σ₁ 到不了門檻(§5.3)。 |
| **圓片掀起** | `LIFT_AFTER_CRACKLEN=75`、`DISC_LIFT_Z=14` | 撕過 ~3/4 圈後,開向上浮力(泡在玻璃體中)把已近乎切下的中央圓片掀起、露出圓洞。**只在大撕之後才啟動**,不會一開始自撕。 |

---

## 3. 實測:做得到什麼(皆有數據)

- **裂縫從應力場湧現、彎成圓**:彎膜放射狀加載下,裂尖半徑維持 r≈5.4–6.4,角度單調掃過
  176°→−31°(約 **207° 圓弧**),裂口開到 ~0.9。沒有任何程式碼畫圓。
- **同規則、換加載 → 換路徑**:對稱加載裂縫半徑 spread=0.4(圓);不對稱(往側邊拉)spread=3.6(跟著拉走)。
  證明「固定半徑」是加載對稱性的結果,不是寫死。
- **一次撕一段**:`MAX_ADVANCE_PER_CHECK=6`,拉力夠時一次前進多格,像「撕」而非一格一格跳。
- **圓片掀起露洞**:撕過 75 格後浮力把圓片從 z=1.5 掀到 **z=7.5**,呈現「撕囊完成、露出圓洞」。
- **不會崩**:暴力猛拉(9000 力)全程維持有限值(面積夾限 + 回滾)。

---

## 4. 診斷工具:`[Pull]` log

`onAnimateBeginEvent` 內建拉動診斷,拉的時候印出:裂尖 σ₁(判據實際看的值)、全場最大 σ₁ 在哪、
你拉的點在哪 + **離裂尖多遠**。這條 log 直接揭示了核心難點(見 §5.3):

```
[Pull] tipSigma1=10 (x2.0=20 vs thr 10) tip@r5.1,-37d | maxSigma1=137@r4.2,-11d | youPull@r4.1,-17d dist-to-tip=1.9
```
你拉的地方 σ₁=137,但傳到 1.9 之外的裂尖只剩 10 —— **判據沒錯,是力傳不到裂尖**。

### 4.1 `cap_membrane.py` 的即時應力觀測器 + 熱圖

`cap_membrane.py` 的 `principal_stress()` 是一個**幾何觀測器**:每 `STRESS_EVERY` 步,從
靜止 vs 當前幾何算 F → Green 應變 ε = ½(FᵀF−I) → 平面應力 σ = C(E,ν):ε → σ₁ 與方向。
它**只讀不施力**,和用 FEM 或 mass-spring 無關(ε 純幾何)。

**觀測器 = FEM 真實應力(小應變下)**:FEM 內部也是用同一個 F、同一條 σ=C:ε 產生力,唯一
自由參數是 E、ν。所以 `_stress_material()` 讓觀測器在 FEM 模式**直接讀 FEM 的 live
`youngModulus`/`poissonRatio`**(會跟著 cloth→paper 在 SWITCH_T 的 ramp 走),回報的 σ₁
就等於 FEM 實際施力用的應力(小應變精確;大應變因觀測器用 Green、FEM 用共旋線性而略有差異)。
mass-spring 模式沒有連續體 E,退回固定 `STRESS_E/STRESS_NU` —— 此時數值只是**幾何應變比例尺**,
但「哪裡受力最大」的空間分佈兩個模式一致。

**與 SOFA 原生 FEM 應力的交叉驗證**(可重現:[`verify_stress.py`](../../Capsulorhexis/scenes/verify_stress.py),
`py -3.12 scenes/verify_stress.py`)。SOFA 的 `TriangularFEMForceFieldOptim` 有自己的主應力
(`computePrincipalStress` + `showStressVector`,`CAP_FEM_STRESS_VIZ=1`),但 `triangleInfo` 在
Python 讀不到("Invalid type")、`stressMaxValue` 只在繪圖時算,所以無法即時逐值比對。改以 numpy
**重實作 SOFA 的公式**(共旋**線性**應變 ε_L = U−I,U = √(FᵀF))和我們的 Green 版逐格比對,結果:

| 均勻拉伸 | 方向差(中位/最大) | σ₁ 比值 corot/green(中位) |
|---|---|---|
| 2% | 0.000° / 0.000° | 0.990 |
| 10% | 0.000° / 0.000° | 0.953 |
| 20% | 0.000° / 0.000° | 0.910 |
| 50% | 0.000° / 0.000° | 0.802 |

- **方向恆等**(0.000°,任意應變):ε_G、ε_L 都與伸張張量 U 同軸,主方向必然相同 → SOFA 的
  `showStressVector` 方向線與瀏覽器白線指同方向。
- **大小**:小應變幾乎相同,大應變我們(Green)略大(`½(U²−I) > U−I`),50% 拉伸時 SOFA≈我們的 80%。
- 對照解析解:單軸 λ=1.2,解析 σ₁=290.1 = 我們 290.1、方向 0° → **觀測器數值可證為正確**。
- `verify_stress.py` 內建 self-check:其 inline Green 與**出貨版 `principal_stress()` 逐格差 <1e-12**,
  確保驗的是真正跑的函式。

**即時力場 UI(解耦式)**(`CAP_HEATMAP=1` / `run_cap.ps1 -Heatmap` / `run_cap.sh --heatmap`):
SOFA 的**變形視窗完全不動**,另外把 σ₁ 場透過一個**極簡本機 HTTP 服務**(Python 標準庫、背景
執行緒)推出去;一個自足的瀏覽器頁面 [`stress_viewer.html`](../../Capsulorhexis/scenes/stress_viewer.html)
輪詢它,畫出**未變形參考圓盤**(= 變形膜的一張材料空間「地圖」)的即時熱圖,支援 **hover 浮現數值**
(σ₁ / 裂縫方向 / 裂向分類)、**時間軸回放**、色階條、說明面板(`?`)。

- **資料流**:controller 每 `STRESS_EVERY` 步把一幀(σ₁ / 裂縫角 ang / area_ratio,逐三角形)
  序列化成 JSON 字串。背景 HTTP 服務五個路由 —— `/`(頁面)、`/geometry`(靜態參考圓盤,只取一次)、
  `/stress`(最新幀,即時輪詢)、`/meta`(緩衝幀範圍)、`/frame?i=N`(第 N 幀,供拖桿回放)。
  字串換參考/append 都在 GIL 下原子完成,server 執行緒讀取無鎖;兩邊各有事件迴圈,互不阻塞。
- **錄製 + 回放(解單螢幕痛點)**:每幀同時 (a) 進一個**上限環形緩衝**(`CAP_STRESS_HISTORY`,
  預設 1500 幀)供頁面**時間軸拖桿/播放**即時回看,(b) append 到 **`scenes/stress_log.jsonl`**
  (每行一幀完整場,已 gitignore)供離線分析。所以**可以先自由拉、不用盯著看,事後再拖回任一時刻
  hover 查數值** —— 不必為了定格而放開滑鼠。空白鍵在 LIVE / 回放間切換。
- **為何放在 SofaImGui 之外**:SofaImGui **無法讓場景注入自訂 widget**,所以 hover-tooltip
  在 SOFA GUI 內做不到;把力場畫在**我們自己的頁面**裡,hover/數值/回放就全部可行。這也符合
  本 repo 既有的 `docs/demo_*.html` canvas demo 慣例。
- **效能 / 穩定性連動**:每幀序列化 4166×3 值原本用 per-element Python 迴圈,**把 FPS 砍半**
  (163→64);而 FPS 一低,即時滑鼠目標在兩步間跑得更遠 → `DISP_CLAMP` 飽和 → **整片彈開**,
  所以這個序列化成本本身就是「扭曲彈開」不穩的來源之一,不只是延遲。修法:(a) numpy 向量化
  `np.round(...).tolist()`(64→99);(b) `STRESS_EVERY` 預設 3→**6**(場更新頻率 ~8 Hz,足夠)
  → **143 FPS(僅比關閉低 ~12%)**。背景執行緒**無效**(GIL 會把它與物理執行緒序列化,實測無改善)。
  拉動仍覺重就把 `CAP_STRESS_EVERY` 調更大。
- **裂向分類**:頁面端重現終端機邏輯 —— 裂縫 ⊥ σ₁(Rankine),量 σ₁ 方向與**徑向**的夾角:
  <30° → 裂縫 CIRCUMFERENTIAL(good);>60° → RADIAL(runs to periphery);之間 → oblique。
  退化三角形(area ratio 超出 `DEGEN_LO..DEGEN_HI`)標灰、σ₁ 非物理。
- **色階用 p98,不用 max**:滑鼠拉點附近少數「近退化但仍合法」(area ratio 逼近 4.0)的三角形
  σ₁ 可達整體 ~100 倍(實測某次拉動峰值 32370,主體僅數百),用 max 當色階上限會把整張圖壓成藍。
  故自動色階取**載荷格的第 98 百分位**(frame 的 `sp98`),峰值仍以飽和紅呈現、但主體分佈看得出來;
  HUD 同時顯示 `peak`(max)與 `p98`。`Scale` 鈕可切固定上限 `STRESS_HEAT_MAX`。
- **預切圈預設關閉**:`generate_cap.py` 的 `TEAR_ENABLE` 改為 env 控制、預設 off(`CAP_PRESLIT=1`
  才開)。它的重合雙頂點環會在膜上呈現一條 seam、並在熱圖 r≈`TEAR_RADIUS` 產生假應力環;做 scripted
  tear 那一階再開。
- **錄製檔保護**:每次啟動會先把上一份 `stress_log.jsonl` 更名為 `.prev`,重跑不會靜默毀掉想分析的紀錄。
- **log 格式**(`stress_log.jsonl`,每行一 JSON):`{i, step, t, s1[Ntri], s2[Ntri], ang[Ntri], aratio[Ntri],
  smax, heatmax}`;三角形拓樸與參考座標見 `/geometry`(或 `cap.obj`)。numpy 逐行 `json.loads` 即可分析。

> [補充] 早一版曾把熱圖直接畫在 SOFA 網格上(每個 band 一個單色 `OglModel` + `IdentityMapping`),
> 但那會**蓋掉變形視圖**、且 hover 數值做不到;官方 `DataDisplay`+`OglColorMap` 又在本 build
> (v25.12 Win64)的 imgui GUI 視覺初始化 SIGABRT(batch 正常、GUI 死),`OglModel` 也未暴露
> 逐頂點顏色。故改走「SOFA 不動 + 解耦 HTTP + 瀏覽器頁面」這條,一併解掉遮擋與 hover 兩個問題。

### 4.2 INRIA argmax-c 判據:即時試算(瀏覽器)+ 數值驗證

在熱圖頁的撕裂門檻面板加了 **criterion 切換**:`Rankine ⊥σ₁`(各向同性)↔ **`INRIA argmax-c`**
(纖維各向異性,Dequidt 2013 Eq.1–4 的**成核形式**,H=1)。實作(`stress_viewer.html` 的
`inriaC()`;numpy 參考實作 + 驗證在 [`verify_stress.py`](../../Capsulorhexis/scenes/verify_stress.py)
的 `inria_c()`):

```
對每個元素、每個候選裂向 d(0–180°,5° 步):
  u = d + 90°                        (開裂法向:垂直裂縫、把裂縫「拉開」的方向)
  σ_u = σ₁·cos²ψ + σ₂·sin²ψ         (Eq.3 改寫到主軸座標;ψ = u 與 σ₁ 方向的夾角)
  σ̄_u = σ̄_T + (σ̄_L−σ̄_T)·(1 − fold(u,f)/90°)^α     (Eq.4;f = 纖維方向)
  c(d) = σ_u / σ̄_u                   (σ_u ≤ 0 壓應力不開裂 → c=0)
撕裂 ⟺ max_d c ≥ 1;裂向 = argmax_d c              (Eq.1–2,成核 H=1)
```

- **σ₂ 需要新增**:重建任意方向的 σ_u 需要**兩個**主值。觀測器本來就算了(`mid−dev`),
  現在 `principal_stress()` 回傳 4-tuple、frame/log 多 `s2` 欄。
- **纖維場 f 解析可得**:囊膜纖維是**同心圓**(Dequidt:每 0.5mm 一圈)→ 每個元素的 f =
  質心方位角 + 90°(切線),`loadGeometry` 時預算。
- **能即時算**:c ≤ σ₁/σ̄_T(σ_u≤σ₁、σ̄_u≥σ̄_T),所以只有 σ₁ ≥ σ̄_T 的元素可能撕 →
  先用這個上界過濾,36 方向搜尋只跑熱區,60fps 無壓力。
- **驗證**(`py -3.12 scenes/verify_stress.py`):
  1. **各向同性特例 = Rankine**(論文明述的等價):σ̄_L=σ̄_T 時,5000 隨機應力態的 argmax
     裂向與 ⊥σ₁ 差 ≤ 搜尋步長、c 與 σ₁/σ̄_T 差在**離散化理論上界**(6.1e-4)內 → OK。
  2. **跨纖維抑制**:單軸拉伸沿纖維(Rankine 裂向的 u ∥ f)→ σ̄_L/σ̄_T=4 時 c 從 5.0 壓到
     1.61,argmax 裂向從 90° 轉向 61°(被纖維帶偏)。
  3. **同心纖維 → 圓周撕**:σ₁ 徑向 + 纖維切向(囊膜情境)→ 200 個元素 argmax 裂向與纖維
     夾角 ≤0.5° → **裂縫沿圓周 = CCC 維持圓弧的機制**,數值重現。

**參數可得性(「還缺什麼拿不到」的正面回答)**:

| 公式需要 | 來源 | 狀態 |
|---|---|---|
| σ 張量(σ₁、σ₂、θ₁) | 幾何觀測器 | ✅(本次補 σ₂) |
| 纖維方向 f | 同心圓解析(切線) | ✅ 幾何導出 |
| **σ̄_T、σ̄_L、α** | **論文未給數值**(原文:門檻依外科醫師回饋調出) | ❌ **不可得 → 滑桿即時調** |
| p、θ_P(Eq.2 的 H 項) | 需要**裂尖追蹤**(上一步裂向) | 下一階段(成核先 H=1) |
| 裂尖鄰域加權應力 | 需要裂尖位置 | 下一階段 |

> [補充] 單位也是「拿不到」的一部分:模擬應力是 sim-unit(E=1200 非 Pa),文獻的囊膜強度
> (MPa 級)無法直接代入 —— 調參是誠實做法,與論文相同。`stress_log.jsonl` 已含 `s2`,
> 離線可對任何錄製重算 c 場。

---

## 5. 做不到什麼、為什麼(這是重點)

反覆調參數**到不了**「像真的撕囊那樣拉起一大片、翻摺、停住」。這**不是調參問題,是模型本質**,四個根本原因:

### 5.1 純彈性,沒有塑性(最大主因)
真實囊膜撕開**不可逆**——撕過永久分開、瓣維持折起。本 demo 是彈性:兩片唇被周圍完好的膜與**邊彈簧**拉回,
一放手裂口就縮回。**實測塑性嘗試失敗**:仿 `cap_membrane` 的做法(把靜止形狀 creep 向當前形狀 + 重烤彎曲靜止角)
不但沒幫忙,反而更差 —— 掀起的瓣放手後只保留 **18%**(塑性)vs **45%**(純彈性)。根因:**邊彈簧一直把瓣拉平**,
而只 creep FEM/彎曲的靜止態贏不過邊彈簧;若連邊彈簧的靜止長也 creep → **無界成長 → 爆炸**。且 `fem.reinit()`
會重載**原始**靜止態、把 creep 洗掉。→ 這個彈性 + 邊彈簧的結構天生做不出「形狀停住」。

### 5.2 裂縫被網格邊量化
裂縫只能沿現有邊、一次一格,做不出平滑大弧,也做不出「一撕一大片」的連續感。INRIA 用**沿路徑重網格**
就是為擺脫這點([`ccc_method/2`](../ccc_method/2_topological_remesh.md)、[`reference/8`](../reference/8_inria_implementation_deepread.md))。

### 5.3 粗網格的裂尖沒有應力奇異性
真實裂尖 σ→∞,所以輕輕一拉就裂;線性 FEM 把它抹平,裂尖受力被低估 → 要嘛拉不動、要嘛把門檻壓到很低
(不自然)。`TIP_STRESS_GAIN` 只是補一個人工集中係數,治標。且力**傳不到遠處的裂尖**(§4 的 `dist-to-tip`),
所以必須「抓在裂尖旁、隨裂縫重新夾」——正是臨床要重新抓握的原因,但對操作者不直覺。

### 5.4 軟 ↔ 穩定的矛盾
要裂口張得開就得把膜調軟(YOUNG 500 時 max-gap 開到 ~1.5),但一軟、手一用力,三角形就塌陷/翻面 →
FEM `Null determinant` 爆掉。只能在中間妥協(現用 YOUNG 900 + 面積夾限)。兩個目標在此模型**天生打架**。

---

## 6. 對照:EyeSi / INRIA / 本 repo 的 JS 解耦 demo

| | 本 SOFA demo(cap_tear.py) | EyeSi(Weber 2006/2009)[推論] | INRIA(Comas/Allard/Courtecuisse/Dequidt)[推論] | 本 repo JS 解耦 demo |
|---|---|---|---|---|
| 力學 | 線性共旋膜 FEM,**純彈性** | 為即時觸覺設計的完整物理;斷裂**不可逆** | **纖維各向異性 FEM** + 約束式接觸 | Verlet + PBD 距離約束 + 折皺力 |
| 撕裂判據 | σ₁ 門檻 + ⊥σ₁(Rankine) | 應力特徵值門檻(與本 demo 同族) | argmax 斷裂判據(Marchal) | 規則層 curr = rotate(drift + pull) |
| 裂縫路徑 | **綁死網格邊** | — | **沿任意路徑重網格**(擺脫網格) | Layer B 純幾何軌跡,可換膜 |
| 「瓣停住/翻摺」 | ✗(彈性彈回,§5.1) | ✓(不可逆 + 觸覺硬體) | ✓(重網格 + 適當本構) | ✓(PBD + `Attached` 旗標凍結) |
| 即時策略 | 只在裂尖局部分裂 | — | **非同步預條件子(Courtecuisse 2010)** | **只算脫離節點**(其餘凍結為錨) |
| 硬體 | 滑鼠 | **力回饋觸覺** | 紅外光學追蹤(Dequidt 2013,無力回饋) | 滑鼠 |

論文機制細節見正本:[`ccc_method/3`](../ccc_method/3_weber2009_physical.md)(EyeSi)、
[`ccc_method/4`](../ccc_method/4_inria_fiber_fracture.md)(INRIA)、[`reference/8`](../reference/8_inria_implementation_deepread.md)(INRIA 實作深讀);
架構決策見 [`implementation/3`](3_tearing_architecture_decision.md);本 repo 的 JS 解耦撕裂見
[`implementation/2`](2_freetear_demo.md)。

> **值得注意**:本 repo 的 **JS 解耦 demo**([`implementation/2`](2_freetear_demo.md))其實已用
> 「Layer B 幾何規則 + Layer A 只算脫離節點 + PBD + Delaunay 重網格」**繞過**了 §5 的多數限制
> ——它能折皺、能凍結瓣的形狀。本 SOFA demo 走的是「物理優先」路線,反而正面撞上這些限制。
> 這對照本身就是結論:**要真手感,關鍵不在把彈性膜調到多好,而在換成「解耦幾何路徑 + 不可逆凍結 + 路徑重網格」的架構。**

---

## 7. 結論與下一步

- 本 demo 作為**判據示範**是成功的:裂縫確實照 ⊥σ₁ 自動彎成圓、圓片能掀起露洞,且穩定不崩。
- 作為**手感模擬**已達模型天花板:純彈性 + 網格邊量化 + 無裂尖奇異 + 軟↔穩定矛盾,**調參數改不掉**。
- 要真正的「抓住拉一整片翻起來」,需換架構:
  1. **中期**:仿本 repo JS 解耦 demo,把「裂縫路徑(幾何規則)」與「膜物理(只算脫離片 + PBD/塑性凍結)」解耦;沿路徑重網格。
  2. **完整**:走 INRIA 正本 —— 編 `Capsulorhexis.dll` 的 `FiberFractureEngine`(纖維 FEM + 不可逆斷裂 + 路徑重網格),對齊 Comas 2008 / Allard 2009 / Dequidt 2013。

> 先確認方向,再動工;若走完整路線,第一步是讀 [`ccc_method/4`](../ccc_method/4_inria_fiber_fracture.md) 與
> [`reference/8`](../reference/8_inria_implementation_deepread.md) 把引擎需要的元件/判據/資料流盤清楚。
