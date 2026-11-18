"""V2 candidate evaluation: combined lexical and stylometric features.

Uses exactly the same prompt-disjoint 5-fold GroupKFold scheme as V1.
Data must remain unchanged. No label-based feature selection on validation folds.

Run: python -u src/iterate_v2.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
import sklearn
from scipy.sparse import csr_matrix, hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import balanced_accuracy_score, confusion_matrix, recall_score
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC

from baseline import load_training_data, prompt_disjoint_folds

ROOT = Path(__file__).resolve().parents[1]
TOKENS = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?", re.UNICODE)
SENTENCES = re.compile(r"[.!?]+(?:\s|$)")
WORD_SET = [
    "the", "and", "of", "to", "in", "is", "that", "this", "which",
    "with", "as", "by", "for", "on", "from", "are", "can", "may", "might",
    "will", "should", "could", "we", "you", "i", "they", "it", "not",
    "but", "or", "a", "an", "their", "its", "our", "your",
    "however", "therefore", "indeed", "perhaps", "ultimately",
    "although", "while", "because", "rather", "instead", "through",
    "each", "every", "even", "yet", "only", "often", "also",
]
PHRASES = [
    "for example", "such as", "in fact", "rather than",
    "not only", "not just", "on the other hand", "in other words",
    "at the same time", "in this way", "as a result",
]
PUNCT = list(",;:.!?-—–()[]{}\"'“”‘’/\\*#\n")


def style_vector(text: str) -> np.ndarray:
    """Surface-only, topic-agnostic style statistics."""
    words = [w.lower() for w in TOKENS.findall(text)]
    n = max(1, len(words))
    chars = max(1, len(text))
    lower = text.lower()
    count = {}
    for w in words:
        count[w] = count.get(w, 0) + 1
    counts = np.asarray(list(count.values()), dtype=float) if count else np.array([0.0])
    sent_len = [len(TOKENS.findall(s)) for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if not sent_len:
        sent_len = [n]
    words_len = [len(w) for w in words] or [0]
    vals = [
        np.log1p(chars), np.log1p(n),
        float(np.mean(words_len)), float(np.std(words_len)),
        np.mean(sent_len), np.std(sent_len),
        len(count) / n, np.sum(counts == 1) / n,
        np.sum(counts >= 3) / n,
        sum(len(w) >= 8 for w in words) / n,
        sum(len(w) <= 3 for w in words) / n,
        sum(w[0].isupper() for w in TOKENS.findall(text)) / n,
        sum(c.isupper() for c in text) * 100 / chars,
        sum(c.isdigit() for c in text) * 100 / chars,
        sum(ord(c) > 127 for c in text) * 100 / chars,
        sum(c.isspace() for c in text) * 100 / chars,
        text.count("\n\n") * 100 / chars,
        len(re.findall(r"\b\d+(?:\.\d+)?\b", text)) / n,
    ]
    vals.extend([text.count(p) * 100 / chars for p in PUNCT])
    vals.extend([count.get(w, 0) * 100 / n for w in WORD_SET])
    vals.extend([lower.count(p) * 100 / n for p in PHRASES])
    vals.append(sum(text.startswith(prefix) for prefix in (
        "In ", "The ", "A ", "When ", "Imagine ", "Consider ", "There ", "Every ",
    )))
    return np.asarray(vals, dtype=np.float32)


def style_matrix(texts) -> np.ndarray:
    return np.asarray([style_vector(text) for text in texts], dtype=np.float32)


CANDIDATES = {
    "joint_word_char_svc": {"style_weight": 0., "C": 1.0, "word_weight": 1.0},
    "joint_style_svc": {"style_weight": 0.08, "C": 1.0, "word_weight": 1.0},
    "joint_style_word2_svc": {"style_weight": 0.08, "C": 1.0, "word_weight": 1.6},
}


def evaluate(train_csv: Path, out_dir: Path):
    df = load_training_data(train_csv)
    texts = df["text"].tolist()
    y = df["model"].to_numpy()
    labels = sorted(df["model"].unique().tolist())
    out_dir.mkdir(parents=True, exist_ok=True)
    oof = {
        key: np.full(len(df), None, dtype=object) for key in CANDIDATES
    }
    fold_data = []
    started = time.perf_counter()
    for fold, tr, va in prompt_disjoint_folds(df):
        print(f"V2 prepare fold {fold}/5", flush=True)
        xtr = [texts[i] for i in tr]
        xva = [texts[i] for i in va]
        char = TfidfVectorizer(
            analyzer="char", ngram_range=(3, 5), min_df=2,
            max_features=100_000, sublinear_tf=True, dtype=np.float32,
        )
        word = TfidfVectorizer(
            analyzer="word", ngram_range=(1, 2), min_df=2,
            max_features=80_000, sublinear_tf=True, dtype=np.float32,
        )
        chr_tr, chr_va = char.fit_transform(xtr), char.transform(xva)
        word_tr, word_va = word.fit_transform(xtr), word.transform(xva)
        # Style scaling is fit on the training fold only.
        scaler = StandardScaler()
        sty_tr = scaler.fit_transform(style_matrix(xtr))
        sty_va = scaler.transform(style_matrix(xva))
        # Winsorization of standardized style stats avoids outlier domination.
        sty_tr = csr_matrix(np.clip(sty_tr, -4, 4))
        sty_va = csr_matrix(np.clip(sty_va, -4, 4))
        for name, cfg in CANDIDATES.items():
            weight = cfg["word_weight"]
            parts_tr = [chr_tr, word_tr * weight]
            parts_va = [chr_va, word_va * weight]
            if cfg["style_weight"]:
                parts_tr.append(sty_tr * cfg["style_weight"])
                parts_va.append(sty_va * cfg["style_weight"])
            m = LinearSVC(C=cfg["C"], max_iter=4000)
            m.fit(hstack(parts_tr, format="csr"), y[tr])
            pred = m.predict(hstack(parts_va, format="csr"))
            oof[name][va] = pred
            score = balanced_accuracy_score(y[va], pred)
            fold_data.append({
                "model": name, "fold": fold, "n_train": int(len(tr)),
                "n_val": int(len(va)),
                "train_prompts": int(df.iloc[tr]["prompt_id"].nunique()),
                "val_prompts": int(df.iloc[va]["prompt_id"].nunique()),
                "balanced_accuracy": round(float(score), 6),
            })
            print(f"  {name}: BA={score:.6f}", flush=True)
    results = {}
    recalls = []
    for name, preds in oof.items():
        if any(pred is None for pred in preds):
            raise AssertionError("Incomplete OOF")
        score = balanced_accuracy_score(y, preds)
        folds = [d for d in fold_data if d["model"] == name]
        results[name] = {
            "oof_balanced_accuracy": round(float(score), 6),
            "fold_mean": round(float(np.mean([d["balanced_accuracy"] for d in folds])), 6),
            "fold_std": round(float(np.std([d["balanced_accuracy"] for d in folds])), 6),
            "folds": folds,
            "configuration": CANDIDATES[name],
        }
        matrix = confusion_matrix(y, preds, labels=labels)
        pd.DataFrame(matrix, index=labels, columns=labels).to_csv(
            out_dir / f"confusion_{name}.csv", encoding="utf-8-sig"
        )
        r = recall_score(y, preds, average=None, labels=labels, zero_division=0)
        recalls.extend(
            {"model": name, "label": label, "recall": round(float(value), 6)}
            for label, value in zip(labels, r)
        )
        print(f"V2 {name} OOF Balanced Accuracy: {score:.6f}", flush=True)
    best = max(results, key=lambda k: results[k]["oof_balanced_accuracy"])
    data = {
        "experiment": "V2_feature_fusion",
        "date_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_sha256": hashlib.sha256(train_csv.read_bytes()).hexdigest(),
        "protocol": "same deterministic GroupKFold(n_splits=5), groups=prompt_id as V1",
        "model_candidates": results,
        "best_candidate": best,
        "V1_reference": 0.307813,
        "improvement_vs_V1": round(results[best]["oof_balanced_accuracy"] - .307813, 6),
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "software": {
            "python": platform.python_version(), "sklearn": sklearn.__version__,
            "pandas": pd.__version__, "numpy": np.__version__,
            "scipy": scipy.__version__,
        },
    }
    (out_dir / "metrics.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    pd.DataFrame(fold_data).to_csv(out_dir / "fold_scores.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(recalls).to_csv(out_dir / "per_class_recall.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame({
        "id": df["id"], "prompt_id": df["prompt_id"],
        "model": y, **{"pred_" + k: v for k, v in oof.items()}
    }).to_csv(out_dir / "oof_predictions.csv", index=False, encoding="utf-8-sig")
    lines = [
        "# V2 — 词级、字符级与风格特征融合",
        "",
        "官方训练集五折 GroupKFold，分组键 prompt_id；逐折拟合 TF-IDF 和风格标准化，避免验证集泄漏。",
        "",
        "| 候选模型 | 整体 OOF Balanced Accuracy | 较 V1 最优提升 |",
        "|---|---:|---:|",
    ]
    for name, d in results.items():
        lines.append(f"| {name} | {d['oof_balanced_accuracy']:.6f} | {d['oof_balanced_accuracy'] - .307813:+.6f} |")
    lines.extend([
        "",
        f"当前最好候选：**{best}**，与 V1 的分数差：**{data['improvement_vs_V1']:+.6f}**。",
        "上述为本地 OOF 结果，不是 Kaggle 排行榜成绩。",
        "",
        f"训练数据 SHA-256：{data['dataset_sha256']}",
        f"运行总时间：{data['elapsed_seconds']} 秒。",
    ])
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-csv", type=Path, default=ROOT / "data/raw/train.csv")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/V2_feature_fusion")
    args = parser.parse_args()
    evaluate(args.train_csv, args.output_dir)


if __name__ == "__main__":
    main()
