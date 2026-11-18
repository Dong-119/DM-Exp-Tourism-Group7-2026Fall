"""V4 sparse-prompt matching: text-only pair recovery + conservative Hungarian.

Diagnostic experiment over fixed V2 OOF margins. No test/hidden labels used.
The two-passage-per-prompt scenario is synthetically sampled from the 18-wide
training prompts and used as a stress test, not as ground-truth test structure.
"""
from __future__ import annotations
from pathlib import Path
from collections import defaultdict
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.metrics import balanced_accuracy_score
from baseline import load_training_data,prompt_disjoint_folds
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"outputs/trials_v4_sparse_matching"
OUT.mkdir(parents=True,exist_ok=True)

def propose_pairs(texts,cutoff=0.1,mutual=False,min_gap=0.0):
    tfidf=TfidfVectorizer(analyzer="word",ngram_range=(1,2),stop_words="english",sublinear_tf=True)
    X=tfidf.fit_transform(texts)
    S=cosine_similarity(X)
    np.fill_diagonal(S,-1.0)
    rank=np.argsort(-S,axis=1)
    top=rank[:,0]
    second=np.maximum(0.0,S[np.arange(len(texts)),rank[:,1]])
    ii,jj=np.triu_indices(len(texts),1)
    valid=S[ii,jj]>=cutoff
    if mutual:
        valid &= (top[ii]==jj)&(top[jj]==ii)
    if min_gap:
        valid &= ((S[ii,jj]-second[ii]>=min_gap)&(S[ii,jj]-second[jj]>=min_gap))
    possible=np.flatnonzero(valid)
    possible=possible[np.argsort(-S[ii[possible],jj[possible]],kind="stable")]
    consumed=np.zeros(len(texts),dtype=bool)
    pairs=[]
    for pos in possible:
        i,j=int(ii[pos]),int(jj[pos])
        if consumed[i] or consumed[j]:
            continue
        pairs.append((i,j))
        consumed[i]=True
        consumed[j]=True
    return pairs

def pair_assignment(scores,labels,pairs,penalty_limit=None):
    pred=labels[np.argmax(scores,axis=1)].copy()
    nchanged=0
    for i,j in pairs:
        m=scores[[i,j]]
        r,c=linear_sum_assignment(-m)
        new=labels[c]
        old=pred[[i,j]]
        loss=m.max(axis=1).sum()-m[r,c].sum()
        if penalty_limit is not None and loss>penalty_limit:
            continue
        pred[[i,j]]=new
        nchanged+=int(np.sum(old!=new))
    return pred,nchanged

def main():
    df=load_training_data(ROOT/"data/raw/train.csv")
    labels=np.array(sorted(df.model.unique()))
    rows=[]
    for trial in range(5):
      rng=np.random.default_rng(2026+trial)
      for fold,_,valid in prompt_disjoint_folds(df):
        val=df.iloc[valid].reset_index(drop=True)
        cache=np.load(ROOT/f"outputs/V3_prompt_joint/fold_{fold}_margins.npz",allow_pickle=True)
        assert np.array_equal(val.id.to_numpy(),cache["id"])
        keep=[]
        for _,g in val.groupby("prompt_id"):
            # Each prompt is represented by exactly two unseen-model passages.
            keep.extend(rng.choice(g.index,size=2,replace=False))
        keep=np.asarray(sorted(keep))
        subset=val.iloc[keep].reset_index(drop=True)
        scores=cache["margins"][keep]
        truth=subset.model.to_numpy()
        independent=labels[scores.argmax(axis=1)]
        bas=balanced_accuracy_score(truth,independent)
        # ORACLE for analysis only: never used for a real prediction.
        prompt_ids=subset.prompt_id.to_numpy()
        oracle=[tuple(np.flatnonzero(prompt_ids==p)) for p in np.unique(prompt_ids)]
        pred_oracle,_=pair_assignment(scores,labels,oracle)
        oracle_ba=balanced_accuracy_score(truth,pred_oracle)
        for cutoff in (0.05,0.1,0.15,0.20,0.25):
          for mutual in (False,True):
            pairs=propose_pairs(subset.text.tolist(),cutoff=cutoff,mutual=mutual)
            correct=sum(prompt_ids[i]==prompt_ids[j] for i,j in pairs)
            for penalty in (None,0.03,0.1,0.3):
                pred,changed=pair_assignment(scores,labels,pairs,penalty)
                score=balanced_accuracy_score(truth,pred)
                rows.append({
                  "trial":trial,"fold":fold,"cutoff":cutoff,
                  "mutual":mutual,"penalty_limit":-1.0 if penalty is None else penalty,
                  "n_pairs":len(pairs),"n_correct_pairs":correct,
                  "pair_precision":correct/max(len(pairs),1),
                  "base_ba":bas,"oracle_ba":oracle_ba,"joint_ba":score,
                  "changed_labels":changed
                })
        print(f"trial {trial} fold {fold}: base={bas:.4f}, oracle={oracle_ba:.4f}",flush=True)
    all=pd.DataFrame(rows)
    all.to_csv(OUT/"all_trials.csv",index=False)
    summ=all.groupby(["cutoff","mutual","penalty_limit"]).agg(
      mean_baseline=("base_ba","mean"),
      mean_oracle=("oracle_ba","mean"),
      mean_joint=("joint_ba","mean"),
      pair_precision=("pair_precision","mean"),
      mean_pairs=("n_pairs","mean"),
      n_change=("changed_labels","mean")
    ).reset_index()
    summ.to_csv(OUT/"summary.csv",index=False)
    print("TOP:",flush=True)
    print(summ.sort_values("mean_joint",ascending=False).head(12).round(4).to_string(index=False),flush=True)
    print("BASE",all.base_ba.mean(),"ORACLE",all.oracle_ba.mean(),flush=True)

if __name__=="__main__":
    main()
