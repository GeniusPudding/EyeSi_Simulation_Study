# INRIA → 商用化:InSimo / HelpMeSee(白內障模擬器的產品端)

INRIA 的即時 FEM 白內障技術(Comas → Allard → Courtecuisse → Dequidt,見 [`reference/3`](3_inria_fem_lineage.md))最終落地成**真正在訓練醫師的商用模擬器**。這條「學術 → 產品」血緣,是本 repo 先前只在 `inria_ccc_roadmap.html` 邊緣提過、缺 md 正本的一塊。

## 兩個不同的「誰」——別混淆

- **HelpMeSee = 出資設題的非營利組織**(誰要做、為什麼做)。
- **InSimo = 做物理引擎的公司**(承 INRIA/SOFA 技術)。
- 兩者是「**委託方 ↔ 技術方**」,不是同一個東西。

## HelpMeSee(組織 / 願景)

- **2010 年由 Al Ueltschi(Albert Lee Ueltschi)與其子 Jim 創立**。
- Ueltschi = **FlightSafety International(全球最大航空訓練公司)創辦人**、Orbis International 共同創辦人。他把航空業「**用模擬器大量訓練飛行員**」的哲學移植到白內障手術,目標消除可預防的白內障失明(主打 **MSICS 小切口手術**)。2012/10 過世。
- 模擬器組成:**Moog(力回饋硬體)+ InSimo(物理引擎)+ SenseGraphics / Surgical Science(3D 渲染)+ Harman(UI)**,並有 Inria 學術支援。含虛擬顯微鏡、兩支力回饋手件、虛擬注射器、頭/手靠、觸控 UI。
- 技術基礎:從**拆解標準化 MSICS 術式 + 在真實手術中量測手術施力**反推效能參數(PMC 2015)。

## InSimo(技術方)

- **2013 年 1 月於 Strasbourg 創立**,是 INRIA/SOFA 的 spin-off(Cotin 把 INRIA 專長帶進 Strasbourg 大學醫院 **MIMESIS** 團隊時創立)。
- 共同創辦人:**Stéphane Cotin、Jérémie Allard、Christian Duriez** + Pierre-Jean Bensoussan、Juan Pablo de la Plata。**Allard / Duriez / Cotin 三位正是 Comas / Dequidt / Courtecuisse 論文的共同作者**——血緣直通本 repo 的 INRIA 主線。
- 落腳 Strasbourg 民醫院 **IRCAD**(Marescaux 1994 創立)/ IHU 影像導引手術所旁;用 **SOFA** 開發醫療模擬器。

## 論文分兩層(回答「HelpMeSee 有技術論文嗎」)

- **「關於 HelpMeSee」= 臨床 / 效度 / 部署**(因引擎閉源):
  - *High-Fidelity Cataract Surgery Simulation and Third World Blindness*(PMC 2015)= **最接近技術的一篇**(MSICS 拆解 + 施力量測建模)。
  - *More than simulation: the HelpMeSee approach*(PMC 2023)= 訓練法 / 課程。
  - face / content validity 研究(2022、2024)。
- **「它用的引擎技術」= 掛 INRIA / InSimo / SOFA 名下**:Comas 2008、Dequidt 2013、Courtecuisse 2010/2014、Filasofia(arXiv 2311.14508)、SOniCS(arXiv 2208.11676)。
- **沒有**同時公開兩者的「HelpMeSee 引擎白皮書」。

## 定位:它補上了 Dequidt 2013 沒做的一塊

Dequidt 2013 白內障系統**無力回饋裝置**(IR 光學追蹤,手感靠視覺 + 眼球約束,見 [`reference/5`](5_dequidt2013_vs_demo.md));而 HelpMeSee 用 **Moog 力回饋硬體 + InSimo(承 Courtecuisse 引擎的接觸 / 1kHz 觸覺能力)**,把「白內障 + 真實力回饋」合起來。

→ 呼應 [`reference/3`](3_inria_fem_lineage.md)「2013 系統 vs 2014 引擎」的分工:**HelpMeSee ≈ 把 Courtecuisse 通用引擎的觸覺能力,接上白內障應用的商用整合**。

## 來源

- HelpMeSee 沿革:[helpmesee.org/our-history](https://helpmesee.org/our-history/) · Ueltschi 維基:[en.wikipedia.org/wiki/Albert_Lee_Ueltschi](https://en.wikipedia.org/wiki/Albert_Lee_Ueltschi)
- InSimo 沿革 / 團隊:[insimo.com/history](https://www.insimo.com/history/) · [insimo.com/projects/helpmesee](https://www.insimo.com/projects/helpmesee/)
- *High-Fidelity Cataract Surgery Simulation and Third World Blindness*(PMC4365142,2015):[pmc.ncbi.nlm.nih.gov/articles/PMC4365142](https://pmc.ncbi.nlm.nih.gov/articles/PMC4365142/)
- Cotin / InSimo 共同創辦:[Inria — Stéphane Cotin's adventures in medical innovation](https://www.inria.fr/en/stephane-cotins-adventures-medical-innovation)
