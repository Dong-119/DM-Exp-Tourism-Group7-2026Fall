"""V4 typography calibration: train-fold-only per-class mark likelihoods.

Uses precomputed frozen V2 OOF margins. Marker statistics are estimated only
from each fold's training samples; no validation labels used to build rules.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score
from baseline import load_training_data,prompt_disjoint_folds

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"outputs/trials_v4_typography"
OUT.mkdir(parents=True,exist_ok=True)
MARKS=["—","–","’","‘","“","”","…","•","  ","\n","**","##",";",":","?","!"]
WEIGHTS=(0,.02,.05,.1,.15,.25)

def fingerprint(texts):
    return np.asarray([[float(m in text) for m in MARKS] for text in texts],dtype=np.float64)

def log_likelihood(xtr,ytr,xva,labels,alpha=2):
    binary_tr=fingerprint(xtr)
    binary_va=fingerprint(xva)
    global_p=(binary_tr.sum(axis=0)+alpha)/(len(xtr)+2*alpha)
    out=np.zeros((len(xva),len(labels)),dtype=np.float64)
    for col,lab in enumerate(labels):
        subset=binary_tr[ytr==lab]
        prob=(subset.sum(axis=0)+alpha)/(len(subset)+2*alpha)
        log_p=np.log(prob/global_p)
        log_not=np.log((1-prob)/(1-global_p))
        out[:,col]=(binary_va@log_p)+((1-binary_va)@log_not)
    return out

def main():
    df=load_training_data(ROOT/"data/raw/train.csv")
    labels=np.array(sorted(df.model.unique()))
    y=df.model.to_numpy()
    preds={w:np.full(len(df),None,dtype=object) for w in WEIGHTS}
    folds=[]
    for fold,tr,va in prompt_disjoint_folds(df):
        cache=np.load(ROOT/f"outputs/V3_prompt_joint/fold_{fold}_margins.npz",allow_pickle=True)
        assert np.array_equal(cache["id"],df.iloc[va].id.to_numpy())
        base=cache["margins"]
        extra=log_likelihood(df.iloc[tr].text.tolist(),y[tr],df.iloc[va].text.tolist(),labels)
        info={"fold":fold}
        for weight in WEIGHTS:
            p=labels[np.argmax(base+weight*extra,axis=1)]
            preds[weight][va]=p
            info[f"w_{weight}"]=balanced_accuracy_score(y[va],p)
        folds.append(info)
        print("fold",fold,info,flush=True)
    results={str(w):float(balanced_accuracy_score(y,p)) for w,p in preds.items()}
    print("OOF",results,flush=True)
    (OUT/"metrics.json").write_text(json.dumps({
      "marks":MARKS,"weights":WEIGHTS,"folds":folds,"oof_scores":results,
      "v2_reference":0.358553,"protocol":"5-fold prompt-disjoint, fold-train-only typography probability estimates"
    },indent=2,ensure_ascii=False),encoding="utf-8")
    for w,p in preds.items():
        pd.DataFrame({"id":df.id,"true":y,"pred":p}).to_csv(
            OUT/f"oof_mark_weight_{w}.csv",index=False
        )

if __name__=="__main__":
    main()
