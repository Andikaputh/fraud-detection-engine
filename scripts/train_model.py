"""Train the risk model and write the model card.

Usage:
    python -m scripts.train_model
    python -m scripts.train_model --version iforest-2026.03
"""

from __future__ import annotations

import argparse
import json

from backend.config import settings
from backend.ml.trainer import train


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the Sentinel anomaly model")
    parser.add_argument("--version", default=settings.model_version)
    parser.add_argument("--output", default=str(settings.model_dir))
    args = parser.parse_args()

    from pathlib import Path

    artifact = train(Path(args.output), args.version)
    metrics = artifact.card["metrics"]
    print(json.dumps(
        {
            "version": artifact.card["version"],
            "training_rows": artifact.card["training_rows"],
            "roc_auc": metrics["roc_auc"],
            "pr_auc": metrics["pr_auc"],
            "best_f1": metrics["best_f1"],
            "artifact": f"{args.output}/model.joblib",
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
