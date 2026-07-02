# 系統架構:兩層整合、Node+Connector、vrmDesign → SOFA

來源:Schill 2001 Ch5(vrmDesign);Weber 2006(兩層);現代對應 SOFA。

---

## 1. 兩層架構(CCC 模擬器的骨架)

```
┌──────────────────────────────────────────────┐
│ Layer B:撕裂傳播 = Indicator 描述式(docs 06)   │  決定撕痕往哪走
│   + 拓樸改變 remeshing(docs 07)                │
├──────────────────────────────────────────────┤
│ Layer A:囊膜變形 = mass-spring(docs 02)        │  掀起的膜瓣怎麼飄
│   (只跑 Attached==False 的節點)                 │
└──────────────────────────────────────────────┘
       共用同一份節點(Node)
```

## 2. 統一抽象:Node + Connector(vrmDesign 的核心)

Schill 發現 mass-spring、FEM、ChainMail、甚至 OpenGL 繪圖,底層都是**點 + 連接**:

| 方法 | 點 | 連接 |
|---|---|---|
| mass-spring | mass | spring |
| FEM | node | element |
| ChainMail | element | chain |
| OpenGL | vertex | triangle |

→ 抽象成:
- **Node** = 空間離散化的點(位置 + 屬性)
- **Connector** = 排序原則(2-connector=彈簧/鏈,3-connector=三角形,1-connector=查找表/串列)
- **雙向指標**:節點知道自己連哪些 connector,connector 知道自己連哪些節點。
  → ChainMail 靠此**不需全域結構**,從 sponsor 沿圖局部旅行。

## 3. 「一組共用節點 + 多組件插在上面」是什麼意思

```
一份 Node 清單(位置的唯一真相來源)
   ▲          ▲           ▲
碰撞組件     模擬組件      繪圖組件     ← 三段程式都讀寫同一份節點
```
- 像一份共編的 Google 文件:三個編輯者(碰撞/模擬/繪圖)改同一份文件,**不各存影本、不用手動對帳**。
- 解掉 Schill 講的「**多重表示(multiple representations)**」惡夢(模擬/繪圖/碰撞各一套會不同步)。
- **組件(component)= 只做一件事、插在共用節點上的模組**(Entity-Component 模式)。
- 想加功能就插新組件(例如 AR 疊加、技能評分),不動底層資料。

## 4. 執行期可換演算法(ECM → mass-spring 鬆弛)

- 一個節點可**同時繼承兩演算法的屬性**(vrmChainNodeBase + vrmMassNodeBase),位置存在共用基底。
- 換演算法 = 同一張圖上換 simulation 物件,**零複製**。
- 所以「ECM 快速定形 + mass-spring 鬆弛」是同一份資料上接力,不是兩套程式硬接。

## 5. vrmDesign 本身能用嗎?→ 用 SOFA

- **vrmDesign = Schill 2001 的私有 C++ 框架**,從未公開,後成 EyeSi/VRmagic 商品內部引擎 → **無法直接使用**。
- **現代開源後繼者 = [SOFA](https://www.sofa-framework.org/)**(INRIA,即 EyeSi 文獻庫門派④):
  - scene-graph + component 架構,與 vrmDesign 同哲學;
  - 內建 mass-spring / co-rotational FEM / 等,**快或準你每個物體自己選**;
  - 為即時互動手術模擬而生(GPU、降階、coarse-sim↔fine-visual mapping)。
  - **誤解澄清**:SOFA 不是「只能 FEM、太物理」;它是框架,描述式(mass-spring / 自訂)完全可行,
    甚至能把 ChainMail 寫成自訂 component。

## 6. 建議實作路線

```
用 SOFA 搭場景圖
 ├─ MechanicalObject(節點) ← 囊膜網格
 ├─ MassSpringForceField     ← Layer A(docs 02)
 ├─ 自訂 TearComponent       ← Layer B Indicator(docs 06)
 ├─ 自訂 Remeshing           ← 拓樸改變(docs 07)
 └─ OglModel(繪圖)+ 立體 + 陰影(深度線索)
```
