# 自由撕囊 demo 的實作(Layer B → 橋 → Layer A → remesh)

對應檔案:[`demo_remesh_attached.html`](../demo_remesh_attached.html)
這份說明把該 demo 的每一幀流程拆開,逐段對到程式裡的變數/函式。它是把
[`demo_decoupling_tear`](../demo_decoupling_tear.html)(只有 Layer B 軌跡)接上**真網格 + Layer A + Attached + Delaunay 重網格**的完整版,忠於
**Weber, Wagner & Männer 2006**(見 [`ccc_method/1 描述式撕裂`](../ccc_method/1_tearing_descriptive.md)、[`ccc_method/2 remesh`](../ccc_method/2_topological_remesh.md))。

---

## 0. 一張圖:每一幀的資料流

```
按住滑鼠(鑷子)
   │
   ▼
Layer B(規則,大腦)──────────────────────────────
   你拉(PullDir) + drift(DriftDir)  → 算出撕痕方向 curr → tip 前進一步
   │ 單向耦合(B 只丟兩件事給下游,從不讀 A 的結果)
   ├─ inPoly(node)  → 內側節點 Attached=FALSE(det=true)  →「哪些是瓣膜」
   └─ segCross(...) → 撕痕掃過的邊 severed            →「哪裡被切開」
   ▼
Layer A(物理,身體)──────────────────────────────
   只算 det=true 的節點:Verlet + 折皺力 + 鑷子抓取 + PBD 距離約束
   ▼
Delaunay 重網格:flip / split / collapse 維持三角形品質
   ▼
渲染:灰=Attached、藍=瓣膜、隱藏=切開的縫
```

關鍵心法:**Layer B 決定「撕痕往哪走」,Layer A 決定「膜長什麼樣」,兩者各算各的**;
中間只有一條**單向**橋(B→A),A 的物理結果永遠不回頭影響 B。這就是論文的「解耦」。

---

## 1. Layer B:你拉 + drift → 撕痕方向 → tip 前進

狀態變數:
- `tip` — 撕痕尖端座標
- `curr` — 撕痕目前方向(單位向量)
- `path` — 撕痕走過的折線(point-in-polygon 用)
- `C=(CX,CY)` — 撕囊中心(drift 的參考點)

每幀(按住、且鑷子離尖端夠遠 = 張力 `tension>1`)執行:

```js
const PullDir = vnorm(mouse - tip);      // 你拉的方向
const DriftDir = vnorm(tip - C);         // 永遠指向周邊(懸韌帶張力)
const thP = signedAngle(curr, PullDir);  // 你拉 與 撕痕方向 的夾角
const thD = signedAngle(curr, DriftDir);

// 手法自動判定:拉的方向 ⊥ 撕痕 → ripping;∥ 撕痕 → shearing
mode = Math.abs(thP) > 0.9 ? 'ripping' : 'shearing';   // 0.9rad ≈ 51°

let driftA, pullA;                       // 兩個帶正負號的旋轉角(論文 §3.1)
if (mode === 'shearing') {
  driftA = 0.012 * sign(thD);            // drift 影響小
  pullA  = clamp(thP, ±0.06);            // 裂痕「跟著」你拉(小幅修正)
} else { // ripping
  driftA = 0.05 * sign(thD);             // drift 影響大
  pullA  = clamp(0.15 * thP, ±0.10);     // 只取夾角的一小部分 → 裂痕保持~垂直於拉、漸展開
}
curr = rotate(curr, driftA + pullA);     // 新方向 = 繞著轉 (DriftAngle + PullAngle)
tip  = tip + curr * step;                // 沿新方向前進一小段(step ∝ tension)
path.push(tip);
```

對應論文 §3.1:`新方向 = rotate(CurrDir, DriftAngle + PullAngle)`。
- **shearing**:`PullAngle` 取完整夾角(有上限)→ 裂痕跟著器械走,只能小幅偏。
- **ripping**:`PullAngle` 只取夾角的「一小部分 (0.15)」→ 你**垂直拉**時裂痕**保持垂直方向往前展開**,靠 drift 慢慢繞 → 把整片漸漸拉開。

> 這整段**沒有任何 mass-spring**——它只吃兩個方向向量。換成別的膜模型也一行不用改 → 即時。

---

## 2. 橋:單向把結果丟給 Layer A(Attached 旗標 + 切斷)

撕痕前進的同一幀,順手做兩件事,決定 Layer A 的「範圍」與「拓樸」:

### (a) inPoly → Attached=FALSE(誰是瓣膜)
```js
for (const n of nodes)
  if (!n.det && inPoly(n.x, n.y)) { n.det = true; n.px = n.x; n.py = n.y; }
```
`inPoly` 用 ray-casting 判斷節點是否落在**撕痕圍出的多邊形** `[start, ...path, tip]` 內側。
內側 → `det=true`(Attached **TRUE→FALSE**),成為瓣膜的一部分;`px,py` 設成現值,讓 Verlet 初速為 0(不跳動)。
外側節點維持 `det=false`,**凍結在原格子當錨**(不參與物理 → 便宜)。

### (b) segCross → severed(哪裡被切開)
```js
for (const e of buildEdges().values())
  if (segCross(prevTip, tip, nodes[e.a], nodes[e.b])) severed.add(key(e.a,e.b));
```
`segCross` 判斷「撕痕尖端這一幀走的線段 prevTip→tip」是否**穿過**某條網格邊;穿過就加入 `severed`。
被切斷的邊 → 其相鄰三角形在 `triActive()` 被判定為 inactive → **不畫、不參與物理 = 一條縫**。

> ⚠️ 已知小瑕疵見 §5:`inPoly`(面)與 `segCross`(線)兩套判斷不完全吻合,加上重網格新生邊,會讓**極少數邊界邊漏切**。

---

## 3. Layer A:脫離節點的 mass-spring / PBD + 鑷子折皺

只對 `freed(n) = n.det && !n.dead` 的節點做物理;`Attached` 節點固定不動(邊界條件)。每幀:

```js
// (1) Verlet 積分:慣性 + 阻尼(給「被拉、會晃」的手感)
for (freed n) { const vx=(n.x-n.px)*0.9, vy=(n.y-n.py)*0.9; n.px=n.x; n.py=n.y; n.x+=vx; n.y+=vy; }

// (2) 折皺力:論文「the patch is folded and crumpled by the surgical instrument」
//     整片脫離節點都往鑷子靠 2.8% → 整片被帶起、折皺
if (gripping) for (freed n) { n.x += (mouse.x-n.x)*0.028; n.y += (mouse.y-n.y)*0.028; }

// (3) 鑷子抓取:離滑鼠最近的脫離節點 → 釘在滑鼠上(器械夾住瓣膜)
gi = argmin_{freed} dist(n, mouse);

// (4) PBD 距離約束投影 ×5:把每條邊兩端搬回接近原長 → 維持膜的形狀
for (it = 0..4) {
  nodes[gi] = mouse;                       // 抓取點固定
  for (active edge a-b, 非抓取點) {
    d = |b-a|; diff = (d - restLen(a,b)) / d;
    // 太長就互相靠近、太短就推開;一端是 Attached(固定)則另一端吃全部修正
    move a,b along edge by ±diff
  }
}
```

要點:
- **rest length** = 節點**原始格子座標**間距(`restLen` 用 `rx,ry` 算)→ 膜記得自己原本的形狀。
- **PBD = 用「直接搬位置」取代「施力」**:沒有彈力、沒有能量儲存 → 比純彈簧穩定。迭代次數 = 剛度(多=硬、少=軟,這裡用 5,偏軟好折皺)。
- 安全網:NaN 防護 + 節點數上限,防極端情況炸到無限遠(平常無感)。

> 為何只算脫離節點?因為**整片囊膜大多是 Attached(凍結、免費)**,只有撕到的那一小坨要算 → 即時的關鍵(撕到哪、算到哪)。見 [`ccc_method/2 remesh`](../ccc_method/2_topological_remesh.md)。

---

## 4. Delaunay 重網格:flip / split / collapse(維持品質)

膜被拉變形、撕痕穿過時,三角形會變爛 → 每幀沿著變形處整理(論文 §3.2,Nienhuys 法,見 [`ccc_method/2 remesh`](../ccc_method/2_topological_remesh.md)):

| 函式 | 動作 | 觸發條件 |
|---|---|---|
| `flipPass` | **Delaunay 翻邊**:邊不符空外接圓性質就翻 | `inCircle(a,b,c,d) > 0`(對面點落在外接圓內) |
| `splitPass` | **切長邊**:插中點、一分為二 | `dist(a,b) > 2.1 × restLen` |
| `collapsePass` | **併短邊**:把一端併入另一端 | `dist(a,b) < 0.4 × restLen`(且兩端皆脫離) |

`flipPass` 的核心(空外接圓判準):
```js
// 邊 (a,b) 兩側三角形的對角點 c,d;若 d 落在 (a,b,c) 外接圓內 → 非 Delaunay → 翻成 (c,d)
let inc = inCircle(a,b,c,d); if (orient(a,b,c) < 0) inc = -inc;
if (inc > 1e-6) { tris = [a,c,d],[b,c,d]; }   // 翻邊 → 最小角變大、消除 sliver
```
這些操作只在尖端/變形處局部發生,所以即時。

---

## 5. 已知小瑕疵:為何「撕一圈偶爾極少數還連著」

兩個原因疊加(對應 §2 的判斷不一致):

1. **segCross 漏網**:「脫離」用 `inPoly`(面內外)、「切斷」用 `segCross`(線有沒有穿過)。兩條曲線不完全重合 → 邊界上**有些「脫離↔黏著」的邊,尖端沒從它身上跨過去** → 沒切到。
2. **remesh 橋接**:`flipPass`/`splitPass` 會**新長出邊**;若新邊一端脫離、一端黏著,就把剛切開的縫**又接回去**(不在 `severed` 名單裡)。

> 一刀切的修法(「只要一端脫離一端黏著就一律切斷」)能解決,但會把**整圈邊界三角形都判成切斷而隱藏 → 看不到脫離區**,所以目前保留原狀。要徹底修需讓「脫離判斷」與「切斷判斷」用同一套來源,並在每次 remesh 後重新標記跨界邊——屬可改進項。

---

## 6. 一句話總結

```
Layer B(規則)  你拉 + drift → curr → tip 前進        ← 純幾何,即時,可換膜
   │ 單向:inPoly→Attached=FALSE、segCross→切斷
   ▼
Layer A(物理)  脫離節點 Verlet + 折皺 + PBD 約束       ← 只算一小坨,穩定
   +  Delaunay flip/split/collapse 維持網格
```
- **解耦**讓即時(≥30Hz)與逼真兼得。
- 對照:[`demo_decoupling_tear`](../demo_decoupling_tear.html) 只有 Layer B;[`demo_shearing_ripping`](../demo_shearing_ripping.html) 是 Fig 3 的側視 3D 折疊;本檔是 Fig 2 / §3.2 的俯視完整實作。
