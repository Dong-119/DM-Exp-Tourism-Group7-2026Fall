"""Conservative, auditable cleaning. Preserve POIs, times, route arrows and conditions."""
import html
import re
import unicodedata
from collections import Counter
from html_reader import Node, BLOCK

DEFAULT_RULES = {
    'drop_tags': ['script', 'style', 'nav', 'aside', 'footer', 'noscript', 'template'],
    'drop_classes': ['breadcrumb', 'sharebar', 'related', 'comment', 'comments', 'meta', 'metadata', 'crawl-residue'],
    'join_words': ['游览'],
    'mojibake_tokens': ['锟斤拷', '\ufffd'],
    'adjacent_duplicate_min_chars': 30,
    'near_duplicate_threshold': 0.97,
    'near_duplicate_min_length_ratio': 0.97,
    'min_content_chars': 40,
}
URL_RE = re.compile(r'(?:https?://|www\.)[^\s<>\u4e00-\u9fff，。；！？、）】,;!?)\]\}]+', re.I)
INVISIBLE_RE = re.compile('[\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]')
CONTROL_RE = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
META_LINE = re.compile(r'^(?:来源网址|来源链接|本文链接|原文链接|发布时间|发布于|采集日期|作者|责任编辑|编辑|编码提示)\s*[:：]')
TAIL_HEADER = re.compile(r'^(?:本文相关网站|本篇相关网站|相关推荐|推荐阅读|相关阅读)\s*[:：]?\s*$')
UI_LINE = re.compile(r'^(?:返回顶部|返回列表|展开全文|收起全文|分享到.*|扫一扫.*|网友留言|此游记对我[:：]?|[・·]?自说自话型[:：].*)$')


def normalize(value, counts, rules):
    s = html.unescape(value)
    if s != value:
        counts['decode_entities'] += 1
    cleaned, n = INVISIBLE_RE.subn('', s)
    counts['remove_invisible_chars'] += n
    s, n = CONTROL_RE.subn('', cleaned)
    counts['remove_control_chars'] += n
    s2 = unicodedata.normalize('NFKC', s)
    if s2 != s:
        counts['normalize_unicode_nfkc'] += 1
    s = s2
    for token in rules['mojibake_tokens']:
        counts['remove_known_mojibake'] += s.count(token)
        s = s.replace(token, '')
    s, n = URL_RE.subn('', s)
    counts['remove_urls'] += n
    for word in rules['join_words']:
        pat = r'\s+'.join(re.escape(c) for c in word)
        s, n = re.subn(pat, word, s)
        counts['repair_configured_split_words'] += n
    # Only standardize punctuation next to Chinese text; 09:00, 2.5h and Latin names survive.
    s, n = re.subn(r'(?<=[\u4e00-\u9fff]),|,(?=[\u4e00-\u9fff])', '，', s)
    counts['normalize_chinese_commas'] += n
    s, n = re.subn(r'(?<=[\u4e00-\u9fff])\.(?=[\u4e00-\u9fff\s]|$)', '。', s)
    counts['normalize_chinese_stops'] += n
    s, n = re.subn(r'(?<=[\u4e00-\u9fff]):', '：', s)
    counts['normalize_chinese_colons'] += n
    s2 = re.sub(r'[^\S\n]+', ' ', s).strip()
    if s2 != s:
        counts['normalize_whitespace'] += 1
    return s2


def clean_body(body, rules=None):
    rules = rules or DEFAULT_RULES
    counts = Counter()
    removals = []

    def walk(node):
        attrs = node.attrs
        classes = set(attrs.get('class', '').split())
        hidden = 'hidden' in attrs or attrs.get('aria-hidden', '').lower() == 'true' or re.search(r'display\s*:\s*none|visibility\s*:\s*hidden', attrs.get('style', ''), re.I)
        if node.tag in rules['drop_tags'] or classes.intersection(rules['drop_classes']) or hidden:
            counts['remove_noise_blocks'] += 1
            removals.append({'rule': 'noise_block', 'tag': node.tag, 'class': attrs.get('class'), 'text_excerpt': node.text()[:180]})
            return ''
        # Alt text is not an observed travel description and is not added to body text.
        if node.tag == 'img':
            counts['remove_image_placeholders'] += 1
            return ''
        parts = [walk(c) if isinstance(c, Node) else c for c in node.children]
        value = ''.join(parts)
        counts['remove_html_elements'] += 1
        return value + ('\n' if node.tag in BLOCK else '')

    text = walk(body)
    lines = []
    for line in text.replace('\r\n', '\n').replace('\r', '\n').splitlines():
        # Metadata must be tested before removing bare URL values.
        original = line.strip()
        if META_LINE.match(original):
            counts['remove_metadata_lines'] += 1
            removals.append({'rule': 'metadata_line', 'text_excerpt': original[:180]})
            continue
        if TAIL_HEADER.match(original):
            counts['truncate_related_links_tail'] += 1
            removals.append({'rule': 'related_links_tail', 'text_excerpt': original})
            break
        s = normalize(line, counts, rules)
        if not s:
            continue
        if UI_LINE.fullmatch(s):
            counts['remove_ui_lines'] += 1
            removals.append({'rule': 'ui_line', 'text_excerpt': s[:180]})
            continue
        if lines and s == lines[-1] and len(s) >= rules['adjacent_duplicate_min_chars']:
            counts['remove_adjacent_duplicate_paragraphs'] += 1
            removals.append({'rule': 'adjacent_duplicate_paragraph', 'text_excerpt': s[:180]})
            continue
        lines.append(s)
    cleaned = '\n'.join(lines)
    warnings = []
    if counts['remove_known_mojibake']:
        warnings.append('unrecoverable_mojibake_removed_not_reconstructed')
    if re.search('[\ufffd\u200b]', cleaned):
        warnings.append('residual_invalid_characters')
    if re.search(r'<\s*/?\w+[^>]*>', cleaned):
        warnings.append('literal_html_like_text_remaining')
    return cleaned, dict(sorted((k, v) for k, v in counts.items() if v)), removals, warnings
