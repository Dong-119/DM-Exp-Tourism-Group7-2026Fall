import unittest

from tourism_mining.config import DEFAULT_EXPERIMENT3_INPUT
from tourism_mining.adapters.route_files import load_documents
from tourism_mining.domain.routes import (
    canonical_name,
    canonical_site_name,
    compare_routes,
    hierarchy,
    lcs_length,
    make_step,
    parse_annotated_travelogue,
    parse_numbered_timed_route,
    parse_official_chain,
)


class RouteMiningTests(unittest.TestCase):
    def test_arrow_chain_preserves_parenthetical_exhibit_and_unknown_time(self):
        document = {
            "doc_id": "official",
            "scenic_name": "故宫",
            "provenance_kind": "official_route_facts",
            "title": "官方路线事实",
            "reference_url": "https://example.test/route",
            "clean_content": (
                "推荐行进顺序：午门-太和门-弘义阁(皇朝礼乐展)-太和殿\n"
                "时间未知，不应补造。"
            ),
        }
        route = parse_official_chain(document)
        self.assertEqual(
            [step["poi"] for step in route["steps"]],
            ["午门", "太和门", "弘义阁", "太和殿"],
        )
        self.assertEqual(route["steps"][2]["activity"], "皇朝礼乐展")
        self.assertEqual(route["time_hierarchy"]["unknown"], route["steps"])
        self.assertTrue(all(step["time_source"] == "not_stated" for step in route["steps"]))
        self.assertEqual(route["steps"][0]["step_type"], "entry")
        self.assertEqual(route["steps"][-1]["step_type"], "exit")

    def test_arrow_separator_chain_is_supported(self):
        document = {
            "doc_id": "official-arrow",
            "scenic_name": "故宫",
            "provenance_kind": "official_route_facts",
            "title": "箭头路线",
            "reference_url": None,
            "clean_content": "推荐行进顺序：午门 → 太和殿 → 神武门",
        }
        route = parse_official_chain(document)
        self.assertEqual([step["poi"] for step in route["steps"]], ["午门", "太和殿", "神武门"])

    def test_time_sections_and_numbered_steps(self):
        document = {
            "doc_id": "timed",
            "scenic_name": "故宫",
            "provenance_kind": "synthetic_teaching",
            "title": "分时路线",
            "reference_url": None,
            "clean_content": (
                "上午：先参观。\n"
                "1. 09:00—09:20，午门：入院与导览。\n"
                "中午：暂停。\n"
                "2. 12:00—13:00，休息点：用餐。"
            ),
        }
        route = parse_numbered_timed_route(document)
        self.assertEqual([step["time_slot"] for step in route["steps"]], ["morning", "noon"])
        self.assertEqual([step["time_start"] for step in route["steps"]], ["09:00", "12:00"])
        self.assertEqual(route["steps"][1]["poi"], "休息点")
        self.assertEqual(route["steps"][1]["poi_kind"], "descriptive_location")
        self.assertEqual(route["steps"][-1]["step_type"], "exit")
        for step in route["steps"]:
            span = step["source_span"]
            self.assertEqual(document["clean_content"][span["start"]:span["end"]], step["source_quote"])

    def test_traveler_annotations_are_evidence_anchored_and_normalized(self):
        content = (
            "从午门走进故宫。一路欣赏着，来到了太和殿前。"
            "我们游览了干清宫的雄壮气势。紧接着，我们来到了故宫珍宝馆。"
            "从故宫南门进，从北面的神武门出了。"
        )
        document = {
            "doc_id": "GG_T05",
            "scenic_name": "故宫",
            "provenance_kind": "dataset_corpus",
            "title": "游览记录",
            "original_article_url": None,
            "clean_content": content,
        }
        route = parse_annotated_travelogue(document)
        self.assertEqual([step["poi"] for step in route["steps"]], ["午门", "太和殿", "乾清宫", "珍宝馆", "神武门"])
        for step in route["steps"]:
            span = step["source_span"]
            self.assertEqual(content[span["start"]:span["end"]], step["source_quote"])

    def test_processed_travelogue_produces_explicit_time_hierarchy(self):
        documents = load_documents(DEFAULT_EXPERIMENT3_INPUT)
        route = parse_annotated_travelogue(documents["GG_T01"])
        self.assertEqual(len(route["time_hierarchy"]["morning"]), 9)
        self.assertEqual(len(route["time_hierarchy"]["afternoon"]), 4)
        self.assertEqual(len(route["time_hierarchy"]["unknown"]), 0)
        self.assertTrue(all(step["time_start"] is None for step in route["steps"]))

    def test_comparison_metrics_use_shared_points_and_order(self):
        official = {
            "route_id": "official",
            "scenic_name": "故宫",
            "steps": [make_step(i, name, source_quote=name) for i, name in enumerate(
                ["午门", "太和殿", "乾清宫", "御花园", "神武门"], start=1
            )],
        }
        traveler = {
            "route_id": "traveler",
            "steps": [make_step(i, name, source_quote=name) for i, name in enumerate(
                ["午门", "太和殿", "乾清宫", "珍宝馆", "神武门"], start=1
            )],
        }
        result = compare_routes(official, traveler)
        self.assertEqual(result["shared_poi_count"], 4)
        self.assertEqual(result["official_route_coverage"], 0.8)
        self.assertEqual(result["traveler_route_alignment"], 0.8)
        self.assertEqual(result["shared_order_consistency"], 1.0)
        self.assertEqual(result["traveler_only_pois"], ["珍宝馆"])

    def test_comparison_metrics_deduplicate_repeated_stops(self):
        official = {
            "route_id": "official",
            "scenic_name": "故宫",
            "steps": [make_step(i, name, source_quote=name) for i, name in enumerate(
                ["午门", "御花园", "午门"], start=1
            )],
        }
        traveler = {
            "route_id": "traveler",
            "steps": [make_step(i, name, source_quote=name) for i, name in enumerate(
                ["午门", "御花园"], start=1
            )],
        }
        result = compare_routes(official, traveler)
        self.assertEqual(result["official_route_step_count"], 3)
        self.assertEqual(result["official_route_distinct_poi_count"], 2)
        self.assertEqual(result["shared_poi_count"], 2)
        self.assertEqual(result["official_route_coverage"], 1.0)

    def test_parent_and_child_are_not_normalized_to_same_place(self):
        self.assertEqual(canonical_name("紫禁城"), "紫禁城")
        self.assertEqual(canonical_site_name("紫禁城"), "故宫")
        self.assertNotEqual(canonical_name("宁寿宫区"), canonical_name("珍宝馆"))
        self.assertEqual(lcs_length(["a", "b", "c"], ["b", "a", "c"]), 2)


if __name__ == "__main__":
    unittest.main()
