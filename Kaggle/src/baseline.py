"""Name That LLM V1: prompt-disjoint five-fold baseline."""
from __future__ import annotations
import argparse
import hashlib
import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, confusion_matrix, recall_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_COLUMNS = ["id", "prompt_id", "text", "model"]
N_SPLITS = 5


def build_model(name: str) -> Pipeline:
    """Fixed hyperparameters for an honest first-round comparison."""
    if name == "word_lr":
        return Pipeline([
            ("tfidf", TfidfVectorizer(
                analyzer="word", ngram_range=(1, 2), min_df=2,
                max_features=80_000, sublinear_tf=True,
            )),
            ("classifier", LogisticRegression(
                C=2.0, max_iter=600, solver="lbfgs",
            )),
        ])
    if name == "char_svc":
        return Pipeline([
            ("tfidf", TfidfVectorizer(
                analyzer="char", ngram_range=(3, 5), min_df=2,
                max_features=100_000, sublinear_tf=True,
            )),
            ("classifier", LinearSVC(C=1.0, max_iter=4000)),
        ])
    raise ValueError(f"Unknown model: {name}")


def load_training_data(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Official train.csv not found: {path}. Use --train-csv.")
    df = pd.read_csv(path, dtype={"id": str, "prompt_id": str, "text": str, "model": str})
    if list(df.columns) != EXPECTED_COLUMNS:
        raise ValueError(f"Expected columns {EXPECTED_COLUMNS}; got {df.columns.tolist()}")
    if df.empty or df[EXPECTED_COLUMNS].isna().any().any():
        raise ValueError("Train set contains missing values or is empty")
    if df["id"].duplicated().any():
        raise ValueError("Duplicate sample ids")
    if df["model"].nunique() != 18:
        raise ValueError("Expected 18 candidate models")
    if df["prompt_id"].nunique() < N_SPLITS:
        raise ValueError("Not enough prompt groups for GroupKFold")
    return df


def prompt_disjoint_folds(df: pd.DataFrame):
    """Yield (fold, train_indices, validation_indices); no prompt overlap."""
    for fold, (train_idx, val_idx) in enumerate(
        GroupKFold(n_splits=N_SPLITS).split(
            df["text"], df["model"], df["prompt_id"]
        ), start=1
    ):
        if set(df.iloc[train_idx]["prompt_id"]) & set(df.iloc[val_idx]["prompt_id"]):
            raise AssertionError("Prompt leakage detected")
        yield fold, train_idx, val_idx


def evaluate(train_csv: Path, output_dir: Path) -> dict:
    df = load_training_data(train_csv)
    labels = sorted(df["model"].unique().tolist())
    X = df["text"].tolist()
    y = df["model"].to_numpy()
    output_dir.mkdir(parents=True, exist_ok=True)
    fold_ids = np.zeros(len(df), dtype=np.int32)
    folds = list(prompt_disjoint_folds(df))
    for fold, _, val_idx in folds:
        fold_ids[val_idx] = fold
    if not np.all(fold_ids > 0):
        raise AssertionError("Every row must belong to one validation fold")

    meta = {
        "experiment": "V1_baseline",
        "date_utc": datetime.now(timezone.utc).isoformat(),
        "training_sha256": hashlib.sha256(train_csv.read_bytes()).hexdigest(),
        "samples": int(len(df)),
        "prompts": int(df["prompt_id"].nunique()),
        "labels": labels,
        "cv": "GroupKFold(n_splits=5), groups=prompt_id, no overlap",
        "packages": {
            "python": platform.python_version(), "sklearn": sklearn.__version__,
            "pandas": pd.__version__, "numpy": np.__version__
        },
        "models": {},
    }
    oof = df[["id", "prompt_id", "model"]].copy()
    oof["fold"] = fold_ids
    fold_records = []
    recalls = []
    for name in ["word_lr", "char_svc"]:
        predictions = np.full(len(df), None, dtype=object)
        fold_metrics = []
        start = time.perf_counter()
        for fold, train_idx, val_idx in folds:
            model = build_model(name)
            model.fit([X[i] for i in train_idx], y[train_idx])
            pred = model.predict([X[i] for i in val_idx])
            predictions[val_idx] = pred
            score = balanced_accuracy_score(y[val_idx], pred)
            item = {
                "fold": fold, "train_size": int(len(train_idx)),
                "val_size": int(len(val_idx)),
                "train_prompts": int(df.iloc[train_idx]["prompt_id"].nunique()),
                "val_prompts": int(df.iloc[val_idx]["prompt_id"].nunique()),
                "balanced_accuracy": round(float(score), 6),
            }
            fold_metrics.append(item)
            fold_records.append({"model": name, **item})
            print(f"{name} fold={fold} BA={score:.5f}", flush=True)
        if any(p is None for p in predictions):
            raise AssertionError("OOF predictions incomplete")
        oof[f"pred_{name}"] = predictions
        oof_score = balanced_accuracy_score(y, predictions)
        class_recall = recall_score(y, predictions, labels=labels,
                                    average=None, zero_division=0)
        class_support = df["model"].value_counts().to_dict()
        recalls.extend({
            "model": name, "label": label, "support": int(class_support[label]),
            "recall": round(float(value), 6)
        } for label, value in zip(labels, class_recall))
        matrix = confusion_matrix(y, predictions, labels=labels)
        pd.DataFrame(matrix, index=labels, columns=labels).to_csv(
            output_dir / f"confusion_{name}.csv", encoding="utf-8-sig"
        )
        meta["models"][name] = {
            "description": (
                "word 1-2 gram TF-IDF + LogisticRegression(C=2)"
                if name == "word_lr" else
                "character 3-5 gram TF-IDF + LinearSVC(C=1)"
            ),
            "oof_balanced_accuracy": round(float(oof_score), 6),
            "fold_mean_balanced_accuracy": round(float(np.mean(
                [m["balanced_accuracy"] for m in fold_metrics])), 6),
            "fold_std_balanced_accuracy": round(float(np.std(
                [m["balanced_accuracy"] for m in fold_metrics])), 6),
            "folds": fold_metrics,
            "elapsed_seconds": round(time.perf_counter() - start, 2),
        }
        print(f"{name} OOF BA={oof_score:.6f}", flush=True)

    best_name = max(
        meta["models"], key=lambda x: meta["models"][x]["oof_balanced_accuracy"]
    )
    meta["best_model_by_oof"] = best_name
    (output_dir / "metrics.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    oof.to_csv(output_dir / "oof_predictions.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(recalls).to_csv(
        output_dir / "per_class_recall.csv", index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(fold_records).to_csv(
        output_dir / "fold_scores.csv", index=False, encoding="utf-8-sig"
    )
    lines = [
        "# V1 — 首轮本地基线",
        "",
        "验证协议：GroupKFold 五折，按 prompt_id 分组；训练、验证 Prompt 严格不相交。",
        f"数据：{len(df)} 行、{df['prompt_id'].nunique()} 个 Prompt、{len(labels)} 个模型。",
        "",
        "| 模型 | OOF Balanced Accuracy | 五折平均 BA | 五折标准差 |",
        "|---|---:|---:|---:|",
    ]
    for name, result in meta["models"].items():
        lines.append(
            f"| {name} | {result['oof_balanced_accuracy']:.4f} | "
            f"{result['fold_mean_balanced_accuracy']:.4f} | "
            f"{result['fold_std_balanced_accuracy']:.4f} |"
        )
    lines += [
        "",
        f"当前最优基线：**{best_name}**。仅代表本地跨 Prompt 验证，非公榜/私榜成绩。",
        "",
        "本轮尚未提交 Kaggle。下一步分析类别召回率、易混淆标签，再提交 Notebook。",
        "",
        "完整 OOF、每类召回率、混淆矩阵留在本地，不同步原始训练记录。",
        "",
        f"训练文件 SHA-256：{meta['training_sha256']}",
    ]
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return meta


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-csv", type=Path, default=ROOT / "data/raw/train.csv")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/V1_baseline")
    args = parser.parse_args()
    result = evaluate(args.train_csv, args.output_dir)
    print("BEST:", result["best_model_by_oof"], flush=True)
    print("OUTPUT:", args.output_dir.resolve(), flush=True)


if __name__ == "__main__":
    main()
