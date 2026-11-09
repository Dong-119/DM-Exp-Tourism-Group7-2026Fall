# 实验六：多源程序性知识的融合与图谱可视化

本实验融合实验二实体识别、实验三路线结构和实验五条件性建议，使用 NetworkX 构建故宫等景区的程序性知识图谱，并输出 CSV、JSON、GraphML 和 SVG；Matplotlib 可用时额外输出 PNG。

## 运行

在仓库根目录执行：

```powershell
python -m pip install -r task6\requirements.txt
python task6\run_experiment.py
```

无需联网时，如果当前环境已经安装 NetworkX 和 Matplotlib，可直接运行第二条命令。

输出目录为 `task6/results/`：

- `nodes.csv`、`edges.csv`：可导入 Neo4j 或其他图工具的节点和边；
- `knowledge_graph.json`：完整图谱及 Schema；
- `knowledge_graph.graphml`：NetworkX/Gephi 可读取的图谱；
- `knowledge_graph.svg`：故宫两跳完整关系视图；Matplotlib 可正常读取时还会生成 `knowledge_graph.png`；
- `故宫路线结构可视化.svg`：按路线分行展示景点顺序，适合报告插图；
- `故宫条件建议可视化.svg`：按“条件→建议”展示代表性规则，适合阅读；
- `故宫完整游览知识网络.svg`：按景区、路线、景点、时间、交通、活动、条件、建议分层，展示故宫相关完整语义网络；
- `complete_graphs_index.json` 和 `complete_graphs/`：按关系类型分页的完整关系图集，覆盖全部图谱边；
- `validation.json`：节点、关系、连通性和核心节点检查；
- `run_manifest.json`：输入哈希、统计信息和输出清单。

## Schema

节点类型：`scenic`、`route`、`poi`、`transport`、`time`、`activity`、`condition`、`advice`。

关系类型：`contains`、`mentions_transport`、`mentions_time`、`has_route`、`visits`、`next`、`occurs_in`、`has_activity`、`has_condition`、`recommends`。

`contains` 只表示景区与 POI 的归属，不用于时间或交通。实验二中的时间和交通是文档提及，分别使用 `mentions_time` 和 `mentions_transport`；实验三中路线步骤与时间的关系使用 `occurs_in`。实体通过“景区 + 规范名称 + 类型”对齐；时间使用全局规范节点；条件建议使用 `mapping_id` 保留每条规则，避免相同文字造成错误合并。所有关系保留来源文档和来源实验，低质量实体、空条件/建议和无法识别类型会被过滤并计入诊断。
