"""Notebook V6 pair inference tests, no Kaggle dataset or network required."""
import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

ROOT=Path(__file__).resolve().parents[1]
NOTEBOOK=ROOT/"notebooks/V6_sparse_pair_kaggle.ipynb"

def infer_block():
    doc=json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    source="".join(doc["cells"][-1]["source"])
    begin=source.index("pred=labels[np.argmax(raw,axis=1)]")
    end=source.index("submission=pd.DataFrame",begin)
    return compile(source[begin:end],"<V6 inference block>","exec")

class PairAttributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiled=infer_block()
        cls.labels=np.array([f"model{i}" for i in range(18)])

    def apply(self,texts,scores):
        scope={
            "test":pd.DataFrame({"text":texts}),
            "raw":scores,
            "np":np,
            "labels":self.labels,
            "TfidfVectorizer":TfidfVectorizer,
        }
        exec(self.compiled,scope)
        return scope["pred"]

    def test_small_input_is_independent_fallback(self):
        scores=np.zeros((3,18),dtype=float)
        scores[:,0]=1.
        p=self.apply(["one","two","three"],scores)
        np.testing.assert_array_equal(p,np.repeat(self.labels[0],3))

    def test_conservative_pairs_enforce_distinct_labels(self):
        texts=[]
        for i in range(18):
            unique=f"topic{i} rareword{i}"
            paragraph=f"The {unique} has a distinct mechanism and characteristic description."
            texts.extend([paragraph,paragraph])
        score=np.full((36,18),-1.,dtype=float)
        score[:,0]=1.
        score[:,1]=.95
        pred=self.apply(texts,score)
        self.assertEqual(len(pred),36)
        for i in range(0,len(pred),2):
            self.assertNotEqual(pred[i],pred[i+1])
            self.assertTrue(set(pred[i:i+2])==set(self.labels[:2]))

if __name__=="__main__":
    unittest.main()
