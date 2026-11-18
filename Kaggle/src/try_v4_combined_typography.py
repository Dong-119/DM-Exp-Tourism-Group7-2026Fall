"""V4 candidate: restricted external data + train-fold-only typography correction.

The source subset is prepared locally by scripts/build_v4_pool.py.
Produces exact OOF margins, predictions and per-fold Balanced Accuracy.
"""
from __future__ import annotations
import hashlib
import json
import time
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix,hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC
from sklearn.metrics import balanced_accuracy_score,recall_score
from baseline import load_training_data,prompt_disjoint_folds
from iterate_v2 import style_matrix
from try_v4_typography import log_likelihood

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"outputs/trials_v4_combined_typo"
OUT.mkdir(parents=True,exist_ok=True)
EXTERNAL_WEIGHT=.1
TYPO_WEIGHTS=(0.,.03,.05,.08,.1,.15)

def evaluate():
    df=load_training_data(ROOT/"data/raw/train.csv")
    ext_path=ROOT/"outputs/external_data/combined_restricted_v4/external_training.csv"
    ext=pd.read_csv(ext_path)
    assert set(["model","text","source","provenance"])<=set(ext.columns)
    assert len(ext)==8450, "Unexpected curated pool version"
    assert not ext.text.isna().any() and ext.model.isin(df.model.unique()).all()
    labels=np.asarray(sorted(df.model.unique()))
    y=df.model.to_numpy()
    extra_texts=ext.text.tolist()
    oof={w:np.full(len(df),None,dtype=object) for w in TYPO_WEIGHTS}
    folds=[]
    start=time.monotonic()
    for fold,tr,va in prompt_disjoint_folds(df):
        xtr=df.iloc[tr].text.tolist()
        xva=df.iloc[va].text.tolist()
        merged=xtr+extra_texts
        ymerged=np.concatenate([y[tr],ext.model.to_numpy()])
        char=TfidfVectorizer(analyzer="char",ngram_range=(3,5),min_df=2,
                             max_features=100000,sublinear_tf=True,dtype=np.float32)
        word=TfidfVectorizer(analyzer="word",ngram_range=(1,2),min_df=2,
                             max_features=80000,sublinear_tf=True,dtype=np.float32)
        ct,cv=char.fit_transform(merged),char.transform(xva)
        wt,wv=word.fit_transform(merged),word.transform(xva)
        style_train=style_matrix(merged)
        scaler=StandardScaler().fit(style_train)
        st=csr_matrix(np.clip(scaler.transform(style_train),-4,4))
        sv=csr_matrix(np.clip(scaler.transform(style_matrix(xva)),-4,4))
        feat=hstack([ct,wt,st*.08],format="csr")
        val_feat=hstack([cv,wv,sv*.08],format="csr")
        weights=np.concatenate([
            np.ones(len(tr),dtype=np.float32),
            np.full(len(ext),EXTERNAL_WEIGHT,dtype=np.float32)
        ])
        model=LinearSVC(C=1,max_iter=4000)
        model.fit(feat,ymerged,sample_weight=weights)
        assert np.array_equal(model.classes_,labels)
        scores=model.decision_function(val_feat)
        text_scores=log_likelihood(xtr,y[tr],xva,labels,alpha=2)
        np.savez_compressed(OUT/f"fold_{fold}_scores.npz",
                            id=df.iloc[va].id.to_numpy(),scores=scores,
                            typo_scores=text_scores,classes=labels)
        diag={"fold":fold}
        for w in TYPO_WEIGHTS:
            p=labels[(scores+w*text_scores).argmax(axis=1)]
            oof[w][va]=p
            ba=balanced_accuracy_score(y[va],p)
            diag[str(w)]=float(ba)
        folds.append(diag)
        print(f"FOLD {fold} "+ " ".join(f"typow={w} BA={diag[str(w)]:.5f}" for w in TYPO_WEIGHTS),flush=True)
    result={str(w):float(balanced_accuracy_score(y,p)) for w,p in oof.items()}
    rec={str(w):dict(zip(labels,recall_score(y,p,labels=labels,average=None,zero_division=0).tolist())) for w,p in oof.items()}
    record={
      "experiment":"v4_restricted_external_plus_typography",
      "external_csv_sha256":hashlib.sha256(ext_path.read_bytes()).hexdigest(),
      "official_train_sha256":hashlib.sha256((ROOT/"data/raw/train.csv").read_bytes()).hexdigest(),
      "external_n":len(ext),"external_sample_weight":EXTERNAL_WEIGHT,
      "typography_weights":TYPO_WEIGHTS,"oof":result,
      "per_class_recall":rec,"folds":folds,
      "elapsed_seconds":time.monotonic()-start,
      "v2_reference":0.358553
    }
    (OUT/"metrics.json").write_text(json.dumps(record,indent=2,ensure_ascii=False),encoding="utf-8")
    for w,p in oof.items():
        pd.DataFrame({"id":df.id,"true":y,"prediction":p}).to_csv(
          OUT/f"oof_typo_{w}.csv",index=False
        )
    print("TOTAL",result,flush=True)

if __name__=="__main__":
    evaluate()
