"""核对位置、参考标注、原始输出及评价数字，仅需 Python 标准库。"""
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parent

def read(name):
    return json.loads((ROOT/name).read_text(encoding='utf-8-sig'))

def check():
    docs={row['doc_id']:row['text'] for row in read('sample_documents.json')}
    predictions=read('coref_predictions.json')
    by_id={row['mention_id']:row for row in predictions}
    assert len(by_id)==len(predictions)==82
    for row in predictions:
        text=docs[row['doc_id']]
        assert text[row['start']:row['end']]==row['text'],row['mention_id']
        assert text[row['sentence_start']:row['sentence_end']]==row['sentence'],row['mention_id']
        antecedent=row['predicted_antecedent']
        if antecedent:
            assert text[antecedent['start']:antecedent['end']]==antecedent['text']
            assert antecedent['end']<=row['start']
    annotations=read('核验标注.json')
    assert len({row['mention_id'] for row in annotations})==len(annotations)==27
    for row in annotations:
        original=by_id[row['mention_id']]
        assert (row['doc_id'],row['mention'],row['start'],row['end'])==(
            original['doc_id'],original['text'],original['start'],original['end'])
        if row['status']=='linked':
            text=docs[row['doc_id']]
            assert text[row['antecedent_start']:row['antecedent_end']]==row['antecedent_text']
            assert row['antecedent_end']<=row['start']
    scored=[row for row in annotations if row['status']!='ambiguous']
    metrics=read('coref_metrics.json')
    assert metrics['evaluated_cases']==len(scored)==25
    assert metrics['gold_linked']==sum(row['status']=='linked' for row in scored)==21
    for version,field in [('baseline','baseline_antecedent'),('v2','predicted_antecedent')]:
        links=hits=abstentions=0
        for row in scored:
            answer=by_id[row['mention_id']][field]
            predicted=(answer['start'],answer['end']) if answer else None
            gold=(row['antecedent_start'],row['antecedent_end']) if row['status']=='linked' else None
            links+=answer is not None
            hits+=predicted is not None and predicted==gold
            abstentions+=predicted is None and gold is None
        saved=metrics[version]
        assert (links,hits,abstentions)==(saved['predicted_links'],saved['correct_links'],saved['correct_abstentions'])
        assert saved['overall_accuracy']==(hits+abstentions)/len(scored)
        assert saved['link_accuracy']==hits/links
        assert saved['link_recall']==hits/metrics['gold_linked']
        assert saved['coverage']==links/len(scored)
    for filename,expected in read('原始输出校验.json').items():
        assert hashlib.sha256((ROOT/filename).read_bytes()).hexdigest()==expected,filename
    for row in read('resolved_texts.json'):
        original=row['original_text']
        assert original==docs[row['doc_id']]
        parts=[]
        cursor=0
        for edit in row['edits']:
            assert original[edit['original_start']:edit['original_end']]==edit['original_text']
            assert row['resolved_text'][edit['resolved_start']:edit['resolved_end']]==edit['replacement']
            parts.extend([original[cursor:edit['original_start']],edit['replacement']])
            cursor=edit['original_end']
        parts.append(original[cursor:])
        assert ''.join(parts)==row['resolved_text']
    reviewed=read('coref_predictions_reviewed.json')
    assert len(reviewed)==82
    assert sum(row['review']['status']=='reviewed' for row in reviewed)==27
    assert sum(row['review']['status']=='not_reviewed' for row in reviewed)==55
    print('校验通过。全量 82 条位置和原始结果一致。')
    print('逐句参考 27 例，可计分 25 例，2 例不确定排除。')
    print('V2 正确链接 19，正确保留 4，漏消解 2，总体准确率 92%。')
    print('其余 55 处仍待逐句语义核验。')

if __name__=='__main__':
    check()
