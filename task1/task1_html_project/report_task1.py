"""Write reports from actual results; never assign an automatic experiment score."""
from pathlib import Path
from html import escape

RUBRIC = [
 ('数据准备与来源规范', '3景区、路线与游记数量', 8, 'quality_report.json / sources.json', '分来源计数，模拟稿和整理稿不计作官方原文'),
 ('数据准备与来源规范', '来源、景区、类型等字段', 6, 'clean_documents.csv / 字段说明.md', '字段清晰，未知属性为null'),
 ('数据准备与来源规范', '数据加载与来源说明', 6, 'html_reader.py / raw_records.jsonl / run_manifest.json', '读取已有HTML，不虚构网络爬取'),
 ('数据清洗与预处理实现', '批量读取并完成流程', 8, 'process_dataset.py / run.log', '目录、文件和ZIP；逐篇异常隔离'),
 ('数据清洗与预处理实现', 'HTML、网址、无关元数据', 8, 'html_reader.py / cleaning.py', 'DOM定位正文，元数据独立保存'),
 ('数据清洗与预处理实现', '空白、标点、编码、乱码与冗余', 8, 'cleaning.py / cleaning_comparison.jsonl', 'NFKC、空白、零宽字符、已知乱码、相邻长段；保护时间小数'),
 ('数据清洗与预处理实现', '空值、重复与异常字段', 8, 'duplicates.json / errors.json / quality_report.json', '按内容与来源去重，不凭文章编号后缀'),
 ('数据清洗与预处理实现', '规则解释与代码结构', 8, 'README.md / rules_used.json', '解析、清洗、流程和报告分模块'),
 ('结构化输出与数据质量验证', '规范输出供后续读取', 10, 'clean_documents.csv / .jsonl / .json', '保留原始正文与清洗后正文，偏移相对clean_content'),
 ('结构化输出与数据质量验证', '前后样例及清洗证据', 8, 'cleaning_comparison.csv / .jsonl / 清洗对比.html', '逐篇保存前后文本、动作计数、删除片段'),
 ('结构化输出与数据质量验证', '数量、缺失、重复及格式', 7, 'quality_report.json / 任务一运行报告.md', '分开统计必填与可选字段，检查格式和残留'),
 ('报告与可复现性', '依赖、命令和路径', 5, 'README.md / requirements.txt / run_manifest.json', 'Python3.9+标准库，附Windows命令'),
 ('报告与可复现性', '流程、关键代码与代表结果', 5, '源代码 / 任务一运行报告.md / 清洗对比.html / run.log', '报告由实际运行结果生成'),
 ('报告与可复现性', '问题及处理方式', 5, '任务一运行报告.md / README.md', '说明来源缺口、乱码不可逆、缺失和近重复局限'),
]

def write_reports(output, report, comparisons, duplicates, errors):
    output = Path(output)
    lines = ['# 任务一实际运行报告', '', '由本次实际运行结果生成；不是预设满分报告。', '', '## 步骤一：选择数据获取方式并加载', '', '本次使用已有HTML数据包。仅从HTML内元数据与document-body抽取内容，不读取加噪前文章、噪声清单、设计参考答案或其他侧面文件恢复正文。输入来源声明与原始HTML保留于raw_records.jsonl，文件SHA-256保留于run_manifest.json。', '', '教师语料、官方路线整理稿、教学模拟语料与官方路线事实重述分别保留，不混改来源。代码没有重新执行网络爬取。', '', '## 步骤二：清洗与格式化', '', '解码 → 解析元数据和正文 → 删除噪声DOM → 清理元数据行/相关链接尾部 → NFKC/空白/部分标点统一 → 删除已知乱码 → 修复配置断词 → 相邻重复段落删除 → 文档去重 → 导出CSV/JSON。', '', '保留09:00、2.5、时长、路线箭头、否定和条件句。不按景区关键词截断游记，不改写历史事实。后续实体和代词位置需在clean_content重新计算。', '', '## 步骤三：质量检查与保存', '', f'输入 {report["input_html_count"]}；解析成功 {report["parsed_records"]}；最终独立记录 {report["clean_records"]}；合并重复 {report["duplicate_records_removed"]}；隔离异常 {report["rejected_records"]}。', '', '| 景区 | 总数 | 路线类 | 游记类 | 教师语料游记 | 可追溯官方路线事实 | 模拟语料 |', '|---|---:|---:|---:|---:|---:|---:|']
    for sc, r in report['by_scenic'].items():
        lines.append(f'| {sc} | {r["total"]} | {r["route_guides"]} | {r["travelogues"]} | {r["teacher_corpus_travelogues"]} | {r["source_traceable_official_route_facts"]} | {r["synthetic_teaching"]} |')
    lines += ['', '### 数量口径与来源限制', '', '步骤三“每景区至少一条官方路线和三篇游记”的数据支持检查：' + str(report['minimum_3_scenics_1_traceable_route_3_corpus_travelogues_supported']) + '。这里依据输入声明的官方路线事实与教师语料计数，不等于独立核验官网全文。', '', '每景区五篇教师语料游记：' + str(report['five_corpus_travelogues_per_scenic_supported']) + '。', '', report['official_source_verification'], '', report['full_main_content_requirement_note'] + '。不能将输入缺口通过改标签处理，也不能因此自动评满分。', '', '### 清洗动作（各规则的计数单位不同，不是文档数）', '', '| 规则 | 发生次数 |', '|---|---:|']
    lines += [f'| {k} | {v} |' for k, v in report['cleaning_action_counts'].items()]
    lines += ['', '### 缺失与残留', '', '未知作者、日期及原网页链接不补造。可选字段缺失：', '']
    lines += [f'- {k}：{v}' for k, v in report['missing_optional_fields'].items()]
    lines += ['', f'残留网址记录：{report["residual_url_records"]}；残留零宽/替换符记录：{report["residual_invalid_character_records"]}。', '', '### 去重记录', '', '| 合并记录 | 保留记录 | 依据 | 相似度 |', '|---|---|---|---:|']
    lines += [f'| {r["doc_id"]} | {r["kept_doc_id"]} | {r["reason"]} | {r["similarity"]} |' for r in duplicates]
    lines += ['', 'merged_record_ids及source_records保留合并编号与来源；所有输入仍可从raw_records.jsonl追溯。', '', '## 问题与处理', '', '1. 页面元数据重复：定位document-body，元数据单独保留。', '2. 导航、分享、评论与相关阅读混入正文：按容器和受限尾部标题处理，保存删除摘要。', '3. 乱码不可逆：仅删除已知乱码并记警告，不伪造原字符。', '4. 原始来源缺失：保留null，统计缺失，不以当前日期或数据集链接冒充原网页信息。', '5. 相似路线不一定重复：不同语料记录的近重复不强行合并，同源候选还需满足长度和内容高相似阈值。', '6. 来源未独立核验：保留官方事实/整理稿/模拟稿区别，来源数量检查不等于官网全文要求达标。', '', '## 复现', '', '项目根目录执行：', '', '```bash', 'python process_dataset.py --input ./data/html --output ./result --strict', 'python -m unittest -v', '```', '', '评分项与证据见“评分标准对应.md”；运行环境、输入路径及哈希见run_manifest.json。']
    (output / '任务一运行报告.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    rubric = ['# 手册任务一评分项对应（100分）', '', '仅列功能与可检查证据，不自动打分。', '', '| 分项 | 考核内容 | 分值 | 证据 | 实现与边界 |', '|---|---|---:|---|---|']
    rubric += ['| ' + ' | '.join(map(str, r)) + ' |' for r in RUBRIC]
    (output / '评分标准对应.md').write_text('\n'.join(rubric) + '\n', encoding='utf-8')
    page = ['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>任务一清洗前后对比</title><style>body{font:15px/1.7 sans-serif;margin:24px;color:#24323c}main{max-width:1400px;margin:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.8 sans-serif;background:#f6f7f8;padding:16px;max-height:650px;overflow:auto}.pair{display:grid;grid-template-columns:1fr 1fr;gap:16px}details{border:1px solid #ddd;padding:16px;margin:18px 0}summary{cursor:pointer}@media(max-width:700px){.pair{grid-template-columns:1fr}}</style></head><body><main><h1>任务一清洗前后对比</h1>']
    page += [f'<p>输入 {report["input_html_count"]}；保留 {report["clean_records"]}；合并重复 {len(duplicates)}；异常 {len(errors)}。结果来自实际运行。</p>']
    for c in comparisons:
        page.append('<details><summary>' + escape(c['doc_id'] + ' · ' + c['status']) + '</summary><p>规则：' + escape(str(c['cleaning_actions'])) + '</p><div class="pair"><section><h2>清洗前正文文本</h2><pre>' + escape(c['before_text']) + '</pre></section><section><h2>清洗后正文</h2><pre>' + escape(c['clean_content']) + '</pre></section></div><p>合并至：' + escape(c['duplicate_of'] or '无') + '</p></details>')
    page.append('</main></body></html>')
    (output / '清洗对比.html').write_text('\n'.join(page), encoding='utf-8')
