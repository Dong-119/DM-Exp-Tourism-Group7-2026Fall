"""Task 2: Jieba segmentation with dictionary and regex NER with character offsets into task 1 text."""
import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from html import escape
from pathlib import Path

import jieba

ROOT = Path(__file__).resolve().parent
TYPES = ('POI', 'TRANSPORT', 'TIME')
LABELS = dict(zip(TYPES, ('景点 POI', '交通方式', '时间节点')))
NUM = r'(?:[0-9]+(?:\.[0-9]+)?|[零一二两三四五六七八九十百半]+)'
PERIOD = '凌晨|清晨|早晨|早上|上午|中午|午后|下午|傍晚|晚上|夜间'
CLOCK = r'(?:[01]?[0-9]|2[0-3])[:：][0-5][0-9]'
COMMON_TIME = [
    rf'(?:{PERIOD})?\s*{CLOCK}',
    rf'(?:约|大约|将近)?(?:{NUM}(?:个)?半?|半个)(?:小时|分钟|秒钟)(?:左右)?',
    r'(?:[0-9]{4}年)?(?:1[0-2]|0?[1-9])月(?:3[01]|[12][0-9]|0?[1-9])[日号]',
    rf'第{NUM}天|半天|一天|{PERIOD}',
]
EXTRA_TIME = [
    rf'(?:{PERIOD})?\s*{CLOCK}\s*(?:—|–|~|～|至|-)\s*(?:{PERIOD})?\s*{CLOCK}',
    rf'(?:{PERIOD})?\s*(?:[01]?[0-9]|2[0-3]|[一二两三四五六七八九十]{{1,3}})点(?:半|多|[0-5]?[0-9]分)?(?![钟钱滴])',
    r'昨天|今天|明天|次日|当天',
]
LINE = re.compile(r'(?:地铁[0-9一二三四五六七八九十]+号线|[0-9一二三四五六七八九十]+号线(?:号线)?地铁)')
BUS = re.compile(r'(?<=坐)[0-9]{1,4}路|(?<=乘)[0-9]{1,4}路|[0-9]{1,4}路公交(?:车)?')
SENT = re.compile(r'[^。！？!?\n]+[。！？!?]?|[。！？!?]')


def load_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def load_docs(path):
    source = path.read_text(encoding='utf-8-sig')
    if source.lstrip().startswith('['):
        docs = json.loads(source)
    else:
        docs = [json.loads(line) for line in source.splitlines() if line.strip()]
    if not docs:
        raise ValueError('输入没有文章')
    ids = set()
    for doc in docs:
        if not isinstance(doc.get('clean_content'), str) or not doc['clean_content'].strip():
            raise ValueError(f"正文为空或缺少 clean_content：{doc.get('doc_id')}")
        if not doc.get('scenic_name') or not doc.get('doc_id') or doc['doc_id'] in ids:
            raise ValueError(f"缺少景区、缺少编号或编号重复：{doc.get('doc_id')}")
        ids.add(doc['doc_id'])
    return docs


def compile_rules(config, improved, dictionary_path):
    entries = {}
    for area, names in config['POI'].items():
        for name in names:
            entries.setdefault(name, []).append(area)
    if improved:
        for area, names in config.get('poi_additions', {}).items():
            for name in names:
                entries.setdefault(name, []).append(area)
    noise = set(config['baseline_noise'])
    if improved:
        noise -= set(config.get('stopwords', []))
    for name in noise:
        entries.setdefault(name, []).append('未定位')
    transport = config['TRANSPORT'] + (config.get('transport_additions', []) if improved else [])
    aliases = config['alias'] if improved else {}

    # 自定义词典将多字专名加入 Jieba 的候选切分路径。
    gates = config.get('scoped_gates', {}) if improved else {}
    words = set(entries) | set(transport)
    for aliases_by_gate in gates.values():
        words.update(aliases_by_gate)
    dictionary_path.write_text(
        ''.join(f'{word} 1000000\n' for word in sorted(words)), encoding='utf-8'
    )
    # 每个版本使用独立的分词器，V2 的词表不会改变 V1。
    tokenizer = jieba.Tokenizer()
    tokenizer.load_userdict(str(dictionary_path))

    return {
        'tokenizer': tokenizer, 'owners': entries,
        'transport': set(transport), 'aliases': aliases,
        'time': [re.compile(p) for p in COMMON_TIME + (EXTRA_TIME if improved else [])],
        'improved': improved,
        'gates': gates,
    }


def recognize(doc, rules):
    text = doc['clean_content']
    scenic = doc['scenic_name']
    candidates = []
    gates = rules['gates'].get(scenic, {})
    # Jieba 产出的 token 及字符边界直接用于 POI 与普通交通实体。
    for term, start, end in rules['tokenizer'].tokenize(text, HMM=False):
        canonical = rules['aliases'].get(term, term)
        if term in rules['owners']:
            candidates.append((start, end, 'POI', term, canonical))
        elif term in gates:
            left = text[max(0, start - 10):start]
            if not re.search(r'(?:酒店|车站|地铁站|颐和园|动物园|圆明园)(?:的)?$', left):
                candidates.append((start, end, 'POI', term, gates[term]))
        if term in rules['transport']:
            # 设施或街名中的交通词不单独记为交通方式。
            facility_suffix = {'地铁': '站', '步行': '街'}.get(term)
            if rules['improved'] and facility_suffix and text.startswith(facility_suffix, end):
                continue
            candidates.append((start, end, 'TRANSPORT', term, canonical))
    # 线路号和时间可跨多个 token，使用原文正则保留完整跨度。
    if rules['improved']:
        for pattern, canonical in [(LINE, '地铁'), (BUS, '公交')]:
            candidates.extend((*m.span(), 'TRANSPORT', m.group(), canonical) for m in pattern.finditer(text))
    for pattern in rules['time']:
        for match in pattern.finditer(text):
            term = match.group().lstrip()
            start = match.end() - len(term)
            if start and text[start - 1].isdigit() and term[0].isdigit():
                continue
            candidates.append((start, match.end(), 'TIME', term, term))

    # 先取最长候选，等长按位置和类别稳定排序。保留每次出现，消除同位置的重复命中。
    occupied = set()
    entities = []
    sentences = list(SENT.finditer(text))
    for start, end, kind, term, canonical in sorted(
        set(candidates), key=lambda c: (c[0] - c[1], c[0], c[2], c[3], c[4])
    ):
        span = range(start, end)
        if occupied.intersection(span):
            continue
        occupied.update(span)
        owners = rules['owners'].get(term, []) if kind == 'POI' else []
        if kind == 'POI' and term in rules['gates'].get(scenic, {}):
            owners = [scenic]
        scope = None
        if kind == 'POI':
            scope = scenic if scenic in owners else owners[0] if len(owners) == 1 else '未定位'
        sentence = next((m for m in sentences if m.start() <= start < m.end()), None)
        entities.append(dict(type=kind, text=term, canonical=canonical, start=start, end=end,
                             poi_scope=scope, in_target_scope=(scope == scenic) if kind == 'POI' else None,
                             entity_key=f'{scope}:{canonical}' if kind == 'POI' else f'{kind}:{canonical}',
                             sentence=sentence.group() if sentence else None,
                             sentence_start=sentence.start() if sentence else None))
    return sorted(entities, key=lambda e: e['start'])


def frequency(results):
    return Counter((d['scenic_name'], e['type'], e['entity_key'], e['canonical'])
                   for d in results for e in d['entities'])


def csv_frequency(path, counts):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['scenic_name', 'type', 'entity_key', 'canonical', 'count'])
        for row, count in sorted(counts.items()):
            writer.writerow([*row, count])


def chart(path, counts, title):
    colors = ['#35699b', '#228577', '#9d5825']
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="430" viewBox="0 0 1080 430">',
             '<rect width="1080" height="430" fill="#f7f9fb"/>',
             '<g font-family="Microsoft YaHei, PingFang SC, Noto Sans CJK SC, sans-serif" fill="#1e3347">',
             f'<text x="28" y="44" font-size="26" font-weight="bold">{escape(title)}</text>',
             '<text x="28" y="72" font-size="14">每类前 8 项 · 三景区合计 · 横条按各类最大词频缩放</text>']
    for index, kind in enumerate(TYPES):
        x = 28 + index * 354
        ranked = Counter()
        for (_, typ, key, name), n in counts.items():
            if typ == kind:
                ranked[(key, name)] += n
        top = sorted(ranked.items(), key=lambda pair: (-pair[1], pair[0]))[:8]
        limit = top[0][1] if top else 1
        parts.append(f'<text x="{x}" y="112" font-size="18" font-weight="bold">{LABELS[kind]}</text>')
        for row, ((key, name), n) in enumerate(top):
            label = key if kind == 'POI' and key.startswith(('天坛:长廊', '颐和园:长廊')) else name
            y = 140 + row * 32
            width = max(1, 153 * n / limit)
            parts += [f'<text x="{x}" y="{y+15}" font-size="13">{escape(label)}</text>',
                      f'<rect x="{x+136}" y="{y}" width="{width:.1f}" height="20" rx="3" fill="{colors[index]}"/>',
                      f'<text x="{x+143+width:.1f}" y="{y+15}" font-size="13">{n}</text>']
    parts.append('</g></svg>')
    path.write_text('\n'.join(parts), encoding='utf-8')


def evaluate(reference, results, documents):
    predictions = {d['doc_id']: d['entities'] for d in results}
    totals = Counter()
    cases = []
    for sample in reference:
        doc_id = sample['doc_id']
        source = documents[doc_id]
        start, end = sample['start'], sample['end']
        if source[start:end] != sample['text']:
            raise ValueError(f'样例正文或位置与任务一数据不一致：{sample["case_id"]}')
        gold = {(e['start'], e['end'], e['type']) for e in sample['entities']}
        pred = {(e['start'], e['end'], e['type']) for e in predictions[doc_id]
                if start <= e['start'] and e['end'] <= end}
        totals.update(tp=len(gold & pred), fp=len(pred - gold), fn=len(gold - pred))
        def expand(items):
            return [dict(start=a, end=b, type=k, text=source[a:b]) for a, b, k in sorted(items)]
        cases.append(dict(case_id=sample['case_id'], doc_id=doc_id,
                          false_positives=expand(pred-gold), false_negatives=expand(gold-pred)))
    tp, fp, fn = (totals[k] for k in ('tp', 'fp', 'fn'))
    return dict(tp=tp, fp=fp, fn=fn, precision=tp/max(1,tp+fp), recall=tp/max(1,tp+fn),
                f1=2*tp/max(1,2*tp+fp+fn), cases=cases)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT/'data/clean_documents.jsonl')
    parser.add_argument('--output', type=Path, default=ROOT/'result')
    parser.add_argument('--config', type=Path, default=ROOT/'config/entities.json')
    parser.add_argument('--review', type=Path, help='可选的抽查样例，仅用于计算指标')
    parser.add_argument('--version', choices=['v1', 'v2', 'both'], default='v2')
    parser.add_argument('--inspect-doc', help='额外导出指定文档的 Jieba 分词和字符位置')
    args = parser.parse_args()
    # 步骤一：读取任务一正文，按版本编译词典和时间规则。
    docs = load_docs(args.input)
    config = load_json(args.config)
    if args.inspect_doc and not any(doc['doc_id'] == args.inspect_doc for doc in docs):
        parser.error(f'找不到文档编号 {args.inspect_doc}')
    args.output.mkdir(parents=True, exist_ok=True)
    summary = {'input_sha256': hashlib.sha256(args.input.read_bytes()).hexdigest(),
               'config_sha256': hashlib.sha256(args.config.read_bytes()).hexdigest(),
               'offset_convention': 'Unicode 字符索引，左闭右开，针对任务一 clean_content',
               'documents': len(docs), 'jieba_version': jieba.__version__, 'hmm': False, 'versions': {}}
    for version in (('v1', 'v2') if args.version == 'both' else (args.version,)):
        dictionary_path = args.output / f'userdict_{version}.txt'
        rules = compile_rules(config, version == 'v2', dictionary_path)
        results = []
        for doc in docs:
            entities = recognize(doc, rules)
            if doc['doc_id'] == args.inspect_doc:
                tokens = [
                    dict(token=term, start=start, end=end)
                    for term, start, end in rules['tokenizer'].tokenize(doc['clean_content'], HMM=False)
                ]
                save_json(args.output / f'tokens_{version}.json', dict(doc_id=args.inspect_doc, tokens=tokens))
            assert all(doc['clean_content'][e['start']:e['end']] == e['text'] for e in entities)
            assert all(a['end'] <= b['start'] for a, b in zip(entities, entities[1:]))
            meta = {k: doc.get(k) for k in ('doc_id','scenic_name','title','text_type',
                                            'provenance_kind','source_name','source_url','input_path','reference_url','source_record_id','content_origin','source_records')}
            results.append(dict(**meta, entities=entities))
        # 步骤二：统计每次提及，保存图表供基线分析与迭代对比。
        counts = frequency(results)
        # 步骤三：导出实体及证据。实体规范表随项目提供。
        save_json(args.output/f'entities_{version}.json', results)
        csv_frequency(args.output/f'frequency_{version}.csv', counts)
        chart(args.output/f'frequency_{version}.svg', counts, f'{version.upper()} 实体词频')
        by_scenic = {s: dict(Counter(e['type'] for d in results if d['scenic_name'] == s
                                   for e in d['entities']))
                     for s in sorted({d['scenic_name'] for d in docs})}
        summary['versions'][version] = dict(by_scenic=by_scenic, mentions=sum(counts.values()))
        if args.review:
            review = evaluate(load_json(args.review), results, {d['doc_id']: d['clean_content'] for d in docs})
            save_json(args.output/f'review_{version}.json', review)
        print(version, 'documents', len(docs), 'mentions', sum(counts.values()), by_scenic)
    save_json(args.output/'run_summary.json', summary)


if __name__ == '__main__':
    main()
