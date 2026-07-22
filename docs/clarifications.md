# 釐清 FAQ(精簡)

> 🔖 **隨查層(Lookup)**——非主幹,需要時翻。閱讀主幹見 [`overview.md`](overview.md) 的 START HERE。

把學習過程中釐清的關鍵事實集中於此。

## 引擎 / ECM

**Q：被夾座標的「元素(element)」是什麼?**
代表組織的**離散格點**。體積物(玻璃體/水晶體核)= 3D 規則格點、每點連 6 鄰;表面/膜(囊膜)= 2D 格點、每點連 4 鄰。
mass-spring 叫 mass/node、FEM 叫 node、ChainMail 叫 element——**都是「代表組織的點」**。

**Q：ECM 具體在夾什麼?**
夾**元素的座標 (x,y,z)**,使**相鄰元素的距離(與剪切)**待在 [min, max] 內。
太遠→沿連線拉到 max;太近→推到 min。不算力、不用 F=ma。

**Q：EyeSi 都用 ECM 嗎?**
否。EyeSi 是工具箱(vrmDesign),不同部位用不同引擎:ECM 規劃用於**玻璃體**(3D 穩定);
mass-spring 用於**膜**;**撕囊模組(Weber 2006)= mass-spring 囊膜 + 描述式撕裂**。

**Q：為何叫 ECM(Enhanced ChainMail)?**
ChainMail = 行為像中世紀鎖子甲(拉一環、鬆弛被吃掉、繃緊才拖下一環);
Enhanced = Schill 增強原始版以支援**非均質材料**(改用「違反量最大者優先」)。

## 撕囊兩層

**Q：ECM 能算出撕痕方向(CurrDir/DriftDir/PullDir)嗎?**
**不能。** 算方向是 **Layer B(Weber 描述式撕裂)** 的事;ECM/mass-spring 是 **Layer A**,只管變形與應力。
問「ECM 能否算方向」= 問「引擎能否決定方向盤」——不行,不同零件。

**Q：兩層怎麼接(解耦後的應力觸發)?**
- Layer A(mass-spring)算膜瓣**應力**。
- 應力 ≥ 門檻 → **觸發** Layer B 撕一步;否則撕痕不動、膜瓣只被拉變形。
- Layer B 算**方向**(切平面 CurrDir+DriftDir+PullDir)、末端前進固定距離。
- **應力決定「何時撕」(物理),描述式決定「往哪撕」(可控)。** 這就是 Weber 2006 的設計。

**Q：撕痕方向怎麼理解?**
撕痕末端 = 會走的點;每幀算一個方向向量(c 往 p、d 各轉一點)、走一小步、remesh。
不是一次算整圈,而是**一步步走描出曲線(理想是圓)**。

**Q：切平面 / CurrDir / DriftDir / PullDir?**
水晶體是彎曲球面,撕痕是其上的 2D 路徑。在末端鋪一張貼著球面的平面(切平面)以便算角度。
c=CurrDir 目前走向、p=PullDir 鑷子拉向、d=DriftDir 往周邊漂移(懸韌帶張力,撕囊難的根源)。
新方向 = rotate(c, 往d轉 DriftAngle + 往p轉 PullAngle);角度大小由 shearing/ripping 決定。

## 兩條撕裂路線

| | 應力驅動(EYESIM/Ch4) | 描述式 Indicator(Weber) | 混合(= Weber 實際做法) |
|---|---|---|---|
| 何時斷 | 彈簧超伸即斷 | 固定步前進 | **應力超門檻才斷(物理)** |
| 往哪斷 | 往最大應力(易暴衝) | 拉力+漂移+手法(可控) | **描述式(可控)** |
| 適合 | — | — | **訓練器:物理手感 + 可教控制** |
