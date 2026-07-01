# 13 — 現代 AI 撕囊影片分析(2023–2026):從「模擬」到「真實手術影片理解」

前面 00–12 是「**如何模擬 CCC**」(Schill/Weber/INRIA);
這份是「**如何用 AI 分析真實 CCC 手術影片**」——研究重心的延伸方向,對接個人專案 SurgeryOCR。

---

## 一、三篇關鍵論文(2025–2026)

### ① Cataract-LMM(Scientific Data 2026)— AI 基準資料集
- **3,000 支**白內障手術影片,**多中心**(德黑蘭 Farabi 2930 + Noor 70),1,134 小時,772 GB。
- **四個標註任務**:
  | 任務 | 規模 | baseline(SOTA) |
  |---|---|---|
  | 階段辨識(13 階段) | 150 支 | MViT-B 85.7% / Swin-T 85.5% |
  | 實例分割(器械, COCO+YOLO) | 6,094 幀 | YOLOv11 73.9 mAP > Mask R-CNN 53.7 |
  | 物件追蹤(撕囊 clip) | 170 支 / 469,118 幀 | ID+mask+bbox+keypoint |
  | 技能評估(ICO-OSCAR) | 170 支 | TimeSformer 82.5% |
- **關鍵發現**:**跨中心時追蹤/分割明顯掉分**(domain shift)。
- 授權 CC BY-NC-ND。技術棧 PyTorch 2.0 / CUDA 11.8。

### ② Meta Surgery(npj Digital Medicine 2025)— AI 導引撕囊 +40%
標題:*Digitalization of surgical features improves surgical accuracy via surgeon guidance and robotization*。
- **17,538 支撕囊影片**;2 專家分級 ideal/acceptable/poor(資深醫師理想率僅 16.7%)。
- **影像處理管線**:
  1. **InceptionResNetV2**(分類)認角膜緣/瞳孔/撕囊開口(準確度 88/92/86%),分級 AUC 0.92–0.96。
  2. **Mask R-CNN**(實例分割)逐幀分割 CL/瞳孔/CO 像素遮罩。
  3. **幾何特徵**:用**角膜緣面積當自校正尺規**解決放大率不一 →
     **理想撕囊 = 圓心在瞳孔中心、半徑 = 角膜緣半徑 × 0.58、直徑 5.15–5.39 mm、圓度 0.98、偏心 <0.30 mm**。
  4. **即時導引**:每幀疊加理想圓 + 有刻度 lens caliper;豬眼上導引手術機器人自動撕囊。
- **結果**:LC 組理想率 **86% vs 對照 46%**(各 50 眼)= +40 個百分點。
- ⭐ 可直接借:**理想圓公式、角膜緣尺規校正、分割>偵測框、圓度/偏心指標**。

### ③ AI vs 人類 meta-analysis(npj Digital Medicine 2026)
- PRISMA:9,270 記錄 → 66 篇質性 → 27 篇量化。
- **多數任務 pooled 敏感度/特異度 > 0.80**;AI 在**明確任務(階段辨識、解剖辨識)可媲美/超越醫師,眼科尤佳**。
- **三大缺口**:(1) 顯著異質性;(2) 多為回溯性/單中心 → 泛化受限;(3) **即時前瞻臨床效用「大致未證實」**。
- → 呼籲**標準化報告 + 前瞻性驗證**。

---

## 二、資料集:Cataract-1K vs Cataract-LMM(不一樣、互補)

| | Cataract-1K(2023) | Cataract-LMM(2026) |
|---|---|---|
| 規模/來源 | 1,000 支 / 單中心(奧地利) | 3,000 支 / **多中心**(德黑蘭) |
| 獨有 | **異常偵測**(瞳孔反應、IOL 旋轉) | **追蹤 469K 幀 + 技能評估** |
| 分割 | 2,256 幀 / 30 支(COCO) | 6,094 幀 / 150 支(COCO+YOLO) |
| 授權/託管 | CC BY / Synapse | CC BY-NC-ND / HuggingFace `mjahmadi/Cataract-LMM` |

- **各自獨立收案**(LMM 非衍生自 1K,論文把 1K 當比較基準)。
- 撕囊異常→用 1K;撕痕追蹤/技能→用 LMM;分割/理想圓→兩者皆可。
- 下載細節見 SurgeryOCR repo `docs/datasets.md`。

---

## 三、SurgeryOCR 的定位與三個缺口

SurgeryOCR(個人專案)= 解析手術影片**每一幀的儀器數值**(phaco 螢幕讀數 OCR,CRNN 已訓練)。
**只讀螢幕數值,不碰術野解剖** → 要往「手術品質分析」走,補三缺口:

| 缺口 | 做法 | 資料 | 價值 |
|---|---|---|---|
| **1 階段辨識升級** | RMSE 模板 → 加視覺深度模型(MViT/Swin)交叉驗證 | 1K/LMM 階段 | 泛化↑,OCR+視覺雙訊號 |
| **2 解剖分割** | Mask R-CNN/SAM 分割瞳孔/角膜緣/撕囊 + Meta Surgery 理想圓 | 1K/LMM 分割 | 從「讀數值」→「懂術野」 |
| **3 液面+逐幀撕痕偏離** | 分割基礎上加液面偵測 + 逐幀「實際撕痕 vs 理想圓」偏差 | — | **三篇都沒做 = 原創貢獻** |
| 基礎 | eval 腳本 + 測試集 + 跨中心驗證 | LMM 多中心 | 回應 meta-analysis 缺口 |

---

## 四、兩條研究線如何銜接

```
經典模擬(00–12):    如何「生成」CCC 撕裂
  Schill mass-spring/ECM → Weber 描述式 → INRIA 纖維 FEM(SOFA)
        │  共用的核心概念:理想撕囊 = 以瞳孔為心的圓、撕痕沿纖維/應力傳播
        ▼
現代 AI(本篇):      如何「分析」真實 CCC 影片
  Cataract-LMM(資料) + Meta Surgery(理想圓+導引) + meta-analysis(缺口)
        │  SurgeryOCR 從螢幕數值 → 補解剖分割 + 液面 + 逐幀偏離
        ▼
交會點:Meta Surgery 的「理想圓」= 模擬端的「理想撕痕路徑」
        → 模擬(生成理想路徑)與 AI(量測實際偏離)可互相驗證
```

> 核心洞見:**模擬端定義的「理想撕囊圓」(以瞳孔為心、固定半徑比例),與 AI 端從真實影片萃取的理想圓(Meta Surgery: 0.58×角膜緣半徑),是同一個東西。**
> 這讓「模擬訓練」與「影片 AI 評估」能共用同一套理想撕囊指標(直徑/圓度/偏心)。

## 來源
- Cataract-LMM: arXiv 2510.16371 / Scientific Data 2026 · HF `mjahmadi/Cataract-LMM`
- Cataract-1K: arXiv 2312.06295 / Scientific Data 2024 · github.com/Negin-Ghamsarian/Cataract-1K
- Meta Surgery: npj Digital Medicine 2025, doi 10.1038/s41746-025-01887-6(本機 papers/MetaSurgery_2025_npjDM_AIguidedCCC.pdf)
- AI meta-analysis: npj Digital Medicine 2026, doi 10.1038/s41746-026-02401-2
