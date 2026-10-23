"""Risk scoring service.

The final score blends the unsupervised model (38%) with policy evidence (62%).
The blend is intentional: rules dominate for known attack shapes, while the model
can still push previously unseen behaviour into the review band. An agreement
bonus handles cases where both layers independently flag the transaction.
"""

from __future__ import annotations

import threading
from typing import Any

import joblib
import numpy as np

from backend.config import settings
from backend.ml.features import FEATURE_NAMES
from backend.ml.rules import build_reasons
from backend.ml.trainer import ensure_artifact

_LOCK = threading.Lock()
_INSTANCE: "RiskScorer | None" = None


class _ForestEvaluator:
    """Vectorised isolation-forest traversal for single-event scoring.

    scikit-learn's ``decision_function`` is fast in batch but carries roughly
    40 ms of Python overhead per call on a 220-tree forest: every tree is scored
    through a separate joblib task with fitted-state and warning checks. At a
    streaming rate of a few hundred events per second that dominates the request
    budget. The trees are static after training, so their structure is copied
    into contiguous arrays once and traversed level-by-level with NumPy.

    The arithmetic is identical to ``IsolationForest.score_samples``; the
    evaluator returns the raw uncalibrated score and the scorer applies the same
    calibration that was fitted during training.
    """

    def __init__(self, model) -> None:
        estimators = list(model.estimators_)
        if not estimators:
            raise ValueError("Isolation forest has no estimators")
        self.trees = len(estimators)
        max_nodes = max(estimator.tree_.node_count for estimator in estimators)
        self.left = np.full((self.trees, max_nodes), -1, dtype=np.int32)
        self.right = np.full((self.trees, max_nodes), -1, dtype=np.int32)
        self.feature = np.zeros((self.trees, max_nodes), dtype=np.int32)
        self.threshold = np.zeros((self.trees, max_nodes), dtype=np.float64)
        self.leaf_depth = np.zeros((self.trees, max_nodes), dtype=np.float64)

        for index, estimator in enumerate(estimators):
            tree = estimator.tree_
            nodes = tree.node_count
            self.left[index, :nodes] = tree.children_left
            self.right[index, :nodes] = tree.children_right
            self.feature[index, :nodes] = tree.feature
            self.threshold[index, :nodes] = tree.threshold
            self.leaf_depth[index, :nodes] = (
                model._decision_path_lengths[index]
                + model._average_path_length_per_tree[index]
                - 1.0
            )

        max_samples = float(model._max_samples)
        if max_samples <= 1.0:
            average_path = 0.0
        else:
            average_path = 2.0 * (np.log(max_samples - 1.0) + np.euler_gamma) - 2.0 * (
                max_samples - 1.0
            ) / max_samples
        self.denominator = self.trees * average_path
        self.columns = np.arange(self.trees)
        self.offset = float(getattr(model, "offset_", 0.0))

    def raw_score(self, vector: np.ndarray) -> float:
        nodes = np.zeros(self.trees, dtype=np.int32)
        # Depth is bounded by the training subsample size; the guard keeps the
        # loop finite if a corrupted artifact contains a cycle.
        for _ in range(256):
            child = self.left[self.columns, nodes]
            active = child != -1
            if not active.any():
                break
            split_feature = self.feature[self.columns, nodes]
            go_left = vector[split_feature] <= self.threshold[self.columns, nodes]
            candidate = np.where(go_left, child, self.right[self.columns, nodes])
            nodes = np.where(active, candidate, nodes)
        depth = float(self.leaf_depth[self.columns, nodes].sum())
        if self.denominator <= 0:
            return 0.0
        score_samples = -(2.0 ** (-depth / self.denominator))
        # decision_function = score_samples - offset_; the raw score negates it.
        return -score_samples + self.offset


class RiskScorer:
    def __init__(self) -> None:
        self._bundle = joblib.load(settings.model_dir / "model.joblib")
        self.model = self._bundle["model"]
        self.card = self._bundle["card"]
        self.calibration = self.card["calibration"]
        if list(self.card.get("feature_names", [])) != FEATURE_NAMES:
            raise RuntimeError("Model feature schema does not match the feature builder")
        if getattr(self.model, "n_features_in_", len(FEATURE_NAMES)) != len(FEATURE_NAMES):
            raise RuntimeError("Model expects a different number of features")
        self._fast: _ForestEvaluator | None = None
        if all(hasattr(self.model, name) for name in ("_decision_path_lengths", "_average_path_length_per_tree")):
            self._fast = _ForestEvaluator(self.model)

    def _calibrate(self, raw: np.ndarray) -> np.ndarray:
        p50 = self.calibration["p50"]
        p99 = self.calibration["p99"]
        p999 = self.calibration["p999"]
        low = 70.0 * (raw - p50) / max(p99 - p50, 1e-6)
        high = 70.0 + 30.0 * (raw - p99) / max(p999 - p99, 1e-6)
        return np.clip(np.where(raw <= p99, low, high), 0, 100)

    def model_score(self, features: dict[str, float]) -> float:
        vector = np.array([features[name] for name in FEATURE_NAMES], dtype=float)
        if self._fast is not None:
            raw = self._fast.raw_score(vector)
        else:  # scikit-learn changed its private helpers; stay correct, not quick.
            raw = float(-self.model.decision_function(vector.reshape(1, -1))[0])
        return float(self._calibrate(np.array([raw], dtype=float))[0])

    def model_scores(self, features_list: list[dict[str, float]]) -> list[float]:
        """Score a batch through one BLAS-backed scikit-learn call.

        Used by the historical backfill, where Python-level loop overhead on the
        single-event evaluator would turn a two-day seed into a minute of work.
        """
        if not features_list:
            return []
        matrix = np.array(
            [[features[name] for name in FEATURE_NAMES] for features in features_list],
            dtype=float,
        )
        raw = -self.model.decision_function(matrix)
        return [float(value) for value in self._calibrate(np.asarray(raw, dtype=float))]

    def assess(
        self,
        event: dict[str, Any],
        features: dict[str, float],
        meta: dict[str, Any],
        cfg: dict[str, Any],
        model_score: float | None = None,
    ) -> dict[str, Any]:
        if model_score is None:
            model_score = self.model_score(features)
        reasons = build_reasons(event, meta, cfg)
        rule_score = min(100.0, float(sum(reason["weight"] for reason in reasons)))

        risk = 0.62 * rule_score + 0.38 * model_score
        if rule_score >= 60 and model_score >= 55:
            risk += 6
        if rule_score >= 80:
            risk += 4
        risk_score = int(round(min(100.0, max(0.0, risk))))

        if risk_score >= cfg["block_threshold"] and cfg["auto_block"]:
            decision = "block"
        elif risk_score >= cfg["review_threshold"]:
            decision = "review"
        else:
            decision = "allow"

        if risk_score >= 90 or (risk_score >= 80 and event["amount"] >= 20_000_000):
            severity = "critical"
        elif risk_score >= 70:
            severity = "high"
        else:
            severity = "medium"

        return {
            "risk_score": risk_score,
            "model_score": round(model_score, 2),
            "rule_score": round(rule_score, 2),
            "decision": decision,
            "reasons": reasons,
            "severity": severity,
            "model_version": self.card.get("version", settings.model_version),
        }

    def reload(self) -> None:
        with _LOCK:
            bundle = joblib.load(settings.model_dir / "model.joblib")
            self.model = bundle["model"]
            self.card = bundle["card"]
            self.calibration = self.card["calibration"]
            self._fast = (
                _ForestEvaluator(self.model)
                if all(
                    hasattr(self.model, name)
                    for name in ("_decision_path_lengths", "_average_path_length_per_tree")
                )
                else None
            )


def get_scorer() -> RiskScorer:
    global _INSTANCE
    if _INSTANCE is None:
        with _LOCK:
            if _INSTANCE is None:
                ensure_artifact(settings.model_dir, settings.model_version)
                _INSTANCE = RiskScorer()
    return _INSTANCE
