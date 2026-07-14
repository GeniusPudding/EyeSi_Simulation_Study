# Demo:方形紙躺在底座上,拉力超過黏著門檻才會被撕/剝離底座

`paper_gel_tear.py` 是一個**只用 stock SOFA** 的獨立示範場景(**不需要**編譯
`Capsulorhexis.dll`)。模型:一張**方形紙平躺在底座上**,被一層**有門檻的黏著**黏住;
你把一邊往上拉,**拉力(黏著力)超過門檻的地方就剝離底座**,像撕膠帶、也像水晶體
囊袋(capsule)從皮質剝離。門檻以下拉不動、黏著以下就停在原地。

## 執行

```powershell
.\Capsulorhexis\scenes\run_paper.ps1
# 實際包裝:runSofa -l SofaPython3 -g imgui -a scenes\paper_gel_tear.py
```

- 內建腳本會自動把**左邊**往上抬,你可以看到**剝離前緣**一路往右推進(console 印
  `[Peel] ... spots still glued`)。
- 你也可以 **Shift + 左鍵拖曳** 任一點自己拉:輕輕拉→黏著撐住不動;拉力超過門檻→
  該處黏著「啪」地斷開、剝離底座。

## 黏著門檻怎麼做的(核心)

- **黏著 = `RestShapeSpringsForceField`**:每個節點都被一條彈簧拉回它在底座上的位置
  (rest = 平躺的原位)。這就是「紙黏在底座上」。
- **門檻 = 一個小 controller**:每步算每個節點的黏著力 `f = ADHESION_STIFF × 抬起距離`;
  一旦 `f > BREAK_FORCE`,就把該節點從黏著清單移除(彈簧斷掉)→ 該處剝離。
- 所以:**拉力 < 門檻 → 撐住不動;拉力 > 門檻 → 剝離**。有效剝離抬起距離 =
  `BREAK_FORCE / ADHESION_STIFF`。

## 我幫你調好的關鍵旋鈕

```python
ADHESION_STIFF = 120.0   # 黏著硬度
BREAK_FORCE    = 60.0    # 黏著門檻:調高=更黏(更難剝);調低=一拉就剝
SCRIPTED_PULL  = True    # 自動抬左邊示範剝離(關掉就純手動拉)
PULL_HEIGHT    = 8.0     # 左邊抬多高(調小=只剝一部分,其餘留在底座上)
ENABLE_MOUSE   = True    # Shift+左鍵拖曳自己拉
PAPER_YOUNG    = 1200.0  # 紙的硬度(別上 4000+,會把三角形壓爆成 NaN)
EDGE_STIFFNESS = 2500.0  # 每條邊硬度 → 紙不亂伸縮
DAMPING        = 2.0     # 輕黏滯 → 柔軟、不亂晃
```

想只剝一半、其餘留在底座上 → 把 `PULL_HEIGHT` 調小(例如 3);想「幾乎撕不動」→ 把
`BREAK_FORCE` 調大。

## 你回報的三個問題,這版都修了

- **FPS 太低(≤20)**:元凶是 `CGLinearSolver iterations=150`。這網格很小,改成 **30**
  後實測 GUI **~120 FPS**(headless solve-only 90 步/秒)。
- **四邊固定住沒法拉**:改掉了。現在**沒有固定邊**,整張紙靠**黏著**貼在底座上;
  你(或腳本)拉哪裡、哪裡就剝。
- **中間框框看不懂**:那是 `BoxROI drawBoxes=True` 的除錯框。已全部 `drawBoxes=False`,
  畫面乾淨。

## ⭐「拉完變形的部分為何彈回?怎麼讓它不彈回」

**根因**:紙是**彈性**材料,rest 形狀是平的;剝離只是把它從底座「解黏」,並沒有讓
材料**記住**變形後的形狀。所以一放手,彈性(尤其**底座黏著彈簧**,它的目標是平的
底座)就把它拉回平面。**加阻尼只會拖慢,擋不住。**

**解法 = 塑性 freeze**:把當前形狀設成新的 rest,彈簧就不再往回拉。controller 在
`FREEZE_T` 自動做(或你**按 `F` 鍵**手動 freeze):

```python
mo.rest_position.value = mo.position.value   # rest 形狀 <- 當前變形
springs.reinit(); bending.reinit()           # 邊/彎折彈簧 rest <- 當前
adhesion.points = []; adhesion.stiffness = 0 # 清掉底座黏著(關鍵!否則它一直把紙拉回平底座)
pull.indices = []                            # 放開,證明它自己停住
```

實測:剝離抬起後 freeze+放開 → 形狀維持(mean z 停在 ~1.07、max ~3.8),一路到
Time=54s、**230 FPS** 都不彈回、不當掉。**互動時**:Shift+拖曳把紙拉成你要的樣子,
**按 `F` 凍結**,再放手就定型不彈回。

關鍵旋鈕:`FREEZE_T`(何時自動凍結)、`RELEASE_AFTER_FREEZE`(凍結後是否放手驗證)。

## 需不需要 SofaCUDA?→ 不需要

當初的當機是 CPU 撕裂 remesh 卡住,不是算力問題;而且這網格才 ~774 節點,CPU 已
120 FPS。**GPU + 執行期拓樸改變在 SOFA 不支援**,你用到的彈簧/阻尼/黏著元件也沒有
CUDA 版。GPU 的舞台是 phaco 水晶體體積網格(上萬四面體),不是這張薄膜。

## 穩定性驗證(實測)
- 剝離前緣隨拉高逐步推進:glued 774 → … → 0(t≈7.2 全剝離),**無 `Null determinant`、
  無 NaN、無當機**。
- GUI:**Time=30s、~120 FPS**,畫面乾淨無除錯框。
