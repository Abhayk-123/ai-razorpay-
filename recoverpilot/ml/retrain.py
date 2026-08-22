"""Export outcomes and retrain recovery model with version bump."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd
from sqlalchemy import select

from recoverpilot.core.config import (
    ARTIFACTS_DIR,
    FEEDBACK_CSV,
    METRICS_PATH,
    MODEL_PATH,
    MODEL_VERSION_PATH,
    SYNTHETIC_CSV,
)
from recoverpilot.core.db import OutcomeRow, PaymentFailureRow, get_engine, session
from recoverpilot.core.paths import ensure_dirs
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split

from recoverpilot.core.config import RANDOM_SEED
from recoverpilot.ml.features import prepare_xy
from recoverpilot.ml.scorer import reload_model
from recoverpilot.ml.train import build_pipeline, precision_at_k


def current_version() -> str:
    if MODEL_VERSION_PATH.exists():
        return MODEL_VERSION_PATH.read_text(encoding="utf-8").strip() or "v1"
    if MODEL_PATH.exists():
        try:
            bundle = joblib.load(MODEL_PATH)
            return str(bundle.get("version", "v1"))
        except Exception:
            return "v1"
    return "v0"


def next_version(cur: str) -> str:
    digits = "".join(ch for ch in cur if ch.isdigit())
    n = int(digits) if digits else 1
    return f"v{n + 1}"


def export_feedback(out_path: Path = FEEDBACK_CSV) -> int:
    """Join outcomes with failures into a labeled CSV compatible with training features."""
    get_engine()
    ensure_dirs()
    rows = []
    with session() as s:
        outcomes = s.scalars(select(OutcomeRow).order_by(OutcomeRow.created_at.asc())).all()
        for oc in outcomes:
            fail = s.get(PaymentFailureRow, oc.failure_id)
            if fail is None:
                continue
            rows.append(
                {
                    "event_id": fail.id,
                    "merchant_id": fail.merchant_id,
                    "customer_id": fail.customer_id,
                    "amount_inr": fail.amount_inr,
                    "payment_method": fail.payment_method,
                    "issuer_bucket": fail.issuer_bucket,
                    "decline_code": fail.decline_code,
                    "attempt_number": fail.attempt_number,
                    "hour_of_day": fail.hour_of_day,
                    "day_of_week": fail.day_of_week,
                    "merchant_category": fail.merchant_category,
                    "customer_tenure_days": fail.customer_tenure_days,
                    "is_subscription": int(fail.is_subscription),
                    "recovered": int(bool(oc.recovered)),
                    "outcome_source": oc.source,
                }
            )
    if not rows:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(out_path, index=False)
        return 0
    df = pd.DataFrame(rows)
    # One label per failure: last outcome wins
    df = df.drop_duplicates(subset=["event_id"], keep="last")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    return len(df)


def retrain(merge_synthetic: bool = True) -> dict:
    ensure_dirs()
    n_feedback = export_feedback()
    frames = []
    if merge_synthetic and SYNTHETIC_CSV.exists():
        frames.append(pd.read_csv(SYNTHETIC_CSV))
    if FEEDBACK_CSV.exists() and n_feedback > 0:
        frames.append(pd.read_csv(FEEDBACK_CSV))
    if not frames:
        from recoverpilot.data.generate import generate_dataset
        from recoverpilot.ml.train import train

        return train()

    df = pd.concat(frames, ignore_index=True)
    # Ensure required columns
    if "recovered" not in df.columns:
        raise RuntimeError("Training frame missing recovered label")

    x, y = prepare_xy(df)
    # Stratify only if both classes present
    strat = y if len(set(y.tolist())) > 1 else None
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=0.2, random_state=RANDOM_SEED, stratify=strat
    )
    pipe, model_name = build_pipeline()
    pipe.fit(x_train, y_train)
    proba = pipe.predict_proba(x_test)[:, 1]

    metrics = {
        "model_name": model_name,
        "rows": int(len(df)),
        "feedback_rows": int(n_feedback),
        "positive_rate": float(y.mean()),
        "roc_auc": float(roc_auc_score(y_test, proba)) if len(set(y_test.tolist())) > 1 else None,
        "pr_auc": float(average_precision_score(y_test, proba)) if len(set(y_test.tolist())) > 1 else None,
        "brier": float(brier_score_loss(y_test, proba)),
        "precision_at_20pct": precision_at_k(y_test, proba, 0.2),
        "notes": "Retrained on synthetic + feedback outcomes. Not production A/B lift.",
    }
    ver = next_version(current_version())
    metrics["version"] = ver
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({"pipeline": pipe, "model_name": model_name, "version": ver}, MODEL_PATH)
    MODEL_VERSION_PATH.write_text(ver, encoding="utf-8")
    METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    reload_model()
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--export-only", action="store_true")
    parser.add_argument("--no-synthetic", action="store_true")
    args = parser.parse_args()
    if args.export_only:
        n = export_feedback()
        print(f"exported_feedback_rows={n} path={FEEDBACK_CSV}")
    else:
        metrics = retrain(merge_synthetic=not args.no_synthetic)
        print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
