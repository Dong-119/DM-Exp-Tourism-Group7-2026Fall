"""命令行交互入口：python cli.py --mode demo --question '带孩子去故宫玩一天'。"""
import argparse
import json
from pathlib import Path

from agent import GRAPH, agent_run


def main():
    parser = argparse.ArgumentParser(description="实验七：知识图谱旅游规划 Agent")
    parser.add_argument("--question", help="自然语言旅游请求")
    parser.add_argument("--interactive", action="store_true", help="持续交互，输入 quit 退出")
    parser.add_argument("--mode", choices=("demo", "api"), default="demo",
                        help="demo=无需模型的可复现规则演示；api=真正调用配置的 LLM")
    parser.add_argument("--graph", type=Path, default=GRAPH)
    parser.add_argument("--output", type=Path, help="保存 JSON 轨迹，含工具输入/输出与证据")
    args = parser.parse_args()
    if not args.question and not args.interactive:
        parser.error("请设置 --question 或 --interactive")
    questions = [args.question] if args.question else []
    if args.interactive:
        print(f"已进入 {args.mode} 模式，输入 quit 退出。")
        while True:
            q = input("旅游需求> ").strip()
            if q.lower() in ("quit", "exit", "q"):
                break
            if q:
                questions.append(q)
                record = agent_run(q, mode=args.mode, graph_path=args.graph)
                print(f"[{record['status']}] {record['message']}")
                for warning in record.get("warnings", []):
                    print("提示：", warning)
                if record.get("source_route_steps"):
                    print("原路线顺序参考：", " → ".join(s['poi'] for s in record['source_route_steps']))
                print("工具：", "、".join(t["tool"] for t in record["trace"] if t["phase"] == "action_observation") or "未调用")
        return
    record = agent_run(questions[0], mode=args.mode, graph_path=args.graph)
    print(f"[{record['status']}] {record['message']}")
    for warning in record.get("warnings", []):
        print("提示：", warning)
    if record.get("source_route_steps"):
        print("原路线顺序参考：", " → ".join(s['poi'] for s in record['source_route_steps']))
    print("工具：", "、".join(t["tool"] for t in record["trace"] if t["phase"] == "action_observation") or "未调用")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("轨迹：", args.output)
    if record["status"] not in ("ok", "partial", "needs_clarification", "conflict", "no_match"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
