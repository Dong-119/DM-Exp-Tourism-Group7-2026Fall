"""固定场景回归：离线模式验证真实图谱证据链；不冒充 LLM 模型测试。"""
import hashlib
import json
from pathlib import Path

from agent import ROOT, GRAPH, agent_run

SCENARIOS = [
    {"id": "S01", "type": "亲子+一天", "query": "我带孩子去故宫玩一天，怎么规划？", "expect": "ok", "tools": ["query_routes", "query_advice"]},
    {"id": "S02", "type": "老人+半天", "query": "带老人去故宫游玩半天，希望轻松一点", "expect": "ok", "tools": ["query_routes", "query_advice"]},
    {"id": "S03", "type": "情侣+两天", "query": "情侣去故宫两天，有什么合适的路线？", "expect": "ok", "tools": ["query_routes", "query_advice"]},
    {"id": "S04", "type": "不同景区无有序路线", "query": "亲子去颐和园玩一天如何安排？", "expect": "partial", "tools": ["query_routes", "query_advice", "query_pois"]},
    {"id": "S05", "type": "未收录景区", "query": "明天想去圆明园玩一天", "expect": "no_match", "tools": []},
    {"id": "S06", "type": "缺少景区", "query": "带孩子玩一天，帮我规划", "expect": "needs_clarification", "tools": []},
    {"id": "S07", "type": "时长冲突", "query": "故宫我既要安排一天又要安排两天，怎么做？", "expect": "conflict", "tools": []},
    {"id": "S08", "type": "跨景区冲突", "query": "一天玩故宫和天坛怎么规划？", "expect": "conflict", "tools": []},
    {"id": "S09", "type": "无该景区路线", "query": "带老人游天坛一天", "expect": "partial", "tools": ["query_routes", "query_advice", "query_pois"]},
    {"id": "S10", "type": "已知与未知景区混合", "query": "去故宫和圆明园玩一天", "expect": "conflict", "tools": []},
    {"id": "S11", "type": "一天与小时补充描述", "query": "带孩子去故宫一天，共8小时", "expect": "ok", "tools": ["query_routes", "query_advice"], "constraints": {"days": 1, "hours": 8}},
    {"id": "S12", "type": "多位小时超出支持范围", "query": "故宫玩13小时", "expect": "needs_clarification", "tools": [], "constraints": {"hours": 13}},
    {"id": "S13", "type": "多位天数超出支持范围", "query": "故宫玩10天", "expect": "needs_clarification", "tools": [], "constraints": {"days": 10}},
    {"id": "S14", "type": "否定亲子需求", "query": "不带孩子，独自去故宫一天", "expect": "ok", "tools": ["query_routes", "query_advice"], "constraints": {"visitor": "未特定"}},
    {"id": "S15", "type": "排除一个景区", "query": "不去故宫，去天坛一天", "expect": "partial", "tools": ["query_routes", "query_advice", "query_pois"], "constraints": {"scenic": "天坛"}},
    {"id": "S16", "type": "同时带老人和孩子", "query": "带老人和孩子去故宫半天", "expect": "ok", "tools": ["query_routes", "query_advice"], "constraints": {"visitor": "亲子、老人"}},
    {"id": "S17", "type": "中文多位小时", "query": "故宫玩十三小时", "expect": "needs_clarification", "tools": [], "constraints": {"hours": 13}},
]


def check_result(rec, item):
    observed = [x["tool"] for x in rec["trace"] if x.get("phase") == "action_observation"]
    ok = rec["status"] == item["expect"] and observed == item["tools"]
    ok = ok and all(rec['constraints'].get(k) == v for k, v in item.get('constraints', {}).items())
    if rec["status"] == "ok":
        routes = rec["tool_results"]["query_routes"]["routes"]
        original = {x["visit_id"]: x["order"] for x in routes[0]["steps"]}
        selected = rec["itinerary"]
        ok = ok and bool(selected) and all(x["visit_id"] in original for x in selected)
        ok = ok and [original[x["visit_id"]] for x in selected] == sorted(original[x["visit_id"]] for x in selected)
        ok = ok and selected[0]['step_type'] == 'entry' and selected[-1]['step_type'] == 'exit'
        ok = ok and all(a['condition_evaluation'] == 'matched' for a in rec['advice_used'])
        ok = ok and rec["selected_route"]["document_id"] == routes[0]["document_id"]
    if rec["status"] == "partial":
        ok = ok and not rec["itinerary"] and rec["selected_route"] is None
    return ok, observed


def main():
    dest = ROOT / "results"
    dest.mkdir(exist_ok=True)
    verdicts = []
    for item in SCENARIOS:
        rec = agent_run(item["query"], mode="demo")
        valid, called = check_result(rec, item)
        path = dest / f"{item['id']}_trace.json"
        path.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        verdicts.append({"id": item["id"], "category": item["type"], "input": item["query"],
                         "expected_status": item["expect"], "actual_status": rec["status"],
                         "expected_tools": item["tools"], "actual_tools": called,
                         "selected_pois": [x["poi"] for x in rec.get("itinerary", [])],
                         "matched_advice_count": len(rec.get("advice_used", [])),
                         "result_file": path.name, "pass": bool(valid), "answer": rec["message"]})
        print(item["id"], item["type"], rec["status"], "PASS" if valid else "FAIL")
    summary = {"experiment": 7, "execution_mode": "demo_offline_NO_LLM", 
               "graph_sha256": hashlib.sha256(GRAPH.read_bytes()).hexdigest(),
               "scenario_count": len(verdicts), "passed": sum(v["pass"] for v in verdicts),
               "scenarios": verdicts}
    (dest / "scenario_evaluation.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if summary["passed"] != summary["scenario_count"]:
        raise SystemExit("场景验证未通过")
    print(f"全部通过 {summary['passed']}/{summary['scenario_count']}; 具体轨迹见 results/")


if __name__ == "__main__":
    main()
