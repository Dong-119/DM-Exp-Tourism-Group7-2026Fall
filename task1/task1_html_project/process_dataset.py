"""Task 1: batch HTML loading -> cleaning -> structured output -> quality checks."""
import argparse
import copy
import csv
import difflib
import hashlib
import json
import logging
import re
import sys
import time
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from html_reader import decode_html, extract_article
from cleaning import DEFAULT_RULES, clean_body

VERSION = '1.0.0'
SCENICS = ['故宫', '颐和园', '天坛']
TYPES = {'travelogue', 'route_guide'}
FIELDS = ['doc_id', 'title', 'scenic_name', 'text_type', 'provenance_kind', 'source_name', 'source_url', 'original_article_url', 'reference_url', 'source_published_at', 'author', 'source_file', 'source_row', 'source_record_id', 'content_origin', 'input_path', 'encoding', 'raw_content', 'clean_content', 'text', 'clean_sha256', 'clean_char_count', 'warnings', 'merged_record_ids', 'source_records']


def sha(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def load_inputs(inputs, output):
    """Read HTML bytes directly from directories, individual files or ZIPs. Never extract ZIP paths."""
    seen = set()
    output = output.resolve()
    for name in inputs:
        path = Path(name)
        if not path.exists():
            raise FileNotFoundError('输入不存在：' + str(path))
        if path.is_dir():
            if path.resolve() == output:
                raise ValueError('输入目录不能与输出目录相同')
            files = sorted(p for p in path.rglob('*') if p.is_file() and p.suffix.lower() in {'.html', '.htm'} and not p.resolve().is_relative_to(output))
        else:
            files = [path]
        for f in files:
            key = str(f.resolve())
            if key in seen:
                continue
            seen.add(key)
            if f.suffix.lower() == '.zip':
                with zipfile.ZipFile(f) as archive:
                    members = sorted((m for m in archive.infolist() if not m.is_dir() and Path(m.filename).suffix.lower() in {'.html', '.htm'}), key=lambda m: m.filename)
                    for index, m in enumerate(members):
                        if m.file_size > 20 * 1024 * 1024:
                            raise ValueError('单个HTML超过20MiB：' + m.filename)
                        yield str(f) + '::' + m.filename + ('#member' + str(index) if sum(n.filename == m.filename for n in members) > 1 else ''), archive.read(m)
            elif f.suffix.lower() in {'.html', '.htm'}:
                if f.stat().st_size > 20 * 1024 * 1024:
                    raise ValueError('单个HTML超过20MiB：' + str(f))
                yield str(f), f.read_bytes()
            else:
                raise ValueError('仅支持HTML文件、HTML目录或ZIP：' + str(f))


def infer_origin(meta):
    if meta.get('provenance_kind'):
        return meta['provenance_kind']
    if meta.get('source_record_id'):
        return 'dataset_corpus'
    if '非官方原文' in (meta.get('content_origin') or ''):
        return 'editorial_route_guide'
    return 'unknown'


def normalize_date(value):
    if value in (None, '', '未提供'):
        return None
    m = re.fullmatch(r'(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?', str(value).strip())
    if not m:
        raise ValueError('invalid_date_format')
    return date(*map(int, m.groups())).isoformat()


def canonical_url(value):
    if not value:
        return None
    parts = urlsplit(value)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, '', ''))


def prepare_record(label, data, rules, scenics):
    source, encoding, warnings = decode_html(data)
    meta, node, raw_body, before, parse_warnings = extract_article(source)
    warnings.extend(parse_warnings)
    required = ['doc_id', 'title', 'scenic_name', 'text_type', 'source_name', 'content_origin']
    missing = [k for k in required if not isinstance(meta.get(k), str) or not meta[k].strip()]
    if missing:
        raise ValueError('missing_required_metadata:' + ','.join(missing))
    for key in ['source_url', 'original_article_url', 'reference_url', 'source_published_at', 'author', 'source_file', 'source_record_id', 'provenance_kind']:
        if meta.get(key) is not None and not isinstance(meta[key], str):
            raise ValueError('metadata_type_error:' + key)
    if meta['scenic_name'] not in scenics:
        raise ValueError('unexpected_scenic:' + meta['scenic_name'])
    if meta['text_type'] not in TYPES:
        raise ValueError('unexpected_text_type:' + meta['text_type'])
    for key in ['source_url', 'original_article_url', 'reference_url']:
        if meta.get(key) and not (urlsplit(meta[key]).scheme in {'http', 'https'} and urlsplit(meta[key]).netloc):
            warnings.append('invalid_url_field:' + key)
    source_date = meta.get('source_published_at')
    try:
        normalized_date = normalize_date(source_date)
    except ValueError:
        normalized_date = None
        warnings.append('invalid_source_date_preserved_in_raw')
    clean, changes, removals, clean_warnings = clean_body(node, rules)
    warnings.extend(clean_warnings)
    if len(clean) < rules['min_content_chars']:
        raise ValueError('empty_or_too_short_content:' + str(len(clean)))
    if not meta.get('source_url') and infer_origin(meta) != 'synthetic_teaching':
        warnings.append('non_synthetic_source_url_missing')
    if any(w.startswith('visible_metadata_conflict:') for w in warnings):
        # Conflicting identity/source fields must not silently be treated as resolved.
        raise ValueError('metadata_conflict:' + ','.join(w for w in warnings if w.startswith('visible_metadata_conflict:')))
    record = {k: meta.get(k) for k in FIELDS}
    record.update(provenance_kind=infer_origin(meta), source_published_at=normalized_date, input_path=label, encoding=encoding, raw_content=raw_body, clean_content=clean, text=clean, clean_sha256=sha(clean), clean_char_count=len(clean), warnings=sorted(set(warnings)), merged_record_ids=[meta['doc_id']])
    source_ref = {k: record.get(k) for k in ['doc_id', 'input_path', 'source_name', 'source_url', 'original_article_url', 'reference_url', 'source_file', 'source_row', 'source_record_id', 'provenance_kind']}
    record['source_records'] = [source_ref]
    raw_record = {'input_path': label, 'input_sha256': hashlib.sha256(data).hexdigest(), 'encoding': encoding, 'metadata_original': meta, 'raw_html': source, 'raw_content': raw_body, 'before_text': before}
    comparison = {'doc_id': meta['doc_id'], 'input_path': label, 'before_text': before, 'clean_content': clean, 'before_char_count': len(before), 'after_char_count': len(clean), 'cleaning_actions': changes, 'removed_examples': removals, 'source_date_before': source_date, 'source_date_after': normalized_date, 'warnings': sorted(set(warnings)), 'status': 'kept', 'duplicate_of': None}
    return record, raw_record, comparison


def compact(s):
    return re.sub(r'\s+', '', s)


def grams(s):
    s = compact(s)
    return {s[i:i + 5] for i in range(max(1, len(s) - 4))}


def deduplicate(records, rules):
    """Use content plus provenance gates, never IDs ending in _DUP or a supplied answer key."""
    kept, duplicates = [], []
    fingerprints = {}
    for r in records:
        key = (r['scenic_name'], r['text_type'], r['provenance_kind'], compact(r['clean_content']))
        match = fingerprints.get(key)
        reason, similarity = 'normalized_exact', 1.0
        if match is None:
            for candidate in kept:
                if (candidate['scenic_name'], candidate['text_type'], candidate['provenance_kind']) != (r['scenic_name'], r['text_type'], r['provenance_kind']):
                    continue
                source_id, candidate_id = r.get('source_record_id'), candidate.get('source_record_id')
                if source_id and candidate_id and source_id != candidate_id:
                    continue
                same_source = (source_id and source_id == candidate_id) or (r.get('source_url') and canonical_url(r['source_url']) == canonical_url(candidate.get('source_url')))
                if not same_source:
                    continue
                a, b = compact(r['clean_content']), compact(candidate['clean_content'])
                if min(len(a), len(b)) / max(len(a), len(b)) < rules['near_duplicate_min_length_ratio']:
                    continue
                if difflib.SequenceMatcher(None, r['title'], candidate['title'], autojunk=False).ratio() < .85:
                    continue
                x, y = grams(a), grams(b)
                similarity = len(x & y) / max(1, len(x | y))
                if similarity >= rules['near_duplicate_threshold']:
                    match, reason = candidate, 'same_source_high_similarity'
                    break
        if match is not None:
            duplicates.append({'doc_id': r['doc_id'], 'kept_doc_id': match['doc_id'], 'reason': reason, 'similarity': round(similarity, 6), 'input_path': r['input_path'], 'kept_input_path': match['input_path']})
            match['merged_record_ids'].append(r['doc_id'])
            match['source_records'].extend(r['source_records'])
        else:
            kept.append(r)
            fingerprints[key] = r
    return kept, duplicates


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write_jsonl(path, values):
    with path.open('w', encoding='utf-8', newline='\n') as f:
        for value in values:
            f.write(json.dumps(value, ensure_ascii=False) + '\n')


def write_csv(path, values, fields):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for r in values:
            writer.writerow({k: json.dumps(r.get(k), ensure_ascii=False) if isinstance(r.get(k), (list, dict)) else r.get(k) for k in fields})


def quality_report(all_records, kept, duplicates, errors, comparisons, scenics):
    by_scenic = {}
    for scenic in scenics:
        rows = [r for r in kept if r['scenic_name'] == scenic]
        corpus = [r for r in rows if r['text_type'] == 'travelogue' and r['provenance_kind'] == 'dataset_corpus']
        fact = [r for r in rows if r['text_type'] == 'route_guide' and r['provenance_kind'] == 'official_route_facts' and r.get('reference_url')]
        by_scenic[scenic] = {'total': len(rows), 'route_guides': sum(r['text_type'] == 'route_guide' for r in rows), 'travelogues': sum(r['text_type'] == 'travelogue' for r in rows), 'teacher_corpus_travelogues': len(corpus), 'source_traceable_official_route_facts': len(fact), 'synthetic_teaching': sum(r['provenance_kind'] == 'synthetic_teaching' for r in rows), 'step3_quantity_supported': len(fact) >= 1 and len(corpus) >= 3, 'five_corpus_travelogues_supported': len(corpus) >= 5}
    optional = ['author', 'source_published_at', 'original_article_url', 'source_url']
    missing = {field: sum(r.get(field) in (None, '', []) for r in kept) for field in optional}
    residual_urls = sum(bool(re.search(r'https?://|www\.', r['clean_content'], re.I)) for r in kept)
    residual_symbols = sum(bool(re.search('[\u200b\ufffd]', r['clean_content'])) for r in kept)
    events = Counter()
    for c in comparisons:
        events.update(c['cleaning_actions'])
    return {'input_html_count': len(all_records) + len(errors), 'parsed_records': len(all_records), 'clean_records': len(kept), 'duplicate_records_removed': len(duplicates), 'rejected_records': len(errors), 'by_scenic': by_scenic, 'minimum_3_scenics_1_traceable_route_3_corpus_travelogues_supported': len(by_scenic) >= 3 and all(v['step3_quantity_supported'] for v in by_scenic.values()), 'five_corpus_travelogues_per_scenic_supported': all(v['five_corpus_travelogues_supported'] for v in by_scenic.values()), 'official_full_original_articles_verified': 0, 'official_source_verification': '仅检查输入声明与参考链接存在，不进行联网来源真实性核验；路线事实不等于官方全文，整理稿及模拟稿不计作官方原文', 'full_main_content_requirement_note': '手册主要内容若按每景区5篇独立官方原文理解，当前输入不满足；代码不能通过改类型或补写来源解决该数据缺口', 'missing_optional_fields': missing, 'missing_required_fields_in_kept': {field: sum(not r.get(field) for r in kept) for field in ['doc_id', 'title', 'scenic_name', 'text_type', 'source_name', 'content_origin', 'clean_content']}, 'provenance_counts': dict(Counter(r['provenance_kind'] for r in kept)), 'text_type_counts': dict(Counter(r['text_type'] for r in kept)), 'residual_url_records': residual_urls, 'residual_invalid_character_records': residual_symbols, 'format_consistency': {'unique_doc_ids': len({r['doc_id'] for r in kept}) == len(kept), 'dates_iso_or_null': all(r['source_published_at'] is None or bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}', r['source_published_at'])) for r in kept), 'body_no_blank_lines': all('\n\n' not in r['clean_content'] for r in kept)}, 'cleaning_action_counts': dict(sorted(events.items())), 'warnings': [{'doc_id': r['doc_id'], 'items': r['warnings']} for r in kept if r['warnings']], 'limitations': ['来源真实性依据输入声明保留，不能等同于独立网页核验', '明显乱码只能删除并记录，不能恢复未知原字符', '不改写游记中的历史事实、实际路线、否定或条件语义', '近重复识别采用保守阈值与来源约束，不能保证发现所有改写转载', '只清洗原有数据，不根据文章编号或人工审核答案强制保留/删除记录', '实体/共指偏移需在clean_content重新计算，不能沿用原HTML或加噪前参考偏移']}


def run(inputs, output, config=None, scenics=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger('task1')
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    for handler in [logging.StreamHandler(sys.stdout), logging.FileHandler(output / 'run.log', mode='w', encoding='utf-8')]:
        handler.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(handler)
    rules = copy.deepcopy(DEFAULT_RULES)
    if config:
        custom = json.loads(Path(config).read_text(encoding='utf-8-sig'))
        unknown = set(custom) - set(rules)
        if unknown:
            raise ValueError('未知配置字段：' + ','.join(sorted(unknown)))
        rules.update(custom)
    if not 0 <= rules['near_duplicate_threshold'] <= 1 or not 0 <= rules['near_duplicate_min_length_ratio'] <= 1:
        raise ValueError('重复阈值须在0到1之间')
    scenics = scenics or SCENICS
    started = time.perf_counter()
    all_records, raw_records, comparisons, errors = [], [], [], []
    ids = set()
    logger.info('步骤1/3：批量读取原始HTML，仅从HTML自身提取元数据和正文')
    for label, data in load_inputs(inputs, output):
        try:
            record, raw, comparison = prepare_record(label, data, rules, scenics)
            if record['doc_id'] in ids:
                raise ValueError('duplicate_doc_id_requires_distinct_record_ids:' + record['doc_id'])
            ids.add(record['doc_id'])
            all_records.append(record)
            raw_records.append(raw)
            comparisons.append(comparison)
        except (ValueError, TypeError, KeyError, RecursionError) as exc:
            errors.append({'input_path': label, 'error_type': type(exc).__name__, 'reason': str(exc), 'input_sha256': hashlib.sha256(data).hexdigest(), 'raw_html': data.decode('utf-8', errors='replace')})
        if (len(all_records) + len(errors)) % 10 == 0:
            logger.info('已读取 %s 个HTML', len(all_records) + len(errors))
    if not all_records and not errors:
        raise ValueError('没有发现HTML；请将--input指向含HTML的目录或数据ZIP')
    logger.info('步骤2/3：正文清洗与去重，原文件不修改')
    # Mutations caused by provenance merging must not change per-input diagnostics.
    kept, duplicates = deduplicate(copy.deepcopy(all_records), rules)
    duplicate_map = {r['doc_id']: r['kept_doc_id'] for r in duplicates}
    for c in comparisons:
        if c['doc_id'] in duplicate_map:
            c.update(status='duplicate_removed', duplicate_of=duplicate_map[c['doc_id']])
    logger.info('步骤3/3：质量检查、结构化导出与前后对比')
    report = quality_report(all_records, kept, duplicates, errors, comparisons, scenics)
    write_jsonl(output / 'raw_records.jsonl', raw_records)
    write_jsonl(output / 'clean_documents.jsonl', kept)
    write_json(output / 'clean_documents.json', kept)
    write_csv(output / 'clean_documents.csv', kept, FIELDS)
    write_jsonl(output / 'cleaning_comparison.jsonl', comparisons)
    write_csv(output / 'cleaning_comparison.csv', comparisons, ['doc_id', 'input_path', 'before_text', 'clean_content', 'before_char_count', 'after_char_count', 'cleaning_actions', 'source_date_before', 'source_date_after', 'status', 'duplicate_of', 'warnings'])
    write_json(output / 'duplicates.json', duplicates)
    write_json(output / 'errors.json', errors)
    write_json(output / 'quality_report.json', report)
    write_json(output / 'rules_used.json', rules)
    provenance = [{k: r.get(k) for k in ['doc_id', 'scenic_name', 'text_type', 'provenance_kind', 'source_name', 'source_url', 'original_article_url', 'reference_url', 'source_file', 'source_row', 'source_record_id', 'content_origin', 'source_records']} for r in kept]
    write_json(output / 'sources.json', provenance)
    write_json(output / 'run_manifest.json', {'version': VERSION, 'python_version': sys.version.split()[0], 'inputs': list(map(str, inputs)), 'output': str(output), 'source_mode': '已有HTML数据包，沿用其教师语料/整理稿/模拟稿来源声明；不是新执行网络爬取', 'input_files': [{'input_path': r['input_path'], 'sha256': r['input_sha256']} for r in raw_records] + [{'input_path': r['input_path'], 'sha256': r['input_sha256'], 'rejected': True} for r in errors], 'rules_sha256': sha(json.dumps(rules, sort_keys=True, ensure_ascii=False)), 'elapsed_seconds': round(time.perf_counter() - started, 4)})
    from report_task1 import write_reports
    write_reports(output, report, comparisons, duplicates, errors)
    logger.info('完成：输入 %s，保留 %s，合并重复 %s，隔离异常 %s', report['input_html_count'], len(kept), len(duplicates), len(errors))
    logger.info('各景区统计：%s', json.dumps(report['by_scenic'], ensure_ascii=False))
    logger.info('结果目录：%s', output)
    logger.info('注意：官方原文全文已独立核验数量为0，路线事实与模拟稿没有改标为官方原文。')
    return report


def main():
    parser = argparse.ArgumentParser(description='任务一：批量HTML清洗、结构化与数据质量检查，无人工复核/无需API')
    parser.add_argument('--input', nargs='+', default=['data/html'], help='HTML目录、单篇HTML或ZIP，可给多个输入')
    parser.add_argument('--output', default='result', help='输出目录，不能与输入目录相同')
    parser.add_argument('--config', help='可选清洗规则JSON，未提供时使用内置规则')
    parser.add_argument('--scenics', nargs='+', default=SCENICS, help='允许的景区元数据值；不是按正文关键词截断文章')
    parser.add_argument('--strict', action='store_true', help='输入异常、格式失败或手册步骤最低数量不足时返回非零状态')
    args = parser.parse_args()
    try:
        report = run(args.input, args.output, args.config, args.scenics)
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        parser.exit(2, '处理失败：' + str(exc) + '\n')
    failed = report['rejected_records'] > 0 or not report['minimum_3_scenics_1_traceable_route_3_corpus_travelogues_supported'] or not all(report['format_consistency'].values())
    return 1 if args.strict and failed else 0

if __name__ == '__main__':
    raise SystemExit(main())
