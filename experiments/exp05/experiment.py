"""读取景区文章，抽取并校验条件建议，输出映射表和分类统计。"""
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from corpus_io import load_corpus
from extract_rules import extract_candidates, deduplicate

SCOPES=['故宫','颐和园','天坛','北京通用']
VISITORS=['亲子','老人','行动不便','青年','摄影爱好者','自由行','情侣','未特定']
CONDITIONS=['游客类型','时间安排','天气季节','游览偏好','出行安排','现场情境','开放与通行','复合条件']
ORIGINS={'dataset_corpus':'原语料游记','editorial_route_guide':'路线整理稿',
         'official_route_facts':'官方路线事实重述','synthetic_teaching':'教学模拟'}


def write_json(path,data):
    Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def candidate_key(row):
    text='\0'.join(str(row[k]) for k in ['doc_id','sentence_id','rule_id','condition_text','advice_text'])
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


def classify(condition):
    visitors=[name for name,pattern in [('亲子','孩子|儿童|小孩|亲子|遛娃|婴儿'),
        ('老人','老人|老年|长者|父母'),('行动不便','行动不便|轮椅|腿脚'),('青年','青年|年轻'),
        ('摄影爱好者','摄影|拍照'),('自由行','自由行'),('情侣','情侣|恋人')] if re.search(pattern,condition)]
    kinds=[name for name,pattern in [('游客类型','老人|孩子|儿童|游客|亲子|情侣|轮椅|摄影爱好者|年轻'),
        ('时间安排','时间|小时|半天|上午|下午|日程|来得晚'),('天气季节','雨|雪|风|天气|炎热|高温|夏|冬|阴天|气温'),
        ('游览偏好','喜欢|想|兴趣|拍照|摄影|顺序浏览|博物馆'),('出行安排','住宿|房间|预订|预定|出行|交通'),
        ('开放与通行','开放|关闭|封闭|闭园|停航|通行')] if re.search(pattern,condition)]
    primary='复合条件' if len(kinds)>1 and re.search('且|并且|同时|只有|除非|或',condition) else (kinds or ['现场情境'])[0]
    return visitors or ['未特定'],primary,kinds or ['现场情境']


def locate(doc,fragment,sentences):
    fragment=str(fragment)
    for sentence in sentences:
        local=sentence['text'].find(fragment)
        if local>=0:
            start=sentence['start']+local
            return fragment,{'doc_id':doc['doc_id'],'start':start,'end':start+len(fragment)}
    start=doc['clean_text'].find(fragment)
    if start<0:raise ValueError(f"{doc['doc_id']}中找不到原文片段：{fragment}")
    return fragment,{'doc_id':doc['doc_id'],'start':start,'end':start+len(fragment)}


def make_record(pair,doc,sentences):
    preferred=set(pair.get('context_sentence_ids',[]))|{pair.get('sentence_id')}
    same_doc=[s for s in sentences if s['doc_id']==doc['doc_id']]
    nearby=[s for s in same_doc if s['sentence_id'] in preferred]
    condition,cspan=locate(doc,pair['condition_text'],nearby)
    advice,aspan=locate(doc,pair['advice_text'],nearby)
    visitors,kind,kinds=classify(condition)
    evidence=[{'doc_id':doc['doc_id'],'sentence_id':s['sentence_id'],'quote':s['text'],
               'start':s['start'],'end':s['end']} for s in same_doc
              if s['sentence_id'] in preferred or any(s['start']<p['end'] and s['end']>p['start'] for p in [cspan,aspan])]
    return {'doc_id':doc['doc_id'],'source_scenic':doc['source_scenic'],'source_type':doc['source_type'],
        'provenance_kind':doc['provenance_kind'],'source_group_id':doc['source_group_id'],
        'source_urls':doc['source_urls'],'source_path':doc['source_path'],
        'duplicate_doc_ids':doc.get('duplicate_doc_ids',[]),
        'condition_text':condition,'advice_text':advice,
        'condition_operator':pair.get('condition_operator','context'),
        'condition_mode':pair.get('condition_mode','context'),
        'condition_type':pair.get('condition_type',kind),'condition_types':kinds,
        'visitor_types':pair.get('visitor_types',visitors),
        'target_scope':pair.get('target_scope',doc['source_scenic']),
        'spans':{'condition_text':cspan,'advice_text':aspan},'evidence':evidence}


def export_csv(path,rows):
    fields=['mapping_id','doc_id','condition_type','condition_operator','condition_text','advice_text',
            'visitor_types','target_scope','source_scenic','provenance_kind']
    with Path(path).open('w',encoding='utf-8-sig',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=fields,extrasaction='ignore');writer.writeheader()
        for row in rows:
            writer.writerow({k:'、'.join(row[k]) if isinstance(row[k],list) else row[k] for k in fields})


def run(base=None,make_plots=True):
    base=Path(base) if base else Path(__file__).resolve().parent
    output=base/'results';output.mkdir(exist_ok=True)
    docs,sentences,summary=load_corpus(base/'data/clean_documents.json')
    documents={d['doc_id']:d for d in docs}
    check=json.loads((base/'data/人工校验.json').read_text(encoding='utf-8'))
    candidates={}
    for row in extract_candidates(sentences):
        row=dict(row,candidate_id=candidate_key(row));candidates.setdefault(row['candidate_id'],row)
    missing=set(check['candidate_adjustments'])-set(candidates)
    if missing:raise ValueError('部分校验条目未找到对应候选，请检查输入与规则是否一致')
    source_pairs=[p for p in check['additional_pairs'] if documents[p['doc_id']]['provenance_kind']=='dataset_corpus']
    context_pairs=[p for p in check['additional_pairs'] if documents[p['doc_id']]['provenance_kind']!='dataset_corpus']
    records=[make_record(p,documents[p['doc_id']],sentences) for p in source_pairs]
    counts=Counter()
    for key,row in candidates.items():
        adjustment=check['candidate_adjustments'].get(key,{})
        action=adjustment.get('action','accept');counts[action]+=1
        if action=='exclude':continue
        pair=dict(row);pair.update(adjustment.get('fields',{}))
        records.append(make_record(pair,documents[pair['doc_id']],sentences))
    records.extend(make_record(p,documents[p['doc_id']],sentences) for p in context_pairs)
    main=[r for r in records if r['target_scope'] in SCOPES]
    outside=[r for r in records if r['target_scope'] not in SCOPES]
    mapping,merges=deduplicate(main);outside,outside_merges=deduplicate(outside)
    for prefix,group in [('M',mapping),('X',outside)]:
        for i,row in enumerate(group,1):row['mapping_id']=f'{prefix}{i:03d}'
    stats={'input':summary,'rule_candidates':len(candidates),'candidate_counts':dict(counts),
        'additional_source_pairs':len(source_pairs),'contextual_pairs':len(context_pairs),
        'accepted_before_dedup':len(records),'main_before_dedup':len(main),
        'main_after_dedup':len(mapping),'outside_scope':len(outside),'dedup_merges':len(merges),
        'by_visitor_type':{v:sum(v in r['visitor_types'] for r in mapping) for v in VISITORS},
        'by_condition_type':{v:sum(r['condition_type']==v for r in mapping) for v in CONDITIONS},
        'by_target_scope':{v:sum(r['target_scope']==v for r in mapping) for v in SCOPES},
        'by_provenance':{v:sum(r['provenance_kind']==v for r in mapping) for v in ORIGINS}}
    write_json(output/'分句语料.json',{'summary':summary,'documents':docs,'sentences':sentences})
    write_json(output/'规则候选.json',list(candidates.values()))
    write_json(output/'条件建议映射表.json',mapping);write_json(output/'范围外建议.json',outside)
    write_json(output/'统计结果.json',stats);export_csv(output/'条件建议映射表.csv',mapping)
    if make_plots:
        from figures import generate
        generate(output,mapping,stats)
    from result_page import write_page
    write_page(output,mapping,outside,stats)
    return stats
