"""Train recovery probability model.

Uses XGBoost when available; falls back to sklearn GradientBoosting.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from recoverpilot.core.config import METRICS_PATH, MODEL_PATH, RANDOM_SEED, SYNTHETIC_CSV
from recoverpilot.core.paths import ensure_dirs
from recoverpilot.ml.features import CATEGORICAL, NUMERIC, prepare_xy


def _make_model():
    try:
        from xgboost import XGBClassifier

        clf = XGBClassifier(
            n_estimators=200,
            max_depth=5,
            learning_rate=0.08,
            subsample=0.9,
            colsample_bytree=0.9,
            objective="binary:logistic",
            eval_metric="aucpr",
            random_state=RANDOM_SEED,
            n_jobs=4,
        )
        name = "xgboost"
    except Exception:
        clf = GradientBoostingClassifier(
            random_state=RANDOM_SEED,
            n_estimators=150,
            max_depth=3,
            learning_rate=0.08,
        )
        name = "sklearn_gboost"
    return clf, name


def build_pipeline() -> tuple[Pipeline, str]:
    clf, name = _make_model()
    pre = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
            ("num", "passthrough", NUMERIC),
        ]
    )
    pipe = Pipeline(steps=[("pre", pre), ("clf", clf)])
    return pipe, name


def precision_at_k(y_true: np.ndarray, scores: np.ndarray, k: float = 0.2) -> float:
    n = max(1, int(len(scores) * k))
    idx = np.argsort(scores)[::-1][:n]
    return float(y_true[idx].mean())


def train(csv_path: Path = SYNTHETIC_CSV) -> dict:
    ensure_dirs()
    if not csv_path.exists():
        from recoverpilot.data.generate import generate_dataset

        df = generate_dataset()
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(csv_path, index=False)
    else:
        df = pd.read_csv(csv_path)

    x, y = prepare_xy(df)
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=0.2, random_state=RANDOM_SEED, stratify=y
    )

    pipe, model_name = build_pipeline()
    pipe.fit(x_train, y_train)
    proba = pipe.predict_proba(x_test)[:, 1]

    metrics = {
        "model_name": model_name,
        "rows": int(len(df)),
        "positive_rate": float(y.mean()),
        "roc_auc": float(roc_auc_score(y_test, proba)),
        "pr_auc": float(average_precision_score(y_test, proba)),
        "brier": float(brier_score_loss(y_test, proba)),
        "precision_at_20pct": precision_at_k(y_test, proba, 0.2),
        "notes": "Metrics computed on synthetic holdout. Not production A/B lift.",
    }

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"pipeline": pipe, "model_name": model_name, "version": "v1"}, MODEL_PATH)
    from recoverpilot.core.config import MODEL_VERSION_PATH

    MODEL_VERSION_PATH.write_text("v1", encoding="utf-8")
    METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    try:
        from recoverpilot.ml.scorer import reload_model

        reload_model()
    except Exception:
        pass
    print(json.dumps(metrics, indent=2))
    print(f"Saved model -> {MODEL_PATH}")
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=SYNTHETIC_CSV)
    args = parser.parse_args()
    train(args.csv)


if __name__ == "__main__":
    main()
