# Mass-Spring:數學 → 虛擬碼 → 真實度

來源:Schill 2001 §3.2;Webster 2004/2005。
**一句話**:把物體離散成「有質量的質點 + 彈簧」,**算力 → F=ma → 積分**,跑很多時間步晃到平衡。

---

## 1. 基本量(符號上的「點」= 對時間微分 = 每秒變化率)

| 量 | 符號 | 白話 |
|---|---|---|
| 位置 | x | 它在哪 |
| 速度 | v = ẋ | 位置每秒變多少 |
| 加速度 | a = ẍ | 速度每秒變多少 |

## 2. 引擎:牛頓第二定律

$$F = ma \quad\Longrightarrow\quad a = \frac{F}{m}$$

合力 ÷ 質量 = 加速度。越重(m 大)加速越慢。

## 3. 力 = 彈簧力 + 阻尼力 + 外力

### ① 彈簧力(虎克定律)
$$g_{ij} = \underbrace{\frac{x_j - x_i}{\|x_j - x_i\|}}_{\text{方向(單位向量)}} \times \underbrace{k_{ij}}_{\text{軟硬}} \times \underbrace{(\|x_j - x_i\| - R_{ij})}_{\text{拉伸量 = 當前長 − 靜止長 }R}$$

白話:**沿彈簧方向,大小 = 軟硬 × 拉伸多少**。被拉長(正)→ 往內拉;被壓短(負)→ 往外推。

### ② 阻尼力(防止永遠抖動)
$$ -\gamma_i\,\dot{x}_i = -\gamma_i v_i $$
方向永遠與速度相反(像在糖漿裡),把運動煞下來。沒有它彈簧永遠盪不停。

### ③ 外力 fᵢ
重力、鑷子拉力、撕扯力……

## 4. 每個質點的運動方程(= F=ma 而已)

$$\underbrace{m_i \ddot{x}_i}_{ma} = \underbrace{-\gamma_i \dot{x}_i}_{\text{阻尼}} + \underbrace{\sum_j g_{ij}}_{\text{所有連到它的彈簧力}} + \underbrace{f_i}_{\text{外力}}$$

## 5. 矩陣形式(只是把所有點的 F=ma 打包)

$$M\ddot{x} + D\dot{x} + Kx = f$$

- M = 質量矩陣(對角),D = 阻尼矩陣,K = 剛度矩陣,x = 所有點位置疊起來,f = 所有外力。
- 解:$\dot{v} = M^{-1}(-Dv - Kx + f),\ \dot{x} = v$。**M⁻¹ = ÷質量的矩陣版 → 就是 a = F/m。**
- 實作不需真的組大矩陣,用逐節點寫法即可(見虛擬碼)。

## 6. 時間積分(模擬迴圈的心臟)— explicit Euler

```
a = F / m
v_new = v_old + a * dt
x_new = x_old + v_new * dt
```
**數字實例**:m=1, v=(0,0,0), 受力(1,0,0), dt=0.1 → a=(1,0,0) → v=(0.1,0,0) → x 移 (0.01,0,0)。

## 7. explicit vs implicit(穩定性)

- **explicit(顯式)**:用「現在」的力算下一步。**硬彈簧(k 大)+ 大 dt → 衝過頭 → 爆炸**。
- **implicit(隱式)**:找一個下一步,讓它用「下一步」的力也自洽 → **天生穩定、可用大 dt**,代價是每步要解方程組。
  Webster 用「**預先算好近似解**」加速(*modified implicit predictor*)。
- 入門:explicit + 小 dt;硬組織:implicit。

→ 對應虛擬碼:[`../pseudocode/mass_spring.py`](../pseudocode/mass_spring.py)

---

## 真實度(realism)

- **物理上的地位**:介於物理與描述之間。用了質量、彈簧(物理詞),但**彈簧係數 k 通常靠調而非量測** → 偏描述式。
- **準確度**:不如 FEM。Keeve 的對比研究:FEM 比 mass-spring 準,但 mass-spring 對術前規劃常已夠準,且**能即時互動**。
- **拓樸網格依賴**:變形行為會受網格走向影響(各向異性假象)。
- **弱點**:穩定性/時間步爆炸;能量分布不保證均勻。
- **適用**:即時、對精度要求中等的軟組織(CCC 的囊膜 Layer A 就用它)。
