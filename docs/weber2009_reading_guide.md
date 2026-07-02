# Weber 2009 博論逐章導讀(中德對照 + 教學)

> **原文**:Weber, K. (2009). *Interaktive Echtzeitsimulation deformierbarer Oberflächen für Trainingssysteme in der Augenchirurgie*
> (Interactive Real-time Simulation of Deformable Surfaces for Training Systems in Eye Surgery). PhD thesis, Univ. Mannheim.
> **德文、161 頁、無英文版**;PDF 存 `papers/Weber_2009_PhD_DeformableSurfaces_EyeSurgery.pdf`。
> **本檔用途**:逐章「德文重點 → 中文翻譯 → 教學/與本專案連結」的讀書導讀,隨進度累積。
> 方法精華另見 [`ccc_method/3_weber2009_physical.md`](ccc_method/3_weber2009_physical.md)。

## 進度 / 路線圖
| 章 | 主題 | 狀態 |
|---|---|---|
| 1 Einleitung | 導論:醫學動機 + 兩元件撕裂哲學 + 即時 | ✅ 本檔 §1 |
| 2 EYESi | 模擬器硬體/軟體/教育 | ✅ 本檔 §2 |
| 3 Simulation deformierbarer Objekte | 可變形物體基礎(連續體/FEM/mass-spring、積分、碰撞) | ✅ 本檔 §3 |
| 4 Membranen im Auge | Feder-Masse 框架 + Velocity-Verlet + 碰撞 + 彎曲/貼合脫離/Locking | ✅ 本檔 §4 |
| 5 Reißen | 撕裂:斷裂準則 + 拓樸實現 | ✅ 見 ccc_method/3 |
| 6 Instrument–Membran | 針/無摩擦/滑·靜摩擦/勾住 | 🔜 |
| 7 Anwendungen | 7.1 撕囊 ✅;7.2 ILM、7.3 ERM peeling | 部分 |
| 8 Diskussion | 討論/展望 | 🔜 |

---

## §1 Kapitel 1 — Einleitung(導論)

### 1.1 醫學動機:三種「膜」手術
- **ERM-Peeling**:剝除視網膜前膜(增生、擋視力)。
- **ILM-Peeling**:剝除內限膜(視網膜最表層),露出底下組織。
- **Kapsulorhexis(撕囊)**:白內障手術一步,打開包住水晶體的**囊袋 (Kapselsack)**。
> 全書統一主題是「**膜 (Membran)**」——三者都在撕/剝一層膜。她做的是**通用膜撕裂/剝離引擎**,撕囊是其中最難的應用。

### 1.1 撕囊為何最難
> *"Der Riss …muss einer exakt vorgegebenen Kreisbahn folgen."*(裂縫必須沿精確圓形軌跡走。)
開口須**正圓、置中、半徑準確**,囊袋才能當人工水晶體容器。→ 要求對裂縫**完全控制**(不能像「拉斷彈簧」那樣隨機),這決定了 §5 的斷裂準則 + 拓樸實現設計。

### 1.1 針器械難處
> 施力太小 → 針尖**滑掉 (abrutscht)**;太大 → **造成傷害**。→ 預告第 6 章(摩擦 + 勾住 Verhaken)。

### 1.1 四大重點(Schwerpunkte)
1. **即時 ≥ 25 fps** 最高優先。
2. 核心=操作膜 → 模擬**可變形「曲面」**:**2D 離散、忽略膜厚**(四面體體積離散會變慢)。
3. **物理基礎變形模型**:即時算內部變形力 + 收外力。
4. 共用 **framework**:變形模型 + 數值積分 + 碰撞偵測 + 碰撞回應;針–膜互動另章(針尖可穿膜不碰節點 → 高精度 + 模「勾住」)。
5. **撕裂 = 兩獨立元件**:**Bruchkriterien 斷裂準則**(是否/何處/何方向/多長)+ **拓樸實現**;撕囊需完全控制 + 精確路徑,且初始離散不可限制拓樸實現。

### 1.1 成果
新演算法整合進 EYESi 的撕囊/ILM/ERM 模組;**撕囊模組經醫師驗證後納入 VRmagic 產品線販售**(→ 商品化、閉源)。

### 1.2 全書結構
`2 EYESi → 3 可變形基礎 → 4 框架 → 5 撕裂 → 6 針/摩擦 → 7 應用 → 8 討論`。

📌 **小結**:主題=膜的撕裂/剝離;撕囊最難(需精確圓);主軸=即時 2D 可變形曲面 + 撕裂兩元件;成果已商品化。

---

## §2 Kapitel 2 — Der Augenoperationssimulator EYESi

### 開場 + 眼解剖
EYESi = VRmagic 商用眼科訓練模擬器(2001 起,龍頭),手術在**立體顯微鏡**下做。眼分**前段**(結膜/角膜/水晶體/虹膜)、**後段**(玻璃體/視網膜/脈絡膜,=玻璃體視網膜手術)。器械如 Vitrektor(振動刀+抽吸),用腳踏板+觸控控制。撕囊屬**前段**。

### 2.1 硬體
- 顯微鏡內兩片 **OLED(各 800×600)**→目鏡看**立體影像**;塑膠**頭模**(觸覺真實、臉部幾何限制器械);
- **機械眼=半球**:旋轉自由度如真眼、彈簧模擬眼肌回復力、固定**插針孔**;
- **光學追蹤**:繞光源 **3 台 FPGA 相機**看器械+眼上**彩色標記**(2 台可重建 3D,第 3 台減少遮擋);器械**繞長軸旋轉**用**手柄磁感測器**。→ 即 Köpfle MOSCOT 追蹤。

### 2.2 軟體:抽象 vs 真實模組 + 器械硬約束
GUI(選器械:鑷子/vitrector/針/套管…)+ VR(算手術影像)。
- **抽象模組**:操作非解剖物件練基本功;**關鍵約束**:器械**只能繞自身軸 + 繞插針孔轉**(不能任意平移)。
- **真實模組**:如注清液**穩定眼內壓** → 再**撕囊**。
> 「器械只能繞軸/繞孔」是真實硬約束;注液穩壓 = 撕囊模組黏彈劑/`pressure` 之源。

### 2.3 手術教育
2001 首台原型(DOG);全球約百台;ORBIS 2005 採用。**Drylab** 訓練課;**DOG 2003、美國 2007 把模擬訓練列入標準/指引**。醫師接受關鍵:擬真 + EYESi **代行教官**(背景資料、步驟引導、**評分系統**、**多難度**)。
> → 第 7 章所有新模組(含撕囊)**必做評分 + 多難度**,是 EYESi 框架要求。

📌 **小結**:立體顯微鏡 + 機械眼 + 光學追蹤的即時 VR;器械**只能繞軸/繞孔**;模組必備評分+難度;撕囊屬前段、需先注液穩壓。

---

## §3 Kapitel 3 — Simulation deformierbarer Objekte(數學)

### 3.1 物理變形模型:連續體 → FEM → mass-spring
- **連續體力學**:對稱 3×3 **應變張量 V**(位移的空間偏導)與**應力張量 S**;彈性定律線性關係 V↔S。
- **FEM**:運動方程 `ρ ẍ = ∇·S + f`(∇·S=內力);離散 `x(m,t) ≈ Σ xᵢ(t) bᵢ(m)`(bᵢ=形狀函數)→ 代數方程組。⚠️ 線性化應變張量失旋轉不變性 → 大變形**幻影力** → **co-rotational** 修正。
- **mass-spring**(無 PDE):質點 mᵢ、xᵢ、vᵢ;彈簧(lᵢⱼ, cᵢⱼ)。線彈性力
  `f_i = c_ij (|x_ij| − l_ij) · x_ij/|x_ij|`,`x_ij=x_j−x_i`;唯一 ODE `F_i = m_i ẍ_i`。
  能量式:`f_i = −∂E/∂x_i`(可加面積/體積守恆項,Teschner)。
- **correct vs plausible**:FEM「物理正確」(材料常數可查表);mass-spring「物理合理」(彈簧常數需調參、真實材料無對應)。布料反而適合 mass-spring(織物非連續體)。

### 3.2 數值積分:顯式 vs 隱式 Euler
- IVP:`ẏ = g(y,t)`, `y(t₀)=y₀`。
- **顯式 Euler**:Taylor 截一階 → `y(t+h)=y(t)+h ẏ`。質點降階系統
  `[ẋ; v̇]=[v; f/m]` → `[x;v](t+h)=[x;v]+h[v; f/m]`(n 點疊成 6n 維)。便宜、易發散。
- **隱式 Euler**:`y₁=y₀+h g(y₁)`;線性化 `g(y₀+Δy)≈g(y₀)+g'(y₀)Δy` →
  `(I/h − g'(y₀)) Δy = g(y₀)` → **每步解線性系統**(含 Jacobian)。
- 兩者皆**階數 1**;隱式**任意步長穩定**,但矩陣**只有拓樸不變時可離線預先反轉**。
  🔑 撕裂改拓樸 → 隱式失去預算優勢 → Weber 選**顯式**(§4.2)。

### 3.3 碰撞:偵測 + 回應
- **偵測**:BVH(球/AABB/OBB/k-DOP)、Broad/Narrow phase、Spatial Subdivision、Distance Field(剛體用)、CCD(補漏 (t,t+h) 穿隧)。
- **回應**:硬約束(不可互穿)vs 軟約束(彈簧原長)。
  - **Penalty**:先允許穿透 → 罰力 ∝ 穿深(便宜、會抖)。
  - **Constraint**:事先限制、需接觸時刻 tk 並回捲(正確、貴)。
  - 即時 + 可變形 → 多略過接觸時刻、用便宜 penalty/位移投影。

📌 **小結**:`ρẍ=∇·S+f`(FEM)vs `f_i=c(|x_ij|−l)x̂`+`F_i=mẍ`(mass-spring);顯式便宜易爆、隱式穩但撕裂使其失優勢;碰撞即時多用便宜 penalty。

---

## §4 Kapitel 4 — Simulation von Membranen im menschlichen Auge(數學)

### 4.1 膜=Feder-Masse(第 1 課已述)
同 m、同 c 的三角網 + 五條一致性規則;rest≠start → **預張力**(rest length ×<1)。

### 4.2 積分:Velocity-Verlet + 阻尼
- 顯式 Euler 太差 → 多步法。**Verlet** `x(t+h)=2x(t)−x(t−h)+a h²`(無速度)。
- **Velocity-Verlet**(採用):`x(t+h)=x+vh+½a h²`;`v(t+h)=v+(a(t)+a(t+h))/2·h`;**階數 2**。
- **阻尼**:別在顯式步加額外力(增不穩)→ 把阻尼併進積分器:**每步 `v *= 因子(<1)`**(Fuhrmann)。→ 你 demo `vx*=DAMP` 之源。

### 4.3 碰撞(即時取捨)
- 只算膜 vs 器械;**不用 CCD/distance-field**;膜 vs 剛器械 → **球+圓柱包圍體**(無需 BVH);narrow=貼身、broad=半徑+d;針尖 → 用「三角形↔包圍體」距離。
- 回應 = **penalty**:**只施力**、方向=脫離包圍體最短路徑、**大小 ∝ 穿透深度**;可疊加。
- **模擬步驟**:30Hz → 每幀 0.033s 切成 **n 步 `h=0.033/n`**(n 取最大);追蹤每幀給一次 **MV(4×4)** → n 步間**線性內插 MV**;每步:歸零→內力→外力(內插MV→narrow→penalty)→`velocityVerlet(h)`。

### 4.4.1 彎曲剛度
基本 mass-spring 無彎曲剛度(共點兩彈簧可任意夾角)。→ 加**彎曲彈簧**(連兩相鄰三角形的對角節點;缺點:也影響拉伸剛度)或曲率式(貴)。她用彎曲彈簧。

### 4.4.2 貼合/脫離(= demo 的 Attached)
- **Homing 彈簧(l₀=0)**:`f = k_homing (x_homing − x)`,**免開根號**(比一般彈簧便宜)。
- 每節點 homing 位置(=rest,底層變形時跟著調);**脫離** = homing 常數**數迭代遞減到 0**(避免瞬跳)。
- **判準**:`|x − x_homing| > 門檻`;`detachMembrane()` 每幀積分後呼叫一次。
- 對照 demo:`det` 旗標 = homing 常數→0 的簡化;可加「距離門檻」判準更真實。

### 4.4.3 Locking 問題(★ demo「折起又彈回」的病)
- **Locking**:拓樸限制運動自由度——無彎曲元件的三角網,只有「一串邊剛好落在折線上」才能無變形折;任意折會生應變,網格越粗越明顯。
- 臨床:針把脫離膜折平,真實會躺平,**模擬會沿脫離邊彈起**(折疊壓縮的彈簧回推)。
- **解**:Choi-Ko —— 邊**高拉伸剛度、壓縮幾乎無回復力**;她的 **`supportFoldedEdge()`**:在脫離前緣附近**暫時停用被壓縮的彈簧**(`k=0`),不再壓縮/離開前緣就重啟。
- 🔑 **升級 demo**:要讓折起的膜躺平不彈回,就對脫離區被壓縮的邊暫時 `k=0`。

📌 **小結**:Velocity-Verlet(2 階)+ 速度×因子阻尼;球/圓柱包圍體 + penalty(力∝穿深)+ 每幀 n 積分步 + MV 內插;彎曲彈簧;homing 彈簧(免根號、常數→0 脫離);Locking 用 Choi-Ko/supportFoldedEdge。

---

## §5–§8:待續
依進度接續補上(§5 撕裂精華見 ccc_method/3、§6 針/摩擦、§7.2/7.3 peeling、§8 討論)。
