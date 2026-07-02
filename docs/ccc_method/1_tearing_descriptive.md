# CCC Indicator 撕裂演算法(shearing / ripping)

來源:**Weber, Wagner & Männer 2006**, "Simulation of the Continuous Curvilinear Capsulorhexis Procedure"
(整個 CCC 群組裡實作最完整的一篇)。

---

## 0. 最關鍵的設計決定:撕裂 ⊥ 囊膜變形(解耦)

物理正確地模撕囊需要**非線性模型 + 拓樸改變**,運算量太高,達不到即時(≥30Hz)。
所以**把撕裂傳播和囊膜變形拆成兩層**:

```
Layer A 囊膜變形 = mass-spring(docs 02)  →「掀起的膜瓣怎麼飄」+ 算應力,次要
Layer B 撕裂傳播 = Indicator 描述式演算法  →「撕痕下一步往哪走」,核心
```
> 囊膜的 stress **只用來「觸發」撕裂**;一旦觸發,撕往哪走**完全由 Layer B 決定,不依賴物理模擬**。
> 這個解耦 = 即時的關鍵;mass-spring 參數與時間積分變得「不敏感、怎麼設都行」。

### 應力觸發(兩層怎麼接起來)
```
mass-spring(Layer A)算膜瓣應力 → 應力 ≥ 門檻? ──否──► 撕痕不動,膜瓣只被拉變形
                                      │是
                                      ▼
                              觸發撕一步 → Layer B 算方向 → 末端前進固定距離
```
- **應力(來自 mass-spring)只決定「何時撕」**(醫生拉夠緊才撕)——物理真實手感。
- **應力不決定「往哪撕」**——方向由 Layer B 的描述式算(CurrDir/DriftDir/PullDir)——可控、可教。
- 這正是「混合 = 應力觸發 when + 描述式控制 where」的由來,**就是 Weber 2006 本身的設計**。

## 0b. EyeSi 撕囊的端到端流程(每一幀)

囊膜 = 三角網格;每節點有 `Attached` 旗標:True=黏在水晶體不動,False=剝離的膜瓣(才跑 mass-spring)。
撕痕末端 = 一個沿囊膜表面走的點。
```
1. 讀鑷子位置 → 夾住的膜瓣節點跟著鑷子跑
2. Layer A:對 Attached=False 節點跑 mass-spring → 膜瓣變形 + 算應力
3. 應力觸發:應力 ≥ 門檻 → 撕一步;否則撕痕不動
4. Layer B:算撕痕方向(切平面,§3),末端前進一小段固定距離
5. 拓樸:remesh(docs 07);撕裂前緣掃過的節點 Attached: True→False(膜瓣長大)
6. 繪圖(立體 + 陰影)
```
兩層耦合點:Layer A 算應力 → 觸發 Layer B;Layer B 前進 → 改 Attached → 回饋 Layer A;
鑷子同時驅動兩層(夾住節點推 Layer A,尖端給 Layer B 的 PullDir)。

## 1. 兩種手法(來自 Seibel《Phacodynamics》)

| | **Shearing(剪切)** | **Ripping(撕扯)** |
|---|---|---|
| 膜瓣怎麼放 | 攤平,內面朝上 | 折起,內面朝向水晶體 |
| 撕痕跟隨 | 大致跟著器械移動 | 要圓須**往水晶體中心拉**(反直覺) |
| 改方向能力 | 只能小幅修正 | 能大幅急轉、**救歪掉的撕痕** |

## 2. 自動判斷手法 → `Indicator`

```
觀察「撕痕末端旁、且屬於已剝離膜瓣」的三角形法向量(normal):
  若法向量朝向水晶體表面 → Indicator := Shearing
  否則                    → Indicator := Ripping
```
等於**從膜瓣被折的方向,自動偵測醫生用哪種手法**,不需手動輸入。

## 3. 撕裂方向計算(切平面上的向量合成)

水晶體是光滑凸面。在撕痕末端,用**水晶體表面法向量**定義一個**切平面(tangent plane)**,
所有計算在此 2D 平面上做。投影出三個向量(對應論文 Fig 4):

| 向量 | 符號 | 意義 |
|---|---|---|
| `CurrDir` | c | 目前撕痕方向 |
| `PullDir` | p | 器械拉的方向(器械尖端投影) |
| `DriftDir` | d | **漂移方向,指向周邊**(模擬懸韌帶張力 → 撕囊難的根源) |

**新方向 = 把 CurrDir 繞切平面法向量旋轉一個角度:**

$$\text{newDir} = \text{rotate}\big(\text{CurrDir},\ \text{DriftAngle} + \text{PullAngle}\big)$$

- `DriftAngle` = 往 DriftDir(周邊)轉多少
- `PullAngle` = 往 PullDir(拉的方向)轉多少
- **兩角度取決於 Indicator**:

```
if Indicator == Shearing:
    DriftAngle = 小常數                         # 漂移影響小
    PullAngle  = angle(CurrDir, PullDir)
    PullAngle  = min(PullAngle, MAX_shear)      # 只能小幅修正(上限低)

if Indicator == Ripping:
    DriftAngle = 較大值                          # 漂移影響大(易往周邊跑)
    PullAngle  = FRACTION * angle(CurrDir, PullDir)   # 模擬「拉向近乎垂直」的反直覺行為
    PullAngle  = min(PullAngle, MAX_rip)        # 上限高 → 允許急轉、救援
```
- 每步:撕痕末端**沿新方向前進一小段固定距離**,然後更新網格(見 docs 07)。

## 4. 為何這能重現真實行為

- 新手不慎從 **shearing 切到 ripping** → 拉的方向不對 → **撕痕暴衝往周邊** = 真實世界最常見的撕囊失敗。
- 醫學文獻建議用**受控 ripping** 救歪掉的撕痕 → 模型中只有 ripping 能大幅急轉 →
  訓練者學會用 planned ripping maneuver 救援。

→ 對應虛擬碼:[`../pseudocode/ccc_tearing.py`](../pseudocode/ccc_tearing.py)

---

## 真實度(realism)

- **物理地位**:純**描述式**——直接把醫學教科書的操作指南翻成幾何規則,不解組織應力場。
- **驗證**:眼科醫師驗證「撕痕行為夠真實,足以用於撕囊訓練」。
- **限制(Weber 2006 自述)**:
  - 撕痕是**單一、預先初始化**的,不能在過程中於任意位置下刀;
  - 後續工作:**多重撕痕**(整合初始切口)+ **黏彈性流體注入**影響組織。
