"""按来源浏览条件建议，并展开相应原句。"""
from html import escape
from experiment import ORIGINS


def write_page(folder,main,outside,stats):
    def table(rows):
        parts=[]
        for row in rows:
            quote='<br>'.join(escape(e['quote']) for e in row['evidence'])
            logic={'all':'合取或单一条件','any':'析取条件','necessary':'只有……才……',
                   'unless':'除非……否则……','context':'上下文情景'}[row['condition_operator']]
            parts.append(f"<tr data-origin='{row['provenance_kind']}'><td>{row['mapping_id']}<br>{escape('、'.join(row['visitor_types']))}</td>"
                f"<td>{escape(row['condition_text'])}<br><small>{logic}</small></td><td>{escape(row['advice_text'])}</td>"
                f"<td>{escape(row['target_scope'])}<br>{ORIGINS[row['provenance_kind']]}</td>"
                f"<td><details><summary>{row['doc_id']} 原句</summary>{quote}</details></td></tr>")
        return '<table><tr><th>编号与人群</th><th>条件</th><th>建议</th><th>地点与来源</th><th>原文</th></tr>'+''.join(parts)+'</table>'
    options=''.join(f'<option value="{k}">{v}</option>' for k,v in ORIGINS.items())
    page=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>实验五 条件建议映射表</title>
<style>body{{font:15px/1.8 'Microsoft YaHei',sans-serif;max-width:1350px;margin:28px auto;padding:0 20px;color:#243e4d}}table{{width:100%;border-collapse:collapse}}td,th{{border:1px solid #ccd8df;padding:10px;text-align:left;vertical-align:top}}th{{background:#edf3f5}}td:nth-child(2){{width:21%}}td:nth-child(3){{width:30%}}summary{{cursor:pointer}}small{{color:#6a7f8a}}img{{max-width:100%}}select{{padding:6px}}</style>
<h1>实验五 条件性游览建议的抽取</h1><p>使用实验一提供的{stats['input']['records']}篇结构化文章，整理得到{len(main)}条主体建议和{len(outside)}条其他地点建议。最终映射表已完成人工复核。</p>
<p>来源筛选：<select id="filter"><option value="">全部</option>{options}</select>　<a href="条件建议映射表.csv">CSV映射表</a></p>
<h2>抽取流程</h2><img src="条件建议抽取流程.png" alt="抽取流程"><h2>主体映射表</h2>{table(main)}
<h2>分类统计</h2><img src="游客类型统计.png" alt="游客类型"><img src="条件类型统计.png" alt="条件类型"><img src="来源与适用范围.png" alt="来源与适用范围">
<h2>其他地点建议</h2>{table(outside)}
<script>document.querySelector('#filter').onchange=e=>document.querySelectorAll('tr[data-origin]').forEach(r=>r.hidden=!!e.target.value&&r.dataset.origin!==e.target.value)</script></html>'''
    (folder/'映射表.html').write_text(page,encoding='utf-8')
