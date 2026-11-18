# Name That LLM · V4 正式版本

## 结论

**当前首选提交版本**：V2 词级/字符级 TF-IDF + 110 项风格特征，添加经过来源筛选的公开训练数据，并用模型专属标点概率轻度校准。**不再强制测试集按 Prompt 凑齐 18 个模型**。

- 五折 `GroupKFold(prompt_id)` 整体 OOF Balanced Accuracy：**0.400062**。
- 相对 V2 独立模型 OOF **0.358553**，提升 **+0.041509（+4.15 个百分点）**。
- 仅添加外部数据、权重 0.10：**0.396358**；再加入标点校准权重 0.05：**0.400062**。
- V3 完整分组下得到 0.443045，但第一次 Kaggle 公榜仅 0.298；V2 独立分类公榜 **0.349**。因此版本选用依据优先考虑**无需完整测试 Prompt 结构**，线上 V4 成绩仍需正式提交核实。

## 五折结果

| Fold | 受限外部数据（w=0.10） | 外部数据 + 标点（w=0.05） |
|---|---:|---:|
| 1 | 39.07% | 37.96% |
| 2 | 40.74% | 41.48% |
| 3 | 38.15% | 37.78% |
| 4 | 39.63% | 42.04% |
| 5 | 40.59% | 40.77% |

## 数据和模型

- 官方训练集：2,699 条、150 个 `prompt_id`，五折严格隔离 Prompt。
- 受限外部数据：**8,450 条**，其中公共 in-style pool **4,854 条**，prvsiyan new 非代理路线 **3,596 条**。
- 仅选 5 个明确列出的公共数据池来源，排除名称包含 proxy 的来源、所有 pool Gemini 3.7（版本归属风险），prvsiyan 扩展数据仅保留 `split=new` 且 `provider_route` 属于 `anthropic/openai/google/openrouter`。
- 对模型标签与标准化文本去重、剔除与官方训练文本完全相同的行；不是使用官方隐藏测试样本。
- 公共数据池为 [prvsiyan/ntl-public-in-style-pool-v1](https://www.kaggle.com/datasets/prvsiyan/ntl-public-in-style-pool-v1)，CC BY-SA 4.0；扩展数据为 [prvsiyan/prvsiyans-extended-name-that-llm-dataset](https://www.kaggle.com/datasets/prvsiyan/prvsiyans-extended-name-that-llm-dataset)，CC BY 4.0。最终数据遵守较严格的 CC BY-SA 4.0，并保留原数据源署名。
- **注意方法学限制**：公共 in-style pool 在公开前使用完整官方训练集的字体符号分布作筛选，可能让 CV 相对真实独立数据稍显乐观；因而以 Kaggle 线上评分作为最终有效性检查，不能保证 0.400062 在线上完全复现。
- 外部数据权重 0.10；`LinearSVC(C=1.0)`；词 ngram=(1,2)、字符 ngram=(3,5)，110 项风格特征放大系数 0.08。
- 额外标点校准权重 0.05；标点似然只使用**该折的官方训练样本**统计，验证折标签不参与统计。
- 原始外部池、官方原始数据、缓存、训练预测、模型产物只保存在本地 `outputs/` 与 `data/`，**不上传 GitHub**。
- 两个公共输入数据集通过 Kaggle Notebook 的 `dataset_sources` 挂载，正式评分禁用互联网。

## 实验代码与验证

- `scripts/build_v4_pool.py`：构建受限外部样本，输出 `outputs/external_data/combined_restricted_v4/external_training.csv` 和 manifest。
- `src/try_v4_combined_typography.py`：服务器五折训练与 OOF，原始实测结果在本地 `outputs/trials_v4_combined_typo/`。
- `src/try_v4_typography.py`：训练折估计的标点似然。
- `notebooks/V4_restricted_external_typography_kaggle.ipynb`：自包含 Kaggle 运行版本。
- 离线 Notebook 已用官方 3 条测试示例完成完整推理，并真实生成、读回 Parquet 文件；字段 `id,model` 正确。
- **Kaggle 官方正式提交成功**：Submission ID `58503681`，状态 `COMPLETE`，Public Score **0.397**，较先前线上最好 V2 `0.349` 提升 **0.048（4.8 个百分点）**；Private Score 尚未公布。

## 淘汰试验

- 原 V3 联合分配在每个 Prompt 只有 2 条的模拟中，从独立 BA 约 0.3548 降至约 0.3068；推断测试集并非完整 18 条的直接证据来自官方成绩和此项压力测试，但实际隐藏组大小未知。
- 单独“稀疏配对 + Hungarian”：两条/Prompt 情况下平均只提高约 1 个百分点，不足以晋升。
- 家族分层分类：最优五折 **0.364119**，仅比 V2 高约 0.56 个百分点。
- 独立标点校准：最优五折 **0.373748**。
- 小型高质量外部数据：最优五折 **0.373758**。
- 本轮真正达到 +2 个百分点以上门槛的版本为 V4。

## 后续

1. V4 已在 Kaggle 正式评分成功，成为**当前线上最佳版本**。
2. 补全官方 Submissions 页面成绩截图（提交 ID 和分数已存档，不伪造截图）。
3. 继续建设更有代表性的稀疏 Prompt 验证和训练数据来源审计，避免仅针对公榜调参；至少再完成两次有独立改进的有效提交。
