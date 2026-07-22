# Weber 2009 物理版撕裂方法:技術精讀與 2006 差異

> 來源:**Weber, K. (2009).** *Interaktive Echtzeitsimulation deformierbarer Oberflächen für Trainingssysteme in der Augenchirurgie*
> (Interactive Real-time Simulation of Deformable Surfaces for Training Systems in Eye Surgery). PhD thesis, Univ. Mannheim.
> 原文 **德文、161 頁、無英文版**(`papers/Weber_2009_PhD_DeformableSurfaces_EyeSurgery.pdf`)。本文為第 5、6、7.1 章的**中英夾雜精讀翻譯 + 技術解讀**。
> 相關:[`ccc_method/1 描述式撕裂`](1_tearing_descriptive.md)(2006 描述式)、[`implementation/2 demo`](../implementation/2_freetear_demo.md)(本 repo demo 實作)、[`reference/2 引用地圖`](../reference/2_weber2006_citations.md)(引用地圖)。

---

## 0. 一句話定位:典範轉移(paradigm shift)

| | **Weber 2006(= 本 repo `demo_remesh_attached`)** | **Weber 2009(本文)** |
|---|---|---|
| 裂縫方向 (tear direction) | **描述式 descriptive**:`rotate(CurrDir, DriftAngle+PullAngle)`、shearing/ripping | **物理啟發式 physically-motivated heuristic**:讀 mass-spring 的**應變場 (strain field)**,往「應變最小」方向裂 |
| 底層變形 | mass-spring | mass-spring(**不變**,仍即時 ≥25 fps) |
| drift | 向量分量 | **降為 fallback**(僅撕囊特例) |

**關鍵澄清**:2009 的「物理」**不是 FEM**。作者明說 mass-spring 沒有應力/應變張量,但可從連續體力學準則**抽出一個便宜的啟發式**搬到 mass-spring。所以「即時 vs FEM 太慢」的取捨**沒有被違反**——它是「mass-spring + 便宜啟發式」,幾乎不增加計算量。

---

## 1. 斷裂準則 Bruchkriterien(決定「是否/何處/何方向/多長」)

Weber 把撕裂演算法拆成**兩個獨立元件**:
**(A) Bruchkriterien(fracture criteria)** 決定裂縫的「**位置 Ort / 方向 Richtung / 長度 Länge**」;**(B) Topologische Umsetzung(topological realization)** 把裂縫實際切進網格。本章講 (A),第 2 章講 (B)。

### 1.1 為何用啟發式(§5.4.1)
連續體力學:材料破壞可用 **最大主應力準則(Rankine criterion)** ——當最大主應力超過門檻即破壞,裂面法線沿最大主應力方向 → **2D 中裂縫沿「最小主應力/應變」方向擴展**。
> *"FEM-Modelle erfüllen diese Bedingung, Feder-Masse-Modelle dagegen nicht. Allerdings ist den Kriterien eine einfache Heuristik zu entnehmen … : Wenn ein (2D) Objekt reißt, dann in die Richtung minimaler (negativster) Verzerrung oder Spannung."*
> (FEM 有應力/應變張量,mass-spring 沒有;但可抽出啟發式:2D 物體會往**應變/應力最小**的方向裂。)

### 1.2 位置 Ort der Rissausbreitung(§5.4.3)—— 基於**應力 Spannung**
每個節點 k 指定一個應力值,由掛在它上的所有彈簧 fᵢ 的伸長量決定:

$$s(k)=\sum_i \tfrac{c_i}{2}\,\bigl|\,l(f_i)-l_0(f_i)\,\bigr|$$

其中 `l₀`=彈簧原長 (rest length)、`l`=現長、`cᵢ`=彈簧常數。→ **直接讀 mass-spring 現成的伸長量,幾乎零成本。**

**三種節點型別(承自 Grimm)+ 三個門檻:**
- **innerer Knoten (inner node)**:每條掛著的彈簧都是兩三角形共用邊。
- **Randknoten (edge/boundary node)**:恰有兩條彈簧、各只屬一個三角形;沿裂縫邊**成對**出現、共享同一 rest position(網格鬆弛時兩者疊回 → 閉合裂縫)。
- **Risskeim (tear seed / crack-tip node)**:特殊 Randknoten,**無對應節點**(即裂縫尖端)。

$$minSproutStress \ll minEdgeStress \ll minInnerStress$$

每步找各型別中「最超標」的節點,選取優先序 **Risskeim > Randknoten > innerer**(尖端延伸優先於新開裂縫)。

### 1.3 方向 Richtung der Rissausbreitung(§5.4.2)—— 基於**應變 Verzerrung**
在裂縫尖端 `~a`(=Risskeim)周圍的 Rissregion(尖端所屬三角形)中,對每個三角形 `(~a,~b,~c)`,在對邊 `~c−~b` 上找一點 `d~`(重心座標 `t∈[0,1]`),使「**變形後長度 / 原長**」(= 應變)最小:

$$f(t)=\frac{|\,\vec b_v + t(\vec c_v-\vec b_v)-\vec a_v\,|}{|\,\vec b_u + t(\vec c_u-\vec b_u)-\vec a_u\,|}=\frac{|\vec d_v-\vec a_v|}{|\vec d_u-\vec a_u|}$$

(下標 `u`=unverzerrt/rest,`v`=verzerrt/deformed)。令 `g(t)=f²(t)`,解 `g'(t)=0`(一個二次式)得候選 `tᵢ`,與端點 `f(0),f(1)` 比較取 `t_min`。**跨 Rissregion 所有三角形,取應變最小者為 Rissdreieck(tear triangle)**,其 `(三角形, t)` 即裂縫方向。

> 直覺:裂縫往「**最不被拉伸(最鬆)**」的方向走 = Rankine 準則在 mass-spring 上的離散近似。

### 1.4 長度 Länge der Rissausbreitung(§5.4.4)—— 與**應力成正比**

$$tearLength = minTearLength + \lambda\,(maxTearLength-minTearLength)$$
$$\lambda=\frac{sproutStress-minSproutStress}{maxSproutStress-minSproutStress}\in[0,1]$$

`maxTearLength` ≈ 全網格彈簧平均原長。拉越用力(應力越高)→ 一次撕越長。對 §2.2 的演算法,`tearLength` 另需被 `|d~−a~|−ε` 上限約束(讓新尖端 `~e` 不要太貼近對邊)。

---

## 2. 拓樸實現 Topologische Umsetzung(把裂縫切進網格,§5.5)

兩種演算法**共用上面的斷裂準則**,差在如何把裂縫實際切進 mesh。所有網格調整**先在 rest positions 上做,再用重心座標映射到變形後的 mesh**。

### 2.1 Ansatz 1:常數三角形數(constant triangle count,§5.5.2)
擴展 Boux de Casson / Grimm:沿**既有三角形邊**分離,只沿裂縫邊新增節點/彈簧 → **三角形總數不變**,但裂縫邊可能很鋸齒、且應力累積↔前進呈**跳動**。用 **Node Snapping + 動畫**改成 pseudo-continuous:
- 把 Rissdreieck 的 `~b` 或 `~c`(離 `d~` 較近者)吸附到 `d~` → 一條掛在 `~a` 的彈簧轉向裂縫方向。
- 每次尖端應力超標,把 `~a` 沿方向前進 `tearLength`:
$$\vec a := \vec a + tearLength\cdot\frac{\vec d-\vec a}{|\vec d-\vec a|}$$
- 前進時把該邊兩三角形**暫時**拆成四個 → 裂縫像**拉鍊 (Reißverschluss/zipper)** 沿邊打開;到位後再併回兩個。→ 因為只是暫時插入,總三角形數維持常數。

### 2.2 Ansatz 2:漸進切割(progressive cutting,§5.5.3)★撕囊採用此法
把 **Nienhuys & van der Stappen** 的互動切割演算法改用於撕裂(把 aktiver Knoten→**Risskeim**、aktive Region→**Rissregion**、Schnittkante→**Risskante**)。四個操作:

1. **Bewegung des Risskeims(移動尖端)**:把 Risskeim 移到 Rissdreieck 內的新尖端位置。**限制方向只能與 Risskante `~a−~r` 成銳角** → 強制「向前」走,不會把裂縫邊縮回(尖端不綁器械位置,縮回會很不自然)。
2. **Löschen von Knoten(刪節點)**:尖端太靠近某鄰點時,把該點移到尖端位置 → 相關三角形退化成線段而可移除,**不留洞**。
3. **Teilung der Risskante(切分裂縫邊)**:尖端後方的裂縫邊過長就切分,新增兩三角形;用 **Delaunay 準則**判斷(兩相鄰三角形的外接圓若含全部四點 → 違反 → 需處理),並加一個**長度門檻**保證裂縫邊解析度不隨網格解析度浮動。
4. **Flippen(翻邊)**:用 **Delaunay 準則**翻邊以提升三角形品質(增大最小角)。⚠️ 但翻邊會**改變 mesh 內力分佈、且在 3D 曲面上會局部翻轉曲率**,所以**只對「當前 Rissregion 的邊」翻**,不大範圍翻。Fig 5.12 顯示:正是靠翻邊,Rissregion 才能「隨尖端在 mesh 中滑行」(前方納入新三角形、後方擠出舊三角形)。

> §5.4.4 那個「新尖端 `~e` 要離對邊至少 ε」的規定,原因就在這:擋路的那條邊必須**先 flip 掉**,Rissregion 才能在尖端前方打開。

#### 2.2.1 逐圖走查(Fig 5.9–5.12)

**Fig 5.9 — Delaunay 翻邊判準(flip criterion)**
把共享一條邊的兩三角形攤平到同一平面。**該邊「不滿足」Delaunay ⟺ 兩三角形的外接圓各自都把「全部四個頂點」包進去**。翻邊後,每個外接圓只含自身三個頂點 → 滿足;此操作**增大兩三角形的最小角**,產生 well-shaped 三角形。
> 變形網格要先「攤平 (entfalten)」兩三角形再判,因為 Delaunay 是平面性質。

**Fig 5.10 — 移動尖端 → 刪點 → 切邊(a→b→c→d)**
- **(a) 出發**:Risskeim 與其 Rissregion(周圍三角形)。斷裂準則(§1.3)算出**深灰三角形**為 Rissdreieck,其中黑點為**新尖端位置**。
- **(a→b) Bewegung(移動尖端)**:把 Risskeim 移到該黑點。注意:掛在 Risskeim 上的**兩個 Randknoten 共用同一 rest position `~r`**;移動會改變 Risskante `~a−~r` 的方向與長度。**方向被限制只能與 `~a−~r` 成銳角** → 強制「向前」,不會把裂縫邊縮回(尖端不綁器械,縮回不自然)。
- **(b→c) Löschen(刪點)**:移動後尖端**很靠近** Rissregion 的另一節點;若距離 < 門檻,把該鄰點**移到尖端位置** → 深灰三角形退化成線段 → 連同鄰點一起移除,**不留洞**。
- **(c→d) Teilung(切邊)**:尖端後方的 Risskante 變長;對「兩個共用 rest position 的 Randknoten 所夾」的三角形套 Delaunay(即使它們不共享實體邊,因為兩 Randknoten rest 位置相同)→ 違反 → **切分 Risskante、生兩個新三角形**。另加**長度門檻**:Risskante 超長就切,保證解析度不隨網格浮動。

**Fig 5.11 — 3D 翻邊的副作用**
在 3D 可變形曲面上翻一條邊會**局部翻轉曲率**,而且**一條(通常已變形的)彈簧消失、改對另兩個節點施力 → 擾動 mesh 內力分佈**。所以翻邊**要盡量少用**,只在必要處翻。

**Fig 5.12 — Rissregion 靠翻邊「滑行」穿過網格(a→f)**(這是 progressive 的精髓)
- **(a)** 尖端接近一條邊,但與鄰點距離**未**低於刪點門檻(呼應 §1.4:新尖端與 Rissdreieck 對邊至少留 ε)。
- **(b)** 裂縫要繼續前進,**擋路的那條邊必須先 flip 掉** → Rissregion 在尖端**前方**打開。
- **(c)** 尖端繼續前進;後方的三角形邊被拉長,尤其箭頭標的那條。
- **(d)** 箭頭那條邊 flip → 含箭頭的三角形被**擠出 Rissregion 到後方** → Rissregion 由 7 個三角形降為 6。
- **(e)** 接著 Risskante 不再滿足 Delaunay → **切分**。
- **(f)** 再翻兩條邊 → Rissregion 收斂到 4 個三角形。
- **結論**:**正是翻邊讓 Rissregion 能隨尖端「滑行」**——前方納入新三角形、後方擠出舊三角形。因此演算法**只對「當前 Rissregion 的邊」做 Delaunay 檢查/翻邊**(不大範圍翻,兼顧 Fig 5.11 的內力/曲率顧慮)。

> 一句話串起來:**移動(向前銳角約束)→ 擋路邊 flip 讓前方開路 → 後方邊被拉長後 flip 擠出、Risskante 過長則 split → 太近的點 collapse**。四個操作協同,讓單一裂縫沿任意路徑平滑穿過三角網,且三角形數幾乎不膨脹。

### 2.3 裂縫生成/結束(§5.5.4)
- **在邊界生成**:Randknoten 被選為 Rissknoten → 調整一條邊 → 沿該邊**完全切開、把 Rissknoten 與該邊加倍 (verdoppeln)**,在原內部節點處生出新 Risskeim。(Randknoten 須至少掛兩三角形。)
- **在內部生成**:內部 Rissknoten → 需 mesh 細化,在調整邊中點插兩新節點,邊兩端各生一個 Risskeim。
- **結束**:尖端接近 Randknoten / 邊界邊到門檻 → 沿連線切開 / 把該三角形一分為二,讓裂縫**垂直於邊界**收尾。Ansatz 1 不需特別處理(邊終點在 Randknoten 時自動 verdoppeln 分開)。

---

## 3. 撕囊訓練模組工程(§7.1.4)

| 元件 | 實作 |
|---|---|
| **Linsen-System** | 晶體=剛體,掛線彈簧(zonular fibers);器械壓 → 表面**凹陷 (Eindellung)**,壓深 → 整體位移甚至扯出 |
| **Kapselsack(囊膜)** | 圓形三角網 mass-spring;**邊緣藏虹膜後、整段固定為邊界**(防整片脫離) |
| **Anhaften/Ablösen(貼合/脫離)** | 起始全節點 homing 到未變形晶體;每幀把**未脫離**節點的 homing 位置投影到晶體面 → 膜貼合晶體變形 |
| **Spannung(張力)** | `pressure`(前房壓,normalized);rest 位置 ×(<1) 拉進晶體內 → homing 力須撐開膜=張力;壓力隨時間漏 → 注**黏彈劑 Viskoelastikum** 補 |
| **Instrumente** | 鑷子 Pinzette / cystotome Zystotom / 注射針 Kanüle(見第 4 章) |
| **Reißen** | 用 **§5.5.3 連續型**演算法(可精確走圓);每幀撕裂演算法跑 **3 次**,與 mass-spring 的 **4×10 積分步**交錯 |
| **Bewertung(評分)** | 抽撕囊邊節點 → 擬合平均圓心/半徑 → 算偏差 → 評「置中/半徑/圓度」 |
| **Schwierigkeit(難度)** | 5 級(由 `trigger` 門檻)→ 10 個 EYESi 關;最難關**從裂痕朝外開始 → 要「救援」拉回圓** |

### 3.1 混合:drift 用描述式 fallback(§7.1.4)
物理方向搞不定「往周邊 drift」,故撕囊**特別**加回描述式:每當 Risskeim 應力超出門檻 `minSproutStress` 的量為 `x`,檢查 `x < trigger`?
- **是** → 走**物理**方向;
- **否** → 觸發**描述式**:取當前裂縫方向向量,**依 `x` 大小旋向周邊**,當作方向送給撕裂演算法 → 裂縫外漂。

> 因為「尖端應力在鑷子夾點靠近裂縫尾端時最好控制」→ **強迫使用者頻繁 re-grasp**、以細膩手法操作(把臨床技巧內建進物理量)。

---

## 4. 器械模型(§6,含轉換差異)

| 器械 | 接觸/施力模型 | 對膜 |
|---|---|---|
| **Pinzette(鑷子)** | 閉合時把碰到三角形的節點綁上**相對器械的 homing 力**;張開即解除 | 夾住並**拉**(舊 EYESi 用位移法→節點瞬間「凍結」,較生硬;Weber 改力基更平滑) |
| **Zystotom(針/cystotome)** | 第 6 章:針尖可**穿膜而不碰節點** → 需**高精度碰撞偵測 + 勾住 Verhaken 模型 + Gleit-/Haftreibung(動/靜摩擦)** | **推/挑**膜(Fig 7.1:針做「垂直於裂痕」的推 → 導向切線、瓣膜立起折過去) |
| **Kanüle(注射針)** | 注黏彈劑 | 調 `pressure` → 調張力 |

第 6 章方法:先建**無摩擦接觸 (reibungsfreie Interaktion)** 基礎,再疊**滑動/靜摩擦 (Gleit-/Haftreibung)** 讓膜能被「勾住、受控拖動」。
> **對本 repo demo 的啟示**:若把 Layer B 換成 §1 的**應變場方向**,則「鑷子拉 vs 針推」造成的應變場不同 → **同一套撕裂邏輯會自動對兩種器械給出不同裂向**,不必寫兩套規則。這正是 2009 物理化的最大好處。

---

## 5. 2006 vs 2009 逐項差異總表

| 面向 | 2006(demo) | 2009(本文) |
|---|---|---|
| 裂縫**方向** | 描述式旋轉(pull+drift) | **應變最小三角形**(Rankine 啟發式,§1.3) |
| 裂縫**位置** | 沿尖端 | **節點應力 `s(k)`** 超三門檻(§1.2) |
| 裂縫**長度** | 固定步長 | **∝ 應力**(§1.4) |
| **drift** | 主要機制 | **描述式 fallback**(`trigger` 門檻,§3.1) |
| 拓樸 | Nienhuys progressive | **兩種**(常數三角形 §2.1 / progressive §2.2);撕囊用後者 |
| flip 範圍 | (一般 Delaunay) | **僅當前 Rissregion**(避免擾動內力/翻曲率,§2.2) |
| 方向約束 | — | **只准與 Risskante 成銳角**(強制向前,§2.2) |
| 器械 | 單一(滑鼠) | 鑷子(homing) / 針(摩擦+勾住,§4) |
| 範圍 | 撕囊 | 撕囊 + ILM/ERM peeling |
| 泛化性 | 需逐案手刻規則 | **自動泛化**(讀真實變形) |
| 狀態 | 論文原型 | **商品化進 VRmagic EYESi** |

**核心洞見**:2006→2009 的躍升,是把「撕裂方向」從**手工描述規則**換成**讀取 mass-spring 自身應變場的物理啟發式**,在**不犧牲即時性**下取得**跨器械/跨互動的自動泛化**;僅在「周邊 drift」這個物理難以重現的特例保留描述式 fallback → **hybrid**。

---

## 6. 德–英–中 術語對照

| Deutsch | English | 中文 |
|---|---|---|
| Bruchkriterium | fracture criterion | 斷裂準則 |
| Rissausbreitung | tear propagation | 裂縫擴展 |
| Risskeim | tear seed / crack-tip node | 裂縫尖端節點 |
| Rissregion | tear region | 尖端所屬三角形群 |
| Risskante | tear edge | 裂縫邊 |
| Rissdreieck | tear triangle | 裂縫三角形 |
| Randknoten / innerer Knoten | edge (boundary) / inner node | 邊界 / 內部節點 |
| Spannung / Verzerrung | stress / strain | 應力 / 應變 |
| Ruheposition / Nulllänge | rest position / rest length | 靜止位置 / 原長 |
| Anhaften / Ablösen | attach / detach | 貼合 / 脫離 |
| Homing-Kraft | homing force | 歸位力(把節點拉回目標位) |
| Zystotom / Verhaken | cystotome / hooking | 囊膜切開針 / 勾住 |
| Gleit- / Haftreibung | kinetic / static friction | 動 / 靜摩擦 |
| Node Snapping / Reißverschluss | node snapping / zipper | 節點吸附 / 拉鍊式 |

---

## 7. 對本 repo 的升級路徑
- 現況:`demo_remesh_attached` = **2006 描述式**(見 [`implementation/2 demo`](../implementation/2_freetear_demo.md))。
- 升級成 2009 物理版需改 **Layer B**:
  1. 每幀對脫離區的每個三角形算**應變**(現長/原長),尖端周圍取**應變最小**方向(§1.3);
  2. 節點應力 `s(k)`(§1.2)決定何處/是否延伸;長度 ∝ 應力(§1.4);
  3. drift 改成 `trigger` fallback(§3.1);
  4. 拓樸維持現有 Nienhuys/Delaunay(§2.2 已對應)。
- 好處:器械(鑷子/針)差異**自動**由應變場體現,無需分別寫規則。
