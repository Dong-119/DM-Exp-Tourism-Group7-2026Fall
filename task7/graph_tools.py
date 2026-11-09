"""实验七：基于实验六结构化结果的实际知识图谱工具。"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


class GraphError(Exception):
    pass


class TourismGraph:
    """直接检索 task6 原始节点和有向边，不把文本提及误认为交通路线。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        try:
            raw = self.path.read_bytes()
            data = json.loads(raw.decode("utf-8-sig"))
            self.nodes = {node["id"]: node for node in data["nodes"]}
            self.edges = data["edges"]
            self.schema = data["schema"]
            if len(self.nodes) != len(data["nodes"]):
                raise GraphError("图谱存在重复节点ID")
            self.by_source: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
            for edge in self.edges:
                if edge["relation"] not in self.schema["edge_types"]:
                    raise GraphError("图谱关系未在Schema声明：" + edge["relation"])
                if edge["source"] not in self.nodes or edge["target"] not in self.nodes:
                    raise GraphError("图谱出现悬空关系")
                self.by_source[edge["source"]][edge["relation"]].append(edge)
            self.graph_hash = hashlib.sha256(raw).hexdigest()
            self.scenics = {n["label"]: n["id"] for n in self.nodes.values()
                            if n.get("kind") == "scenic" and n.get("label") != "北京通用"}
        except (OSError, ValueError, KeyError, UnicodeError, TypeError) as exc:
            raise GraphError(f"无法读取有效的实验六图谱：{exc}") from exc

    def _scenic_id(self, scenic: str) -> str:
        if scenic not in self.scenics:
            raise GraphError(f"图谱中没有景区「{scenic}」；已收录：{'、'.join(self.scenics)}")
        return self.scenics[scenic]

    def query_routes(self, scenic: str, limit: int = 5) -> dict[str, Any]:
        """工具 Schema：{scenic: str, limit: int=5} -> {status, routes, count}。"""
        sid = self._scenic_id(scenic)
        routes = []
        for edge in self.by_source[sid]["has_route"]:
            route = self.nodes[edge["target"]]
            steps = []
            for visit in self.by_source[route["id"]]["visits"]:
                poi = self.nodes[visit["target"]]
                steps.append({"id": poi["id"], "poi": poi["label"], "order": visit.get("order"),
                              "visit_id": f"{route['id']}@{visit['order']}", "step_type": visit.get("step_type"),
                              "provenance_kind": visit.get("provenance_kind", route.get("provenance_kind", "unknown")),
                              "source_document": visit.get("source_document"), "evidence_relation": "visits"})
            steps.sort(key=lambda x: (int(x["order"] or 9999), x["poi"]))
            if not steps:
                continue
            routes.append({"id": route["id"], "kind": route.get("route_kind", "unknown"),
                           "provenance_kind": route.get("provenance_kind", "unknown"),
                           "reference_url": route.get("reference_url"),
                           "document_id": route.get("document_id"), "steps": steps})
        # 优先官方事实，游客实际路线其次，教学模拟只能明确标注作为对照。
        rank = {"official_route_facts": 0, "traveler_actual_route": 1, "synthetic_teaching_fixture": 2}
        routes.sort(key=lambda r: (rank.get(r["kind"], 3), r["id"]))
        return {"status": "ok" if routes else "empty", "scenic": scenic,
                "count": len(routes), "routes": routes[:max(1, min(int(limit), 30))]}

    def query_pois(self, scenic: str, limit: int = 12) -> dict[str, Any]:
        """工具 Schema：{scenic: str, limit: int=12} -> {status, pois, count}。"""
        sid = self._scenic_id(scenic)
        pois: dict[str, dict[str, Any]] = {}
        excluded = set()
        for edge in self.by_source[sid]["mentions_poi"] + self.by_source[sid]["contains"]:
            node = self.nodes[edge["target"]]
            if node["kind"] != "poi":
                continue
            if node["label"] in self.scenics and node["label"] != scenic:
                excluded.add(node["label"])
                continue
            pois[node["id"]] = {"id": node["id"], "name": node["label"],
                                "source_document": edge.get("source_document"),
                                "source_documents": sorted(set(edge.get("source_documents", [])) | set(pois.get(node["id"], {}).get("source_documents", []))),
                                "provenance_kinds": node.get("source_kinds", []),
                                "membership": "route_supported" if edge["relation"] == "contains" else "text_mention_only",
                                "source_type": edge.get("source_type"),
                                "mention_count": int(node.get("source_count", 1))}
        result = sorted(pois.values(), key=lambda p: (-p["mention_count"], p["name"], p["id"]))
        return {"status": "ok" if result else "empty", "scenic": scenic,
                "count": len(result), "candidate_only": True, "excluded_other_scenics": sorted(excluded),
                "pois": result[:max(1, min(int(limit), 30))]}

    def query_advice(self, scenic: str, visitor: str = "", request: str = "",
                     limit: int = 5) -> dict[str, Any]:
        """按人群/明确条件匹配，不能无条件应用‘除非’‘只有’等规则。"""
        sid = self._scenic_id(scenic)
        matched = []
        for edge in self.by_source[sid]["has_condition"]:
            condition = self.nodes[edge["target"]]
            c_text = str(condition.get("label", ""))
            for recommend in self.by_source[condition["id"]]["recommends"]:
                advice = self.nodes[recommend["target"]]
                tags = [s for s in str(advice.get("visitor_types") or "").split(";") if s]
                # 人群类型必须精确命中；其它条件仅在请求明确提及时命中。
                visitor_set = set(re.split(r"[、,;]", visitor)) - {"", "未特定"}
                match = bool(visitor_set & set(tags))
                if not match and request:
                    words = ("下雨", "雨天", "拍照", "摄影", "体力", "走散", "迷路", "寒冷", "带水")
                    match = any(w in request and w in c_text for w in words)
                if not match:
                    continue
                # 标签匹配只能证明人群相关；复合条件中的疲劳/天气等不能被省略。
                context_groups = [("疲劳", "累", "体力不足"), ("下雨", "雨天"),
                                  ("走散", "迷路"), ("寒冷", "冷"), ("拍照", "摄影")]
                unknown_context = any(any(w in c_text for w in group) and not any(
                    w in request and not re.search(r"(?:不|没|没有)\s*$", request[:m.start()])
                    for w in group for m in re.finditer(re.escape(w), request))
                    for group in context_groups)
                compound_unknown = condition.get("operator") == "all" and bool(re.search(r"且|同时|并且", c_text))
                condition_confirmed = not unknown_context and not compound_unknown
                if condition.get("operator") == "any" and visitor_set & set(tags):
                    condition_confirmed = True
                if compound_unknown:
                    # 对未完整建模的合取条件仅在原条件原文被请求明确复述时认定。
                    condition_confirmed = c_text in request
                matched.append({"condition_id": condition["id"],
                                "condition": c_text, "operator": condition.get("operator"),
                                "condition_type": condition.get("condition_type"),
                                "advice_id": advice["id"], "advice": advice["label"],
                                "visitor_types": tags,
                                "source_document": recommend.get("source_document"),
                                "source_urls": advice.get("source_urls", []),
                                "provenance_kind": advice.get("provenance_kind", "unknown"),
                                "source_label": {"dataset_corpus": "语料游记", "editorial_route_guide": "编辑指南", "synthetic_teaching": "教学模拟"}.get(advice.get("provenance_kind"), "来源待核验"),
                                "condition_evaluation": "matched" if condition_confirmed else "requires_confirmation",
                                "source_type": recommend.get("source_type")})
        # 不覆盖条件语义，保留完整条件句及来源；不把模拟语料当作官方消息。
        matched.sort(key=lambda x: (x["condition_id"], x["advice_id"]))
        return {"status": "ok" if matched else "empty", "scenic": scenic,
                "count": len(matched), "advice": matched[:max(1, min(int(limit), 30))]}

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        specs = {
            "query_routes": (self.query_routes, {"scenic", "limit"}),
            "query_pois": (self.query_pois, {"scenic", "limit"}),
            "query_advice": (self.query_advice, {"scenic", "visitor", "request", "limit"}),
        }
        if name not in specs:
            return {"status": "error", "message": "未知图谱工具", "tool": name}
        func, allowed = specs[name]
        if not isinstance(arguments, dict) or set(arguments) - allowed:
            return {"status": "error", "message": "工具参数不符合 Schema", "tool": name}
        if not isinstance(arguments.get("scenic"), str) or not arguments["scenic"].strip():
            return {"status": "error", "message": "缺少 scenic 字符串", "tool": name}
        if "limit" in arguments and (type(arguments["limit"]) is not int or not 1 <= arguments["limit"] <= 30):
            return {"status": "error", "message": "limit 必须为 1—30 的整数", "tool": name}
        if any(key in arguments and not isinstance(arguments[key], str) for key in ("visitor", "request")):
            return {"status": "error", "message": "visitor/request 必须为字符串", "tool": name}
        try:
            return func(**arguments)
        except (GraphError, TypeError, ValueError) as exc:
            return {"status": "error", "message": str(exc), "tool": name}


TOOL_SCHEMAS = [
    {"name": "query_routes", "description": "查询景区官方/游客/模拟路线与按序景点，返回真实 route/POI ID 与文档证据。",
     "parameters": {"type": "object", "properties": {"scenic": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 30}}, "required": ["scenic"]}},
    {"name": "query_pois", "description": "查询景区包含的 POI 候选，不提供路线顺序、开放时间或距离。",
     "parameters": {"type": "object", "properties": {"scenic": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 30}}, "required": ["scenic"]}},
    {"name": "query_advice", "description": "按游客类别或用户明确提出的条件检索实验五条件建议。",
     "parameters": {"type": "object", "properties": {"scenic": {"type": "string"},
                    "visitor": {"type": "string"}, "request": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 30}},
                    "required": ["scenic"]}},
]
