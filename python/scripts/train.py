"""
Train a standard GP surrogate from a dataset.npz file.

Usage:
    python scripts/train.py --data ./data/dataset.npz
    python scripts/train.py --data ./data/dataset.npz --ablation
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
import numpy as np

from src.data import load_intermediate, stratified_train_test_split
from src.surrogate import Surrogate, evaluate, run_ablation


def main() -> None:
    parser = argparse.ArgumentParser(description="GP surrogate training + ablation")
    parser.add_argument("--data", default="./data/dataset.npz", help="Path to dataset.npz")
    parser.add_argument("--out_dir", default="./results", help="Output directory")
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    parser.add_argument("--ablation", action="store_true", help="Run ablation sweep")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    X, y = load_intermediate(args.data)
    print(f"Loaded: {args.data}  -- X: {X.shape}, y: {y.shape}")

    X_tr, X_te, y_tr, y_te = stratified_train_test_split(X, y, test_frac=0.2)
    print(f"Train: {len(X_tr)}  Test: {len(X_te)}")

    surr = Surrogate(device=args.device)
    surr.fit(X_tr, y_tr)

    print("\n--- Test set evaluation ---")
    mu_mean, mu_std, sigma_mean, sigma_std = surr.predict(X_te)
    metrics = evaluate(X_te, y_te, mu_mean, sigma_mean)

    mu_ls = surr.get_lengthscales("mu")
    sigma_ls = surr.get_lengthscales("sigma")
    labels_mu = ["cn", "pu", "Vop"] + [f"d{i}" for i in range(3, len(mu_ls))]
    labels_sigma = ["Vop", "cn", "pu"]
    print(f"\nARD lengthscales (smaller = more important):")
    print(f"  mu GP:    {', '.join(f'{l}={v:.3f}' for l, v in zip(labels_mu, mu_ls))}")
    print(f"  sigma GP: {', '.join(f'{l}={v:.3f}' for l, v in zip(labels_sigma, sigma_ls))}")

    with open(out_dir / "surrogate_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    if args.ablation:
        sizes = [50, 100, 200, 400, 800, 1000]
        ab_results = run_ablation(X, y, sizes, device=args.device)
        ab_data = {str(k): v for k, v in ab_results.items()}
        with open(out_dir / "ablation_results.json", "w") as f:
            json.dump(ab_data, f, indent=2)
        print(f"\nAblation results saved to {out_dir}/ablation_results.json")


if __name__ == "__main__":
    main()
