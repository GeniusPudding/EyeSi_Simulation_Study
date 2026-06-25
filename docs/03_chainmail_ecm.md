# 03 — ChainMail / Enhanced ChainMail:數學 → 虛擬碼 → 真實度

來源:Schill 2001 Ch4(ChainMail by Gibson 1997;ECM 為 Schill 的貢獻)。
**一句話**:不算力,用**幾何規則「夾位置」**——把鄰居夾回它和你的合法距離內,一個 pass 傳播完。

---

## 1. 與 mass-spring 的根本對比

| | Mass-Spring | ChainMail |
|---|---|---|
| 你做什麼 | **算力** F 再積分 | **夾位置**(clamp)直接搬 |
| 怎麼動 | F=ma → 速度 → 位置(多時間步) | 夾到合法距離(一個 pass) |
| 慣性/時間 | 有 | 無(t 藏在處理順序裡) |
| 驅動 | 力驅動 | **位移驅動**(把 sponsor 搬到新位置) |

## 2. 資料結構(沒有質量、沒有速度)

```
Element: pos                       # 只有位置
Link(a,b): minDist, maxDist, maxShear   # 約束「就地」存在每條 Link
```
- 每個 element 連最近鄰(2D 4 個 / 3D 6 個)。
- **材料軟硬藏在約束**:軟 = maxDist 大(rest 10 → max 15);硬 = maxDist≈rest(rest 10 → max 10.5)。
- **約束就地存 → 每條可不同 → 能模非均質**(mass-spring 用全域 k 做不到)。

## 3. 核心操作:約束檢查 + 夾位置(ChainMail 的「虎克定律」)

```
給定鄰居 x、其 sponsor x_s:
  if (x − x_s) < minDist:  x = x_s + minDist   # 太近 → 推到最小距離
  if (x − x_s) > maxDist:  x = x_s + maxDist   # 太遠 → 拉到最大距離
  否則: 不動
```
3D 多一條剪切約束(垂直方向夾在 ±maxShear)。
**數字**:鄰居 x=10、sponsor 移到 −8、maxDist=11 → 距離18>11 → 夾到 x = −8+11 = **3**。

## 4. 傳播:一個 pass 的連鎖(1D 走查)

初始 E0..E3 = 0,10,20,30(rest=10,**maxDist=11**)。把 **E0 往左拉 8 → E0=−8**:
```
E1 vs E0: 18>11 → E1 = −8+11 =  3   (移7)
E2 vs E1: 17>11 → E2 =  3+11 = 14   (移6)
E3 vs E2: 16>11 → E3 = 14+11 = 25   (移5)
→ 全部=11,結束
```
**三個精髓**:
1. 每鏈吸收 1 單位 → 位移每段遞減 1。
2. **拉 8 只影響 ~8 個元素** → 局部性 → **線性複雜度**(處理時間 ∝ 受影響元素數)。
3. **一個 pass 定形**(不像 mass-spring 跑幾百步)。

## 5. 為何原始 ChainMail 碰非均質會撕裂

原始版用**固定順序**(先右左、再上下),**每元素只處理一次**。
剛硬塊嵌在軟組織裡時,某 element 可能相對於「還沒被正確安置的鄰居」被夾位置,
而**只處理一次、不回頭修正** → 剛硬塊內部不一致 → **被扯破**。

## 6. Enhanced ChainMail 的修正:違反最大者優先

```
違反量 = 當前距離 − maxDist
```
維護一條**依違反量排序的清單**(binary tree / 優先佇列),**永遠先處理違反最嚴重者**。

**為何救剛硬塊**:剛硬材料 maxDist 極小 → 一被波及就**嚴重違反** → 被最優先處理 →
**整塊一起剛性移動**,在軟組織把它扯歪前就先就位。

**複雜度**:$O(\#dispDir \times \#nodes)$(2D),3D 多一個 objectDim 因子。
線性來自**局部性**;「近乎」線性的 log 因子來自**排序清單的二元樹插入 O(log n)**。

## 7. ECM pseudocode

```
initialSponsor.pos = newPos
queue = SortedQueue(by = 違反量, 大的在前)
for nb in neighbors(sponsor): queue.insert(nb, sponsor)
while queue not empty:
    elem, spons = queue.pop_largest_violation()
    if clamp_to_constraints(elem, spons):   # 有移動
        for nb in neighbors(elem):
            if nb != spons: queue.insert(nb, elem)
```
> 與原始版唯一差別:原始用 4 條固定順序清單;ECM 用 **1 條依違反量排序的清單**。

→ 對應虛擬碼:[`../pseudocode/chainmail_ecm.py`](../pseudocode/chainmail_ecm.py)

## 8. 補物理:彈性鬆弛(接回 mass-spring)

ChainMail 定形後能量可能不均,跑第二步 **mass-spring 鬆弛**攤勻能量:
```
for link: deflection = |d| − restLength
          move = dir * springConst * deflection / 2
          a.pos += move; b.pos -= move
```
- 每跑完一輪都在合法 ECM 狀態 → **可隨時中斷**(完整 mass-spring 鬆弛若中斷會把節點推出界 → 致命)。
- 這就是「**描述式打底 + 物理修正**」的具體實現。

## 9. ChainMail = mass-spring 的極限版

階躍彈簧(拉伸 < maxDist 力=0,≥ maxDist 力=∞)+ 無限阻尼 的 mass-spring,
其最終形狀 = ChainMail。**[min,max] 約束 = 階躍彈簧力的幾何化身。**

---

## 真實度(realism)

- **物理地位**:描述式(基礎是幾何約束),但用彈性鬆弛注入部分物理。
- **準確度**:幾何近似,不解連續體力學;但視覺合理、**穩定性極佳**(尤其 3D)。
- **優勢**:即時、局部、**可非均質**(就地約束)、可中斷;Schill 指出 3D 時穩定性明顯勝 mass-spring,
  計畫用於玻璃體(vitreous)。
- **弱點**:非真實物理量;絕對精度不如 FEM;非凸物體需特殊處理。
