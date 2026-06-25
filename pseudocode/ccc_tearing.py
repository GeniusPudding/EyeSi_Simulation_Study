"""
CCC(撕囊)Indicator 撕裂演算法 + 兩層整合(教學用虛擬碼)
對應文件:docs/06_ccc_tearing.md、docs/07_topological_changes.md、docs/08_architecture.md

核心:撕裂傳播(Layer B,描述式)與囊膜變形(Layer A,mass-spring)解耦。
      Layer B 決定撕痕往哪走;Layer A 只讓掀起的膜瓣飄動。
"""

SHEARING = "shearing"
RIPPING = "ripping"


def detect_indicator(tear_end, lens):
    """
    從膜瓣被折的方向自動判斷手法。對應 docs/06 §2。
    看撕痕末端旁、屬於已剝離膜瓣的三角形法向量:朝向水晶體 -> shearing,否則 ripping。
    """
    tris = adjacent_detached_triangles(tear_end)
    if all(faces_lens_surface(t.normal, lens) for t in tris):
        return SHEARING
    return RIPPING


def next_tear_direction(tear_end, instrument_tip, lens, params):
    """
    在切平面上把 CurrDir 旋轉 (DriftAngle + PullAngle) 得新撕裂方向。
    對應 docs/06 §3。
    """
    # 1) 切平面:水晶體表面法向量 + 撕痕末端定義 tangent plane
    n = lens_surface_normal(tear_end, lens)        # 切平面法向量(旋轉軸)

    # 2) 三個向量投影到切平面
    curr_dir = project(current_tear_dir(tear_end), n)         # c:目前撕痕方向
    pull_dir = project(sub(instrument_tip, tear_end), n)      # p:器械拉的方向
    drift_dir = project(periphery_dir(tear_end, lens), n)     # d:漂移(指向周邊,懸韌帶張力)

    indicator = detect_indicator(tear_end, lens)

    # 3) 依手法算兩個旋轉角(對應 docs/06 §3 的 if/else)
    if indicator == SHEARING:
        drift_angle = params.DRIFT_SMALL                         # 漂移影響小
        pull_angle = min(angle(curr_dir, pull_dir), params.MAX_SHEAR)  # 只能小幅修正
    else:  # RIPPING
        drift_angle = params.DRIFT_LARGE                         # 漂移影響大(易往周邊跑)
        pull_angle = min(params.FRACTION * angle(curr_dir, pull_dir), params.MAX_RIP)  # 允許急轉

    total_angle = signed(drift_angle, toward=drift_dir) + signed(pull_angle, toward=pull_dir)
    return rotate_around(curr_dir, axis=n, angle=total_angle)


def advance_tear(tear_end, direction, step, mesh, mass_spring_nodes):
    """撕痕前進一小段 + 拓樸改變 + 解放節點。對應 docs/07。"""
    new_end = add(tear_end.pos, scale(direction, step))
    tear_end.pos = new_end

    # 拓樸 remeshing(docs/07 §1):collapse / split / Delaunay flip
    for nb in adjacent_nodes(tear_end, mesh):
        if length(sub(tear_end.pos, nb.pos)) < mesh.COLLAPSE_THRESHOLD:
            mesh.collapse(nb)                       # 太近 -> 刪鄰居節點
    for edge in tearing_edges_behind(tear_end, mesh):
        if edge.length() > mesh.SPLIT_THRESHOLD:
            mesh.split(edge)                        # 太長 -> 切分
    for edge in surrounding_edges(tear_end, mesh):
        if not is_delaunay(edge):
            mesh.flip(edge)                         # 維持三角形品質

    # 膜瓣長大(docs/07 §2):撕裂前緣掃過的節點 Attached: True -> False
    for node in nodes_passed_by_tearing_front(tear_end, mesh):
        node.fixed = False                          # 解放進 mass-spring(= Attached False)


# === 整個 CCC 模擬器每一幀(docs/08 §1 兩層整合)===
def frame(instrument_tip, lens, mesh, ms_nodes, ms_springs, dt, params):
    # --- Layer B:撕裂傳播(描述式)---
    tear_end = mesh.tear_end
    direction = next_tear_direction(tear_end, instrument_tip, lens, params)
    advance_tear(tear_end, direction, params.STEP, mesh, ms_nodes)

    # --- Layer A:囊膜變形(mass-spring,只跑 fixed==False 的節點)---
    import_from = "see pseudocode/mass_spring.py :: simulate_step"
    simulate_step(ms_nodes, ms_springs, dt)         # 飄動的膜瓣

    # --- 繪圖(立體 + 陰影,深度線索)---
    render(mesh, stereo=True, shadow=True)

# 備註:本演算法為「單一預先初始化的撕痕」;多重撕痕 + 黏彈性流體為 Weber 2006 的後續工作。
