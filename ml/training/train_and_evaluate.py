"""
RazorGuard model training + evaluation.

Trains two models on the engineered feature set:
  1. Logistic Regression (baseline, interpretable, calibrated via class_weight)
  2. Random Forest (stronger, handles non-linearity/interactions)

Uses a TIME-BASED split (train on earliest ~75% of days, test on the most
recent ~25%) rather than a random split, because that's what production
scoring actually looks like: you only ever have the past to predict the
present. Random splitting would overstate performance.

All metrics are computed on the held-out test set and printed + saved to
JSON. Nothing here is fabricated — these numbers come directly from this
run against ml/data/processed/features.csv.
"""

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.metrics import (
    precision_score, recall_score, f1_score, roc_auc_score,
    average_precision_score, confusion_matrix, classification_report,
)

sys.path.append(str(Path(__file__).resolve().parent.parent / "features"))
from feature_engineering import FEATURE_COLUMNS, CATEGORICAL_COLUMNS  # noqa: E402

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
MODELS_DIR.mkdir(exist_ok=True)


def time_based_split(df: pd.DataFrame, test_frac: float = 0.25):
    df = df.sort_values("timestamp")
    split_idx = int(len(df) * (1 - test_frac))
    split_ts = df.iloc[split_idx]["timestamp"]
    train = df[df["timestamp"] < split_ts]
    test = df[df["timestamp"] >= split_ts]
    return train, test, split_ts


def build_preprocessor():
    numeric = FEATURE_COLUMNS
    categorical = CATEGORICAL_COLUMNS
    return ColumnTransformer([
        ("num", StandardScaler(), numeric),
        ("cat", OneHotEncoder(handle_unknown="ignore"), categorical),
    ])


def evaluate(name, model, X_test, y_test, threshold=0.5):
    proba = model.predict_proba(X_test)[:, 1]
    preds = (proba >= threshold).astype(int)

    cm = confusion_matrix(y_test, preds)
    tn, fp, fn, tp = cm.ravel()
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    fnr = fn / (fn + tp) if (fn + tp) > 0 else 0.0

    metrics = {
        "model": name,
        "threshold": threshold,
        "precision": round(precision_score(y_test, preds, zero_division=0), 4),
        "recall": round(recall_score(y_test, preds, zero_division=0), 4),
        "f1": round(f1_score(y_test, preds, zero_division=0), 4),
        "roc_auc": round(roc_auc_score(y_test, proba), 4),
        "pr_auc": round(average_precision_score(y_test, proba), 4),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "false_positive_rate": round(fpr, 4),
        "false_negative_rate": round(fnr, 4),
        "test_size": int(len(y_test)),
        "test_fraud_count": int(y_test.sum()),
    }

    print(f"\n=== {name} (threshold={threshold}) ===")
    for k, v in metrics.items():
        if k not in ("confusion_matrix",):
            print(f"  {k}: {v}")
    print(f"  confusion_matrix: TN={tn} FP={fp} FN={fn} TP={tp}")
    return metrics, proba


def main():
    processed_path = Path(__file__).resolve().parent.parent / "data" / "processed" / "features.csv"
    df = pd.read_csv(processed_path, parse_dates=["timestamp"])

    train_df, test_df, split_ts = time_based_split(df, test_frac=0.25)
    print(f"Split at {split_ts} | train={len(train_df)} rows ({train_df['fraud_label'].sum()} fraud) "
          f"| test={len(test_df)} rows ({test_df['fraud_label'].sum()} fraud)")

    X_train, y_train = train_df, train_df["fraud_label"]
    X_test, y_test = test_df, test_df["fraud_label"]

    preprocessor = build_preprocessor()

    results = {}

    # ---- 1. Logistic Regression baseline ----
    logreg = Pipeline([
        ("prep", preprocessor),
        ("clf", LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42)),
    ])
    logreg.fit(X_train, y_train)
    metrics_lr, proba_lr = evaluate("LogisticRegression", logreg, X_test, y_test)
    results["logistic_regression"] = metrics_lr
    joblib.dump(logreg, MODELS_DIR / "logistic_regression.joblib")

    # ---- 2. Random Forest ----
    rf_preprocessor = build_preprocessor()
    rf = Pipeline([
        ("prep", rf_preprocessor),
        ("clf", RandomForestClassifier(
            n_estimators=300, max_depth=10, min_samples_leaf=5,
            class_weight="balanced_subsample", random_state=42, n_jobs=-1,
        )),
    ])
    rf.fit(X_train, y_train)
    metrics_rf, proba_rf = evaluate("RandomForest", rf, X_test, y_test)
    results["random_forest"] = metrics_rf
    joblib.dump(rf, MODELS_DIR / "random_forest.joblib")

    # ---- feature importances (RF) for explainability ----
    feature_names = (
        FEATURE_COLUMNS
        + list(rf.named_steps["prep"].named_transformers_["cat"].get_feature_names_out(CATEGORICAL_COLUMNS))
    )
    importances = rf.named_steps["clf"].feature_importances_
    fi = sorted(zip(feature_names, importances), key=lambda x: -x[1])
    print("\n=== Random Forest feature importances (top 10) ===")
    for name, imp in fi[:10]:
        print(f"  {name}: {imp:.4f}")
    results["random_forest_feature_importance_top10"] = [
        {"feature": n, "importance": round(float(i), 4)} for n, i in fi[:10]
    ]

    # ---- comparison summary ----
    print("\n=== Model comparison (PR-AUC is the headline metric given class imbalance) ===")
    print(f"  LogisticRegression: PR-AUC={metrics_lr['pr_auc']}  ROC-AUC={metrics_lr['roc_auc']}  F1={metrics_lr['f1']}")
    print(f"  RandomForest:       PR-AUC={metrics_rf['pr_auc']}  ROC-AUC={metrics_rf['roc_auc']}  F1={metrics_rf['f1']}")

    results["split_info"] = {
        "split_timestamp": str(split_ts),
        "train_size": int(len(train_df)),
        "train_fraud_count": int(train_df["fraud_label"].sum()),
        "test_size": int(len(test_df)),
        "test_fraud_count": int(test_df["fraud_label"].sum()),
    }

    with open(MODELS_DIR / "evaluation_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved models + evaluation_results.json to {MODELS_DIR}")


if __name__ == "__main__":
    main()
