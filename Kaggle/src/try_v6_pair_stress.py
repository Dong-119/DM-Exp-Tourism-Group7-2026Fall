"""Sparse group matching stress test for V5 scores.

Label/prompt_id are used only for evaluation and subsampling, never matching.
Candidate V6 must be robust to one/two texts per prompt.
"""
from pathlib import Path
import warnings
import numpy as np,pandas as pd
from sklearn.metrics import balanced_accuracy_score
from scipy.special import softmax
from baseline import load_training_data
from try_v5_sparse_matching import propose_pairs,pair_assignment
warnings.filterwarnings("ignore",message="y_pred contains classes not in y_true")
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"outputs/trials_v6_pair_sparse"
OUT.mkdir(parents=True,exist_ok=True)
D=load_training_data(ROOT/"data/raw/train.csv")
NAMES=np.asarray(sorted(D.model.unique()))
ids=[];scores=[];folds=[]
for f in range(1,6):
    z=np.load(ROOT/f"outputs/trials_v5_largepool/fold_{f}_scores.npz",allow_pickle=True)
    ids.extend(z["id"].astype(str))
    scores.append(z["scores"]+.03*z["typo_scores"])
    folds.extend([f]*len(z["id"]))
loc={k:i for i,k in enumerate(ids)}
values=np.vstack(scores)[[loc[k] for k in D.id.astype(str)]]
folds=np.asarray(folds)[[loc[k] for k in D.id.astype(str)]]

def adjust(s):
    if len(s)<200:return s
    bias=np.zeros(len(NAMES))
    for _ in range(30):
        p=softmax(s/.6+bias,axis=1)
        bias+=.5*(np.log(1/len(NAMES))-np.log(np.maximum(p.mean(axis=0),1e-12)))
    return s+.3*bias

records=[]
for rep in range(3):
    for fold in range(1,6):
        val=D.loc[folds==fold].reset_index(drop=True)
        m=values[folds==fold]
        rng=np.random.default_rng(2026+rep*100+fold)
        for scenario in ('single','two','mixed','full'):
            if scenario=='full': sel=np.arange(len(val))
            else:
                wanted={'single':(1,1),'two':(2,2),'mixed':(1,5)}[scenario]
                picks=[]
                for _,group in val.groupby('prompt_id'):
                    n=int(rng.integers(wanted[0],wanted[1]+1))
                    picks.extend(rng.choice(group.index,n,replace=False))
                sel=np.array(sorted(picks))
            x=val.iloc[sel].reset_index(drop=True)
            s=adjust(m[sel])
            original=NAMES[s.argmax(axis=1)]
            b=balanced_accuracy_score(x.model,original)
            for cutoff in (.05,.1,.15,.2):
                pairs=propose_pairs(x.text.tolist(),cutoff=cutoff,mutual=True)
                precision=sum(x.prompt_id[i]==x.prompt_id[j] for i,j in pairs)/max(1,len(pairs))
                for penalty in (None,.1,.3):
                    pred,changes=pair_assignment(s,NAMES,pairs,penalty)
                    score=balanced_accuracy_score(x.model,pred)
                    records.append(dict(rep=rep,fold=fold,scenario=scenario,cutoff=cutoff,
                                        penalty=-1 if penalty is None else penalty,
                                        base=b,after=score,delta=score-b,
                                        n_pairs=len(pairs),precision=precision,changes=changes))
            print(f"rep={rep} fold={fold} scenario={scenario} base={b:.4f}",flush=True)
all=pd.DataFrame(records)
all.to_csv(OUT/"all.csv",index=False)
result=all.groupby(["scenario","cutoff","penalty"]).agg(
    base=("base","mean"),after=("after","mean"),delta=("delta","mean"),
    precision=("precision","mean"),pairs=("n_pairs","mean")
).reset_index()
result.to_csv(OUT/"summary.csv",index=False)
for scenario in result.scenario.unique():
    print(scenario,flush=True)
    print(result[result.scenario==scenario].sort_values("delta",ascending=False).head(6).round(4).to_string(index=False),flush=True)
