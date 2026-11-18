"""Recover groups with size constraint, without using prompt labels."""
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import adjusted_rand_score
from sklearn.metrics.pairwise import cosine_similarity

from baseline import load_training_data, prompt_disjoint_folds

ROOT=Path(__file__).resolve().parents[1]

def group_greedy_cosine(texts:list[str], group_size:int=18):
    v=TfidfVectorizer(analyzer="word",ngram_range=(1,2),stop_words="english",
                      min_df=1,max_features=50000,sublinear_tf=True)
    x=v.fit_transform(texts)
    sim=cosine_similarity(x)
    n=len(texts)
    ii,jj=np.triu_indices(n,k=1)
    order=np.argsort(-sim[ii,jj],kind="stable")
    parent=list(range(n))
    sizes=[1]*n
    num_groups=n
    def root(x):
        while parent[x]!=x:
            parent[x]=parent[parent[x]]
            x=parent[x]
        return x
    for pos in order:
        i,j=int(ii[pos]),int(jj[pos])
        ri,rj=root(i),root(j)
        if ri==rj:continue
        if sizes[ri]+sizes[rj]>group_size:continue
        if sizes[ri]<sizes[rj]:ri,rj=rj,ri
        parent[rj]=ri
        sizes[ri]+=sizes[rj]
        num_groups-=1
        if num_groups==int(np.ceil(n/group_size)):
            break
    roots=[root(i) for i in range(n)]
    _, groups=np.unique(roots,return_inverse=True)
    return groups

def main():
    df=load_training_data(ROOT/"data/raw/train.csv")
    for fold,_,val in prompt_disjoint_folds(df):
        subset=df.iloc[val].reset_index(drop=True)
        p=group_greedy_cosine(subset.text.tolist())
        t=subset.prompt_id.to_numpy()
        ari=adjusted_rand_score(t,p)
        sz=pd.Series(p).value_counts()
        from collections import Counter
        purity=sum(Counter(t[p==g]).most_common(1)[0][1] for g in np.unique(p))/len(t)
        print(f"FOLD {fold}: greedy group ARI {ari:.6f} purity {purity:.6f}; "
              f"size range {sz.min()}-{sz.max()}",flush=True)

if __name__=="__main__":
    main()
