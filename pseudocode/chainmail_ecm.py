"""
Enhanced ChainMail(ECM)變形引擎(教學用虛擬碼)
對應文件:docs/03_chainmail_ecm.md

原理:不算力,用幾何規則「夾位置」——把鄰居夾回它和 sponsor 的合法距離內,
      依「約束違反量」由大到小處理,一個 pass 傳播完。可模非均質、穩定、即時。
"""


class Element:
    def __init__(self, pos):
        self.pos = pos          # 只有位置,沒有質量、沒有速度
        self.links = []         # 連到的 Link(雙向指標 -> 不需全域結構)


class Link:
    def __init__(self, a, b, rest, min_dist, max_dist, max_shear):
        self.a = a
        self.b = b
        self.rest = rest
        self.min_dist = min_dist    # 約束:距離下限
        self.max_dist = max_dist    # 約束:距離上限(材料軟硬就藏在這:硬->max≈rest)
        self.max_shear = max_shear  # 約束:剪切上限


def violation(elem, sponsor):
    """約束違反量 = 當前距離 - max_dist(超標多少)。對應 docs/03 §6"""
    link = link_between(elem, sponsor)
    d = length(sub(elem.pos, sponsor.pos))
    return d - link.max_dist


def clamp_to_constraints(elem, sponsor):
    """把 elem 夾到與 sponsor 的合法距離內,回傳是否移動。對應 docs/03 §3"""
    link = link_between(elem, sponsor)
    d = sub(elem.pos, sponsor.pos)
    L = length(d)
    if L == 0:
        return False
    direction = scale(d, 1.0 / L)
    if L > link.max_dist:                                  # 太遠 -> 夾到 max
        elem.pos = add(sponsor.pos, scale(direction, link.max_dist))
        return True
    if L < link.min_dist:                                  # 太近 -> 夾到 min
        elem.pos = add(sponsor.pos, scale(direction, link.min_dist))
        return True
    # (3D 另需檢查剪切 max_shear;此處省略)
    return False                                            # 在範圍內,不動


def ecm_move(initial_sponsor, new_pos):
    """
    Enhanced ChainMail 主流程(位移驅動)。對應 docs/03 §7。
    與原始 ChainMail 唯一差別:用「依違反量排序的單一清單」(原始版用 4 條固定順序清單)。
    """
    initial_sponsor.pos = new_pos

    # 依違反量排序的優先佇列(實作上常用 binary tree / STL multiset)
    queue = PriorityQueue(key=lambda pair: -violation(pair[0], pair[1]))  # 大的在前

    for nb in neighbors(initial_sponsor):
        queue.insert((nb, initial_sponsor))

    while not queue.empty():
        elem, sponsor = queue.pop()        # 取「違反最嚴重」者 -> 剛硬材料優先 -> 不被扯散
        if clamp_to_constraints(elem, sponsor):
            for nb in neighbors(elem):
                if nb is not sponsor:
                    queue.insert((nb, elem))
        # 清單空 = 全部滿足約束 -> 結束(一個 pass)
        # 複雜度 ~ O(受影響元素數);log 因子來自佇列插入(二元樹)


def relax(links, spring_const, passes=3):
    """
    彈性鬆弛:ECM 定形後用 mass-spring 攤勻能量(描述式打底 + 物理修正)。
    對應 docs/03 §8。每跑完一輪都在合法 ECM 狀態 -> 可隨時中斷。
    """
    for _ in range(passes):
        for link in links:
            d = sub(link.b.pos, link.a.pos)
            L = length(d)
            if L == 0:
                continue
            direction = scale(d, 1.0 / L)
            deflection = L - link.rest
            move = scale(direction, spring_const * deflection / 2.0)
            link.a.pos = add(link.a.pos, move)   # 兩端各往平衡挪一半
            link.b.pos = sub(link.b.pos, move)


def neighbors(elem):
    out = []
    for link in elem.links:
        out.append(link.b if link.a is elem else link.a)
    return out


# --- 向量小工具(同 mass_spring.py) ---
def add(a, b):   return tuple(x + y for x, y in zip(a, b))
def sub(a, b):   return tuple(x - y for x, y in zip(a, b))
def scale(a, s): return tuple(x * s for x in a)
def length(a):   return sum(x * x for x in a) ** 0.5

# link_between(a, b) / PriorityQueue 為示意,實作時補上。
