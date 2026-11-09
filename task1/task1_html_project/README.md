# 任务一：景区指南HTML数据预处理

本项目对应手册“实验项目1：景区指南数据采集与预处理”。使用上一版数据包的50篇逐篇HTML作为输入，自动完成读取、清洗、结构化与质量检查，无人工复核步骤，不需要reviewed.csv、API或额外下载数据。

## 先运行

Python 3.9或更新版本，仅使用标准库。解压本项目，在包含process_dataset.py的目录打开PowerShell：

```powershell
python --version
python process_dataset.py --input ./data/html --output ./result --strict
```

项目已附原始50个HTML及本次实际运行结果，data/html中的文章与上一版数据包一致，程序只读，不覆盖原文件。默认也可直接执行：

```powershell
python process_dataset.py
```

读取你另外保存的数据包也可以，无须先解压：

```powershell
python process_dataset.py --input "D:\Downloads\景区文章_任务1至7数据包.zip" --output ./result_zip --strict
```

或者读取已经解压的原数据包：

```powershell
python process_dataset.py --input "D:\Downloads\景区文章逐篇HTML\html" --output ./result --strict
```

路径有空格时保留双引号。程序不读取同目录的噪声生成清单、加噪前文章和参考答案；ZIP中只读取.html/.htm。输出目录不能与输入目录相同，输入目录中若包含输出子目录则跳过该输出子目录。不要将其他HTML报告放入输入目录，否则也会被视为待处理文件并检查。

--strict表示解析异常、输出格式不一致或手册步骤最低数量不足时返回非零退出码；可选字段缺失不会因此丢弃文章。strict成功不等于官方全文来源已核验，也不等于自动获得满分。项目最低数量检查针对默认3景区；处理单篇文章时可不加--strict。

## 按手册三个步骤操作

### 步骤一：数据获取方式、加载与字段理解

本次采用已有数据包，并非重新爬取网页。游客语料来自教师参考数据集IndustryCorpus2_tourism_geography；其他内容包括路线整理稿、教学模拟稿和官方路线事实重述。HTML内的来源与正文性质如实保留。

html_reader.py解码HTML并建立轻量DOM树。优先从script#article-metadata读取元数据，可回退到可见dl.metadata中的基本字段；定位唯一的div.document-body抽取正文，不将标题、基本信息表和JSON脚本混入正文。遇到多个文章容器、关键字段缺失、身份字段冲突、无正文等情况，不猜测内容，而是写入errors.json隔离。

原始文件内容、原始元数据、原始正文及输入SHA-256均保存，便于追溯。正文不因出现其他景点、未到访内容或历史名称被截断；这些现象是后续任务的研究对象。

### 步骤二：Python清洗与格式化

cleaning.py按以下顺序处理：

1. 剔除script/style/nav/footer等非正文标签，以及breadcrumb/sharebar/related/comment等噪声容器与隐藏元素；图片不把alt自动转成游客叙述。
2. 删除来源网址、发布时间、编码提示等独立元数据行；遇到“本文相关网站”等独立尾部标题，截掉其后的相关链接块。
3. 解码HTML实体，统一Unicode为NFKC，去除零宽字符和控制字符。
4. 删除明确的乱码标记“锟斤拷”和替换符。原字符无法恢复，不生成看似正确的替代文字，记录不可逆处理警告。
5. 删除正文网址；在中文附近有限统一逗号、句号与冒号。保留09:00、小数2.5、路线箭头、时间区间。
6. 合并横向空白、规范段落换行，仅修复配置中指定的“游 览→游览”，不把所有中文词间空格盲目删除。
7. 删除相邻、完全一致且达到长度阈值的重复段落。短句重复默认保留，避免删除正常的连续动作。
8. 清洗后文档去重：先按景区/类型/来源性质分组，并比较忽略空白的全文；近重复额外要求同源、标题相近、长度比≥0.97及字符5-gram Jaccard≥0.97。不同教师语料记录不会仅因近似就合并。

合并记录仍通过merged_record_ids和source_records保留所有编号与来源。实现不根据_DUP或_M等后缀、指定文章编号、设计答案和源记录列表决定删除。

清洗只处理格式和明确噪声，不纠正历史事实、改写路线、补造时间、处理任务2实体或任务4共指。条件词“如果/除非”、否定“没有去”以及段落先后保留。

### 步骤三：检查并保存

输出CSV（UTF-8带BOM，便于Windows Excel打开）、JSONL和JSON。对每个景区分别统计路线类、游记类、教师语料游记、来源可追溯的官方路线事实和模拟语料。检查必填/可选字段缺失、重复记录、日期ISO格式、残留网址及异常符号、ID唯一性。

手册步骤三的最低要求是每景区至少1条官方路线与3篇游记；代码按输入声明的官方路线事实和教师语料游记检查，并另列每景区5篇教师语料游记。来源链接存在只说明可追溯，不等于完成官网真实性或全文核验。

**当前数据的限制：官方路线整理稿和事实重述不是官网全文。若将手册主要内容理解为每景区5篇独立官方原文，则该项数据条件当前仍不满足，代码不会改标签假装满足。** 此限制在quality_report.json和运行报告中明确输出；其余清洗与结构化工作已实际实现。

## 输出文件

| 文件 | 用途 |
|---|---|
| result/clean_documents.csv | 规范化主数据，Excel可打开 |
| result/clean_documents.jsonl | 后续任务推荐读取，一行一条记录 |
| result/clean_documents.json | 相同主数据的JSON数组 |
| result/raw_records.jsonl | 所有解析成功输入的原始HTML、元数据、正文与哈希 |
| result/cleaning_comparison.csv | 每篇正文清洗前后、字符数、日期与状态对比 |
| result/cleaning_comparison.jsonl | 另含被删除片段摘要与规则计数 |
| result/清洗对比.html | 浏览器可打开，逐篇展开查看前后结果 |
| result/quality_report.json | 数量、来源分层、缺失、格式、残留与局限 |
| result/duplicates.json | 重复合并关系、方法及相似度 |
| result/errors.json | 异常隔离记录，含原始HTML；当前输入实际为空数组 |
| result/sources.json | 来源清单及合并来源追踪 |
| result/rules_used.json | 本次实际规则快照 |
| result/run_manifest.json | 版本、Python、输入输出路径、输入哈希、耗时 |
| result/run.log | 实际运行日志 |
| result/任务一运行报告.md | 自动生成的步骤、结果及问题说明 |
| result/评分标准对应.md | 20+40+25+15分各项与代码/证据逐条对应 |

clean_documents中保留raw_content（原始正文HTML），原文件全文位于raw_records。清洗结果为clean_content；text只是同值兼容字段，后续只选择其中一个读取，不将两列拼接。

## 后续任务如何读取

```python
import json
from pathlib import Path

records = [json.loads(line) for line in Path("result/clean_documents.jsonl").read_text(encoding="utf-8").splitlines()]
for record in records:
    content = record["clean_content"]
    scenic = record["scenic_name"]
    source_kind = record["provenance_kind"]
```

后续实体、共指、条件等的start/end应针对clean_content，按Unicode字符索引、左闭右开重新计算。不要沿用HTML或上一数据包评测参考文本的偏移。官方/游客路线比较及图谱融合必须同时查看provenance_kind和content_origin，不能仅凭text_type判断真实性。

## 规则调整与验证

```powershell
python -m unittest -v
python process_dataset.py --input ./data/html --output ./result_custom --config ./rules.example.json
```

rules.example.json是完整默认配置，可修改噪声类名、断词修复词表与去重阈值。HTML若来自其他网站，需要适配正文/元数据结构；本项目严格针对本次数据包及同结构HTML，不能保证任意原网站页面无需适配。

近重复比较适合本实验规模，最坏复杂度随文档数近似平方增长。当前50篇的处理很轻，耗时以run_manifest.json为准，大规模数据应换用候选检索或MinHash。测试覆盖正文范围、时间小数、否定条件、乱码、编码、异常、来源隔离及去重误删边界；不使用测试结果冒充任务2—7效果评估。
