"""读取实验一的结构化文章，按原文分句并保留字符位置。"""
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
import hashlib
import json
import re

END = re.compile(r'[。！？!?]+[”’"\')）]*|(?<!\d)\.(?!\d)[”’"\')）]*(?=\s|[\u4e00-\u9fff]|$)')


def _build_sentences(docs):
    sentences = []
    for doc in docs:
        paragraph_start = sequence = 0
        for paragraph_index, paragraph in enumerate(doc['paragraphs'], 1):
            left = 0
            boundaries = [match.end() for match in END.finditer(paragraph)]
            if not boundaries or boundaries[-1] != len(paragraph):
                boundaries.append(len(paragraph))
            for right in boundaries:
                piece = paragraph[left:right]
                start = paragraph_start + left + len(piece) - len(piece.lstrip())
                end = paragraph_start + left + len(piece.rstrip())
                if piece.strip():
                    sequence += 1
                    sentences.append({'sentence_id': f"{doc['doc_id']}_S{sequence:03d}",
                        'doc_id': doc['doc_id'], 'scenic': doc['source_scenic'],
                        'source_type': doc['source_type'], 'text': doc['clean_text'][start:end],
                        'start': start, 'end': end, 'paragraph_index': paragraph_index})
                left = right
            paragraph_start += len(paragraph) + 1
    return sentences


def load_corpus(path):
    """保持clean_content的字符、段落与独立文章集合。"""
    rows = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(rows, list) or not rows:
        raise ValueError('结构化输入应为非空文章数组')
    documents, seen = [], set()
    for row in sorted(rows, key=lambda item: item['doc_id']):
        doc_id, text = row['doc_id'], row['clean_content']
        if not doc_id or doc_id in seen or not isinstance(text, str) or not text.strip():
            raise ValueError(f'文章编号重复或正文缺失：{doc_id}')
        seen.add(doc_id)
        digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
        if digest != row['clean_sha256'] or len(text) != row['clean_char_count']:
            raise ValueError(f'正文与实验一的哈希或字符数不符：{doc_id}')
        if row.get('text', text) != text:
            raise ValueError(f'text与clean_content不一致：{doc_id}')
        urls = list(dict.fromkeys(row[key] for key in
                    ['source_url', 'original_article_url', 'reference_url'] if row.get(key)))
        reference = row.get('reference_url') or row.get('source_url')
        parts = urlsplit(reference or '')
        url = urlunsplit((parts.scheme.casefold(), parts.netloc.casefold(),
                         parts.path.rstrip('/') or '/', '', '')) if reference else None
        record_id = row.get('source_record_id')
        group = (f'dataset:{record_id}' if record_id is not None else f'url:{url}' if url
                 else f"synthetic:{doc_id}" if row['provenance_kind']=='synthetic_teaching' else f'doc:{doc_id}')
        documents.append({'doc_id':doc_id, 'title':row['title'],
            'source_scenic':row['scenic_name'], 'source_type':row['text_type'],
            'provenance_kind':row['provenance_kind'], 'source_group_id':group,
            'source_urls':urls, 'original_record_id':record_id,
            'source_path':row['input_path'],
            'source_paths':[item['input_path'] for item in row['source_records']],
            'duplicate_doc_ids':[item for item in row['merged_record_ids'] if item != doc_id],
            'clean_text':text, 'paragraphs':text.split('\n'), 'clean_sha256':digest})
    sentences = _build_sentences(documents)
    summary = {'input_records':len(documents), 'records':len(documents), 'sentences':len(sentences),
        'counts':dict(sorted(Counter(f"{d['source_scenic']}/{d['source_type']}" for d in documents).items())),
        'by_provenance':dict(sorted(Counter(d['provenance_kind'] for d in documents).items()))}
    return documents, sentences, summary
