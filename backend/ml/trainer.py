"""Model training and calibration.

The shipped model is an Isolation Forest over 16 behavioural features. Training
data is generated from the same statistical families the simulator emits, which
keeps the demo self-contained; the model card explicitly marks the evaluation as
synthetic. For a production deployment, replace `generate_dataset` with labelled
chargeback data and keep the rest of the pipeline unchanged.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, roc_auc_score

from backend.ml.features import FEATURE_NAMES

RNG_SEED = 42


def _normal(n: int, rng: np.random.Generator) -> np.ndarray:
    hour = rng.uniform(0, 24, n)
    log_amount = rng.normal(12.6, 1.0, n).clip(9.5, 15.2)
    velocity_1m = rng.poisson(0.45, n) + 1
    return np.column_stack(
        [
            log_amount,
            rng.normal(0, 0.5, n).clip(-2.2, 2.8),
            rng.normal(0, 0.9, n).clip(-4, 4),
            velocity_1m,
            velocity_1m + rng.poisson(1.1, n),
            rng.normal(0, 0.35, n).clip(0, 3),
            rng.binomial(1, 0.06, n),
            np.sin(2 * np.pi * hour / 24),
            np.cos(2 * np.pi * hour / 24),
            rng.beta(2, 7, n) * 0.9,
            rng.binomial(1, 0.03, n),
            rng.choice([0.2, 0.3, 0.35, 0.55, 0.6], n),
            rng.normal(5.6, 1.1, n).clip(0.7, 8.5),
            rng.poisson(0.04, n),
            rng.integers(1, 3, n),
            rng.binomial(1, 0.01, n),
        ]
    )


def _anomalies(n: int, rng: np.random.Generator) -> np.ndarray:
    """Three observable attack shapes: amount abuse, card testing, account takeover."""
    family = rng.integers(0, 3, n)
    rows = np.zeros((n, len(FEATURE_NAMES)))

    amount_idx = family == 0
    if amount_idx.any():
        k = int(amount_idx.sum())
        rows[amount_idx, 0] = rng.normal(16.4, 0.7, k)
        rows[amount_idx, 1] = rng.normal(2.6, 0.8, k)
        rows[amount_idx, 2] = rng.normal(3.4, 1.2, k)
        rows[amount_idx, 3] = rng.integers(1, 3, k)
        rows[amount_idx, 4] = rng.integers(2, 6, k)
        rows[amount_idx, 5] = rng.normal(0.3, 0.4, k)
        rows[amount_idx, 6] = rng.binomial(1, 0.15, k)
        rows[amount_idx, 7] = rng.uniform(-1, 1, k)
        rows[amount_idx, 8] = rng.uniform(-1, 1, k)
        rows[amount_idx, 9] = rng.beta(4, 2, k) * 0.95
        rows[amount_idx, 10] = rng.binomial(1, 0.2, k)
        rows[amount_idx, 11] = rng.choice([0.55, 0.6, 0.8], k)
        rows[amount_idx, 12] = rng.normal(3.2, 1.0, k)
        rows[amount_idx, 13] = rng.poisson(0.5, k)
        rows[amount_idx, 14] = rng.integers(1, 3, k)
        rows[amount_idx, 15] = rng.binomial(1, 0.08, k)

    velocity_idx = family == 1
    if velocity_idx.any():
        k = int(velocity_idx.sum())
        rows[velocity_idx, 0] = rng.normal(10.6, 0.9, k)
        rows[velocity_idx, 1] = rng.normal(-0.6, 0.5, k)
        rows[velocity_idx, 2] = rng.normal(-0.4, 0.8, k)
        rows[velocity_idx, 3] = rng.integers(5, 14, k)
        rows[velocity_idx, 4] = rng.integers(14, 36, k)
        rows[velocity_idx, 5] = rng.normal(0.5, 0.8, k)
        rows[velocity_idx, 6] = rng.binomial(1, 0.65, k)
        rows[velocity_idx, 7] = rng.uniform(-1, 1, k)
        rows[velocity_idx, 8] = rng.uniform(-1, 1, k)
        rows[velocity_idx, 9] = rng.uniform(0.1, 0.7, k)
        rows[velocity_idx, 10] = rng.binomial(1, 0.15, k)
        rows[velocity_idx, 11] = rng.choice([0.3, 0.55, 0.6], k)
        rows[velocity_idx, 12] = rng.normal(5.0, 1.2, k)
        rows[velocity_idx, 13] = rng.poisson(0.2, k)
        rows[velocity_idx, 14] = rng.integers(1, 3, k)
        rows[velocity_idx, 15] = rng.binomial(1, 0.3, k)

    ato_idx = family == 2
    if ato_idx.any():
        k = int(ato_idx.sum())
        rows[ato_idx, 0] = rng.normal(15.2, 1.2, k)
        rows[ato_idx, 1] = rng.normal(1.8, 1.0, k)
        rows[ato_idx, 2] = rng.normal(2.2, 1.5, k)
        rows[ato_idx, 3] = rng.integers(1, 4, k)
        rows[ato_idx, 4] = rng.integers(1, 8, k)
        rows[ato_idx, 5] = rng.normal(9.2, 1.0, k)
        rows[ato_idx, 6] = 1
        rows[ato_idx, 7] = rng.uniform(-1, 1, k)
        rows[ato_idx, 8] = rng.uniform(-1, 1, k)
        rows[ato_idx, 9] = rng.uniform(0.3, 0.95, k)
        rows[ato_idx, 10] = 1
        rows[ato_idx, 11] = rng.choice([0.55, 0.6], k)
        rows[ato_idx, 12] = rng.normal(3.0, 1.5, k)
        rows[ato_idx, 13] = rng.poisson(0.4, k)
        rows[ato_idx, 14] = rng.integers(2, 5, k)
        rows[ato_idx, 15] = rng.binomial(1, 0.2, k)

    return rows


def generate_dataset(n_normal: int = 18_000, n_anomaly: int = 900, seed: int = RNG_SEED):
    """Build a labelled dataset with deliberate overlap.

    Perfectly separable synthetic data produces meaningless 0.999 AUCs. Fifteen
    percent of fraud rows are blended toward normal behaviour (evasive fraud) and
    1.5% of normal rows borrow fraud-like tails (legitimate high-value / travel
    behaviour), which keeps the evaluation honest about the difficult cases.
    """
    rng = np.random.default_rng(seed)
    normal = _normal(n_normal, rng)
    anomaly = _anomalies(n_anomaly, rng)

    hard_negative_count = max(int(n_normal * 0.015), 1)
    hard_idx = rng.choice(n_normal, size=hard_negative_count, replace=False)
    donors = _anomalies(hard_negative_count, rng)
    alpha = rng.uniform(0.15, 0.45, size=(hard_negative_count, 1))
    normal[hard_idx] = alpha * donors + (1 - alpha) * normal[hard_idx]

    stealth_count = max(int(n_anomaly * 0.18), 1)
    stealth_idx = rng.choice(n_anomaly, size=stealth_count, replace=False)
    stealth_donors = _normal(stealth_count, rng)
    beta = rng.uniform(0.65, 0.88, size=(stealth_count, 1))
    anomaly[stealth_idx] = beta * stealth_donors + (1 - beta) * anomaly[stealth_idx]

    x = np.vstack([normal, anomaly])
    y = np.concatenate([np.zeros(n_normal, dtype=int), np.ones(n_anomaly, dtype=int)])
    return x, y, normal


@dataclass
class TrainedArtifact:
    model: IsolationForest
    calibration: dict[str, float]
    card: dict


def _normalise(raw: np.ndarray, calibration: dict[str, float]) -> np.ndarray:
    p50 = calibration["p50"]
    p99 = calibration["p99"]
    p999 = calibration["p999"]
    low_span = max(p99 - p50, 1e-6)
    high_span = max(p999 - p99, 1e-6)
    low = 70.0 * (raw - p50) / low_span
    high = 70.0 + 30.0 * (raw - p99) / high_span
    return np.clip(np.where(raw <= p99, low, high), 0, 100)


def _permutation_importance(model, x, baseline_raw, rng) -> list[dict]:
    sample = x[rng.choice(len(x), size=min(1500, len(x)), replace=False)]
    base = -model.decision_function(sample)
    importances: list[dict] = []
    for index, name in enumerate(FEATURE_NAMES):
        deltas = []
        for _ in range(3):
            shuffled = sample.copy()
            rng.shuffle(shuffled[:, index])
            deltas.append(float(np.mean(np.abs(-model.decision_function(shuffled) - base))))
        importances.append({"feature": name, "importance": round(float(np.mean(deltas)), 5)})
    total = sum(item["importance"] for item in importances) or 1.0
    for item in importances:
        item["weight"] = round(100 * item["importance"] / total, 1)
    importances.sort(key=lambda item: item["weight"], reverse=True)
    return importances


def train(model_dir: Path, version: str) -> TrainedArtifact:
    model_dir.mkdir(parents=True, exist_ok=True)
    x, y, normal = generate_dataset()
    rng = np.random.default_rng(RNG_SEED + 1)

    model = IsolationForest(
        n_estimators=220,
        max_samples=4096,
        contamination=0.045,
        max_features=1.0,
        random_state=RNG_SEED,
        n_jobs=-1,
    )
    model.fit(x)

    train_raw = -model.decision_function(normal)
    calibration = {
        "p50": float(np.percentile(train_raw, 50)),
        "p99": float(np.percentile(train_raw, 99)),
        "p999": float(np.percentile(train_raw, 99.9)),
    }

    holdout_x, holdout_y, _ = generate_dataset(n_normal=4000, n_anomaly=800, seed=RNG_SEED + 7)
    raw = -model.decision_function(holdout_x)
    scores = _normalise(raw, calibration)

    precision_curve, recall_curve, thresholds = [], [], []
    for threshold in (60, 70, 75, 80, 85, 90):
        predicted = scores >= threshold
        tp = int(((predicted == 1) & (holdout_y == 1)).sum())
        fp = int(((predicted == 1) & (holdout_y == 0)).sum())
        fn = int(((predicted == 0) & (holdout_y == 1)).sum())
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        precision_curve.append({"threshold": threshold, "precision": round(precision, 4)})
        recall_curve.append({"threshold": threshold, "recall": round(recall, 4)})
        thresholds.append(threshold)

    f1_scores = [
        (2 * p["precision"] * r["recall"]) / max(p["precision"] + r["recall"], 1e-9)
        for p, r in zip(precision_curve, recall_curve)
    ]
    best_index = int(np.argmax(f1_scores))
    fpr_threshold = float(np.percentile(scores[holdout_y == 0], 99))
    tpr_at_fpr = float(np.mean(scores[holdout_y == 1] >= fpr_threshold))

    metrics = {
        "roc_auc": round(float(roc_auc_score(holdout_y, raw)), 4),
        "pr_auc": round(float(average_precision_score(holdout_y, raw)), 4),
        "precision_at_best_f1": precision_curve[best_index]["precision"],
        "recall_at_best_f1": recall_curve[best_index]["recall"],
        "best_f1": round(float(f1_scores[best_index]), 4),
        "decision_threshold": precision_curve[best_index]["threshold"],
        "tpr_at_1pct_fpr": round(tpr_at_fpr, 4),
        "holdout_rows": int(len(holdout_y)),
        "precision_recall_curve": [
            {"threshold": p["threshold"], "precision": p["precision"], "recall": r["recall"]}
            for p, r in zip(precision_curve, recall_curve)
        ],
        "evaluation": "synthetic holdout",
    }

    importance = _permutation_importance(model, x[:6000], None, rng)
    score_distribution = {
        "p50": round(float(np.percentile(scores, 50)), 2),
        "p90": round(float(np.percentile(scores, 90)), 2),
        "p99": round(float(np.percentile(scores, 99)), 2),
    }

    card = {
        "version": version,
        "algorithm": "IsolationForest",
        "library": "scikit-learn",
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "training_rows": int(len(x)),
        "anomaly_fraction": 0.045,
        "n_estimators": 220,
        "feature_names": FEATURE_NAMES,
        "calibration": {k: round(v, 6) for k, v in calibration.items()},
        "metrics": metrics,
        "feature_importance": importance,
        "score_distribution": score_distribution,
        "limitations": [
            "Trained on synthetic data; not a substitute for chargeback-labelled production data.",
            "Scores are relative to the training population and require periodic recalibration.",
            "No device-fingerprint or consortium signals are included in this build.",
        ],
    }

    joblib.dump({"model": model, "card": card}, model_dir / "model.joblib", compress=3)
    (model_dir / "model_card.json").write_text(json.dumps(card, indent=2), encoding="utf-8")
    return TrainedArtifact(model=model, calibration=card["calibration"], card=card)


def ensure_artifact(model_dir: Path, version: str) -> dict:
    path = model_dir / "model.joblib"
    if path.exists():
        try:
            bundle = joblib.load(path)
            card = bundle.get("card", {})
            if card.get("feature_names") == FEATURE_NAMES and bundle.get("model") is not None:
                return card
        except Exception:
            pass
    artifact = train(model_dir, version)
    return artifact.card
