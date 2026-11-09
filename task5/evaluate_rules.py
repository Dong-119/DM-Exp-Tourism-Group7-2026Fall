"""在30个设计样例上比较基础规则和改进规则的条件、建议边界。"""
import json
import re
import unicodedata
from pathlib import Path
from corpus_io import load_corpus
from baseline_rules import extract_candidates as baseline_extract
from extract_rules import extract_candidates
from experiment import write_json


def canonical(text,advice=False):
    text=unicodedata.normalize('NFKC',text or '').strip()
    prefix=r'^(?:则|才|否则|建议|可以)' if advice else r'^(?:如果|假如|若是|若|只要|只有|除非)'
    return re.sub(r'[\s，,。；;：:！!？?]','',re.sub(prefix,'',text))


def evaluate(base=None):
    base=Path(base) if base else Path(__file__).resolve().parent
    cases=json.loads((base/'data/规则对照样例.json').read_text(encoding='utf-8'))
    doc_ids={c['doc_id'] for c in cases}
    docs,sentences,_=load_corpus(base/'data/clean_documents.json')
    texts={d['doc_id']:d['clean_text'] for d in docs if d['doc_id'] in doc_ids}
    sentences=[s for s in sentences if s['doc_id'] in doc_ids]
    result={'sample_count':len(cases),'positive_cases':sum(c['reference_condition'] is not None for c in cases),
            'negative_cases':sum(c['reference_condition'] is None for c in cases), 'methods':{}}
    for name,extractor in [('基础规则',baseline_extract),('改进规则',extract_candidates)]:
        candidates=extractor(sentences);details=[]
        for case in cases:
            text=texts[case['doc_id']];span=case['source_span']
            start=text.find(span)
            if start<0:raise ValueError('对照样例不在当前清洗正文中：'+case['case_id'])
            end=start+len(span);relevant=[]
            for row in candidates:
                if row['doc_id']!=case['doc_id']:continue
                cstart=text.find(row['condition_text']);astart=text.find(row['advice_text'])
                if min(cstart,astart)<0:continue
                if min(cstart,astart)<end and max(cstart+len(row['condition_text']),astart+len(row['advice_text']))>start:
                    relevant.append(row)
            positive=case['reference_condition'] is not None
            relation_hit=exact=False
            if positive:
                expected_c=canonical(case['reference_condition']);expected_a=canonical(case['reference_advice'],True)
                for row in relevant:
                    condition=canonical(row['condition_text']);advice=canonical(row['advice_text'],True)
                    hit=expected_c in condition and expected_a in advice
                    if case['condition_type']=='combined':hit &= row.get('condition_operator')=='necessary'
                    if case['condition_type']=='negation':hit &= row.get('condition_operator')=='unless'
                    relation_hit |= hit
                    exact |= hit and condition==expected_c and advice==expected_a
            details.append({'case_id':case['case_id'],'doc_id':case['doc_id'],
                'positive':positive,'relation_hit':relation_hit,'exact_pair':exact,
                'false_positive':not positive and bool(relevant)})
        result['methods'][name]={'positive_relation_hits':sum(c['relation_hit'] for c in details),
            'exact_pair_matches':sum(c['exact_pair'] for c in details),
            'negative_false_positives':sum(c['false_positive'] for c in details),'cases':details}
    (base/'results').mkdir(exist_ok=True)
    write_json(base/'results/规则对照结果.json',result)
    return result


if __name__=='__main__':
    result=evaluate()
    print(json.dumps({name:{k:v for k,v in data.items() if k!='cases'}
                     for name,data in result['methods'].items()},ensure_ascii=False,indent=2))
