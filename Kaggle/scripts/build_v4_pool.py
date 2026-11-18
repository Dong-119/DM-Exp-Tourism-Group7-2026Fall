"""Build a reproducible, provenance-filtered, offline external training subset.

The source 'in-style pool' is CC BY-SA 4.0. No Kaggle Benchmarks Proxy
sources, no reconstructed host train prompts, no questionable Gemini3.7 from
the union pool. prvsiyan's separately verified 'new' API rows are permitted.
"""
from __future__ import annotations
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"outputs/deps_pyarrow"))
import pandas as pd
import numpy as np

GOOD_SOURCES=(
    "willrice/name-that-llm-openrouter-harvest",
    "seyitkaangunes/ntl-extra-api-passages",
    "michaelsemenoff/ntl-own-extra-v1",
    "zbigniewkirchner/ntl-extra-gpt-passages",
    "prvsiyan/ntl-own-prompt-generations-v1",
)
ROUTES=("anthropic","openai","google","openrouter")
POOL_CAP_PER_MODEL=300
SEED=20261118

def norm(text):
    return re.sub(r"\s+"," ",str(text).strip().lower())

def construct():
    raw=ROOT/"data/raw/train.csv"
    in_style=ROOT/"outputs/external_data/in_style/pool_v1.parquet"
    source=ROOT/"outputs/external_data/prvsiyan/passages_clean.csv"
    out=ROOT/"outputs/external_data/combined_restricted_v4"
    out.mkdir(parents=True,exist_ok=True)
    official=pd.read_csv(raw)
    pool=pd.read_parquet(in_style)
    a=pool.loc[pool.source.isin(GOOD_SOURCES)].copy()
    # No Gemini3.7 from the mixed public pool; version identity is not fully verified.
    a=a.loc[a.model.ne("gemini-3.7-flash")]
    blocks=[]
    for model,g in a.groupby("model",sort=True):
        blocks.append(g.sample(n=min(POOL_CAP_PER_MODEL,len(g)),random_state=SEED))
    selected_pool=pd.concat(blocks,ignore_index=True)
    ext=pd.read_csv(source)
    selected_extra=ext.loc[
        ext["split"].eq("new") &
        ext["provider_route"].isin(ROUTES),
        ["prompt_id","model","text","provider_route"]
    ].copy()
    selected_pool=selected_pool[["prompt_id","model","text","source"]].copy()
    selected_pool["provenance"]="public_in_style_pool_v1"
    selected_extra["source"]="prvsiyan/prvsiyans-extended-name-that-llm-dataset"
    selected_extra["provenance"]="prvsiyan_new_nonproxy"
    selected_extra=selected_extra[["prompt_id","model","text","source","provenance"]]
    union=pd.concat([selected_pool,selected_extra],ignore_index=True)
    union=union.dropna(subset=["model","text"])
    union=union.loc[union.model.isin(official.model.unique())].copy()
    union["normalized"]=union.text.map(norm)
    official_norm=set(official.text.map(norm))
    assert not union.normalized.isin(official_norm).any(), "External overlaps official text"
    before=len(union)
    union=union.drop_duplicates(subset=["model","normalized"],keep="first").reset_index(drop=True)
    dup=before-len(union)
    assert not union.empty
    output=union[["prompt_id","model","text","source","provenance"]].copy()
    out_path=out/"external_training.csv"
    output.to_csv(out_path,index=False,encoding="utf-8")
    rec={
        "license":"CC BY-SA 4.0 (combined, with public source attributions)",
        "in_style_source":"https://www.kaggle.com/datasets/prvsiyan/ntl-public-in-style-pool-v1",
        "prvsiyan_source":"https://www.kaggle.com/datasets/prvsiyan/prvsiyans-extended-name-that-llm-dataset",
        "restrictions":"only 5 vetted public pool source slugs, excluded proxy sources and all pool Gemini3.7; prvsiyan only new and non-proxy routes; strict original normalized text exclusion",
        "pool_n":len(selected_pool),"prvsiyan_n":len(selected_extra),
        "deduplicated":dup,"merged_n":len(output),
        "per_model":output.model.value_counts().to_dict(),
        "sha256":hashlib.sha256(out_path.read_bytes()).hexdigest(),
        "random_state":SEED
    }
    (out/"selection_manifest.json").write_text(json.dumps(rec,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps({k:v for k,v in rec.items() if k!="per_model"},indent=2),flush=True)
    return rec

if __name__=="__main__":
    construct()
