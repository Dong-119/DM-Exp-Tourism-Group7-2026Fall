"""V3 joint attribution: unsupervised prompt recovery + Hungarian assignment."""
from __future__ import annotations
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from scipy.sparse import csr_matrix, hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import balanced_accuracy_score, adjusted_rand_score, recall_score
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC
from baseline import load_training_data, prompt_disjoint_folds
from iterate_v2 import style_matrix
from try_v3_greedy import group_greedy_cosine

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"outputs"/"V3_prompt_joint"

def predict_joint(margins,groups,model_names,min_group_size=16):
    """Allocate distinct model labels within near-complete prompt groups."""
    if len(margins)!=len(groups) or margins.shape[1]!=len(model_names):
        raise ValueError("Mismatched model/group dimensions")
    independent=np.asarray(model_names)[margins.argmax(axis=1)]
    matched=independent.copy()
    applied=0
    for cluster in np.unique(groups):
        rows=np.flatnonzero(groups==cluster)
        if len(rows)<min_group_size or len(rows)>len(model_names):
            continue
        ridx,cidx=linear_sum_assignment(-margins[rows])
        matched[rows[ridx]]=model_names[cidx]
        applied+=1
    return independent,matched,applied

def train_v2_margins(xtr,xva,ytr):
    """Exactly the frozen V2 best: char+word+style LinearSVC."""
    char=TfidfVectorizer(analyzer="char",ngram_range=(3,5),min_df=2,
                         max_features=100000,sublinear_tf=True,dtype=np.float32)
    word=TfidfVectorizer(analyzer="word",ngram_range=(1,2),min_df=2,
                         max_features=80000,sublinear_tf=True,dtype=np.float32)
    ct,cv=char.fit_transform(xtr),char.transform(xva)
    wt,wv=word.fit_transform(xtr),word.transform(xva)
    scale=StandardScaler()
    st=csr_matrix(np.clip(scale.fit_transform(style_matrix(xtr)),-4,4))
    sv=csr_matrix(np.clip(scale.transform(style_matrix(xva)),-4,4))
    model=LinearSVC(C=1.0,max_iter=4000)
    model.fit(hstack([ct,wt,st*0.08],format="csr"),ytr)
    return model.decision_function(hstack([cv,wv,sv*0.08],format="csr")),model.classes_

def run():
    OUT.mkdir(parents=True,exist_ok=True)
    src=ROOT/"data/raw/train.csv"
    df=load_training_data(src)
    labels=np.asarray(sorted(df.model.unique()))
    texts=df.text.tolist()
    y=df.model.to_numpy()
    independent_oof=np.full(len(df),None,dtype=object)
    joint_oof=np.full(len(df),None,dtype=object)
    fold_records=[]
    started=time.monotonic()
    for fold,tr,va in prompt_disjoint_folds(df):
        print(f"FOLD {fold} train V2 margins",flush=True)
        xtr=[texts[i] for i in tr]
        xva=[texts[i] for i in va]
        scores,classes=train_v2_margins(xtr,xva,y[tr])
        assert np.array_equal(classes,labels)
        inferred=group_greedy_cosine(xva,group_size=18)
        ari=float(adjusted_rand_score(df.iloc[va].prompt_id,inferred))
        baseline,joint,applied=predict_joint(scores,inferred,classes)
        independent_oof[va]=baseline
        joint_oof[va]=joint
        before=float(balanced_accuracy_score(y[va],baseline))
        after=float(balanced_accuracy_score(y[va],joint))
        fold_records.append({
            "fold":fold,"samples":len(va),"prompts":int(df.iloc[va].prompt_id.nunique()),
            "independent_ba":round(before,6),"joint_ba":round(after,6),
            "improvement":round(after-before,6),
            "group_ari_diagnostic_only":round(ari,6),"clusters_assigned":applied
        })
        print(f"FOLD {fold} V2={before:.6f} JOINT={after:.6f} "
              f"gain={after-before:+.6f} ARI={ari:.3f}",flush=True)
        np.savez_compressed(OUT/f"fold_{fold}_margins.npz",
            id=df.iloc[va].id.to_numpy(),margins=scores,
            classes=classes,inferred_groups=inferred)
    assert not any(p is None for p in joint_oof)
    base_score=float(balanced_accuracy_score(y,independent_oof))
    joint_score=float(balanced_accuracy_score(y,joint_oof))
    print(f"FULL OOF independent={base_score:.6f} JOINT={joint_score:.6f}",flush=True)
    pd.DataFrame({"id":df.id,"prompt_id":df.prompt_id,"model":y,
       "v2_independent":independent_oof,"v3_joint":joint_oof}).to_csv(
       OUT/"oof_predictions.csv",index=False,encoding="utf-8")
    rec1=recall_score(y,independent_oof,labels=labels,average=None,zero_division=0)
    rec2=recall_score(y,joint_oof,labels=labels,average=None,zero_division=0)
    pd.DataFrame({"label":labels,"v2_recall":rec1,
      "v3_joint_recall":rec2,"recall_gain":rec2-rec1}).to_csv(
      OUT/"per_class_recall.csv",index=False,encoding="utf-8")
    meta={
      "experiment":"V3_prompt_joint",
      "date_utc":datetime.now(timezone.utc).isoformat(),
      "train_sha256":hashlib.sha256(src.read_bytes()).hexdigest(),
      "protocol":"Frozen 5fold GroupKFold prompt_id. V2 decision scores. "
                 "Validation groups inferred from validation text only, "
                 "max group size=18; Hungarian for groups of size 16..18.",
      "v2_independent_oof_ba":round(base_score,6),
      "joint_oof_ba":round(joint_score,6),
      "gain_vs_v2":round(joint_score-base_score,6),
      "folds":fold_records,
      "elapsed_seconds":round(time.monotonic()-started,2),
      "status":"TRIAL pending promotion review"
    }
    (OUT/"metrics.json").write_text(json.dumps(meta,indent=2,ensure_ascii=False),encoding="utf-8")
    lines=[
      "# V3 — 无监督 Prompt 分组 + 组内联合模型分配",
      "",
      "1. 继续使用冻结的 V2 五折模型，在每折验证文本上计算18类 SVM margins。",
      "2. 仅使用每个验证折的无标签文本计算 TF-IDF 相似度，并以最大18条约束聚类。",
      "3. 每个聚类有16–18条文本时用 Hungarian 算法做一对一标签分配，其余独立预测。",
      "4. 真正的 prompt_id 只用于划分训练验证集和事后聚类质量审计，不参与预测。",
      "",
      "| Fold | V2 独立 BA | V3 联合 BA | 提升 | 分组 ARI |",
      "|---|---:|---:|---:|---:|",
    ]
    for row in fold_records:
        lines.append(
          f"| {row['fold']} | {row['independent_ba']:.4f} | {row['joint_ba']:.4f} | "
          f"{row['improvement']:+.4f} | {row['group_ari_diagnostic_only']:.3f} |")
    lines += [
      "",
      f"V2 OOF：{base_score:.6f}",
      f"V3 联合 OOF：{joint_score:.6f}，提升 {joint_score-base_score:+.6f}",
      "",
      "注意：隐藏测试集未必遵守每 Prompt 18 个不同模型的训练集结构。本方法"
      "依赖对测试文本做 transductive 无监督聚类，线上收益尚未核实。",
      "分类器的 TF-IDF 和风格标准化仅在训练折拟合，聚类仅利用无标签验证文本。",
      "尚未正式提交 Kaggle；无公榜/私榜成绩。",
      "",
      f"数据 SHA256：{meta['train_sha256']}",
    ]
    (OUT/"summary.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    return meta

if __name__=="__main__":
    run()
