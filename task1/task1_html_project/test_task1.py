"""Regression tests for content preservation, duplicate safety and HTML loading."""
import copy
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from cleaning import DEFAULT_RULES, clean_body
from html_reader import Tree, decode_html, extract_article
from process_dataset import deduplicate, load_inputs, normalize_date, prepare_record


def clean(value):
    root = Tree('<div class="document-body">' + value + '</div>').finish()
    body = root.find_all(lambda n: n.has_class('document-body'))[0]
    return clean_body(body)


def fixture(body, **overrides):
    m = {'doc_id': 'sample', 'title': '故宫参观文章', 'scenic_name': '故宫', 'text_type': 'travelogue', 'source_name': '测试语料', 'content_origin': '测试输入，不是官方原文', 'source_record_id': 'test-record', 'source_url': 'https://example.org/article', 'author': None}
    m.update(overrides)
    return '<html><head><style>.x{color:red}</style></head><body><article class="record"><dl class="metadata"><dt>景区名称</dt><dd>故宫</dd></dl><div class="document-body">' + body + '</div></article><script id="article-metadata" type="application/json">' + json.dumps(m, ensure_ascii=False) + '</script></body></html>'


class CleaningTests(unittest.TestCase):
    def test_noise_dom_and_hidden_removed_but_content_retained(self):
        text, actions, _, _ = clean('<div class="breadcrumb">首页</div><p>上午从午门进入。</p><div style="display:none">隐藏广告</div><div class="comment">网友留言</div><script>evil()</script><style>bad</style>')
        self.assertEqual(text, '上午从午门进入。')
        self.assertEqual(actions['remove_noise_blocks'], 5)

    def test_time_decimal_arrows_negation_conditions_preserved(self):
        value = '上午09:00—11:30，计划2.5小时：午门→太和殿。如果下雨，则减少停留；珍宝馆没有去。'
        text = clean('<p>' + value + '</p>')[0]
        for token in ['09:00', '11:30', '2.5', '午门→太和殿', '如果下雨', '则减少停留', '珍宝馆没有去']:
            self.assertIn(token, text)

    def test_invisible_entities_split_word_and_controls(self):
        text = clean('<p>　故\u200b宫&nbsp;游 览\x01：午门。</p>')[0]
        self.assertEqual(text, '故宫 游览：午门。')

    def test_adjacent_long_duplicate_not_short_intentional_repetition(self):
        p = '上午从午门进入，先看太和殿，再去中和殿，之后慢慢观察保和殿的建筑与周边空间。'
        text, actions, _, _ = clean('<p>' + p + '</p><p>' + p + '</p><p>休息</p><p>休息</p>')
        self.assertEqual(text.count(p), 1)
        self.assertEqual(text.count('休息'), 2)
        self.assertEqual(actions['remove_adjacent_duplicate_paragraphs'], 1)

    def test_metadata_urls_and_related_tail(self):
        text = clean('<p>来源网址：https://example.org/a</p><p>先到午门，参考https://example.org/a，随后休息。</p><p>本文相关网站:</p><p>不相关链接文字</p>')[0]
        self.assertEqual(text, '先到午门，参考，随后休息。')

    def test_unknown_garbled_text_not_reconstructed(self):
        text, actions, _, warnings = clean('<p>故宫锟斤拷参观�记录。</p>')
        self.assertEqual(text, '故宫参观记录。')
        self.assertEqual(actions['remove_known_mojibake'], 2)
        self.assertTrue(warnings)

    def test_idempotent_normalization(self):
        text = clean('<p>　午门\u200b　游 览,然后09:00休息2.5小时。</p>')[0]
        self.assertEqual(text, clean('<p>' + text + '</p>')[0])


class ParsingTests(unittest.TestCase):
    def test_metadata_not_in_body_and_raw_html_slice_exact(self):
        raw = '<p>午门附近休息，随后继续参观。</p>'
        meta, _, body, before, warnings = extract_article(fixture(raw))
        self.assertEqual(body, raw)
        self.assertEqual(meta['doc_id'], 'sample')
        self.assertNotIn('测试语料', before)
        self.assertFalse(warnings)

    def test_decode_declared_gbk(self):
        data = '<meta charset="gbk"><p>故宫</p>'.encode('gbk')
        source, encoding, warnings = decode_html(data)
        self.assertIn('故宫', source)
        self.assertEqual(encoding, 'gbk')
        self.assertFalse(warnings)

    def test_broken_utf8_is_not_silently_reinterpreted(self):
        _, encoding, warnings = decode_html(b'<meta charset="utf-8"><p>\xff</p>')
        self.assertEqual(encoding, 'utf-8-sig')
        self.assertIn('decoding_replacement_used', warnings)

    def test_source_dates_and_invalid_calendar_date(self):
        for value in ['2024/8/8', '2024年8月8日', '2024-08-08']:
            self.assertEqual(normalize_date(value), '2024-08-08')
        self.assertIsNone(normalize_date(None))
        with self.assertRaises(ValueError):
            normalize_date('2024-02-31')

    def test_invalid_json_and_multiple_articles_rejected(self):
        with self.assertRaisesRegex(ValueError, 'invalid_article_metadata_json'):
            extract_article(fixture('<p>故宫</p>').replace('"doc_id": "sample"', '"doc_id":'))
        with self.assertRaisesRegex(ValueError, 'one_article_per_file_required'):
            extract_article('<article class="record"></article><article class="record"></article>')

    def test_missing_critical_field_and_visible_conflict(self):
        body = '<p>' + '午门游览后休息。' * 12 + '</p>'
        with self.assertRaisesRegex(ValueError, 'missing_required_metadata'):
            prepare_record('x.html', fixture(body, title=None).encode(), DEFAULT_RULES, ['故宫'])
        with self.assertRaisesRegex(ValueError, 'metadata_conflict'):
            prepare_record('x.html', fixture(body, scenic_name='天坛').encode(), DEFAULT_RULES, ['故宫', '天坛'])

    def test_zip_html_only_and_no_extract_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); zpath = root / 'input.zip'
            with zipfile.ZipFile(zpath, 'w') as z:
                z.writestr('../outside.html', 'content')
                z.writestr('answers.jsonl', 'must not be read')
            loaded = list(load_inputs([zpath], root / 'result'))
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0][1], b'content')
            self.assertFalse((root.parent / 'outside.html').exists())


class DuplicateTests(unittest.TestCase):
    def record(self, id, text, source_id='same', origin='dataset_corpus'):
        return {'doc_id': id, 'title': '故宫参观游记', 'clean_content': text, 'scenic_name': '故宫', 'text_type': 'travelogue', 'provenance_kind': origin, 'source_record_id': source_id, 'source_url': 'https://example.org/article', 'input_path': id + '.html', 'merged_record_ids': [id], 'source_records': [{'doc_id': id}]}

    def test_exact_duplicate_arbitrary_ids_preserves_provenance(self):
        a = self.record('arbitrary-A', '午门\n太和殿，休息。')
        b = self.record('unmarked-B', '午门 太和殿，休息。')
        kept, duplicates = deduplicate([a, b], DEFAULT_RULES)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]['merged_record_ids'], ['arbitrary-A', 'unmarked-B'])
        self.assertEqual(duplicates[0]['reason'], 'normalized_exact')

    def test_duplicate_suffix_is_not_deletion_rule(self):
        kept, _ = deduplicate([self.record('A_DUP', '午门出发，太和殿停留。'), self.record('B', '神武门出发，在御花园休息。')], DEFAULT_RULES)
        self.assertEqual(len(kept), 2)

    def test_different_corpus_records_not_near_merged(self):
        text = ''.join(chr(0x4e00 + i) for i in range(800))
        a, b = self.record('A', text, 'one'), self.record('B', text[:-1] + '景', 'two')
        kept, _ = deduplicate([a, b], DEFAULT_RULES)
        self.assertEqual(len(kept), 2)

    def test_same_source_near_duplicate_is_detected(self):
        text = ''.join(chr(0x4e00 + i) for i in range(800))
        a, b = self.record('A', text), self.record('B', text[:-1] + '景')
        kept, duplicates = deduplicate([a, b], DEFAULT_RULES)
        self.assertEqual(len(kept), 1)
        self.assertEqual(duplicates[0]['reason'], 'same_source_high_similarity')

    def test_synthetic_not_merged_into_real_source(self):
        kept, _ = deduplicate([self.record('A', '相同内容'), self.record('B', '相同内容', origin='synthetic_teaching')], DEFAULT_RULES)
        self.assertEqual(len(kept), 2)


if __name__ == '__main__':
    unittest.main()
