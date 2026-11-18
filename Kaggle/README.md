# Name That LLM — 第 7 组 Kaggle 竞赛

**任务**：识别一段文本来自哪一个 LLM（18 类）；评测指标为 Balanced Accuracy。隐藏测试集 Prompt 与训练集不重合。

本地完整实验目录：D:\文件\大三上\实验&大作业\数据挖掘\Kaggle竞赛

GitHub 协作目录：DM-Exp-Tourism-GroupX-2026Fall/Kaggle

## 目录和用途

- data/raw/：Kaggle 官方三份原始文件（仅本地，不修改、不推送 Git）
- data/archive/：原始下载 ZIP（仅本地）
- src/：训练/验证/推理代码（同步 GitHub）
- tests/：无需训练数据即可运行的基础测试（同步 GitHub）
- notebooks/：Kaggle Code Competition 提交脚本或 Notebook（同步 GitHub）
- docs/：协作协议及实验记录模板（同步 GitHub）
- outputs/：完整 OOF、混淆矩阵及日志（仅本地）
- experiments/：筛选后的正式实验摘要（同步 GitHub），仅显著提升后晋升版本
- scripts/：本地同步脚本（只在本地执行）

持续优化与资源使用约定见 [docs/持续迭代与版本晋升规范.md](docs/持续迭代与版本晋升规范.md)。默认以跨 Prompt 五折 OOF Balanced Accuracy 为主，达到至少 +0.02 的提升再优先晋升为正式版本；服务器空闲时可使用 GPU，但不挤占已有训练。

## 第一轮本地基线

从本目录执行以下命令：

    python src/baseline.py
    python -m unittest discover -s tests -v

两个模型：word 1–2 gram TF-IDF + LogisticRegression；char 3–5 gram TF-IDF + LinearSVC。均为五折 GroupKFold，分组键 prompt_id，严禁 Prompt 泄漏。

输出到 outputs/V1_baseline/，包括 metrics.json、summary.md、oof_predictions.csv、per_class_recall.csv、fold_scores.csv 和混淆矩阵。

**GitHub 克隆环境**：先从官方 Kaggle 下载 train.csv，放在 Kaggle/data/raw/train.csv（该目录被忽略），再使用同样命令复现。

## 第二轮：词、字符与风格特征

    python src/iterate_v2.py

V2 已完成五折验证：最佳 `joint_style_svc` OOF Balanced Accuracy 0.358553（V1 为 0.307813）。Kaggle 独立分类对照版已成功提交：Submission ID **58502734**，Public Score **0.349**。代码位于 `notebooks/V2_feature_fusion_kaggle.ipynb`；仅在训练折拟合特征。

## 第三轮：Prompt 无监督分组与联合标签分配（本地有效、线上退化）

    python src/try_v3_joint.py

**正式 V3：五折 OOF Balanced Accuracy = 0.443045（44.30%）**，较 V2 **+0.084492（+8.45 个百分点）**，五折全部提升。算法仅凭无标签验证文本、TF-IDF 相似度与最大簇大小 18 的约束推断 Prompt 分组，再对近完整的分组采用 Hungarian 算法进行模型标签的一对一分配；真实 prompt_id 仅用于 CV 划分与事后审计，不参与聚类。详见 `experiments/V3_prompt_joint/`。

提交 Notebook：`notebooks/V3_prompt_joint_kaggle.ipynb`，已用官方 3 条示例做本地完整推理并实际导出 Parquet。**Kaggle 首次正式提交已成功：Submission ID 58502009，官方状态 COMPLETE / Succeeded，Public LB = 0.298。** 线上分数比本地 CV 0.443045 明显更低，可能与隐藏测试的 Prompt 结构或分布不同有关，尚不能确定单一原因。Notebook 保留了小组独立分类回退。详细记录：`docs/20261118_V3_Kaggle首次提交.md`。

服务器离线权重/依赖安装与否定实验记录在 `docs/20261118_迭代试验记录.md`，GPU 微调并未超过 V2，所以未晋升。

## 第四轮：受限外部数据 + 标点风格校准（历史最佳）

基于 V2 独立文本分类，加入来源可追溯的 **8,450 条**外部文本（样本权重 0.10），再加入训练折内拟合的标点类条件似然校准（权重 0.05）。**不依赖测试集 Prompt 的完整分组。** 官方数据按 Prompt 分组的五折 OOF BA 为 **0.400062**，较 V2 +4.15 个百分点。

Kaggle 正式提交 **58503681** 已评分成功，Public Score **0.397**，比此前线上最好 V2 **0.349 提升 4.8 个百分点**。该阶段课程累计有效提交 3/5 次，私榜尚未公布。

- 正式版本：`experiments/V4_restricted_external_typography/`
- 自包含 Kaggle Notebook：`notebooks/V4_restricted_external_typography_kaggle.ipynb`
- 代码：`src/try_v4_combined_typography.py`、`src/try_v4_typography.py`、`scripts/build_v4_pool.py`
- 公开数据来源与许可见 `experiments/V4_restricted_external_typography/summary.md`，完整分析与提交 ID 见 `docs/20261118_V4_验证与上线.md`。原始外部数据与逐条预测只保留在本地 `outputs/`，不推送 Git。

## 第五轮与第六轮：完成 5 次官方提交（当前线上最佳 V5）

V5 沿用 V4 的 SVM 独立分类，将受限公开外部数据扩展为 **14,850 条**（样本权重 0.10），标点校准权重 0.03，并对大批量无标签测试文本做保守的模型类别先验修正。五折 OOF BA 为 **0.417470**，2026-11-18 Kaggle 正式评分 **0.417**，Submission ID **58504997**，当前线上最佳。

V6 在 V5 基础上，尝试只对互为文本最近邻的**可信双回答**做一对一模型分配，五折完整组 OOF BA 约 **0.423014**；但官方公榜仅 **0.411**（Submission ID **58505215**），低于 V5，因此**不替代 V5**，仅作为负面/对照实验保存。

- V5：`experiments/V5_expanded_pool_prior/`、`notebooks/V5_expanded_pool_prior_kaggle.ipynb`
- V6：`experiments/V6_sparse_pair/`、`notebooks/V6_sparse_pair_kaggle.ipynb`
- 完整分析及五次 Kaggle 提交表：`docs/20261118_V5_V6_提交与验证.md`
- 课程要求的**五次有效提交已全部完成（5/5）**，官方状态均为 `COMPLETE`；私榜尚未公布，成绩网页截图、Team Page 及最终私榜截图仍需按课程要求留存。

## GitHub 同步

本地代码与记录是开发源；仓库 Kaggle/ 是用于团队协作的共享成果。修改成功并验证后，可执行：

    powershell -File scripts/sync_to_repo.ps1

脚本只同步白名单中的代码、Notebook、文档和聚合指标；原始数据、OOF 逐条结果、模型权重、缓存和截图默认不推送。提交 GitHub 前用 git diff / git status 审核，不自动 git commit/push。

## 提交 Kaggle

这是 Code Competition：需要 Notebook 在 Kaggle 的隐藏测试集上运行，生成 submission.parquet（列 id, model）。正式执行不能联网，CPU/GPU 最长 9 小时。不要把当前 test.csv 的 3 条示例当成真正的测试集。

课程要求保留至少五次有效提交、提交历史、公榜变化、Team Page 和最终私榜截图。详情见 docs/协作与实验记录规范.md 和 Name_That_LLM_竞赛要求与数据说明.md（完整本地工作区）。
