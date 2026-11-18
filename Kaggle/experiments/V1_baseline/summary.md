# V1 — 首轮本地基线

验证协议：GroupKFold 五折，按 prompt_id 分组；训练、验证 Prompt 严格不相交。
数据：2699 行、150 个 Prompt、18 个模型。

| 模型 | OOF Balanced Accuracy | 五折平均 BA | 五折标准差 |
|---|---:|---:|---:|
| word_lr | 0.2722 | 0.2722 | 0.0134 |
| char_svc | 0.3078 | 0.3078 | 0.0178 |

当前最优基线：**char_svc**。仅代表本地跨 Prompt 验证，非公榜/私榜成绩。

本轮尚未提交 Kaggle。下一步分析类别召回率、易混淆标签，再提交 Notebook。

完整 OOF、每类召回率、混淆矩阵留在本地，不同步原始训练记录。

训练文件 SHA-256：40a22ce8d88c5f46feb4637a099db815bef5f713ffe53e89dbe1b7b21de77707
