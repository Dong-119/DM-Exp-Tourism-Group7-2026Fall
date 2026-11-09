"""实验七：带实际图谱查询、证据链和 OpenAI-compatible 模型适配器的旅游规划 Agent。"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from graph_tools import TourismGraph, TOOL_SCHEMAS

ROOT = Path(__file__).resolve().parent
GRAPH = ROOT / "data" / "knowledge_graph.json"


class LLMError(RuntimeError):
    pass


class ChatLLM:
    """只使用环境变量读取模型配置；不记录 API Key 或完整 HTTP 请求头。"""

    def __init__(self):
        self.base = os.getenv("TOURISM_LLM_BASE_URL", "").rstrip("/")
        self.model = os.getenv("TOURISM_LLM_MODEL", "").strip()
        self.api_key = os.getenv("TOURISM_LLM_API_KEY", "")
        if not self.base or not self.model:
            raise LLMError("API 模式需要 TOURISM_LLM_BASE_URL 和 TOURISM_LLM_MODEL；可选 TOURISM_LLM_API_KEY")
        if not self.base.startswith(("http://", "https://")):
            raise LLMError("LLM 地址必须以 http:// 或 https:// 开头")

    def ask_json(self, system: str, user: str) -> dict[str, Any]:
        # 兼容本地/云端的 OpenAI Chat Completions 接口，无需固定 SDK。
        url = self.base + ("" if self.base.endswith("/chat/completions") else "/chat/completions")
        body = json.dumps({"model": self.model, "temperature": 0,
                           "messages": [{"role": "system", "content": system},
                                        {"role": "user", "content": user}]},
                          ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        req = urllib.request.Request(url, body, headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                payload = json.load(response)
            content = payload["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(item.get("text", "") for item in content if isinstance(item, dict))
            text = str(content).strip()
            if text.startswith("```"):
                text = re.sub(r"^\`{3}(?:json)?\s*|\s*\`{3}$", "", text, flags=re.I)
            obj = json.loads(text)
            if not isinstance(obj, dict):
                raise ValueError("模型返回的 JSON 不是对象")
            return obj
        except (urllib.error.URLError, OSError, KeyError, IndexError, ValueError, TypeError) as exc:
            raise LLMError(f"模型请求或 JSON 解析失败：{str(exc)[:220]}") from exc


def positive_mention(query: str, word: str) -> bool:
    """排除紧邻提及的否定，不把‘不带孩子’当作亲子需求。"""
    return any(not re.search(r"(?:不带(?:着)?|没带|没有带|不去|不游览|不考虑|不包括|排除|不要去|不是|非)\s*$",
                             query[max(0, match.start()-8):match.start()])
               for match in re.finditer(re.escape(word), query))


def duration_number(value: str) -> int:
    if value.isdigit():
        return int(value)
    digits = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9, "零": 0}
    if value in digits:
        return digits[value]
    if value.count("十") == 1:
        tens, ones = value.split("十")
        return digits.get(tens, 1) * 10 + digits.get(ones, 0)
    return 0


def parse_constraints_rule(query: str, scenic_names: list[str]) -> dict[str, Any]:
    found = [s for s in scenic_names if positive_mention(query, s)]
    outside = [s for s in ("圆明园", "长城", "北海公园", "八达岭", "上海迪士尼")
               if positive_mention(query, s) and s not in scenic_names]
    visitors = []
    visitor = "未特定"
    for code, keywords in [
        ("亲子", ("亲子", "孩子", "小孩", "儿童", "小朋友", "宝宝")),
        ("老人", ("老人", "长辈", "父母", "老年", "爷爷", "奶奶")),
        ("情侣", ("情侣", "约会", "女友", "男友")),
        ("摄影爱好者", ("摄影", "拍照", "摄影师"))]:
        if any(positive_mention(query, x) for x in keywords):
            visitors.append(code)
    visitor = "、".join(visitors) or "未特定"
    number = r"(?<![0-9一二两三四五六七八九十百])([0-9]+|[一二两三四五六七八九十百]+)\s*"
    days = {duration_number(m) for m in re.findall(number + r"(?:天|日)(?!期)", query)}
    hours = {duration_number(m) for m in re.findall(number + r"小时", query)}
    if "半天" in query and not hours:
        hours.add(4)   # 半天只用于路线容量估计，并非游览耗时事实。
    errors = []
    if len(found) + len(outside) > 1:
        errors.append("一次请求涉及多个景区，当前只支持单景区路线规划")
    if len(days) > 1 or len(hours) > 1:
        errors.append("时长包含相互冲突的要求，请明确一个时长")
    invalid_duration = any(not 1 <= n <= 3 for n in days) or any(not 1 <= n <= 12 for n in hours)
    if invalid_duration:
        errors.append("当前只支持1—3天或1—12小时，请调整时长；已保留原始数值")
    if not found and not outside:
        errors.append("缺少明确的景区，请补充故宫、颐和园或天坛")
    return {
        "scenic": found[0] if len(found) == 1 else (outside[0] if outside else None),
        "scenic_matches": found, "unsupported_scenic_matches": outside,
        "visitor": visitor, "visitors": visitors,
        "days": min(days) if len(days) == 1 else None,
        "hours": min(hours) if len(hours) == 1 else None,
        "errors": errors,
        "unsupported_scenic": bool(outside and not found),
        "error_status": "needs_clarification" if invalid_duration or not found and not outside else "conflict",
        "parse_method": "local_rules"
    }


def parse_constraints_llm(query: str, rule: dict[str, Any], model: ChatLLM) -> dict[str, Any]:
    system = ("你是旅游意图解析器。仅输出 JSON 对象，键包含 scenic,visitor,days,hours。"
              "visitor 只能是亲子/老人/情侣/摄影爱好者/未特定；未明示的约束用 null。"
              "不得凭空补充景区、时长。不要输出解释。")
    parsed = model.ask_json(system, query)
    # 先保留规则解析的冲突/未知结果，不允许语言模型将不确定内容改成确信事实。
    result = dict(rule)
    # 模型不能凭空增加时长、人群，也不能抹掉已识别的否定、冲突和跨景区请求。
    result["llm_constraints"] = {key: parsed.get(key) for key in ("scenic", "visitor", "days", "hours")}
    result["llm_agrees_with_explicit_constraints"] = all(
        parsed.get(key) == rule.get(key) for key in ("scenic", "visitor", "days", "hours"))
    result["parse_method"] = "llm_checked_by_rules"
    return result


def choose_stops(steps: list[dict[str, Any]], constraints: dict[str, Any]) -> list[dict[str, Any]]:
    hours = constraints.get("hours")
    days = constraints.get("days")
    cap = min(12, max(3, hours + 1)) if hours else 8 if days == 1 else 12 if days and days > 1 else 6
    entries = [i for i, step in enumerate(steps) if step.get("step_type") == "entry"]
    exits = [i for i, step in enumerate(steps) if step.get("step_type") == "exit"]
    mandatory = ({entries[0]} if entries else set()) | ({exits[-1]} if exits else set())
    selected = set(mandatory)
    for i in range(len(steps)):
        if len(selected) >= cap:
            break
        selected.add(i)
    return [steps[i] for i in sorted(selected)]


def validate_proposal(proposal: dict[str, Any], steps: list[dict[str, Any]], budget: int):
    """用访问事件校验模型方案；重复经过同一POI时不得用POI ID消除歧义。"""
    ids = proposal.get("selected_visit_ids")
    key = "visit_id"
    if ids is None:
        ids = proposal.get("selected_poi_ids")
        key = "id"
    if not isinstance(ids, list) or not ids or any(type(x) is not str for x in ids):
        return None, "模型返回了空列表或无效 ID 类型"
    if len(ids) != len(set(ids)):
        return None, "模型返回了重复访问 ID"
    if len({step[key] for step in steps}) != len(steps) and key == "id":
        return None, "该路线重复经过同一景点，必须使用无歧义的 visit_id"
    by_id = {step[key]: (i, step) for i, step in enumerate(steps)}
    if any(value not in by_id for value in ids):
        return None, "模型规划中包含图谱之外的访问 ID"
    indices = [by_id[value][0] for value in ids]
    if indices != sorted(indices):
        return None, "模型改变了来源路线的顺序"
    if len(ids) > budget:
        return None, f"模型给出 {len(ids)} 站，超过本次 {budget} 站的启发式预算"
    selected = [by_id[value][1] for value in ids]
    endpoint_steps = choose_stops(steps, {"hours": 1})
    required = {s["visit_id"] for s in endpoint_steps if s.get("step_type") in ("entry", "exit")}
    if not required <= {s["visit_id"] for s in selected}:
        return None, "模型方案遗漏来源标注的入口或出口"
    return selected, None


def agent_run(query: str, mode: str = "demo", graph_path: Path = GRAPH) -> dict[str, Any]:
    """ReAct 等价的可观察循环：解析/决策 -> 图谱工具 -> 观察 -> 有证据生成。"""
    trace: list[dict[str, Any]] = []
    result: dict[str, Any] = {"query": query, "mode": mode, "llm_used": False,
                              "status": "error", "trace": trace, "tool_schemas": TOOL_SCHEMAS}
    if mode not in ("demo", "api"):
        result["message"] = "mode 必须为 demo 或 api"
        return result
    try:
        graph = TourismGraph(graph_path)
    except Exception as exc:
        result["message"] = str(exc)
        trace.append({"phase": "init", "status": "error", "message": str(exc)})
        return result
    result["graph_sha256"] = graph.graph_hash
    try:
        llm = ChatLLM() if mode == "api" else None
        constraints = parse_constraints_rule(query, list(graph.scenics))
        if llm:
            constraints = parse_constraints_llm(query, constraints, llm)
            result["llm_used"] = True
        result["constraints"] = constraints
        trace.append({"phase": "parse", "constraints": constraints})
        if constraints["errors"]:
            result.update(status=constraints["error_status"],
                          message="；".join(constraints["errors"]))
            trace.append({"phase": "decision", "action": "ask_user", "reason": result["message"]})
            return result
        scenic = constraints["scenic"]
        if scenic not in graph.scenics:
            result.update(status="no_match", message=f"图谱未收录「{scenic}」，仅支持：{'、'.join(graph.scenics)}。")
            trace.append({"phase": "decision", "action": "no_route_without_graph", "reason": result["message"]})
            return result
        tool_outputs: dict[str, dict[str, Any]] = {}

        def observe(tool: str, args: dict[str, Any]) -> dict[str, Any]:
            response = graph.call_tool(tool, args)
            trace.append({"phase": "action_observation", "tool": tool, "arguments": args, "result": response})
            tool_outputs[tool] = response
            if response["status"] == "error":
                raise RuntimeError(response["message"])
            return response

        trace.append({"phase": "decision", "action": "query_routes", "reason": "优先获取有来源的景点先后顺序"})
        routes = observe("query_routes", {"scenic": scenic, "limit": 8})
        advice = observe("query_advice", {"scenic": scenic, "visitor": constraints["visitor"],
                                         "request": query, "limit": 5})
        result["tool_results"] = {"query_routes": routes, "query_advice": advice}
        result["advice_used"] = [a for a in advice["advice"] if a["condition_evaluation"] == "matched"]
        result["advice_pending_confirmation"] = [a for a in advice["advice"] if a["condition_evaluation"] != "matched"]
        result["warnings"] = [
            "图谱没有可靠的开放时间、门票、距离和单景点停留时长；时长仅用于建议行程取舍。",
            "条件建议须结合具体触发条件使用，来源含教学模拟/游客文本，不等于官方承诺。"
        ]
        if not routes["routes"]:
            pois = observe("query_pois", {"scenic": scenic, "limit": 10})
            result["tool_results"]["query_pois"] = pois
            result.update(status="partial", selected_route=None, itinerary=[], candidate_pois=pois["pois"],
                          message=(f"{scenic}存在 {pois['count']} 个图谱 POI，但实验六没有提供该景区的有序路线。"
                                   "以下仅是地点候选，不能断言游览先后：" +
                                   "、".join(p["name"] for p in pois["pois"][:8]) + "。"))
            trace.append({"phase": "generate", "status": "partial", "source": "query_pois"})
            return result
        route = routes["routes"][0]
        selected = choose_stops(route["steps"], constraints)
        if llm:
            system = ("你是路线规划器。只允许从提供的路线步骤选择visit_id，保持原顺序、保留标注的入口出口，不新增景点，不超过max_selected_stops。"
                      "仅输出 JSON 对象：{\"selected_visit_ids\":[\"...\"],\"note\":\"...\"}。"
                      "不要假定票价、开放时间、交通距离或具体耗时。")
            proposal = llm.ask_json(system, json.dumps({
                "query": query, "constraints": constraints, "route": route,
                "max_selected_stops": len(selected),
                "default_selected_visit_ids": [p["visit_id"] for p in selected]}, ensure_ascii=False))
            chosen = proposal.get("selected_visit_ids", proposal.get("selected_poi_ids"))
            default_max = len(selected)
            validated, violation = validate_proposal(proposal, route["steps"], default_max)
            if violation:
                result["warnings"].append("LLM 方案未通过图谱/容量约束校验，已改用图谱内保守方案：" + violation)
                result["plan_source"] = "graph_fallback_after_llm_validation"
                trace.append({"phase": "llm_plan", "model": llm.model,
                              "proposed_count": len(chosen) if isinstance(chosen, list) else None,
                              "proposal": proposal,
                              "validation": "rejected", "reason": violation,
                              "fallback": "graph_ordered_subset"})
            else:
                selected = validated
                result["plan_source"] = "llm_validated"
                trace.append({"phase": "llm_plan", "model": llm.model,
                              "selected_visit_ids": [s["visit_id"] for s in selected], "validation": "graph_ids_order_endpoints_and_budget_pass"})
        result.update(status="ok", selected_route={"id": route["id"], "kind": route["kind"],
                      "document_id": route["document_id"], "provenance_kind": route["provenance_kind"]}, itinerary=selected,
                      source_route_steps=route["steps"],
                      unselected_source_steps=[s for s in route["steps"] if s["visit_id"] not in {p["visit_id"] for p in selected}])
        result["warnings"].append("重点站点之间未选中的原路线步骤仍保留为参考，不代表两站直接连通；入口出口为来源标注，当前通行情况仍需核验。")
        names = " → ".join(x["poi"] for x in selected)
        label = "官方路线事实" if route["kind"] == "official_route_facts" else "游客路线/模拟数据"
        matched = result["advice_used"]
        advice_text = ("；".join(f"[{a['source_label']}] 条件「{a['condition']}」下建议「{a['advice']}」"
                              for a in matched[:3])) if matched else "没有精确命中的人群/情境建议"
        result["message"] = (f"{scenic}（{constraints['visitor']}）建议参考{label}的重点站点：{names}。"
                             f"条件建议：{advice_text}。路线来自 {route['document_id']}；"
                             "站点取舍为规划策略，保留来源标注的入口出口；未选站点及完整来源次序见结构化记录，不能视为直接通行或实测时间表。")
        trace.append({"phase": "generate", "status": "ok", "route_id": route["id"],
                      "selected_poi_ids": [x["id"] for x in selected],
                      "advice_ids": [a["advice_id"] for a in matched]})
        return result
    except (LLMError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        result.update(status="model_error" if isinstance(exc, LLMError) else "error",
                      message=str(exc))
        trace.append({"phase": "failure", "status": result["status"], "message": str(exc)})
        return result
