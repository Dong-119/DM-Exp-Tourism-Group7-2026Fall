# V5 · 扩充来源受限的外部训练数据与保守类别校准

## 结果

- 原 V4：官方训练集严格按 Prompt 分组的五折 OOF Balanced Accuracy 为 **0.400062**，Kaggle Public Score 为 **0.397**。
- **V5 五折 OOF Balanced Accuracy = 0.417470**（+1.74 个百分点）。
- **V5 官方 Kaggle Public Score = 0.417**（+2.0 个百分点），Submission ID **58504997**，状态 `COMPLETE`，Notebook Version 1。
- V5 线上成绩与本地五折十分接近，**当前为已确认的线上最佳**（V6 需等正式评分）。

## 主要改动

基于 V4 的词级与字符级 TF-IDF、110 项写作风格特征、LinearSVC，不使用 Prompt 完整性假设。

1. 在已经筛选过的公开来源中，将每模型最多选取的训练回答数量由 300 扩大至 **700**。受限外部训练集从 8,450 条增至 **14,850 条**，包括受限公共池 11,254 条和独立 API 生成记录 3,596 条，仍保持无重复与来源可追溯。
2. 外部文本样本权重仍为 0.10，标点风格校准使用 0.03（训练折统计）。
3. 对足够大的无标签测试集合（`n >= 200`）根据均衡的模型类别先验，使用温度 0.6、校准强度 0.5 的温和概率质量调节；不强制任何一个 Prompt 内分配完整模型。3 条示例测试数据直接用独立分类回退。

**重要假设**：类别分布校准利用竞赛训练集中各模型数量近乎均衡的事实，但不保证隐藏测试集完全均衡。已额外模拟少量文本和偏移的家族比例，校准平均仍带来小幅正收益；真实有效性以 Kaggle 公榜 0.417 为准。

## 可复现文件与来源

- 外部池筛选：`scripts/build_v5_pool.py`；正式来源 manifest：`experiments/V5_expanded_pool_prior/source_selection.json`。
- 五折训练：`src/try_v5_largepool.py`，使用 `GroupKFold(prompt_id)`；保存原始预测与分数在本地 `outputs/trials_v5_largepool/`。
- 无监督校准和融合检查：`src/try_v5_postprocess.py`；仅在本地 OOF 分数上评估。
- Kaggle 自包含 Notebook：`notebooks/V5_expanded_pool_prior_kaggle.ipynb`。
- 正式 Notebook：[V5 Expanded Pool Prior](https://www.kaggle.com/code/qifanma/name-that-llm-v5-expanded-pool-prior)。
- 数据来源：[公共 in-style pool（CC BY-SA 4.0）](https://www.kaggle.com/datasets/prvsiyan/ntl-public-in-style-pool-v1) 与 [扩展模型回答（CC BY 4.0）](https://www.kaggle.com/datasets/prvsiyan/prvsiyans-extended-name-that-llm-dataset)。沿用 V4 的来源白名单，排除争议代理服务、未证实版本和与官方训练文本重复的行。
- 公开仓库仅同步选择脚本、Notebook、指标与出处，不上传数据文本、模型权重及逐条 OOF。

## 重要说明

- 本机与服务器的 scikit-learn 版本可能让 GroupKFold 的折号排列不同。涉及跨环境 OOF 融合时必须按样本 `id` 对齐，不能按折号直接拼接；本轮相关对比已按 `id` 对齐。
- 公榜成绩不是最终私榜成绩。课程还需保存官方 Submissions 页截图，API 返回的成功记录另行存于本地私有 `outputs/`。
