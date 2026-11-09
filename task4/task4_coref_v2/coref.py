"""任务四第二版。检测、生成候选、规则消解，导出可复核的原文映射。"""
import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from html import escape
from pathlib import Path

import jieba
from recognize import load_docs, save_json

ROOT = Path(__file__).resolve().parent
DEFAULT_DOCS = ['GG_S04', 'YHY_S04', 'TT_S04', 'YHY_T05', 'TT_T04']
PLACE = {'这里', '那里', '这儿', '那儿', '此处', '此地', '原地'}
PEOPLE = {'他', '她', '他们', '她们'}
SPEAKER = {'我', '我们', '你', '你们'}
PAIR = {'前者', '后者'}
DEICTIC = {'这', '那', '这座', '那座', '这条', '那条', '这次', '那次', '这个', '那个',
           '这些', '那些', '这样', '那样', '这种', '那种', '这张', '那张', '这位', '那位'}
FORMS = PLACE | PEOPLE | PAIR | DEICTIC | {'它', '它们', '其', '彼此'}
PRONOUN = re.compile('|'.join(sorted(FORMS, key=lambda term: (-len(term), term))))
# Jieba 用于句内分词。分句由标点正则实现，保持字符偏移。
SENTENCE = re.compile(r'[^。！？!?；;\n]+[。！？!?；;]?')
QUOTES = {'“': '”', '‘': '’', '"': '"', "'": "'", '「': '」', '『': '』'}
PERSON_TERMS = ['工作人员', '同行游客', '售票员', '导游', '同伴', '父亲', '母亲', '孩子',
                '同学', '老师', '朋友', '先生', '女士', '小贩', '中国人']
GROUP_TERMS = ['孩子们', '游客们', '父母', '同学们', '工作人员们', '乘客']
OBJECT_TERMS = {'大熊猫': 'ANIMAL', '熊猫': 'ANIMAL', '无轨电车': 'VEHICLE',
                '公共汽车': 'VEHICLE', '公共电车': 'VEHICLE', '电车': 'VEHICLE',
                '游船': 'VEHICLE', '建筑物': 'OBJECT', '建筑群': 'OBJECT',
                '围墙': 'OBJECT', '照片': 'OBJECT', '挂轴': 'OBJECT', '游戏': 'EVENT'}
ANNOTATION = ['mention_id', 'doc_id', 'mention', 'start', 'end', 'sentence',
              'context_start', 'context', 'status', 'antecedent_text',
              'antecedent_start', 'antecedent_end', 'antecedent_type', 'annotator', 'notes']


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def sentences_for(text):
    return [dict(index=i, start=m.start(), end=m.end(), text=m.group())
            for i, m in enumerate(SENTENCE.finditer(text))]


def sentence_index(sentences, start):
    return next((s['index'] for s in sentences if s['start'] <= start < s['end']), -1)


def detect(doc, tokenizer, sentences, window):
    text = doc['clean_content']
    mentions = []
    for sentence in sentences:
        tokens = [dict(text=term, start=a + sentence['start'], end=b + sentence['start'])
                  for term, a, b in tokenizer.tokenize(sentence['text'], HMM=False)]
        token_spans = {(token['start'], token['end']) for token in tokens}
        occurrence = Counter()
        for match in PRONOUN.finditer(sentence['text']):
            word = match.group()
            start, end = match.start() + sentence['start'], match.end() + sentence['start']
            # 排除其他/其实等词内部的单字。补充独立指示结构“这是/这很”等。
            if len(word) == 1 and (start, end) not in token_spans:
                if word not in {'这', '那'} or not re.match(r'是|很|可能|不应|值得', text[end:]):
                    continue
            occurrence[word] += 1
            left = text[start - 1:start] if start else ''
            quoted = left in QUOTES and text[end:end + 1] == QUOTES[left]
            context_start = max(0, start - window)
            context_end = min(len(text), sentence['end'] + 100)
            mentions.append(dict(
                mention_id=f"{doc['doc_id']}:{start}:{end}", doc_id=doc['doc_id'],
                scenic_name=doc['scenic_name'], text=word, start=start, end=end,
                sentence_id=f"{doc['doc_id']}:s{sentence['index']:03d}",
                sentence_index=sentence['index'], sentence_start=sentence['start'],
                sentence_end=sentence['end'], sentence=sentence['text'],
                sentence_start_offset=start - sentence['start'],
                occurrence_in_sentence=occurrence[word], quoted=quoted,
                context_start=context_start, context_end=context_end,
                context=text[context_start:context_end],
                source_name=doc.get('source_name'), source_url=doc.get('source_url'),
                reference_url=doc.get('reference_url'), source_record_id=doc.get('source_record_id'),
                source_records=doc.get('source_records'), provenance_kind=doc.get('provenance_kind'),
                clean_sha256=digest(text), tokens=tokens))
    return mentions


def candidates(doc, entities, sentences):
    text = doc['clean_content']
    pool = []
    for entity in entities:
        start, end = entity['start'], entity['end']
        if not 0 <= start < end <= len(text) or text[start:end] != entity['text']:
            raise ValueError(f"任务二实体偏移不匹配：{doc['doc_id']} {entity['text']}")
        if entity['type'] == 'POI':
            pool.append(dict(text=entity['text'], start=start, end=end, kind='POI',
                             entity_key=entity.get('entity_key'), canonical=entity.get('canonical')))
    terms = {term: 'PERSON' for term in PERSON_TERMS}
    terms.update({term: 'GROUP' for term in GROUP_TERMS})
    terms.update(OBJECT_TERMS)
    pattern = re.compile('|'.join(re.escape(word) for word in sorted(terms, key=lambda word: (-len(word), word))))
    for match in pattern.finditer(text):
        word = match.group()
        if terms[word] == 'ANIMAL' and text[match.end():match.end()+1] in {'馆', '区'}:
            continue
        if terms[word] == 'ANIMAL' and re.search(r'比[^，。！？;；\n]*$', text[max(0, match.start()-30):match.start()]):
            continue
        start = match.start()
        # 保留“尤先生”“一个售票员”“我朋友”等名词短语的可读边界。
        prefix = text[max(0, start - 4):start]
        extension = re.search(r'一个$|一位$|我的$|我$', prefix)
        if word in {'先生', '女士'} and start and re.match(r'[\u4e00-\u9fff]', text[start - 1]):
            start -= 1
        elif extension and terms[word] == 'PERSON':
            start -= len(extension.group())
        pool.append(dict(text=text[start:match.end()], start=start, end=match.end(), kind=terms[word],
                         entity_key=None, canonical=word))
    # 复数人群与名词短语单独识别，避免把“他们”自己作为先行词。
    for match in re.finditer(r'(?:几个|几位|一群)(?:朋友|同学|孩子|游客|中国人)', text):
        pool = [c for c in pool if not (match.start() <= c['start'] and c['end'] <= match.end())]
        pool.append(dict(text=match.group(), start=match.start(), end=match.end(), kind='GROUP',
                         entity_key=None, canonical=match.group()))
    for candidate in pool:
        candidate['candidate_id'] = f"{doc['doc_id']}:{candidate['start']}:{candidate['end']}:{candidate['kind']}"
        candidate['sentence_index'] = sentence_index(sentences, candidate['start'])
    return sorted({(c['start'], c['end'], c['kind']): c for c in pool}.values(),
                  key=lambda c: (c['end'], c['start'], c['kind']))


def preceding(pool, mention, window, sentence_window):
    return [dict(c, distance_chars=mention['start'] - c['end'],
                 distance_sentences=mention['sentence_index'] - c['sentence_index'])
            for c in pool
            if 0 <= mention['start'] - c['end'] <= window
            and 0 <= mention['sentence_index'] - c['sentence_index'] <= sentence_window]


def resolve_one(mention, nearby, text, previous):
    word = mention['text']
    local_start = max(mention['sentence_start'], text.rfind('，', mention['sentence_start'], mention['start']) + 1)
    clause = text[local_start:mention['sentence_end']]
    if mention['quoted']:
        return None, 'nonreferential', 'quoted_mention', '代词本身被引号引用，保留原词'
    if word in SPEAKER:
        return None, 'nonreferential', 'speaker', '说话者或读者指称，缺少篇内名词链接'
    if re.search(r'先行词|指代|强行对应|替换成|可能指|不能.*对应', clause):
        return None, 'ambiguous', 'metalinguistic', '当前分句讨论指代或替换，最近景点不足以确定所指'
    if word in DEICTIC or word == '彼此':
        return None, 'ambiguous', 'event_or_demonstrative', '可能是事件、限定语或相互指称，保留供核验'
    if word in PAIR:
        places = [c for c in nearby if c['kind'] == 'POI']
        # 优先上一句，防止后者错误地以本句已重复的名称组成新景点对。
        for index in sorted({c['sentence_index'] for c in places}, reverse=True):
            in_sentence = [c for c in places if c['sentence_index'] == index]
            for first, second in reversed(list(zip(in_sentence, in_sentence[1:]))):
                between = text[first['end']:second['start']]
                if (first.get('entity_key') != second.get('entity_key')
                        and re.search(r'又|再|随后|和|与|、', between)):
                    return (first if word == '前者' else second), 'linked', 'ordered_pair', '按最近有顺序线索的景点对选择前项或后项'
        return None, 'unresolved', 'pair_missing', '窗口内缺少两个不同且有顺序线索的景点'
    kinds = ({'POI'} if word in PLACE else {'GROUP'} if word in {'他们', '她们'}
             else {'PERSON'} if word in {'他', '她'} else {'ANIMAL', 'GROUP'} if word == '它们'
             else {'POI', 'OBJECT', 'VEHICLE', 'ANIMAL'})
    compatible = [c for c in nearby if c['kind'] in kinds]
    if word == '它们':
        compatible = [c for c in compatible if c['kind'] == 'ANIMAL']
    if word == '其' and compatible and compatible[-1]['kind'] == 'OBJECT':
        return None, 'ambiguous', 'possessive_scope', '泛称物体与整座景区均可能是所属对象，保留其字供核验'
    # 连续人物代词沿用已建立的指称，当前分句没有新显式人物主语时减少宾语抢占。
    if word in {'他', '她'} and not any(c['kind'] == 'PERSON' and c['start'] >= local_start for c in nearby):
        for record in reversed(previous):
            answer = record['predicted_antecedent']
            if (record['text'] == word and answer and answer['kind'] == 'PERSON'
                    and mention['start'] - record['end'] <= 100
                    and mention['sentence_index'] - record['sentence_index'] <= 2):
                return answer, 'linked', 'person_chain', '当前分句未引入新人物，沿用近邻同形代词的显式先行词'
    if compatible:
        chosen = compatible[-1]
        # 同一句“名词是……，它……”沿用句首主语，避免选到说明中的宾语。
        same = [c for c in compatible if c['sentence_index'] == mention['sentence_index']]
        if same:
            first = same[0]
            between = text[first['end']:mention['start']]
            if re.match(r'是', between):
                chosen = first
                return chosen, 'linked', 'topic_subject', '当前句以该名词作主语展开说明'
        return chosen, 'linked', 'typed_nearest', '按代词类型筛选后，取窗口内最近的显式候选'
    # 仅在本窗口没有兼容名词时沿用已落地的同形代词链接，禁止连向未来。
    for record in reversed(previous):
        answer = record['predicted_antecedent']
        if (record['text'] == word and answer and answer['kind'] in kinds
                and mention['start'] - record['end'] <= 100
                and mention['sentence_index'] - record['sentence_index'] <= 2):
            return answer, 'linked', 'pronoun_chain', '沿用近邻同形代词已链接的显式先行词'
    return None, 'unresolved', 'no_typed_candidate', '窗口内没有满足类型要求的显式先行词'


def selected_docs(args, docs):
    ids = args.docs
    if len(set(ids)) != len(ids) or not 3 <= len(ids) <= 5:
        raise ValueError('请选择 3–5 篇不同的游记')
    for doc_id in ids:
        if doc_id not in docs or docs[doc_id].get('text_type') != 'travelogue':
            raise ValueError(f'不是有效游记：{doc_id}')
    return [docs[doc_id] for doc_id in ids]


def export_mentions(args, docs, selections):
    tokenizer = jieba.Tokenizer()
    tokenizer.load_userdict(str(ROOT / 'config/userdict_v2.txt'))
    mentions = []
    sentence_rows = []
    for doc in selections:
        sentences = sentences_for(doc['clean_content'])
        sentence_rows.append(dict(doc_id=doc['doc_id'], sentences=sentences))
        mentions.extend(detect(doc, tokenizer, sentences, args.window))
    save_json(args.output/'mentions.json', mentions)
    save_json(args.output/'sentences.json', sentence_rows)
    template_path = args.output/'人工标注模板.csv'
    # 重跑保留已存在的标注模板，避免覆盖用户填入的判断。
    write_template = not template_path.exists()
    if template_path.exists():
        with template_path.open(encoding='utf-8-sig', newline='') as stream:
            existing = list(csv.DictReader(stream))
        has_annotations = any(row.get('status', '').strip() for row in existing)
        if has_annotations and {row['mention_id'] for row in existing} != {m['mention_id'] for m in mentions}:
            raise ValueError('现有标注模板已填写且样本改变，请为新样本使用新的输出目录')
        write_template = not has_annotations
    if write_template:
        with template_path.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=ANNOTATION)
            writer.writeheader()
            for mention in mentions:
                writer.writerow({**{key: mention[key] for key in ['mention_id', 'doc_id', 'start', 'end',
                                  'sentence', 'context_start', 'context']}, 'mention': mention['text']})
    save_json(args.output/'sample_documents.json', [
        {**{k: doc.get(k) for k in ['doc_id', 'scenic_name', 'text_type', 'title', 'source_name',
                                   'source_url', 'provenance_kind']},
         'clean_sha256': digest(doc['clean_content']), 'text': doc['clean_content']}
        for doc in selections])
    return mentions


def rewritten_document(doc, predictions):
    text = doc['clean_content']
    parts, edits = [], []
    original_cursor = resolved_cursor = 0
    for record in predictions:
        answer = record['predicted_antecedent']
        if not answer:
            continue
        between = text[original_cursor:record['start']]
        parts.append(between)
        resolved_cursor += len(between)
        replacement = answer['text'] + ('的' if record['text'] == '其' else '')
        edits.append(dict(mention_id=record['mention_id'], original_start=record['start'],
                          original_end=record['end'], original_text=record['text'],
                          resolved_start=resolved_cursor, resolved_end=resolved_cursor + len(replacement),
                          replacement=replacement, antecedent_start=answer['start'], antecedent_end=answer['end']))
        parts.append(replacement)
        resolved_cursor += len(replacement)
        original_cursor = record['end']
    parts.append(text[original_cursor:])
    return dict(doc_id=doc['doc_id'], original_text=text, resolved_text=''.join(parts),
                replacement_count=len(edits), edits=edits)


def export_review(args, docs, predictions, texts):
    fields = ['mention_id', 'doc_id', 'scenic_name', 'provenance_kind', 'mention', 'start', 'end',
              'sentence', 'status', 'antecedent_text', 'antecedent_type', 'antecedent_start',
              'antecedent_end', 'rule', 'reason', 'baseline', 'candidate_count']
    with (args.output/'逐条核验.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for record in predictions:
            answer = record['predicted_antecedent'] or {}
            writer.writerow({**{key: record[key] for key in ['mention_id', 'doc_id', 'scenic_name',
                            'provenance_kind', 'start', 'end', 'sentence', 'status', 'rule', 'reason']},
                             'mention': record['text'], 'antecedent_text': answer.get('text'),
                             'antecedent_type': answer.get('kind'), 'antecedent_start': answer.get('start'),
                             'antecedent_end': answer.get('end'), 'candidate_count': len(record['candidates']),
                             'baseline': (record['baseline_antecedent'] or {}).get('text')})
    sections = []
    for document in texts:
        doc_id = document['doc_id']
        rows = []
        for record in predictions:
            if record['doc_id'] != doc_id:
                continue
            answer = record['predicted_antecedent']
            label = f"{answer['text']} [{answer['start']},{answer['end']}) / {answer['kind']}" if answer else '保留原词'
            marked_sentence = (escape(record['sentence'][:record['start']-record['sentence_start']])
                               + '<mark>' + escape(record['text']) + '</mark>'
                               + escape(record['sentence'][record['end']-record['sentence_start']:]))
            choices = '；'.join(f"{c['text']} [{c['start']},{c['end']}) {c['kind']}" for c in record['candidates'])
            rows.append(f"<tr><td>{escape(record['mention_id'])}</td><td>{marked_sentence}</td>"
                        f"<td>{escape(label)}<br>{escape(record['status'])}<br>{escape(record['rule'])}</td>"
                        f"<td>{escape(record['reason'])}<details><summary>窗口候选 {len(record['candidates'])} 个</summary>"
                        f"{escape(choices)}</details></td></tr>")
        sections.append(f"<section><h2>{escape(doc_id)} · {escape(docs[doc_id]['title'])}</h2>"
                        f"<p>来源类别 {escape(docs[doc_id]['provenance_kind'])}，替换 {document['replacement_count']} 处。</p>"
                        '<table><thead><tr><th>独立提及编号</th><th>原句及代词</th><th>预测</th><th>依据与候选</th></tr></thead>'
                        + '<tbody>' + ''.join(rows) + '</tbody></table><details><summary>全文消解前后对照</summary>'
                        + '<h3>原文</h3><pre>' + escape(document['original_text']) + '</pre><h3>消解后</h3><pre>'
                        + escape(document['resolved_text']) + '</pre></details></section>')
    html = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>任务四 V2 结果核验</title>'
            '<style>body{max-width:1400px;margin:30px auto;padding:0 20px;font:15px/1.7 "Microsoft YaHei",sans-serif;color:#233044}'
            'table{width:100%;border-collapse:collapse}td,th{border:1px solid #cdd5de;padding:10px;text-align:left;vertical-align:top}'
            'th{background:#edf3f8}mark{background:#ffdf80}pre{white-space:pre-wrap}section{margin-top:35px}'
            'td:first-child{overflow-wrap:anywhere;width:17%}td:nth-child(2){width:38%}details{margin:8px 0}</style>'
            '<h1>任务四 V2 结果核验</h1><p>位置对应任务一 clean_content，零基、左闭右开。'
            '黄色只标出当前这一次代词。预测及链接数供逐例核验，人工标注字段留空。</p>'
            '<p>链接类型包含景点、人、群体、动物、车辆及物体。不能确定时保留原文。'
            '全文替换是规则结果展示，可能需要语义修正。</p>' + ''.join(sections) + '</html>')
    (args.output/'核验结果.html').write_text(html, encoding='utf-8')


def resolve_stage(args, docs, mentions):
    entities = {row['doc_id']: row for row in read_json(args.entities)}
    predictions, all_pools = [], {}
    selection = [doc['doc_id'] for doc in selected_docs(args, docs)]
    if any(mention['doc_id'] not in selection for mention in mentions):
        raise ValueError('待消解列表与所选文档不同，请使用原 --docs 或重新检测')
    for doc_id in selection:
        doc = docs[doc_id]
        if doc_id not in entities:
            raise ValueError(f'任务二实体缺少文档：{doc_id}')
        text = doc['clean_content']
        row = entities[doc_id]
        if row.get('scenic_name') != doc['scenic_name']:
            raise ValueError(f'任务二与任务一景区不一致：{doc_id}')
        pool = candidates(doc, row['entities'], sentences_for(text))
        all_pools[doc_id] = pool
        previous = []
        for mention in [m for m in mentions if m['doc_id'] == doc_id]:
            if mention['clean_sha256'] != digest(text) or text[mention['start']:mention['end']] != mention['text']:
                raise ValueError(f"代词列表与输入版本不一致：{mention['mention_id']}")
            nearby = preceding(pool, mention, args.window, args.sentence_window)
            answer, status, rule, reason = resolve_one(mention, nearby, text, previous)
            record = dict(**mention, candidates=nearby, baseline_antecedent=nearby[-1] if nearby else None,
                          predicted_antecedent=answer, status=status, rule=rule, reason=reason)
            previous.append(record)
            predictions.append(record)
    texts = [rewritten_document(docs[doc_id], [p for p in predictions if p['doc_id'] == doc_id])
             for doc_id in all_pools]
    save_json(args.output/'antecedent_candidates.json', all_pools)
    save_json(args.output/'coref_predictions.json', predictions)
    save_json(args.output/'resolved_texts.json', texts)
    save_json(args.output/'coref_relations.json', [
        dict(subject=record['mention_id'], predicate='COREFERS_TO',
             object=record['predicted_antecedent']['candidate_id'], doc_id=record['doc_id'],
             mention_span=[record['start'], record['end']],
             antecedent=record['predicted_antecedent'])
        for record in predictions if record['predicted_antecedent']])
    save_json(args.output/'run_summary.json', dict(
        version='2.0', documents=list(all_pools), mentions=len(predictions),
        links=sum(record['status'] == 'linked' for record in predictions),
        status_counts=dict(Counter(record['status'] for record in predictions)),
        rule_counts=dict(Counter(record['rule'] for record in predictions)),
        per_document={doc_id: dict(
            mentions=sum(record['doc_id'] == doc_id for record in predictions),
            links=sum(record['doc_id'] == doc_id and record['status'] == 'linked' for record in predictions))
            for doc_id in all_pools},
        window_chars=args.window, previous_sentences=args.sentence_window,
        jieba_version=jieba.__version__, hmm=False,
        input_sha256=hashlib.sha256(args.input.read_bytes()).hexdigest(),
        entities_sha256=hashlib.sha256(args.entities.read_bytes()).hexdigest(),
        offsets='任务一 clean_content 的 Unicode 字符零基下标 [start,end)',
        human_review_status='pending'))
    export_review(args, docs, predictions, texts)
    return predictions



def evaluate_stage(args, docs):
    if args.annotations is None:
        raise ValueError('evaluate 需要 --annotations 指定人工标注文件')
    predictions = {p['mention_id']: p for p in read_json(args.output/'coref_predictions.json')}
    checked, skipped, seen = [], [], set()
    with args.annotations.open(encoding='utf-8-sig', newline='') as stream:
        for row in csv.DictReader(stream):
            status = row.get('status', '').strip()
            if not status:
                continue
            mid = row['mention_id']
            if mid in seen or mid not in predictions:
                raise ValueError(f'样例编号重复或未知：{mid}')
            seen.add(mid)
            record = predictions[mid]
            if (row['doc_id'], row['mention'], int(row['start']), int(row['end'])) != (
                    record['doc_id'], record['text'], record['start'], record['end']):
                raise ValueError(f'样例原文或位置被修改：{mid}')
            if status not in {'linked', 'unresolved', 'nonreferential', 'ambiguous'} or not row['annotator'].strip():
                raise ValueError(f'状态或标注人无效：{mid}')
            gold = None
            if status == 'linked':
                start, end = int(row['antecedent_start']), int(row['antecedent_end'])
                text = docs[row['doc_id']]['clean_content']
                if not 0 <= start < end <= record['start'] or text[start:end] != row['antecedent_text']:
                    raise ValueError(f'先行词边界不符：{mid}')
                gold = (start, end)
            elif any(row.get(key, '').strip() for key in ['antecedent_text', 'antecedent_start', 'antecedent_end']):
                raise ValueError(f'无确定链接时先行词应留空：{mid}')
            if status == 'ambiguous':
                skipped.append(mid)
                continue
            checked.append((record, gold, status))
    if len(checked) < 5:
        raise ValueError('至少需要 5 条非 ambiguous 的有效人工标注')
    metrics = {'evaluated_cases': len(checked), 'excluded_ambiguous': skipped,
               'gold_linked': sum(gold is not None for _, gold, _ in checked)}
    for version, field in [('baseline', 'baseline_antecedent'), ('v2', 'predicted_antecedent')]:
        cases, links, hits, abstentions = [], 0, 0, 0
        for record, gold, status in checked:
            answer = record[field]
            span = (answer['start'], answer['end']) if answer else None
            correct_link = span is not None and span == gold
            correct_abstention = span is None and gold is None
            links += answer is not None
            hits += correct_link
            abstentions += correct_abstention
            cases.append(dict(mention_id=record['mention_id'], gold_status=status, gold_span=gold,
                              predicted=answer, correct=correct_link or correct_abstention))
        metrics[version] = dict(predicted_links=links, correct_links=hits,
            correct_abstentions=abstentions, link_accuracy=hits/links if links else None,
            link_recall=hits/metrics['gold_linked'] if metrics['gold_linked'] else None,
            coverage=links/len(checked), overall_accuracy=(hits+abstentions)/len(checked), cases=cases)
    save_json(args.output/'coref_metrics.json', metrics)
    print(f'评估完成，计入 {len(checked)} 例，另排除 {len(skipped)} 例不确定标注')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['run', 'detect', 'resolve', 'evaluate'], nargs='?', default='run')
    parser.add_argument('--input', type=Path, default=ROOT/'data/clean_documents.jsonl')
    parser.add_argument('--entities', type=Path, default=ROOT/'data/entities_v2.json')
    parser.add_argument('--output', type=Path, default=ROOT/'result')
    parser.add_argument('--docs', nargs='+', default=DEFAULT_DOCS)
    parser.add_argument('--window', type=int, default=250)
    parser.add_argument('--sentence-window', type=int, default=3)
    parser.add_argument('--annotations', type=Path, help='evaluate 阶段使用的已填人工标注 CSV')
    args = parser.parse_args()
    try:
        if args.window <= 0 or args.sentence_window < 0:
            raise ValueError('字符窗口必须为正整数，句子窗口不能为负数')
        docs = {doc['doc_id']: doc for doc in load_docs(args.input)}
        selected = selected_docs(args, docs)
        args.output.mkdir(parents=True, exist_ok=True)
        if args.stage == 'evaluate':
            evaluate_stage(args, docs)
            return
        mentions = (read_json(args.output/'mentions.json') if args.stage == 'resolve'
                    else export_mentions(args, docs, selected))
        if args.stage != 'detect':
            predictions = resolve_stage(args, docs, mentions)
            print(f"完成 {len(selected)} 篇游记，检测 {len(predictions)} 处，链接 "
                  f"{sum(p['status'] == 'linked' for p in predictions)} 处。见核验结果.html")
        else:
            print(f'检测完成，共 {len(mentions)} 处。见 mentions.json')
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f'处理失败：{error}\n')


if __name__ == '__main__':
    main()
