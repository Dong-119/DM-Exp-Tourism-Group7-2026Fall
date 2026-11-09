"""Read article HTML only: no use of answer keys, reference JSONL or noise manifests."""
import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Optional

VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}
BLOCK = {'p', 'div', 'section', 'article', 'h1', 'h2', 'h3', 'h4', 'li', 'tr', 'br', 'blockquote', 'figcaption'}

@dataclass
class Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)
    start: int = 0
    inner_start: int = 0
    inner_end: int = 0
    end: int = 0

    def has_class(self, name):
        return name in self.attrs.get('class', '').split()

    def find_all(self, predicate):
        found = [self] if predicate(self) else []
        for child in self.children:
            if isinstance(child, Node):
                found.extend(child.find_all(predicate))
        return found

    def text(self):
        return ''.join(c.text() if isinstance(c, Node) else c for c in self.children)

class Tree(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.source = source
        self.lines = [0] + [m.end() for m in re.finditer('\n', source)]
        self.root = Node('root', inner_end=len(source), end=len(source))
        self.stack = [self.root]
        self.warnings = []

    def absolute_offset(self):
        line, col = self.getpos()
        return self.lines[line - 1] + col

    def handle_starttag(self, tag, attrs):
        start = self.absolute_offset()
        node = Node(tag, dict(attrs), start=start, inner_start=start + len(self.get_starttag_text()), inner_end=len(self.source), end=len(self.source))
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)
        else:
            node.inner_end = node.inner_start
            node.end = node.inner_start

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            node = self.stack.pop()
            node.inner_end = node.inner_start
            node.end = node.inner_start

    def handle_endtag(self, tag):
        matches = [i for i in range(1, len(self.stack)) if self.stack[i].tag == tag]
        if not matches:
            self.warnings.append('unmatched_end_tag:' + tag)
            return
        i = matches[-1]
        if i != len(self.stack) - 1:
            self.warnings.append('recovered_nesting:' + tag)
        start = self.absolute_offset()
        end = self.source.find('>', start)
        for node in self.stack[i:]:
            node.inner_end = start
            node.end = end + 1 if end >= 0 else len(self.source)
        del self.stack[i:]

    def handle_data(self, data):
        self.stack[-1].children.append(data)

    def finish(self):
        self.feed(self.source)
        self.close()
        if len(self.stack) > 1:
            self.warnings.append('unclosed_tags:' + ','.join(n.tag for n in self.stack[1:]))
        return self.root


def decode_html(data):
    declared = re.search(br'<meta\b[^>]*charset\s*=\s*[\'\"]?\s*([A-Za-z0-9_-]+)', data[:4096], re.I)
    encoding = declared[1].decode('ascii') if declared else 'utf-8-sig'
    if encoding.lower() in ('utf-8', 'utf8'):
        encoding = 'utf-8-sig'
    try:
        return data.decode(encoding), encoding, []
    except LookupError:
        return data.decode('utf-8-sig', errors='replace'), 'utf-8-sig', ['unknown_declared_encoding:' + encoding]
    except UnicodeDecodeError:
        # Do not silently decode broken UTF-8 bytes as another Chinese encoding.
        return data.decode(encoding, errors='replace'), encoding, ['decoding_replacement_used']


def raw_text(node):
    """Text before cleaning; retain navigation/comments but omit code/style text."""
    if node.tag in {'script', 'style'}:
        return ''
    value = ''.join(raw_text(c) if isinstance(c, Node) else c for c in node.children)
    return value + ('\n' if node.tag in BLOCK else '')


def extract_article(source):
    parser = Tree(source)
    root = parser.finish()
    warnings = list(parser.warnings)
    metadata_nodes = root.find_all(lambda n: n.tag == 'script' and n.attrs.get('id') == 'article-metadata')
    meta = {}
    if metadata_nodes:
        if len(metadata_nodes) != 1:
            raise ValueError('multiple_article_metadata_blocks')
        try:
            meta = json.loads(metadata_nodes[0].text())
            if not isinstance(meta, dict):
                raise ValueError('metadata_not_object')
        except json.JSONDecodeError as exc:
            raise ValueError('invalid_article_metadata_json') from exc
    else:
        warnings.append('metadata_json_missing_using_visible_fields')
    records = root.find_all(lambda n: n.tag == 'article' and n.has_class('record'))
    if len(records) > 1:
        raise ValueError('one_article_per_file_required')
    article = records[0] if records else root
    bodies = article.find_all(lambda n: n.has_class('document-body'))
    if len(bodies) != 1:
        raise ValueError('exactly_one_document_body_required')
    body = bodies[0]
    visible = {}
    for dl in article.find_all(lambda n: n.tag == 'dl' and n.has_class('metadata')):
        key = None
        for child in dl.children:
            if isinstance(child, Node) and child.tag == 'dt':
                key = child.text().strip()
            elif isinstance(child, Node) and child.tag == 'dd' and key:
                visible[key] = child.text().strip()
    for field_name, label in [('doc_id', '文章编号'), ('title', '文章标题'), ('scenic_name', '景区名称'), ('source_name', '数据来源'), ('content_origin', '正文性质')]:
        v = visible.get(label)
        if field_name in meta and v and meta[field_name] != v:
            warnings.append('visible_metadata_conflict:' + field_name)
        if not meta.get(field_name) and v and v != '未提供':
            meta[field_name] = v
    for k, label in [('source_url', '来源链接'), ('original_article_url', '原文章链接'), ('reference_url', '路线参考链接')]:
        if not meta.get(k) and visible.get(label) not in (None, '', '未提供'):
            meta[k] = visible[label]
    if not meta.get('doc_id'):
        meta['doc_id'] = article.attrs.get('id')
    if not meta.get('scenic_name'):
        meta['scenic_name'] = article.attrs.get('data-scenic')
    if not meta.get('text_type'):
        meta['text_type'] = article.attrs.get('data-type')
    if not meta.get('title'):
        headings = article.find_all(lambda n: n.tag in {'h1', 'h2'})
        meta['title'] = headings[0].text().strip() if headings else None
    return meta, body, source[body.inner_start:body.inner_end], raw_text(body), warnings
