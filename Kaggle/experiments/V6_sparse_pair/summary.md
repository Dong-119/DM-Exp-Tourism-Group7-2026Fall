# V6 · 在 V5 基础上添加保守双回答配对

## 思路与本地验证

V3 的完整 Prompt 约束在 Kaggle 公榜上明显失效。因此 V6 **不强制恢复完整 18 条回答**，只对无标签文本中互为余弦最近邻、词级 TF-IDF 相似度不低于 **0.10** 的一对文本，尝试不同模型标签的最优联合分配。仅当两条文本的总 SVM margin 代价不超过 **0.30** 时，才接受配对；其余全部保持 V5 的独立预测。少于 30 条或超过 5,000 条输入时直接回退 V5。

使用固定 V5 的 OOF margins，只从验证文本推断配对，`prompt_id` 和真实标签仅用于**事后评分和压力测试**。应用 V5 保守类别校准后：

| 场景 | 原预测 Balanced Accuracy | 配对后 | 平均提升 |
|---|---:|---:|---:|
| 完整 18 条/Prompt | 0.41746 | **0.42301** | +0.00556 |
| 每 Prompt 2 条 | 0.43432 | **0.44216** | +0.00783 |
| 每 Prompt 随机 1–5 条 | 0.42363 | **0.42621** | +0.00258 |
| 每 Prompt 1 条 | 0.43588 | **0.43588** | 0.00000 |

这些是固定 OOF 分数上的合成稀疏场景平均值，**不是线上真实分数**；隐藏测试 Prompt 结构未知。配对算法不依赖每组的完整回答集合。测试还确认 Notebook 对 36 条合成配对文本能正确实行不同标签分配，对 3 条示例数据按原方案回退。

## 文件与 Kaggle

- Kaggle Notebook：`notebooks/V6_sparse_pair_kaggle.ipynb`。
- 配对压力测试：`src/try_v6_pair_stress.py`，`src/try_v5_sparse_matching.py`。
- 自动化测试：`tests/test_v6_pair.py`。
- 官方 Notebook：[V6 Sparse Pair](https://www.kaggle.com/code/qifanma/name-that-llm-v6-sparse-pair)。
- Submission ID：**58505215**，Notebook Version 1；**Kaggle 状态 COMPLETE，Public Score 为 0.411**，低于 V5 的 0.417。故 V6 作为已完成的对照实验留档，不替代 V5。

V6 的提升空间预计较小，最终必须由官方公榜实测决定。若低于 V5 的 0.417，保留 V5 作为最终线上最佳，不为满足版本编号而声称 V6 优于 V5。
