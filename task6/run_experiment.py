"""Build and visualize the multi-source tourism knowledge graph."""

from __future__ import annotations

import csv
import hashlib
import json
import html
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import networkx as nx


ROOT = Path(__file__).resolve().parents[1]
ENTITY_INPUT = ROOT / "task2" / "task2_jieba_final" / "result" / "v2" / "entities_v2.json"
ROUTE_INPUT = ROOT / "data" / "processed" / "experiment3" / "routes.json"
ADVICE_INPUT = ROOT / "task5" / "results" / "条件建议映射表.json"
OUTPUT = Path(__file__).resolve().parent / "results"
EDGE_TYPES = ["contains", "mentions_poi", "mentions_transport", "mentions_time",
              "has_route", "visits", "next", "occurs_in", "has_activity", "has_condition", "recommends"]


def node_id(kind: str, *parts: str) -> str:
    return ":".join([kind, *[part.strip() for part in parts if part.strip()]]).replace(" ", "_")


def add_node(graph: nx.MultiDiGraph, identifier: str, kind: str, label: str, **attrs: Any) -> None:
    if identifier not in graph:
        graph.add_node(identifier, kind=kind, label=label, **attrs)
    else:
        existing = graph.nodes[identifier]
        existing["source_count"] = int(existing.get("source_count", 1)) + int(attrs.get("source_count", 1))
        existing["source_kinds"] = sorted(set(existing.get("source_kinds", [])) | set(attrs.get("source_kinds", [])))


def add_edge(graph: nx.MultiDiGraph, source: str, target: str, relation: str, **attrs: Any) -> None:
    # visits/next 是访问事件，键必须区分路线和步骤；其他关系合并来源而非覆盖来源。
    key = (json.dumps([relation, attrs.get("route_id"), attrs.get("order")], ensure_ascii=False)
           if relation in {"visits", "next"} else relation)
    document = attrs.get("source_document")
    provenance = attrs.get("provenance_kind")
    if graph.has_edge(source, target, key):
        existing = graph[source][target][key]
        for field, value in [("source_documents", document), ("provenance_kinds", provenance)]:
            existing[field] = sorted(set(existing.get(field, [])) | ({value} if value else set()))
        existing["evidence_count"] = existing.get("evidence_count", 1) + 1
    else:
        graph.add_edge(source, target, key=key, relation=relation, **attrs,
                       source_documents=[document] if document else [],
                       provenance_kinds=[provenance] if provenance else [], evidence_count=1)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_graph() -> tuple[nx.MultiDiGraph, dict[str, Any]]:
    entities = load_json(ENTITY_INPUT)
    routes = load_json(ROUTE_INPUT)
    advice = load_json(ADVICE_INPUT)
    graph = nx.MultiDiGraph(name="Tourism procedural knowledge graph")
    diagnostics = Counter()
    source_links: defaultdict[str, set[str]] = defaultdict(set)

    for document in entities:
        scenic = document.get("scenic_name") or "北京通用"
        scenic_id = node_id("scenic", scenic)
        add_node(graph, scenic_id, "scenic", scenic, source_count=1, source_kinds=[document.get("provenance_kind", "unknown")])
        for entity in document.get("entities", []):
            entity_type = entity.get("type")
            if entity_type not in {"POI", "TRANSPORT", "TIME"}:
                diagnostics["ignored_entity_type"] += 1
                continue
            canonical = entity.get("canonical") or entity.get("text")
            if not canonical:
                diagnostics["ignored_empty_entity"] += 1
                continue
            kind = {"POI": "poi", "TRANSPORT": "transport", "TIME": "time"}[entity_type]
            if kind == "poi" and canonical == scenic:
                diagnostics["ignored_redundant_scenic_poi"] += 1
                continue
            entity_id = node_id(kind, scenic, canonical) if kind != "time" else node_id(kind, canonical)
            add_node(
                graph,
                entity_id,
                kind,
                canonical,
                scenic_name=scenic if kind != "time" else None,
                source_count=1,
                source_kinds=[document.get("provenance_kind", "unknown")],
            )
            relation = {
                "poi": "mentions_poi",
                "transport": "mentions_transport",
                "time": "mentions_time",
            }[kind]
            add_edge(graph, scenic_id, entity_id, relation, source_document=document.get("doc_id"), source_type="task2",
                     provenance_kind=document.get("provenance_kind", "unknown"))
            source_links[entity_id].add(document.get("doc_id", ""))
            diagnostics[f"task2_{kind}"] += 1

    for route in routes:
        scenic = route["scenic_name"]
        scenic_id = node_id("scenic", scenic)
        route_id = node_id("route", route["route_id"])
        provenance = route.get("provenance_kind", "unknown")
        add_node(graph, route_id, "route", route["route_id"], route_kind=route["route_kind"], document_id=route["document_id"], provenance_kind=provenance, reference_url=route.get("reference_url"))
        add_edge(graph, scenic_id, route_id, "has_route", source_document=route["document_id"], source_type="task3", provenance_kind=provenance)
        previous = None
        for step in route["steps"]:
            poi_id = node_id("poi", scenic, step["poi"])
            add_node(graph, poi_id, "poi", step["poi"], scenic_name=scenic, poi_kind=step["poi_kind"], source_count=1, source_kinds=["task3"])
            add_edge(graph, scenic_id, poi_id, "contains", source_document=route["document_id"], source_type="task3", provenance_kind=provenance)
            add_edge(graph, route_id, poi_id, "visits", order=step["order"], route_id=route["route_id"], step_type=step["step_type"], source_document=route["document_id"], source_type="task3", provenance_kind=provenance)
            if previous is not None:
                add_edge(graph, previous, poi_id, "next", order=step["order"], route_id=route["route_id"], source_document=route["document_id"], source_type="task3", provenance_kind=provenance)
            previous = poi_id
            if step.get("time_slot") and step["time_slot"] != "unknown":
                time_id = node_id("time", step["time_slot"])
                add_node(graph, time_id, "time", step["time_slot"], source_count=1, source_kinds=["task3"])
                add_edge(graph, poi_id, time_id, "occurs_in", source_document=route["document_id"], source_type="task3", provenance_kind=provenance)
            if step.get("activity"):
                activity_id = node_id("activity", scenic, step["activity"])
                add_node(graph, activity_id, "activity", step["activity"], scenic_name=scenic, source_count=1, source_kinds=["task3"])
                add_edge(graph, poi_id, activity_id, "has_activity", source_document=route["document_id"], source_type="task3", provenance_kind=provenance)
            diagnostics["task3_steps"] += 1

    for item in advice:
        target = item.get("target_scope") or item.get("source_scenic") or "北京通用"
        target_id = node_id("scenic", target)
        add_node(graph, target_id, "scenic", target, source_count=1, source_kinds=["task5"])
        condition = item.get("condition_text", "").strip()
        action = item.get("advice_text", "").strip()
        if not condition or not action:
            diagnostics["ignored_invalid_advice"] += 1
            continue
        condition_id = node_id("condition", item.get("mapping_id", condition))
        advice_id = node_id("advice", item.get("mapping_id", action))
        provenance_attrs = {"provenance_kind": item.get("provenance_kind", "unknown"),
                            "source_urls": item.get("source_urls", []), "source_path": item.get("source_path"),
                            "source_document": item.get("doc_id")}
        add_node(graph, condition_id, "condition", condition, condition_type=item.get("condition_type"), operator=item.get("condition_operator"), source_count=1, source_kinds=["task5"], **provenance_attrs)
        add_node(graph, advice_id, "advice", action, visitor_types=";".join(item.get("visitor_types", [])), source_count=1, source_kinds=["task5"], **provenance_attrs)
        add_edge(graph, target_id, condition_id, "has_condition", source_type="task5", **provenance_attrs)
        add_edge(graph, condition_id, advice_id, "recommends", condition_type=item.get("condition_type"), source_type="task5", **provenance_attrs)
        diagnostics["task5_advice"] += 1

    for identifier, documents in source_links.items():
        graph.nodes[identifier]["source_documents"] = sorted(documents)
    for _, data in graph.nodes(data=True):
        data.setdefault("source_count", 1)
        data.setdefault("source_kinds", [])
    return graph, {"diagnostics": dict(diagnostics), "input_documents": {"task2": len(entities), "task3": len(routes), "task5": len(advice)}}


def write_table(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: json.dumps(row.get(field), ensure_ascii=False) if isinstance(row.get(field), (list, dict)) else row.get(field, "") for field in fields} for row in rows)


def export_graph(graph: nx.MultiDiGraph, metadata: dict[str, Any]) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    nodes = [{"id": identifier, **data} for identifier, data in graph.nodes(data=True)]
    edges = [{"source": source, "target": target, **data} for source, target, _, data in graph.edges(keys=True, data=True)]
    node_fields = sorted({key for row in nodes for key in row})
    edge_fields = sorted({key for row in edges for key in row})
    write_table(OUTPUT / "nodes.csv", nodes, node_fields)
    write_table(OUTPUT / "edges.csv", edges, edge_fields)
    graph_json = {
        "schema": {
            "node_types": ["scenic", "route", "poi", "transport", "time", "activity", "condition", "advice"],
            "edge_types": EDGE_TYPES,
            "relation_semantics": {"mentions_poi": "来源文章提及的地点候选，不证明地理隶属", "contains": "结构化路线支持的景点归属，仍保留真实/模拟来源类别"},
        },
        "nodes": nodes,
        "edges": edges,
        "metadata": metadata,
    }
    (OUTPUT / "knowledge_graph.json").write_text(json.dumps(graph_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    graphml_graph = graph.copy()
    for _, data in graphml_graph.nodes(data=True):
        for key, value in data.items():
            if value is None:
                data[key] = ""
            elif isinstance(value, (list, dict)):
                data[key] = json.dumps(value, ensure_ascii=False)
    for _, _, data in graphml_graph.edges(data=True):
        for key, value in data.items():
            if value is None:
                data[key] = ""
            elif isinstance(value, (list, dict)):
                data[key] = json.dumps(value, ensure_ascii=False)
    for _, _, _, data in graphml_graph.edges(keys=True, data=True):
        for key, value in data.items():
            if value is None:
                data[key] = ""
    nx.write_graphml(graphml_graph, OUTPUT / "knowledge_graph.graphml")


def visualize(graph: nx.MultiDiGraph) -> None:
    scenic_id = node_id("scenic", "故宫")
    selected = set(nx.single_source_shortest_path_length(graph.to_undirected(), scenic_id, cutoff=2))
    subgraph = graph.subgraph(selected).copy()
    try:
        position = nx.spring_layout(subgraph, seed=42, k=1.5)
    except ModuleNotFoundError:
        # Keep SVG generation usable when optional NumPy is unavailable.
        nodes = list(subgraph)
        position = {
            node: (
                math.cos(2 * math.pi * index / max(len(nodes), 1)),
                math.sin(2 * math.pi * index / max(len(nodes), 1)),
            )
            for index, node in enumerate(nodes)
        }
    colors = {"scenic": "#d62728", "route": "#9467bd", "poi": "#1f77b4", "transport": "#2ca02c", "time": "#ff7f0e", "activity": "#8c564b", "condition": "#e377c2", "advice": "#7f7f7f"}
    _write_svg(subgraph, position, colors)
    _write_route_svg(graph)
    _write_advice_svg(graph)
    _write_scenic_network_svg(graph, "故宫")
    _write_complete_relation_svgs(graph)
    try:
        import matplotlib.pyplot as plt
        plt.rcParams["font.family"] = ["SimSun", "Microsoft YaHei", "DejaVu Sans"]
        plt.rcParams["font.sans-serif"] = ["SimSun", "Microsoft YaHei", "DejaVu Sans"]
    except (ImportError, OSError, PermissionError):
        return
    plt.figure(figsize=(18, 12))
    for kind, color in colors.items():
        nodes = [node for node, data in subgraph.nodes(data=True) if data.get("kind") == kind]
        if nodes:
            nx.draw_networkx_nodes(subgraph, position, nodelist=nodes, node_color=color, node_size=900 if kind == "scenic" else 520, alpha=0.9, label=kind)
    nx.draw_networkx_edges(subgraph, position, arrows=True, alpha=0.35, width=0.8, connectionstyle="arc3,rad=0.08")
    labels = {node: data.get("label", node)[:16] for node, data in subgraph.nodes(data=True)}
    nx.draw_networkx_labels(subgraph, position, labels=labels, font_size=8)
    plt.title("故宫多源程序性知识图谱（项目2/3/5融合，2跳可视化）")
    plt.legend(loc="upper left")
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(OUTPUT / "knowledge_graph.png", dpi=180, bbox_inches="tight")
    plt.close()


def _write_route_svg(graph: nx.MultiDiGraph) -> None:
    routes = [
        node for node, data in graph.nodes(data=True)
        if data.get("kind") == "route"
        and graph.has_edge(node_id("scenic", "故宫"), node, key="has_route")
    ]
    routes.sort(key=lambda route: graph.nodes[route].get("route_kind", ""))
    width = 1900
    row_height = 130
    top = 100
    height = top + row_height * len(routes) + 100
    colors = {"official_route_facts": "#2563eb", "traveler_actual_route": "#16a34a", "synthetic_teaching_fixture": "#9333ea"}
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<defs><marker id="route-arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L10,3 z" fill="#64748b"/></marker></defs>',
        '<rect width="100%" height="100%" fill="#f8fafc"/>',
        '<text x="50" y="48" font-size="28" font-weight="bold">故宫路线结构可视化</text>',
        '<text x="50" y="78" font-size="16" fill="#475569">按路线分行展示顺序；节点为景点，颜色区分来源，避免全图节点重叠</text>',
    ]
    for row, route in enumerate(routes):
        y = top + row * row_height
        route_data = graph.nodes[route]
        color = colors.get(route_data.get("route_kind"), "#64748b")
        lines.append(f'<text x="50" y="{y + 8}" font-size="16" font-weight="bold" fill="{color}">{html.escape(route_data.get("label", route))}</text>')
        poi_edges = sorted(
            ((data.get("order", 0), target) for _, target, key, data in graph.out_edges(route, keys=True, data=True) if data.get("relation") == "visits"),
            key=lambda item: item[0],
        )
        x_start = 300
        gap = min(130, (width - x_start - 70) / max(len(poi_edges), 1))
        for index, (_, poi) in enumerate(poi_edges):
            x = x_start + index * gap
            if index:
                previous_x = x - gap
                lines.append(f'<line x1="{previous_x + 25:.1f}" y1="{y:.1f}" x2="{x - 25:.1f}" y2="{y:.1f}" stroke="#64748b" marker-end="url(#route-arrow)"/>')
            label = graph.nodes[poi].get("label", poi)
            lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="25" fill="{color}" stroke="#1e293b" stroke-width="2"/>')
            lines.append(f'<text x="{x:.1f}" y="{y + 5:.1f}" text-anchor="middle" font-size="13" fill="white">{html.escape(str(index + 1))}</text>')
            lines.append(f'<text x="{x:.1f}" y="{y + 48:.1f}" text-anchor="middle" font-size="14">{html.escape(str(label)[:8])}</text>')
    lines.append("</svg>")
    (OUTPUT / "故宫路线结构可视化.svg").write_text("\n".join(lines), encoding="utf-8")


def _write_advice_svg(graph: nx.MultiDiGraph) -> None:
    scenic = node_id("scenic", "故宫")
    condition_edges = [
        (target, graph.nodes[target])
        for _, target, key, _ in graph.out_edges(scenic, keys=True, data=True)
        if key == "has_condition"
    ]
    condition_edges.sort(key=lambda item: item[1].get("label", ""))
    condition_edges = condition_edges[:12]
    width = 1700
    row_height = 70
    height = 130 + row_height * len(condition_edges)
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<defs><marker id="route-arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L10,3 z" fill="#c2410c"/></marker></defs>',
        '<rect width="100%" height="100%" fill="#fff7ed"/>',
        '<text x="50" y="45" font-size="27" font-weight="bold">故宫条件性游览建议（示例）</text>',
        '<text x="50" y="75" font-size="15" fill="#7c2d12">条件 → 建议；仅展示 12 条代表性关系，完整数据见条件建议映射表和图谱 JSON</text>',
    ]
    for index, (condition, data) in enumerate(condition_edges):
        y = 115 + index * row_height
        advice_targets = [
            target for _, target, key, _ in graph.out_edges(condition, keys=True, data=True)
            if key == "recommends"
        ]
        advice = graph.nodes[advice_targets[0]].get("label", "") if advice_targets else "未连接建议"
        lines.append(f'<rect x="50" y="{y - 23}" width="500" height="42" rx="8" fill="#fed7aa" stroke="#c2410c"/>')
        lines.append(f'<text x="70" y="{y + 3}" font-size="15">{html.escape(str(data.get("label", ""))[:38])}</text>')
        lines.append(f'<line x1="550" y1="{y - 2}" x2="700" y2="{y - 2}" stroke="#c2410c" stroke-width="2" marker-end="url(#route-arrow)"/>')
        lines.append(f'<rect x="710" y="{y - 23}" width="900" height="42" rx="8" fill="#dcfce7" stroke="#15803d"/>')
        lines.append(f'<text x="730" y="{y + 3}" font-size="15">{html.escape(str(advice)[:80])}</text>')
    lines.append("</svg>")
    (OUTPUT / "故宫条件建议可视化.svg").write_text("\n".join(lines), encoding="utf-8")


def _write_scenic_network_svg(graph: nx.MultiDiGraph, scenic_name: str) -> None:
    scenic_id = node_id("scenic", scenic_name)
    selected = {scenic_id}
    for source, target, data in graph.edges(data=True):
        if source == scenic_id:
            selected.add(target)
        if source in selected:
            selected.add(target)
    # Include targets of route POIs and their semantic attributes.
    changed = True
    while changed:
        changed = False
        for source, target, _ in graph.edges(data=True):
            if source in selected and target not in selected:
                selected.add(target)
                changed = True
            elif target in selected and source.startswith("poi:") and source not in selected:
                selected.add(source)
                changed = True
    subgraph = graph.subgraph(selected).copy()
    layers = [
        ("scenic", "景区", "#b91c1c"),
        ("route", "路线", "#6d28d9"),
        ("poi", "景点", "#1d4ed8"),
        ("time", "时间", "#c2410c"),
        ("transport", "交通", "#15803d"),
        ("activity", "活动", "#7c2d12"),
        ("condition", "条件", "#be185d"),
        ("advice", "建议", "#475569"),
    ]
    columns = {kind: index for index, (kind, _, _) in enumerate(layers)}
    column_width = 390
    row_height = 54
    max_rows = max(
        sum(1 for _, data in subgraph.nodes(data=True) if data.get("kind") == kind)
        for kind, _, _ in layers
    )
    width = column_width * len(layers) + 100
    height = max(850, 150 + max_rows * row_height)
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<defs><marker id="network-arrow" markerWidth="9" markerHeight="9" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#94a3b8"/></marker></defs>',
        '<rect width="100%" height="100%" fill="#f8fafc"/>',
        f'<text x="45" y="42" font-size="29" font-weight="bold">{html.escape(scenic_name)}完整游览知识网络</text>',
        '<text x="45" y="72" font-size="16" fill="#475569">分层展示实验二实体、实验三路线和实验五条件建议；节点大小按来源频次/合并次数突出核心节点</text>',
    ]
    positions: dict[str, tuple[float, float]] = {}
    for kind, title, color in layers:
        nodes = sorted(
            [node for node, data in subgraph.nodes(data=True) if data.get("kind") == kind],
            key=lambda node: (-int(subgraph.nodes[node].get("source_count", 1)), str(subgraph.nodes[node].get("label", node))),
        )
        x = 50 + columns[kind] * column_width
        lines.append(f'<rect x="{x}" y="95" width="300" height="32" rx="6" fill="{color}"/>')
        lines.append(f'<text x="{x + 150}" y="117" text-anchor="middle" font-size="17" font-weight="bold" fill="white">{title}（{len(nodes)}）</text>')
        for index, node in enumerate(nodes):
            y = 155 + index * row_height
            positions[node] = (x + 150, y)
    for source, target, data in subgraph.edges(data=True):
        if source not in positions or target not in positions:
            continue
        x1, y1 = positions[source]
        x2, y2 = positions[target]
        relation = str(data.get("relation", ""))
        lines.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#cbd5e1" stroke-width="1" marker-end="url(#network-arrow)"/>')
        if relation in {"next", "visits", "occurs_in", "has_activity", "has_condition", "recommends"}:
            lines.append(f'<text x="{(x1+x2)/2:.1f}" y="{(y1+y2)/2 - 3:.1f}" font-size="9" fill="#64748b">{html.escape(relation)}</text>')
    for node, (x, y) in positions.items():
        data = subgraph.nodes[node]
        kind = data.get("kind", "unknown")
        color = next((color for node_kind, _, color in layers if node_kind == kind), "#64748b")
        frequency = int(data.get("source_count", 1))
        radius = min(25, 12 + math.log2(frequency + 1) * 3)
        label = str(data.get("label", node))
        lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" fill="{color}" stroke="#1e293b" stroke-width="1.5"/>')
        lines.append(f'<text x="{x + 28:.1f}" y="{y + 4:.1f}" font-size="12">{html.escape(label[:22])} <tspan fill="#64748b">[{frequency}]</tspan></text>')
    lines.append("</svg>")
    (OUTPUT / f"{scenic_name}完整游览知识网络.svg").write_text("\n".join(lines), encoding="utf-8")


def _write_complete_relation_svgs(graph: nx.MultiDiGraph) -> None:
    output_dir = OUTPUT / "complete_graphs"
    output_dir.mkdir(parents=True, exist_ok=True)
    for existing in output_dir.glob("*.svg"):
        existing.unlink()

    grouped: defaultdict[str, list[tuple[str, str, dict[str, Any]]]] = defaultdict(list)
    for source, target, data in graph.edges(data=True):
        grouped[str(data.get("relation", "unknown"))].append((source, target, data))

    index: list[dict[str, Any]] = []
    page_size = 40
    page_number = 0
    for relation in sorted(grouped):
        edges = sorted(
            grouped[relation],
            key=lambda edge: (
                str(graph.nodes[edge[0]].get("label", edge[0])),
                str(graph.nodes[edge[1]].get("label", edge[1])),
            ),
        )
        for start in range(0, len(edges), page_size):
            page_number += 1
            page_edges = edges[start:start + page_size]
            filename = f"{page_number:02d}_{relation}_{start + 1:03d}-{start + len(page_edges):03d}.svg"
            _write_relation_page(
                output_dir / filename,
                relation,
                page_edges,
                graph,
                start + 1,
                len(edges),
            )
            index.append({
                "file": f"complete_graphs/{filename}",
                "relation": relation,
                "edge_start": start + 1,
                "edge_end": start + len(page_edges),
                "edge_count": len(page_edges),
                "total_relation_edges": len(edges),
            })
    (OUTPUT / "complete_graphs_index.json").write_text(
        json.dumps(
            {
                "description": "All graph edges are displayed exactly once in the paginated SVG relation atlas.",
                "total_edges": graph.number_of_edges(),
                "page_count": len(index),
                "pages": index,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )


def _write_relation_page(
    path: Path,
    relation: str,
    edges: list[tuple[str, str, dict[str, Any]]],
    graph: nx.MultiDiGraph,
    start_number: int,
    total_relation_edges: int,
) -> None:
    width = 2100
    row_height = 42
    height = 115 + row_height * len(edges)
    kind_colors = {
        "scenic": "#b91c1c",
        "route": "#6d28d9",
        "poi": "#1d4ed8",
        "transport": "#15803d",
        "time": "#c2410c",
        "activity": "#7c2d12",
        "condition": "#be185d",
        "advice": "#475569",
    }
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="35" y="38" font-size="25" font-weight="bold">完整关系图：{html.escape(relation)}</text>',
        f'<text x="35" y="68" font-size="15" fill="#475569">本页显示该关系第 {start_number}—{start_number + len(edges) - 1} 条，共 {total_relation_edges} 条；每行一条边</text>',
        '<line x1="35" y1="88" x2="2065" y2="88" stroke="#cbd5e1"/>',
    ]
    for offset, (source, target, data) in enumerate(edges):
        y = 110 + offset * row_height
        source_data = graph.nodes[source]
        target_data = graph.nodes[target]
        source_kind = source_data.get("kind", "unknown")
        target_kind = target_data.get("kind", "unknown")
        source_label = str(source_data.get("label", source))
        target_label = str(target_data.get("label", target))
        details = []
        for field in ("order", "step_type", "route_id", "condition_type", "source_document", "source_type"):
            if data.get(field) not in (None, ""):
                details.append(f"{field}={data[field]}")
        detail_text = "；".join(details)
        lines.append(f'<text x="35" y="{y + 5}" font-size="13" fill="#64748b">{start_number + offset}</text>')
        lines.append(f'<rect x="75" y="{y - 17}" width="500" height="28" rx="5" fill="{kind_colors.get(source_kind, "#64748b")}"/>')
        lines.append(f'<text x="90" y="{y + 2}" font-size="14" fill="white">{html.escape(source_kind)} · {html.escape(source_label[:48])}</text>')
        lines.append(f'<line x1="590" y1="{y - 3}" x2="825" y2="{y - 3}" stroke="#64748b" stroke-width="2" marker-end="url(#edge-arrow)"/>')
        lines.append(f'<text x="705" y="{y - 8}" text-anchor="middle" font-size="12" fill="#334155">{html.escape(relation)}</text>')
        lines.append(f'<rect x="850" y="{y - 17}" width="500" height="28" rx="5" fill="{kind_colors.get(target_kind, "#64748b")}"/>')
        lines.append(f'<text x="865" y="{y + 2}" font-size="14" fill="white">{html.escape(target_kind)} · {html.escape(target_label[:48])}</text>')
        if detail_text:
            lines.append(f'<text x="1380" y="{y + 2}" font-size="12" fill="#475569">{html.escape(detail_text[:95])}</text>')
    lines.insert(1, '<defs><marker id="edge-arrow" markerWidth="9" markerHeight="9" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#64748b"/></marker></defs>')
    lines.append("</svg>")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_svg(graph: nx.MultiDiGraph, position: dict[str, tuple[float, float]], colors: dict[str, str]) -> None:
    width, height, margin = 1800, 1200, 80
    xs = [point[0] for point in position.values()] or [0]
    ys = [point[1] for point in position.values()] or [0]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    def point(node: str) -> tuple[float, float]:
        x, y = position[node]
        px = margin + (x - min_x) / (max_x - min_x or 1) * (width - 2 * margin)
        py = margin + (y - min_y) / (max_y - min_y or 1) * (height - 2 * margin)
        return px, py

    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">', '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z" fill="#777"/></marker></defs>', '<rect width="100%" height="100%" fill="white"/>', '<text x="60" y="40" font-size="24">故宫多源程序性知识图谱（项目2/3/5融合，2跳可视化）</text>']
    for source, target, data in graph.edges(data=True):
        x1, y1 = point(source)
        x2, y2 = point(target)
        lines.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#999" stroke-width="1" marker-end="url(#arrow)"/>')
        lines.append(f'<text x="{(x1+x2)/2:.1f}" y="{(y1+y2)/2:.1f}" font-size="9" fill="#555">{html.escape(str(data.get("relation", "")))}</text>')
    for node, data in graph.nodes(data=True):
        x, y = point(node)
        kind = data.get("kind", "unknown")
        radius = 24 if kind == "scenic" else 15
        lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{colors.get(kind, "#999")}" stroke="#333"/>')
        lines.append(f'<text x="{x:.1f}" y="{y + radius + 14:.1f}" text-anchor="middle" font-size="11">{html.escape(str(data.get("label", node))[:16])}</text>')
    lines.append("</svg>")
    (OUTPUT / "knowledge_graph.svg").write_text("\n".join(lines), encoding="utf-8")


def validate(graph: nx.MultiDiGraph) -> dict[str, Any]:
    required = {"scenic", "route", "poi", "transport", "time", "activity", "condition", "advice"}
    node_counts = Counter(data.get("kind") for _, data in graph.nodes(data=True))
    relation_counts = Counter(data.get("relation") for _, _, data in graph.edges(data=True))
    checks = {
        "has_required_node_types": required <= set(node_counts),
        "has_route_order_edges": relation_counts["next"] > 0,
        "has_source_edges": all(data.get("source_type") in {"task2", "task3", "task5"} for _, _, data in graph.edges(data=True)),
        "contains_only_pois": all(
            graph.nodes[target].get("kind") == "poi"
            for source, target, data in graph.edges(data=True)
            if data.get("relation") == "contains"
        ),
        "task2_context_relations_are_typed": all(
            data.get("relation") in {"mentions_poi", "mentions_transport", "mentions_time"}
            for source, target, data in graph.edges(data=True)
            if data.get("source_type") == "task2"
        ),
        "has_connected_components": nx.number_connected_components(graph.to_undirected()) >= 1,
        "all_route_steps_have_poi_edges": all(
            any(edge.get("relation") == "visits" for _, _, edge in graph.out_edges(route, data=True))
            for route, data in graph.nodes(data=True) if data.get("kind") == "route"
        ),
    }
    routes = load_json(ROUTE_INPUT)
    checks["route_events_preserved"] = all(
        sorted((edge["order"], graph.nodes[target]["label"]) for _, target, edge in graph.out_edges(node_id("route", route["route_id"]), data=True) if edge.get("relation") == "visits")
        == [(step["order"], step["poi"]) for step in route["steps"]] for route in routes)
    checks["next_events_preserved"] = relation_counts["next"] == sum(max(0, len(route["steps"]) - 1) for route in routes)
    checks["schema_covers_relations"] = set(relation_counts) <= set(EDGE_TYPES)
    checks["advice_provenance_preserved"] = all(data.get("provenance_kind") not in (None, "unknown") for _, data in graph.nodes(data=True) if data.get("kind") == "advice")
    relation_pages = list((OUTPUT / "complete_graphs").glob("*.svg"))
    relation_index_path = OUTPUT / "complete_graphs_index.json"
    if relation_index_path.exists():
        relation_index = load_json(relation_index_path)
        checks["complete_relation_atlas_covers_all_edges"] = (
            relation_index.get("total_edges") == graph.number_of_edges()
            and sum(page.get("edge_count", 0) for page in relation_index.get("pages", [])) == graph.number_of_edges()
            and len(relation_pages) == relation_index.get("page_count")
        )
    else:
        checks["complete_relation_atlas_covers_all_edges"] = False
    core = sorted(graph.degree, key=lambda item: item[1], reverse=True)[:10]
    return {"checks": checks, "passed": all(checks.values()), "node_counts": dict(node_counts), "relation_counts": dict(relation_counts), "components": nx.number_connected_components(graph.to_undirected()), "core_nodes": [{"id": node, "degree": degree, "label": graph.nodes[node].get("label")} for node, degree in core]}


def main() -> None:
    graph, metadata = load_graph()
    export_graph(graph, metadata)
    visualize(graph)
    validation = validate(graph)
    (OUTPUT / "validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "python": sys.version,
        "inputs": {name: str(path.relative_to(ROOT)) for name, path in {"task2_entities": ENTITY_INPUT, "task3_routes": ROUTE_INPUT, "task5_advice": ADVICE_INPUT}.items()},
        "input_sha256": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in {"task2_entities": ENTITY_INPUT, "task3_routes": ROUTE_INPUT, "task5_advice": ADVICE_INPUT}.items()},
        "node_count": graph.number_of_nodes(),
        "edge_count": graph.number_of_edges(),
        "graph_sha256": hashlib.sha256((OUTPUT / "knowledge_graph.json").read_bytes()).hexdigest(),
        "metadata": metadata,
        "validation": validation,
        "outputs": [
            "nodes.csv",
            "edges.csv",
            "knowledge_graph.json",
            "knowledge_graph.graphml",
            "knowledge_graph.svg",
            "故宫路线结构可视化.svg",
            "故宫条件建议可视化.svg",
            "故宫完整游览知识网络.svg",
            "complete_graphs_index.json",
            "complete_graphs/*.svg",
            "validation.json",
        ] + (["knowledge_graph.png"] if (OUTPUT / "knowledge_graph.png").exists() else []),
    }
    (OUTPUT / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not validation["passed"]:
        raise SystemExit("Graph validation failed")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
