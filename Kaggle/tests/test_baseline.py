"""Small offline checks; do not require competition data."""
import sys
import unittest
from pathlib import Path

import pandas as pd
from sklearn.pipeline import Pipeline

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from baseline import build_model, prompt_disjoint_folds


class BaselineTests(unittest.TestCase):
    def test_grouped_cv_has_no_prompt_overlap(self):
        rows = [
            {"prompt_id": f"prompt_{g:02d}", "text": f"example {g}_{k}", "model": "test"}
            for g in range(10) for k in range(3)
        ]
        frame = pd.DataFrame(rows)
        seen = set()
        for fold, train_idx, val_idx in prompt_disjoint_folds(frame):
            self.assertEqual(fold, len(seen) // 6 + 1)
            tr = set(frame.iloc[train_idx]["prompt_id"])
            val = set(frame.iloc[val_idx]["prompt_id"])
            self.assertFalse(tr & val)
            self.assertFalse(seen & set(val_idx))
            seen.update(val_idx)
        self.assertEqual(seen, set(range(len(frame))))

    def test_model_names_are_supported(self):
        self.assertIsInstance(build_model("word_lr"), Pipeline)
        self.assertIsInstance(build_model("char_svc"), Pipeline)
        with self.assertRaises(ValueError):
            build_model("unknown")


if __name__ == "__main__":
    unittest.main()
