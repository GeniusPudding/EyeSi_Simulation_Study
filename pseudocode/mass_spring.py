"""
Mass-Spring 軟組織變形引擎(教學用虛擬碼)
對應文件:docs/02_mass_spring.md

原理:把物體離散成「有質量的質點 + 彈簧」,
      算力 F → 牛頓 a = F/m → 時間積分,跑多步晃到平衡。

注意:這是「可讀、對應公式」的虛擬碼,非最佳化實作。
      向量運算(+ - * / length)假設為 3D 向量。實務建議用 SOFA。
"""


class Node:
    def __init__(self, pos, mass=1.0, damping=0.5, fixed=False):
        self.pos = pos          # 位置 (x, y, z)
        self.vel = (0, 0, 0)    # 速度
        self.mass = mass
        self.damping = damping  # 阻尼係數 gamma
        self.fixed = fixed      # True = 固定不動(= CCC 的 Attached)


class Spring:
    def __init__(self, i, j, rest_length, k):
        self.i = i              # 連接的節點 a
        self.j = j              # 連接的節點 b
        self.rest_length = rest_length   # 靜止長度 R
        self.k = k              # 彈簧係數(軟硬)


def simulate_step(nodes, springs, dt, gravity=(0, -9.8, 0)):
    """一個時間步。對應 docs/02 的 §6 時間積分。"""
    # 0) 先放外力(重力等)。對應運動方程的 f_i
    force = {n: scale(gravity, n.mass) for n in nodes}

    # 1) 累加每條彈簧的虎克力到兩端。對應 §3① g_ij
    for s in springs:
        d = sub(s.j.pos, s.i.pos)          # i -> j 向量
        L = length(d)
        if L == 0:
            continue
        direction = scale(d, 1.0 / L)      # 單位方向 (x_j - x_i)/||...||
        stretch = L - s.rest_length        # 拉伸量 = 當前長 - 靜止長
        f_spring = scale(direction, s.k * stretch)   # = dir * k * stretch
        force[s.i] = add(force[s.i], f_spring)        # 對 i 往 j 拉
        force[s.j] = sub(force[s.j], f_spring)        # 對 j 反方向(反作用力)

    # 2) 阻尼 + 牛頓積分,更新每個節點。對應 §2、§3②、§6
    for n in nodes:
        if n.fixed:                        # 固定點(還黏在水晶體上的囊膜)不動
            continue
        f_damp = scale(n.vel, -n.damping)  # 阻尼力 = -gamma * v
        f_total = add(force[n], f_damp)
        a = scale(f_total, 1.0 / n.mass)   # a = F / m  (牛頓第二定律)
        n.vel = add(n.vel, scale(a, dt))   # v += a * dt   (explicit Euler)
        n.pos = add(n.pos, scale(n.vel, dt))  # x += v * dt


# --- 向量小工具(示意) ---
def add(a, b):   return tuple(x + y for x, y in zip(a, b))
def sub(a, b):   return tuple(x - y for x, y in zip(a, b))
def scale(a, s): return tuple(x * s for x in a)
def length(a):   return sum(x * x for x in a) ** 0.5


# === 穩定性備註(docs/02 §7)===
# explicit Euler(上面):硬彈簧(k 大)+ 大 dt -> 衝過頭 -> 數值爆炸。
# 解法:(a) 用小 dt;(b) 改 implicit/semi-implicit solver(穩定、可大 dt,
#       但每步要解方程組;Webster 用「預先算好近似解」加速)。
