"""V3 matching and unsupervised grouping tests."""
import sys
import unittest
from pathlib import Path
import numpy as np
from sklearn.metrics import adjusted_rand_score
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from try_v3_joint import predict_joint
from try_v3_greedy import group_greedy_cosine

class V3Tests(unittest.TestCase):
    def test_hungarian_enforces_unique_labels_in_complete_group(self):
        rng=np.random.default_rng(2026)
        margins=rng.normal(size=(18,18))
        groups=np.zeros(18,dtype=int)
        labels=np.array([f"model_{i}" for i in range(18)])
        _, assigned, n=predict_joint(margins,groups,labels)
        self.assertEqual(n,1)
        self.assertEqual(len(set(assigned)),18)
        self.assertTrue(set(assigned)==set(labels))
    def test_partial_group_keeps_independent_pred(self):
        labels=np.array([f"model_{i}" for i in range(18)])
        margins=np.zeros((3,18))
        margins[:,0]=1
        ind,joint,n=predict_joint(margins,np.zeros(3,dtype=int),labels)
        self.assertEqual(n,0)
        np.testing.assert_array_equal(ind,joint)
    def test_recover_prompt_without_labels(self):
        texts=[]
        expected=[]
        for g in range(3):
            token=["astronaut cosmonaut orbit spaceflight","pomegranate orchard plum currant",
                   "volcano magma eruption lava"][g]
            for i in range(18):
                texts.append(f"The {token} is a specific fascinating theme. "
                             f"This topic explores {token}. Example version {i}.")
                expected.append(g)
        got=group_greedy_cosine(texts)
        self.assertAlmostEqual(adjusted_rand_score(expected,got),1.0)

if __name__=="__main__":
    unittest.main()
