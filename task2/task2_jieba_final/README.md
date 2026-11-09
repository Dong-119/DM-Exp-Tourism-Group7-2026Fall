# 任务二 Jieba 分词与自定义词典

本包使用你上传的任务一 JSONL 原件作为输入。故宫、颐和园、天坛各 16 篇，共 48 篇。CSV、JSON 和 JSONL 对应同一批正文，实验只需读取一份。包内提供运行入口、词表配置、输入、规范和空白人工抽查表。词典文本、分词记录、实体 JSON 和词频图会在运行时生成。

## 直接运行最终版 V2

```powershell
python -m pip install -r requirements.txt
python recognize.py --inspect-doc YHY_T02 --output ./result/v2
```

默认版本为 V2。程序根据 `config/entities.json` 生成并加载运行词典。随包的 `config/userdict_v2.txt` 是已经验证的 175 词词典快照，`config/userdict_v1.txt` 是 107 词的基线快照，可用于核对或单独加载。修改配置后，以运行目录中新生成的词典为准。V1 与两版对照的命令见下文。

## 两个概念

- **规则方法**用明确条件判断一个片段是否是实体。例如词典里“午门”属于 POI，匹配时刻格式的“10:00”属于 TIME。上版直接在原文中查找词典词条。
- **Jieba 分词**把连续文本切成词单元。例如“步行到午门”可以切成“步行／到／午门”。它负责提出词边界，类别由任务二词典和规则给出。任务二本版先用 Jieba 配合领域词典保留专名，再给分词单元分类。时刻和完整线路可能跨词单元，因此另用正则在原文中匹配跨度。

## 准备环境

在 PowerShell 进入解压后的 `task2_jieba_final` 目录。如果使用已有的 conda 环境，先激活它。用同一个 Python 安装和执行。

```powershell
conda activate datamining
python -m pip install -r requirements.txt
python -c "import jieba; print(jieba.__version__)"
```

本次验证用 Jieba 0.42.1。源码要求 Python 3.9 或更新版本。控制台显示 `Building prefix dict` 是加载词典的提示。实体定位使用原 `clean_content`，无需重新清洗。

## 步骤一　构建自定义词典并运行基线

```powershell
python recognize.py --version v1 --inspect-doc YHY_T02 --output ./result/v1
```

1. **读取**。`load_docs()` 支持 JSONL 和 JSON 数组。每篇读取 `doc_id`、`scenic_name` 和 `clean_content`，并校验编号唯一及正文非空。程序逐篇处理，来源放在输出文档层。
2. **构建并加载**。`compile_rules()` 汇总配置里的 `POI`、`TRANSPORT` 与待审泛称。按版本输出 `userdict_v1.txt` 或 `userdict_v2.txt`，每行为“词条 空格 词频”。代码采用词频 1000000，使专名整体切分有较强权重。使用独立的 `jieba.Tokenizer()` 实例和 `load_userdict()` 加载每版词典，避免先跑 V2 再跑 V1 时词典相互影响。
3. **实际分词与分类**。`recognize()` 使用 `tokenizer.tokenize(text, HMM=False)`，每次取得词及其原文开始、结束位置。关闭 HMM 的新词识别便于观察用户词典带来的变化。词在 POI 表中就产生景点候选，在交通表中就产生交通候选。普通词和标点仍可出现在分词记录里。
4. **补充跨词单元的候选**。`COMMON_TIME` 在原文匹配日期、时段、钟点、时长。V2 的 `EXTRA_TIME` 识别区间与更多口语表达，`LINE`、`BUS` 识别带线路号的交通表达。
5. **处理重叠**。候选按照跨度从长到短处理。若“地铁”与“地铁5号线”占据部分相同位置，优先保留完整线路。正文中同一词的多个不同位置分别记录，最后按位置排序。

查看 `result/v1/userdict_v1.txt` 可验证真正加载的词条。查看 `result/v1/tokens_v1.json` 可验证 Jieba 如何切分 `YHY_T02`，再到 `entities_v1.json` 对照哪些词获得类别。将 `--inspect-doc` 换成 `GG_S04` 可观察“10／:／00”三个词单元如何由时间正则对应为一个 TIME 实体。

## 步骤二　绘制词频，诊断并迭代

1. 用浏览器打开 `result/v1/frequency_v1.svg`，分别看 POI、交通、时间的前 8 项。图中条长按各类别的最大频次缩放，比较不同类别时看条末次数。
2. 在 `frequency_v1.csv` 查全量词频。用 `entities_v1.json` 的 `sentence` 查高频词的原句，判断是合理实体、泛称误报、别名分散还是跨度问题。基线有意保留待审泛称，用来展示停用词如何改进识别。
3. 查看并按需修改 `config/entities.json`。 `stopwords` 从 V1 的泛称候选中移除“地方”“游客”等。它过滤实体候选，原文和原文位置保持可用。 `poi_additions` 增补“西堤六桥”“界湖桥”等专名，它们会进入 V2 用户词典。 `alias` 用于分类后的名称归一，例如“公共汽车”聚合至“公交”，实体原词仍保存在 `text`。
4. 重跑 V2。对比分词切分、实体边界、词频和原句。分别记录误报减少、漏识别补齐、边界修正及别名归一的证据。

```powershell
python recognize.py --version v2 --inspect-doc YHY_T02 --output ./result/v2
```

在两版 `tokens_*.json` 搜索“西堤”附近的词单元，比较专名的切分。到 `frequency_v2.csv` 核对“西堤六桥”是否进入 POI 统计。回到原句确认它是否确指景点。 `frequency()` 按景区、类型和实体键计数，`csv_frequency()` 写频次表，`chart()` 写 SVG。实体键将天坛和颐和园的“长廊”分开。涉及多景区的同句仍要人工判断归属。

## 步骤三　整理规范、导出并人工抽查

打开 `实体定义规范.md`，按统一边界核对三个景区。最终实体文件为 `result/v2/entities_v2.json`，每个文档有 `entities` 数组。字段 `type` 是 POI、TRANSPORT 或 TIME，`text` 为原词，`canonical` 为统计名称，`start/end` 为相对整篇 `clean_content` 的零基字符下标，左闭右开。比如 `GG_S04` 的“午门”位于 `[98,100)`。 `sentence` 提供原句，文档层的 `source_name`、`source_url`、`source_records`、`provenance_kind` 提供来源。

`main()` 对每个跨度验证切片可还原原词，并检查排序后无重叠。接着用 `人工抽查模板.csv` 从每个景区抽取若干原句，覆盖三类实体。先独立标注，再和 V1、V2 对照，记录误报、漏报、边界或类别错误和修改建议。时刻、跨度与类别的自动检查不能替代人工语义核验。

如果需要计算严格跨度指标，按整篇正文下标填写人工参考 JSON 数组，再用 `--review ./人工标注.json`。每个样例含 `case_id`、`doc_id`、`start`、`end`、`text` 和 `entities`。外层是抽查片段边界，内部每条实体含 `start`、`end`、`type`。样例之间避免重叠。`evaluate()` 以位置与类型同时匹配计算 P/R/F1，边界错误同时计为一次误报和一次漏报。若用抽查样例调词典，应另外选句做独立复核。

## 手册评分项与提交证据

| 评分项 | 分值 | 对应操作与文件 |
|---|---:|---|
| 实体类型定义与规范 | 15 | 10 分查三类定义、边界、示例，5 分查跨景区一致性与歧义。用规范表与“长廊”等原句举证。 |
| 实体识别方法实现 | 35 | 15 分查 Jieba、用户词典和三类候选识别，10 分查专名和线路、时间规则设计，6 分查 48 篇批处理，4 分查类型、位置和来源字段。提交源码、词表和运行记录。 |
| 识别结果与质量检查 | 20 | 8 分查结构化 JSON，8 分查人工抽查、差错与改进，4 分查泛称误报和重叠控制。提交实体 JSON 和你填写的抽查表。 |
| 词频可视化与迭代优化 | 20 | 10 分查三类词频图，10 分查图表、原句、规则变化与重跑效果的证据链。提交两版图、频次表及具体案例。 |
| 报告与可复现性 | 10 | 记录 Jieba 版本、配置、运行命令、输入输出、代表案例及局限。用 `run_summary.json` 保存输入和配置哈希与运行参数。 |

两版一键重跑可用 `python recognize.py --version both --output ./result`。按手册做实验时先跑 V1 并记录观察，再运行或调整 V2。
