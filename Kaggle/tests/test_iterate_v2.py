"""V2 feature engineering smoke tests, no Kaggle data required."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from iterate_v2 import style_vector, style_matrix


class StyleFeatureTests(unittest.TestCase):
    def test_vector_deterministic_and_finite(self):
        sentence = "However, the model says: not just words—it's a style.\n\nReally?"
        a = style_vector(sentence)
        b = style_vector(sentence)
        self.assertEqual(a.shape, b.shape)
        self.assertGreater(len(a), 50)
        self.assertEqual(a.dtype, np.float32)
        np.testing.assert_array_equal(a, b)
        self.assertTrue(np.isfinite(a).all())

    def test_edge_cases(self):
        for text in ["", "123", "——", "a", "\n\n", "中文标点。"]:
            a = style_vector(text)
            self.assertTrue(np.isfinite(a).all(), text)
        self.assertEqual(style_matrix(["a", "b"]).shape[0], 2)


if __name__ == "__main__":
    unittest.main()
