"""可重跑的图谱结构、工具 Schema 和 Agent 编排单元测试。"""
import json
import tempfile
import unittest
from pathlib import Path

from agent import GRAPH, ROOT, agent_run, parse_constraints_rule, parse_constraints_llm, validate_proposal
from graph_tools import TourismGraph


class GraphAndAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = TourismGraph(GRAPH)

    def test_source_graph_counts(self):
        self.assertEqual(len(self.g.nodes), 462)
        self.assertEqual(len(self.g.edges), 654)
        manifest = json.loads((ROOT / 'data/run_manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(self.g.graph_hash,
                         manifest['graph_sha256'])

    def test_tool_schema_errors(self):
        self.assertEqual(self.g.call_tool("not_a_tool", {"scenic": "故宫"})["status"], "error")
        self.assertEqual(self.g.call_tool("query_routes", {"scenic": "故宫", "unknown": 1})["status"], "error")
        self.assertEqual(self.g.call_tool("query_routes", {"scenic": "故宫", "limit": True})["status"], "error")
        self.assertEqual(self.g.call_tool("query_routes", {"scenic": "未知景区"})["status"], "error")

    def test_route_genuine_order(self):
        d = self.g.call_tool("query_routes", {"scenic": "故宫"})
        self.assertEqual(d["status"], "ok")
        self.assertEqual(d["routes"][0]["kind"], "official_route_facts")
        self.assertEqual(d["routes"][0]["document_id"], "GG_F01")
        self.assertEqual(d["routes"][0]["steps"][0]["poi"], "午门")
        seq = [x["order"] for x in d["routes"][0]["steps"]]
        self.assertEqual(seq, sorted(seq))

    def test_no_invented_routes(self):
        self.assertEqual(self.g.query_routes("天坛")["status"], "empty")
        self.assertEqual(self.g.query_routes("颐和园")["status"], "empty")

    def test_only_poi_contains(self):
        for edge in self.g.edges:
            if edge["relation"] == "contains":
                self.assertEqual(self.g.nodes[edge["target"]]["kind"], "poi")

    def test_advice_has_provenance(self):
        d = self.g.query_advice("故宫", visitor="亲子")
        self.assertGreater(d["count"], 0)
        self.assertTrue(all(x["source_document"] and x["condition_id"] and x["advice_id"]
                            for x in d["advice"]))
        self.assertTrue(all(x['provenance_kind'] != 'unknown' for x in d['advice']))
        self.assertEqual(self.g.query_advice("故宫", visitor="未特定")["status"], "empty")

    def test_agent_grounding(self):
        d = agent_run("带孩子去故宫一天", mode="demo")
        self.assertEqual(d["status"], "ok")
        self.assertFalse(d["llm_used"])
        self.assertTrue(d["tool_results"]["query_routes"]["routes"])
        self.assertEqual(d["selected_route"]["kind"], "official_route_facts")
        self.assertTrue(all(x["id"] in self.g.nodes for x in d["itinerary"]))

    def test_unsupported_and_conflicting(self):
        self.assertEqual(agent_run("圆明园一天", mode="demo")["status"], "no_match")
        self.assertEqual(agent_run("老人玩一天", mode="demo")["status"], "needs_clarification")
        self.assertEqual(agent_run("故宫一天又两天", mode="demo")["status"], "conflict")

    def test_llm_overbudget_falls_back(self):
        from unittest.mock import patch
        all_ids = [x["id"] for x in self.g.query_routes("故宫")["routes"][0]["steps"]]

        class FakeModel:
            model = "fake-local-test"
            def ask_json(self, system, user):
                if "意图解析器" in system:
                    return {"scenic": "故宫", "visitor": "亲子", "days": 1, "hours": None}
                return {"selected_poi_ids": all_ids, "note": ""}

        with patch("agent.ChatLLM", return_value=FakeModel()):
            rec = agent_run("带孩子去故宫一天", mode="api")
        self.assertEqual(rec["status"], "ok")
        self.assertTrue(rec["llm_used"])
        self.assertEqual(rec["plan_source"], "graph_fallback_after_llm_validation")
        self.assertEqual(len(rec["itinerary"]), 8)
        self.assertEqual(rec["trace"][-2]["validation"], "rejected")

    def test_llm_valid_subset_accepted(self):
        from unittest.mock import patch
        steps = self.g.query_routes("故宫")["routes"][0]["steps"]
        ids = [steps[0]['id'], steps[1]['id'], steps[-1]['id']]

        class FakeModel:
            model = "fake-local-test"
            def ask_json(self, system, user):
                if "意图解析器" in system:
                    return {"scenic": "故宫", "visitor": "亲子", "days": 1, "hours": None}
                return {"selected_poi_ids": ids, "note": ""}

        with patch("agent.ChatLLM", return_value=FakeModel()):
            rec = agent_run("带孩子去故宫一天", mode="api")
        self.assertEqual(rec["status"], "ok")
        self.assertEqual(rec["plan_source"], "llm_validated")
        self.assertEqual([s["id"] for s in rec["itinerary"]], ids)

    def test_repeated_route_events_are_distinct(self):
        route = next(r for r in self.g.query_routes('故宫')['routes'] if r['document_id'] == 'GG_T01')
        self.assertEqual([s['order'] for s in route['steps']], list(range(1, 14)))
        self.assertEqual(len({s['visit_id'] for s in route['steps']}), 13)
        self.assertEqual(sum(s['poi'] == '神武门' for s in route['steps']), 2)

    def test_mixed_known_unknown_scenics_are_not_ignored(self):
        rec = agent_run('去故宫和圆明园玩一天')
        self.assertEqual(rec['status'], 'conflict')
        self.assertEqual(rec['constraints']['unsupported_scenic_matches'], ['圆明园'])
        self.assertFalse(any(t['phase'] == 'action_observation' for t in rec['trace']))

    def test_day_and_hours_can_describe_same_trip(self):
        rec = agent_run('故宫一天，共8小时')
        self.assertEqual(rec['status'], 'ok')
        self.assertEqual((rec['constraints']['days'], rec['constraints']['hours']), (1, 8))

    def test_multidigit_duration_is_preserved_and_rejected(self):
        for question, field, expected in [('故宫13小时', 'hours', 13), ('故宫10天', 'days', 10), ('故宫十三小时', 'hours', 13)]:
            with self.subTest(question=question):
                rec = agent_run(question)
                self.assertEqual(rec['status'], 'needs_clarification')
                self.assertEqual(rec['constraints'][field], expected)

    def test_negated_visitor_and_scenic(self):
        self.assertEqual(agent_run('不带孩子，独自去故宫一天')['constraints']['visitor'], '未特定')
        rec = agent_run('不去故宫，去天坛一天')
        self.assertEqual(rec['status'], 'partial')
        self.assertEqual(rec['constraints']['scenic'], '天坛')

    def test_entry_exit_and_full_reference_are_preserved(self):
        rec = agent_run('带孩子去故宫一天')
        self.assertEqual(rec['itinerary'][0]['step_type'], 'entry')
        self.assertEqual(rec['itinerary'][-1]['step_type'], 'exit')
        self.assertEqual(rec['itinerary'][-1]['poi'], '神武门')
        self.assertEqual(len(rec['source_route_steps']), 12)
        self.assertEqual(len(rec['unselected_source_steps']), 4)

    def test_proposal_requires_endpoints_and_order(self):
        steps = self.g.query_routes('故宫')['routes'][0]['steps']
        for ids, text in [([steps[0]['visit_id']], '入口或出口'), ([steps[-1]['visit_id'], steps[0]['visit_id']], '顺序'), (['invented'], '图谱之外')]:
            selected, reason = validate_proposal({'selected_visit_ids': ids}, steps, 8)
            self.assertIsNone(selected)
            self.assertIn(text, reason)

    def test_repeated_poi_requires_visit_ids(self):
        steps = next(r['steps'] for r in self.g.query_routes('故宫')['routes'] if r['document_id'] == 'GG_T01')
        _, reason = validate_proposal({'selected_poi_ids': ['poi:故宫:神武门']}, steps, 8)
        self.assertIn('visit_id', reason)

    def test_pending_compound_advice_is_not_applied(self):
        rec = agent_run('带孩子去故宫一天')
        pending = {a['advice_id'] for a in rec['advice_pending_confirmation']}
        self.assertIn('advice:M035', pending)
        self.assertNotIn('advice:M035', {a['advice_id'] for a in rec['advice_used']})

    def test_cross_scenic_mentions_are_not_membership_facts(self):
        result = self.g.query_pois('天坛', 30)
        self.assertIn('故宫', result['excluded_other_scenics'])
        self.assertNotIn('故宫', [p['name'] for p in result['pois']])
        self.assertTrue(all(p['membership'] == 'text_mention_only' for p in result['pois']))

    def test_llm_cannot_invent_explicit_constraints(self):
        class Model:
            def ask_json(self, system, user):
                return {'scenic': '故宫', 'visitor': '亲子', 'days': 2, 'hours': None}
        rule = parse_constraints_rule('不带孩子去故宫一天', list(self.g.scenics))
        result = parse_constraints_llm('不带孩子去故宫一天', rule, Model())
        self.assertEqual(result['visitor'], '未特定')
        self.assertEqual(result['days'], 1)
        self.assertFalse(result['llm_agrees_with_explicit_constraints'])

    def test_bad_graph_is_observable(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.json"
            p.write_text("{}", encoding="utf-8")
            d = agent_run("故宫一天", graph_path=p)
            self.assertEqual(d["status"], "error")
            self.assertEqual(d["trace"][0]["phase"], "init")

    def test_api_missing_config_is_explicit(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {"TOURISM_LLM_BASE_URL": "", "TOURISM_LLM_MODEL": ""}):
            d = agent_run("故宫一天", mode="api")
        self.assertEqual(d["status"], "model_error")
        self.assertFalse(d["llm_used"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
