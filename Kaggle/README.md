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

V2 已正式晋升：最佳 `joint_style_svc` 的五折 OOF Balanced Accuracy 为 0.358553（V1 为 0.307813），五折全部提升。候选对比保存在 `outputs/V2_feature_fusion/`，冻结版本摘要在 `experiments/V2_feature_fusion/`；正式提交 Notebook 位于 `notebooks/V2_feature_fusion_kaggle.ipynb`（尚未在 Kaggle 提交）。只用训练折拟合 TF-IDF 和风格标准化；验证集不参与特征拟合。

## GitHub 同步

本地代码与记录是开发源；仓库 Kaggle/ 是用于团队协作的共享成果。修改成功并验证后，可执行：

    powershell -File scripts/sync_to_repo.ps1

脚本只同步白名单中的代码、Notebook、文档和聚合指标；原始数据、OOF 逐条结果、模型权重、缓存和截图默认不推送。提交 GitHub 前用 git diff / git status 审核，不自动 git commit/push。

## 提交 Kaggle

这是 Code Competition：需要 Notebook 在 Kaggle 的隐藏测试集上运行，生成 submission.parquet（列 id, model）。正式执行不能联网，CPU/GPU 最长 9 小时。不要把当前 test.csv 的 3 条示例当成真正的测试集。

课程要求保留至少五次有效提交、提交历史、公榜变化、Team Page 和最终私榜截图。详情见 docs/协作与实验记录规范.md 和 Name_That_LLM_竞赛要求与数据说明.md（完整本地工作区）。
