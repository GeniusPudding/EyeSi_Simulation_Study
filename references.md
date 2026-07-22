# References

## 核心引擎 / 架構
- **Schill, M. A.** (2001). *Biomechanical Soft Tissue Modeling – Techniques, Implementation and Applications.*
  PhD thesis, University of Mannheim. → ECM 演算法、vrmDesign 架構、EyeSi。
- **Gibson, S.** (1997). *3D ChainMail: a fast algorithm for deforming volumetric objects.* → 原始 ChainMail。
- **Wagner, C.; Schill, M.; Männer, R.** (2002). *Collision Detection and Tissue Modeling in a VR-Simulator for Eye Surgery.* Eurographics Workshop on Virtual Environments.
- **Wagner, C.; Schill, M.; Männer, R.** (2002). *Intraocular surgery on a virtual eye.* Communications of the ACM 45(7):45–49.

## CCC 撕囊模擬
- **Webster, R.; Sassani, J.; Shenk, R.; Good, N.** (2004). *A Haptic Surgical Simulator for the Continuous Curvilinear Capsulorhexis Procedure During Cataract Surgery.* MMVR 12. → CCC 模擬開山。
- **Webster, R. et al.** (2005). *Simulating the Continuous Curvilinear Capsulorhexis Procedure During Cataract Surgery on the EYESI System.* MMVR 13, pp. 592–595.
- **Weber, K.; Wagner, C.; Männer, R.** (2006). *Simulation of the Continuous Curvilinear Capsulorhexis Procedure.* ISBMS 2006, LNCS 4072, pp. 113–121. → **最完整的 CCC 撕裂演算法(Indicator / shearing / ripping + Delaunay remeshing)**。

## 拓樸改變 / 切割
- **Nienhuys, H.-W.; van der Stappen, A. F.** (2002/2003). *A Delaunay Approach to Interactive Cutting in Triangulated Surfaces.* Technical Report UU-CS-2002-044 / Algorithmic Foundations of Robotics V. → remeshing 來源。
- **Ganovelli, F.; O'Sullivan, C.** (2001). *Animating cuts with on-the-fly re-meshing.*
- **Burman, E.** (2010). *Ghost penalty.* C. R. Math. 348:1217–1220. / **Burman, Claus, Hansbo, Larson, Massing** (2015). *CutFEM: Discretizing geometry and partial differential equations.* Int. J. Numer. Methods Eng. 104(7). → CutFEM / ghost-penalty 穩定化。
- **Bui, H. P.; Tomar, S.; Courtecuisse, H.; Cotin, S.; Bordas, S. P. A.** (2019). *Corotational cut finite element method for real-time surgical simulation: application to needle insertion simulation.* Comput. Methods Appl. Mech. Engrg. 345:183–211. [arXiv 1712.03052](https://arxiv.org/abs/1712.03052) → **即時手術免重網格切割**(INRIA 2014 之後的分支;見 docs/ccc_method/5)。

## 手法 / 臨床
- **Seibel, B. S.** (2005). *Phacodynamics – Mastering the Tools and Techniques of Phacoemulsification Surgery*, 4th ed. → shearing / ripping 手法定義。
- **Gimbel, H. V.; Neuhann, T.** (1990). *Development, advantages, and methods of the continuous circular capsulorhexis technique.* J Cataract Refract Surg 16(1). → CCC 術式發明。
- **Karim, S. M. R.; Ong, C. T.; Sleep, T. J.** (2010). *A Novel Capsulorhexis Technique Using Shearing Forces with Cystotome.* J Vis Exp (39):e1962.
- **McCannel, C. A.; Reed, D. C.; Goldman, D. R.** (2013). *Ophthalmic Surgery Simulator Training Improves Resident Performance of Capsulorhexis in the Operating Room.* Ophthalmology 120(12):2456–2461. → 模擬訓練降錯誤撕囊率 68%。

## 後續發展(2006 之後;見 docs/reference/1_lineage_map)
- **Müller, M.; Heidelberger, B.; Hennix, M.; Ratcliff, J.** (2007). *Position Based Dynamics.* J. Visual Communication and Image Representation 18(2):109–118. → PBD,mass-spring 的即時穩定後繼(位置基,≈ ECM 位移驅動)。
- **Belytschko, T.; Black, T.** (1999). *Elastic crack growth in finite elements with minimal remeshing.* Int. J. Numer. Methods Eng. 45(5). / **Moës, N.; Dolbow, J.; Belytschko, T.** (1999). *A finite element method for crack growth without remeshing.* → XFEM,裂縫穿元素免重網格。
- **Marchal, M. et al.** (2009). *A fiber-based fracture model for simulating soft tissue tearing.* INRIA. → 纖維基斷裂模型。
- **(FEM 撕囊力學)** (2021). *A study for lens capsule tearing during capsulotomy by finite element simulation.* Comput. Methods Programs Biomed. → 四層 3D 晶體 FE 模型 + 內聚介面律,豬眼力感測驗證;離線、非即時。

## 引用 Weber 2006 的後續延伸(見 docs/reference/2_weber2006_citations)
- **Weber, K.** (2009). *Interaktive Echtzeitsimulation deformierbarer Oberflächen für Trainingssysteme in der Augenchirurgie.* PhD thesis, Univ. Mannheim. [madoc.bib.uni-mannheim.de/2816](https://madoc.bib.uni-mannheim.de/2816/) → **2006 的直接後繼**:撕痕方向由「描述式」升級為「物理式(應變最小)」,drift 降為 fallback;含 ILM/ERM peeling、針器械互動。原文存 `papers/`。**不在 EndNote**。
- **Peter, R. C.; Peikert, S.; Haide, L.; …; Mathis-Ullrich, F.** (2024). *Lens Capsule Tearing in Cataract Surgery using Reinforcement Learning.* ICRA 2024, pp. 15501–15508. [IEEE](https://ieeexplore.ieee.org/document/10611714/) → **SOFA(FEM)薄組織撕裂當 RL 環境**,精準撕 5.5mm 圓 + domain randomization;RL 自主/輔助撕囊。⚠️ 常被連到的 [github.com/maystroh/RL_cataract](https://github.com/maystroh/RL_cataract) **疑非本篇官方 code**(該 repo 是 Unity;本篇環境實為 SOFA)。
- **Courtecuisse, H.; Jung, H.; Allard, J.; Duriez, C.; Lee, D. Y.; Cotin, S.** (2010). *GPU-based real-time soft tissue deformation with cutting and haptic feedback.* Progress in Biophysics and Molecular Biology 103(2–3):159–168. [HAL hal-00686056](https://inria.hal.science/hal-00686056) → GPU 即時變形 + **切割 + 觸覺**;非同步預條件子這條線的奠基。
- **Dequidt, J.; Courtecuisse, H.; Comas, O.; Allard, J.; Duriez, C.; Cotin, S.; Dumortier, E.; Wavreille, O.; Rouland, J.-F.** (2013). *Computer-based training system for cataract surgery.* SIMULATION 89(12). [HAL hal-00855821](https://inria.hal.science/hal-00855821) → **集大成完整系統**(撕囊+phaco+IOL)= SOFA + GPU 即時 FEM(見 docs/reference/3_inria_fem_lineage、5_dequidt2013_vs_demo)。
- **Courtecuisse, H.; Allard, J.; Kerfriden, P.; Bordas, S. P. A.; Cotin, S.; Duriez, C.** (2014). *Real-time simulation of contact and cutting of heterogeneous soft-tissues.* Medical Image Analysis 18(2):394–410. [HAL hal-01097108](https://inria.hal.science/hal-01097108) → **切割/接觸數值定稿**:非同步預條件子 + **Sherman-Morrison 增量更新** + GPU-CG;白內障/肝/腦三 demo(白內障 18–25 fps、平均 11.6 CG 迭代)。
- **Duriez, C.** (2013). *Real-time haptic simulation of medical procedures involving deformations and device-tissue interactions.* Habilitation. → SOFA 變形/切割/haptic。
- **Le Gouis, B.; Marchal, M.; Arnaldi, B.; Gouranton, V.** (2017). *Haptic Rendering of FEM-based Tearing Simulation using Clusterized Collision Detection.* IEEE World Haptics. [HAL](https://inria.hal.science/hal-01675134) → 通用軟組織撕裂 + haptic(纖維斷裂續作)。
- **Lam, C. K.; Sundaraj, K.; Sulaiman, M. N.** (2013, 2013, 2014). 白內障/phaco VR 模擬器綜述三篇(脈絡)。

## 商用化 / 引擎框架(見 docs/reference/9)
- **HelpMeSee**(2010 由 Al Ueltschi 創立,航空訓練哲學)+ **InSimo**(2013 Strasbourg INRIA/SOFA spin-off;Cotin/Allard/Duriez 共同創辦)+ Moog(力回饋)+ SenseGraphics(渲染)→ 商用 **MSICS 白內障模擬器**。技術基礎:*High-Fidelity Cataract Surgery Simulation and Third World Blindness*(PMC 2015)。→ 血緣正本見 docs/reference/9。
- **Allard, J. et al.** (2007). *SOFA – an Open Source Framework for Medical Simulation.* MMVR. / **Faure, F. et al.** (2012). *SOFA: A Multi-Model Framework for Interactive Physical Simulation.* In *Soft Tissue Biomechanical Modeling for Computer Assisted Surgery*, Springer. [HAL hal-00681539](https://inria.hal.science/hal-00681539) → 整條 INRIA 路線的開源框架奠基。

## 其他 EyeSi 系列(本筆記範圍外)
- **Jakubik, O.** (2009). *Simulation der Phakoemulsifikation im Augenoperationssimulator Eyesi.* PhD thesis, Mannheim. → phaco 機器物理。
- **Köpfle, A.** (2012). *Ein modulares optisches Trackingsystem für medizintechnische Anwendungen (MOSCOT).* PhD thesis, Mannheim. → 光學追蹤。

## 工具
- **SOFA Framework** — https://www.sofa-framework.org/ (INRIA) → vrmDesign 的現代開源後繼者。
