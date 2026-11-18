"""V5 post-processing ablations on strictly OOF margins, ID-aligned across sklearn versions."""
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import softmax
from sklearn.metrics import balanced_accuracy_score
from baseline import load_training_data
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"outputs/trials_v5_postprocess"
OUT.mkdir(parents=True,exist_ok=True)
df=load_training_data(ROOT/"data/raw/train.csv")
labels=np.array(sorted(df.model.unique()))
ys=df.model.to_numpy()
def load(folder):
    ids=[]; scores=[]; typo=[]; foldidx=[]
    for i in range(1,6):
        z=np.load(ROOT/f"outputs/{folder}/fold_{i}_scores.npz",allow_pickle=True)
        assert np.array_equal(z["classes"],labels)
        ids.extend(z["id"].astype(str))
        scores.append(z["scores"])
        typo.append(z["typo_scores"])
        foldidx.extend([i]*len(z["id"]))
    assert len(set(ids))==len(df)
    indexes={val:i for i,val in enumerate(ids)}
    order=np.array([indexes[v] for v in df.id.astype(str)])
    return np.vstack(scores)[order],np.vstack(typo)[order],np.asarray(foldidx)[order]
v4,t4,f4=load("trials_v4_combined_typo")
v5,t5,f5=load("trials_v5_largepool")
assert np.array_equal(t4,t5) or np.max(np.abs(t4-t5))<1e-4

def prior(scores,temp=.6,strength=.5):
    bias=np.zeros(scores.shape[1],float)
    for _ in range(30):
        probs=softmax(scores/temp+bias,axis=1)
        bias+=.5*(np.log(1/scores.shape[1])-np.log(probs.mean(axis=0)))
    return scores+strength*temp*bias

rows=[]
for m in (0,.15,.3,.5,.75,1.):
  for typ in (0,.03,.05,.08):
    for prior_w in (0,.5,1.):
        scores=(1-m)*v5+m*v4+typ*t5
        predictions=np.empty(len(df),dtype=object)
        for f in range(1,6):
            ix=np.flatnonzero(f5==f)
            s=scores[ix]
            if prior_w:
                s=prior(s,temp=.6,strength=prior_w)
            predictions[ix]=labels[s.argmax(axis=1)]
        allba=balanced_accuracy_score(ys,predictions)
        per=[balanced_accuracy_score(ys[f5==f],predictions[f5==f]) for f in range(1,6)]
        rows.append(dict(mix_v4=m,typo=typ,prior=prior_w,oof=allba,
                         **{f"fold{f+1}":p for f,p in enumerate(per)}))
r=pd.DataFrame(rows)
r.to_csv(OUT/"grid.csv",index=False)
print(r.sort_values('oof',ascending=False).head(20).round(5).to_string(index=False),flush=True)
print("base V4",balanced_accuracy_score(ys,labels[(v4+.05*t4).argmax(axis=1)]))
print("base V5",balanced_accuracy_score(ys,labels[(v5+.03*t5).argmax(axis=1)]))
