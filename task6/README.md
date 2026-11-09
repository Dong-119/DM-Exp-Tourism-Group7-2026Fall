# 实验六：多源程序性知识的融合与图谱可视化

本模块融合实验二实体识别结果、实验三结构化路线与实验五条件性建议，使用 NetworkX `MultiDiGraph` 构建多源程序性知识图谱，并导出结构化数据与可视化图集。

## 运行方式

在仓库根目录执行：

```powershell
python -m pip install -r task6equirements.txt
python task6un_experiment.py
python -m unittest discover -s task6 -p "test_*.py" -v
```

## 输出结构

运行后输出位于 `task6/results/`：

- `nodes.csv`、`edges.csv`：节点与有向边属性表，支持导入 Neo4j 或 Gephi；
- `knowledge_graph.json`、`knowledge_graph.graphml`：完整图谱结构与 Schema 定义；
- `故宫完整游览知识网络.svg`：按景区、路线、景点、时间、交通、活动、条件、建议八类节点分层展示的故宫知识子图；
- `故宫路线结构可视化.svg`：按路线分行展示的有序访问序列图；
- `故宫条件建议可视化.svg`：代表性条件与建议映射关系图；
- `complete_graphs_index.json` 与 `complete_graphs/`：覆盖全图 654 条边的分页关系图集；
- `validation.json`、`run_manifest.json`：图谱连通性、Schema 覆盖与构建统计信息。

## 图谱模式（Schema）

- **节点类型（8类）**：`scenic`（景区）、`route`（游览路线）、`poi`（景点/位置）、`transport`（交通方式）、`time`（时间节点）、`activity`（游览活动）、`condition`（适用条件）、`advice`（游览建议）。
- **关系类型（11类）**：`contains`（路线支撑的景区景点归属）、`mentions_poi`（文本提及的地点候选）、`mentions_transport`（文本提及交通）、`mentions_time`（文本提及时间）、`has_route`（景区包含路线）、`visits`（路线按序访问景点）、`next`（同一路线内相邻景点先后顺序）、`occurs_in`（步骤所属时间段）、`has_activity`（景点关联活动）、`has_condition`（景区适用条件）、`recommends`（条件触发建议）。
