"""V4 typography-calibration unit tests, no competition data required."""
import sys
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from try_v4_typography import fingerprint,log_likelihood,MARKS

class TypographyTests(unittest.TestCase):
    def test_fixed_feature_shape_and_finite_likelihood(self):
        train=["Write a brief answer. Do it now!","This is a response with — punctuation.",
               "No symbol? Try again.","Another answer with “quotes” and : clauses"]
        labels=np.array(["a","b","a","b"])
        val=["a test —", "a test?", "", "plain paragraph."]
        self.assertEqual(fingerprint(train).shape,(len(train),len(MARKS)))
        likelihood=log_likelihood(train,labels,val,np.array(["a","b"]))
        self.assertEqual(likelihood.shape,(len(val),2))
        self.assertTrue(np.isfinite(likelihood).all())

    def test_repeatability(self):
        train=["abc—","xyz?","one.","two…"]
        labels=np.array(["a","b","a","b"])
        a=log_likelihood(train,labels,["—","normal"],np.array(["a","b"]))
        b=log_likelihood(train,labels,["—","normal"],np.array(["a","b"]))
        np.testing.assert_array_equal(a,b)

if __name__=="__main__":
    unittest.main()
