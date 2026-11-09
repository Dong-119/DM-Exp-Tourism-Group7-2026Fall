"""检查结构化语料、原句位置、建议证据与关键条件逻辑。"""

import csv
import hashlib
import json
import unittest
from collections import Counter
from pathlib import Path

from corpus_io import load_corpus
from extract_rules import deduplicate, extract_candidates
from experiment import candidate_key


BASE = Path(__file__).resolve().parent


def read(name):
    return json.loads((BASE / name).read_text(encoding="utf-8-sig"))


def sentence(text):
    return {
        "doc_id": "TEST",
        "sentence_id": "TEST_S001",
        "paragraph_index": 1,
        "text": text,
    }


class ExperimentChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.input_rows = read("data/clean_documents.json")
        cls.corpus = read("results/分句语料.json")
        cls.docs, cls.regenerated_sentences, cls.summary = load_corpus(
            BASE / "data/clean_documents.json"
        )
        cls.expected_documents = {doc["doc_id"]: doc for doc in cls.docs}
        cls.documents = {
            doc["doc_id"]: doc for doc in cls.corpus["documents"]
        }
        cls.sentences = cls.corpus["sentences"]
        cls.sentences_by_id = {
            (row["doc_id"], row["sentence_id"]): row for row in cls.sentences
        }
        cls.main = read("results/条件建议映射表.json")
        cls.outside = read("results/范围外建议.json")
        cls.candidates = read("results/规则候选.json")
        cls.stats = read("results/统计结果.json")

    def test_clean_content_text_hash_and_source_identity(self):
        self.assertEqual((len(self.input_rows), len(self.docs), len(self.sentences)),
                         (48, 48, 1406))
        self.assertEqual(self.corpus["summary"], self.summary)
        self.assertEqual(self.stats["input"], self.summary)
        self.assertEqual(set(self.documents), set(self.expected_documents))
        self.assertEqual(sum(self.summary["by_provenance"].values()), 48)

        for row in self.input_rows:
            doc_id = row["doc_id"]
            with self.subTest(doc_id=doc_id):
                output = self.documents[doc_id]
                expected = self.expected_documents[doc_id]
                text = row["clean_content"]
                digest = hashlib.sha256(text.encode("utf-8")).hexdigest()

                self.assertEqual(output["clean_text"], text)
                self.assertEqual(row["clean_sha256"], digest)
                self.assertEqual(output["clean_sha256"], digest)
                self.assertEqual(row["clean_char_count"], len(text))
                self.assertEqual(output["provenance_kind"], row["provenance_kind"])
                self.assertEqual(output["provenance_kind"], expected["provenance_kind"])
                self.assertEqual(output["original_record_id"], row.get("source_record_id"))
                self.assertEqual(
                    output["duplicate_doc_ids"],
                    [item for item in row.get("merged_record_ids", []) if item != doc_id],
                )
                self.assertEqual(
                    output["source_paths"],
                    [item["input_path"] for item in row["source_records"]],
                )
                for field in (
                    "source_group_id",
                    "source_scenic",
                    "source_type",
                    "source_path",
                    "source_urls",
                    "original_record_id",
                    "duplicate_doc_ids",
                ):
                    self.assertEqual(output[field], expected[field], field)

    def test_sentence_positions_and_candidate_source_text(self):
        self.assertEqual(self.sentences, self.regenerated_sentences)
        self.assertEqual(len(self.sentences_by_id), len(self.sentences))

        for row in self.sentences:
            with self.subTest(sentence_id=row["sentence_id"]):
                source = self.documents[row["doc_id"]]
                self.assertGreaterEqual(row["start"], 0)
                self.assertLess(row["start"], row["end"])
                self.assertLessEqual(row["end"], len(source["clean_text"]))
                self.assertEqual(
                    source["clean_text"][row["start"]:row["end"]], row["text"]
                )
                self.assertEqual(row["scenic"], source["source_scenic"])
                self.assertEqual(row["source_type"], source["source_type"])

        self.assertEqual(len(self.candidates), 90)
        for row in self.candidates:
            with self.subTest(candidate_id=row["candidate_id"]):
                self.assertEqual(row["candidate_id"], candidate_key(row))
                source_ids = row.get("context_sentence_ids") or [row["sentence_id"]]
                source_rows = [
                    self.sentences_by_id[(row["doc_id"], sentence_id)]
                    for sentence_id in source_ids
                ]
                self.assertIn(row["sentence_id"], source_ids)
                for field in ("condition_text", "advice_text"):
                    self.assertTrue(
                        any(row[field] in source["text"] for source in source_rows),
                        f"{field}未出现在候选对应原句中：{row[field]}",
                    )

    def test_suggestions_and_evidence_slice_from_original_text(self):
        for row in self.main + self.outside:
            with self.subTest(mapping_id=row.get("mapping_id")):
                source = self.documents[row["doc_id"]]
                self.assertEqual(row["source_scenic"], source["source_scenic"])
                self.assertEqual(row["source_type"], source["source_type"])
                self.assertEqual(row["provenance_kind"], source["provenance_kind"])
                self.assertEqual(row["source_group_id"], source["source_group_id"])
                self.assertEqual(row["source_path"], source["source_path"])
                self.assertEqual(row["duplicate_doc_ids"], source["duplicate_doc_ids"])

                evidence_spans = []
                for evidence in row["evidence"]:
                    evidence_doc = self.documents[evidence["doc_id"]]
                    evidence_key = (evidence["doc_id"], evidence["sentence_id"])
                    sentence_row = self.sentences_by_id[evidence_key]
                    self.assertEqual(evidence["doc_id"], row["doc_id"])
                    self.assertEqual(
                        evidence_doc["clean_text"][evidence["start"]:evidence["end"]],
                        evidence["quote"],
                    )
                    self.assertEqual(evidence["start"], sentence_row["start"])
                    self.assertEqual(evidence["end"], sentence_row["end"])
                    self.assertEqual(evidence["quote"], sentence_row["text"])
                    evidence_spans.append(
                        (evidence["doc_id"], evidence["start"], evidence["end"])
                    )

                for field in ("condition_text", "advice_text"):
                    span = row["spans"][field]
                    self.assertEqual(span["doc_id"], row["doc_id"])
                    self.assertGreaterEqual(span["start"], 0)
                    self.assertLess(span["start"], span["end"])
                    self.assertLessEqual(span["end"], len(source["clean_text"]))
                    self.assertEqual(
                        source["clean_text"][span["start"]:span["end"]], row[field]
                    )
                    self.assertTrue(
                        any(doc_id == span["doc_id"] and start <= span["start"]
                            and end >= span["end"]
                            for doc_id, start, end in evidence_spans),
                        f"{field}位置未被原文证据覆盖：{row.get('mapping_id')}",
                    )

    def test_result_counts_classifications_and_csv(self):
        self.assertEqual((len(self.main), len(self.outside)), (95, 10))
        self.assertEqual(self.stats["main_after_dedup"], len(self.main))
        self.assertEqual(self.stats["outside_scope"], len(self.outside))
        self.assertEqual(self.stats["rule_candidates"], len(self.candidates))
        self.assertEqual(
            self.stats["candidate_counts"],
            {"accept": 64, "correct": 9, "exclude": 17},
        )
        self.assertEqual(
            (self.stats["additional_source_pairs"], self.stats["contextual_pairs"]),
            (26, 6),
        )
        for key, field in (
            ("by_condition_type", "condition_type"),
            ("by_target_scope", "target_scope"),
            ("by_provenance", "provenance_kind"),
        ):
            self.assertEqual(
                {name: value for name, value in self.stats[key].items() if value},
                dict(Counter(row[field] for row in self.main)),
            )
        for key, value in self.stats["by_visitor_type"].items():
            self.assertEqual(value, sum(key in row["visitor_types"] for row in self.main))
        with (BASE / "results/条件建议映射表.csv").open(
            encoding="utf-8-sig", newline=""
        ) as file:
            self.assertEqual(len(list(csv.DictReader(file))), len(self.main))

    def test_corrections_and_additional_pairs_match_candidates(self):
        extracted = extract_candidates(self.sentences)
        self.assertEqual(len(extracted), 90)
        candidate_ids = {candidate_key(row) for row in extracted}
        check = read("data/人工校验.json")
        self.assertTrue(set(check["candidate_adjustments"]) <= candidate_ids)
        self.assertEqual(
            Counter(row["action"] for row in check["candidate_adjustments"].values()),
            {"exclude": 17, "correct": 9},
        )
        self.assertEqual(len(check["additional_pairs"]), 32)

    def test_chinese_and_english_comma_use_same_real_boundary(self):
        actual = next(
            (
                row for row in self.sentences
                if row["doc_id"] == "TT_T03"
                and "时间充足的话，在里边散步拍照，相信" in row["text"]
            ),
            None,
        )
        self.assertIsNotNone(actual, "未找到语料中的真实逗号边界样例")

        def profile_pairs(source):
            return [
                (row["condition_text"], row["advice_text"])
                for row in extract_candidates([source])
                if row["rule_id"] == "R_VISITOR_PROFILE"
            ]

        chinese_pairs = profile_pairs(actual)
        self.assertEqual(chinese_pairs, [("时间充足的话", "在里边散步拍照")])

        english = dict(actual)
        english["text"] = actual["text"].replace(
            "时间充足的话，", "时间充足的话,", 1
        ).replace("，相信", ",相信", 1)
        self.assertNotEqual(english["text"], actual["text"])
        self.assertEqual(profile_pairs(english), chinese_pairs)

    def test_necessary_unless_and_negative_examples(self):
        necessary = extract_candidates(
            [sentence("只有体力允许并且相关区域开放，才加入下午支线。")]
        )
        self.assertEqual(necessary[0]["condition_operator"], "necessary")
        self.assertIn("并且", necessary[0]["condition_text"])
        unless = extract_candidates(
            [sentence("除非天气与开放情况得到确认，否则不承诺乘船、登高或进入特定院落。")]
        )
        self.assertEqual(unless[0]["condition_operator"], "unless")
        self.assertIn("不承诺", unless[0]["advice_text"])
        self.assertFalse(
            extract_candidates([sentence("如果我上次早点出门就好了，但这只是在回顾遗憾。")])
        )
        self.assertFalse(extract_candidates([sentence("建议先看导览图。")]))

    def test_dedup_preserves_negation_and_numbers(self):
        def record(advice):
            return {
                "doc_id": "TEST",
                "condition_text": "时间充足",
                "advice_text": advice,
                "target_scope": "故宫",
                "condition_type": "时间安排",
                "visitor_types": ["未特定"],
                "condition_operator": "all",
                "provenance_kind": "dataset_corpus",
                "evidence": [{"doc_id": "TEST", "sentence_id": "TEST_S001"}],
            }

        merged, _ = deduplicate(
            [record("建议提前预约门票"), record("提前预约门票")]
        )
        self.assertEqual(len(merged), 1)
        protected = [
            record("建议休息20分钟"),
            record("建议休息30分钟"),
            record("不建议休息20分钟"),
        ]
        self.assertEqual(len(deduplicate(protected)[0]), 3)

    def test_rule_comparison(self):
        data = read("results/规则对照结果.json")
        self.assertEqual((data["positive_cases"], data["negative_cases"]), (21, 9))
        old, new = data["methods"]["基础规则"], data["methods"]["改进规则"]
        self.assertEqual(
            (old["positive_relation_hits"], old["exact_pair_matches"],
             old["negative_false_positives"]),
            (15, 15, 3),
        )
        self.assertEqual(
            (new["positive_relation_hits"], new["exact_pair_matches"],
             new["negative_false_positives"]),
            (18, 18, 0),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
