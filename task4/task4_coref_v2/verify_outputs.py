"""校验结果结构、字符位置和改写映射。此检查不判断消解语义。"""
import argparse
import json
from pathlib import Path

from recognize import load_docs


def verify(data, result):
    docs = {d['doc_id']: d for d in load_docs(data)}
    predictions = json.loads((result/'coref_predictions.json').read_text(encoding='utf-8'))
    seen = set()
    for p in predictions:
        mid = p['mention_id']
        assert mid not in seen, f'提及编号重复：{mid}'
        seen.add(mid)
        text = docs[p['doc_id']]['clean_content']
        assert text[p['start']:p['end']] == p['text'], mid
        assert text[p['sentence_start']:p['sentence_end']] == p['sentence'], mid
        assert p['sentence'][p['sentence_start_offset']:p['sentence_start_offset']+len(p['text'])] == p['text'], mid
        for candidate in p['candidates']:
            assert text[candidate['start']:candidate['end']] == candidate['text'], mid
            assert candidate['end'] <= p['start'], mid
        answer = p['predicted_antecedent']
        assert (answer is not None) == (p['status'] == 'linked'), mid
        if answer:
            assert text[answer['start']:answer['end']] == answer['text'], mid
            assert answer['end'] <= p['start'], mid
    texts = json.loads((result/'resolved_texts.json').read_text(encoding='utf-8'))
    for row in texts:
        original = docs[row['doc_id']]['clean_content']
        assert original == row['original_text']
        edits = row['edits']
        cursor = 0
        parts = []
        for edit in edits:
            assert cursor <= edit['original_start']
            assert original[edit['original_start']:edit['original_end']] == edit['original_text']
            assert row['resolved_text'][edit['resolved_start']:edit['resolved_end']] == edit['replacement']
            parts.extend([original[cursor:edit['original_start']], edit['replacement']])
            cursor = edit['original_end']
        parts.append(original[cursor:])
        assert ''.join(parts) == row['resolved_text']
        assert row['replacement_count'] == len(edits)
    print(f'通过位置与映射校验：{len(texts)} 篇，{len(predictions)} 处提及。')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path(__file__).parent/'data/clean_documents.jsonl')
    parser.add_argument('--result', type=Path, default=Path(__file__).parent/'result')
    args = parser.parse_args()
    verify(args.input, args.result)
