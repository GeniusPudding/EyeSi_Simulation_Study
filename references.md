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

## 手法 / 臨床
- **Seibel, B. S.** (2005). *Phacodynamics – Mastering the Tools and Techniques of Phacoemulsification Surgery*, 4th ed. → shearing / ripping 手法定義。
- **Gimbel, H. V.; Neuhann, T.** (1990). *Development, advantages, and methods of the continuous circular capsulorhexis technique.* J Cataract Refract Surg 16(1). → CCC 術式發明。
- **Karim, S. M. R.; Ong, C. T.; Sleep, T. J.** (2010). *A Novel Capsulorhexis Technique Using Shearing Forces with Cystotome.* J Vis Exp (39):e1962.
- **McCannel, C. A.; Reed, D. C.; Goldman, D. R.** (2013). *Ophthalmic Surgery Simulator Training Improves Resident Performance of Capsulorhexis in the Operating Room.* Ophthalmology 120(12):2456–2461. → 模擬訓練降錯誤撕囊率 68%。

## 其他 EyeSi 系列(本筆記範圍外)
- **Jakubik, O.** (2009). *Simulation der Phakoemulsifikation im Augenoperationssimulator Eyesi.* PhD thesis, Mannheim. → phaco 機器物理。
- **Köpfle, A.** (2012). *Ein modulares optisches Trackingsystem für medizintechnische Anwendungen (MOSCOT).* PhD thesis, Mannheim. → 光學追蹤。

## 工具
- **SOFA Framework** — https://www.sofa-framework.org/ (INRIA) → vrmDesign 的現代開源後繼者。
