"""
Generate a synthetic Aave-style dataset for training risk models.

Run from repo root:
    python -m src.ml.generate_dataset

Writes: data/synthetic_aave_data.csv
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = PROJECT_ROOT / "data" / "synthetic_aave_data.csv"
N_ROWS = 10_000
RNG_SEED = 42


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -50.0, 50.0)))


def generate_synthetic_frame(n: int, rng: np.random.Generator) -> pd.DataFrame:
    """
    Features correlate with liquidation risk in a monotonic, interpretable way:
    - Lower health factor -> higher liquidation probability.
    - Higher debt_to_collateral_ratio -> higher probability.
    - Higher recent_borrow_count -> modestly higher probability (borrowing pressure).
    """
    # Health factor: mixture so we see both safe positions and stressed ones.
    log_hf = rng.normal(loc=0.35, scale=0.45, size=n)
    current_health_factor = np.exp(log_hf)
    current_health_factor = np.clip(current_health_factor, 0.35, 12.0)

    # Debt/collateral ratio in [0, ~2]; heavy tail toward risky ratios.
    debt_to_collateral_ratio = rng.exponential(scale=0.25, size=n)
    debt_to_collateral_ratio = np.clip(debt_to_collateral_ratio, 0.0, 2.5)

    # Borrow bursts in the last hour (count feature).
    recent_borrow_count = rng.poisson(lam=1.2, size=n)
    recent_borrow_count = np.clip(recent_borrow_count, 0, 24)

    # Logistic latent: stressed users much more likely to liquidate.
    z = (
        3.8 * (1.0 / np.maximum(current_health_factor, 0.25))
        + 2.4 * debt_to_collateral_ratio
        + 0.08 * recent_borrow_count
        - 4.2
    )
    # Mild interaction: worst when HF low AND ratio high.
    z += 1.2 * (debt_to_collateral_ratio / np.maximum(current_health_factor, 0.3))

    p = _sigmoid(z)
    # Small calibration noise so labels are not perfectly separable.
    p = np.clip(p + rng.normal(0.0, 0.04, size=n), 0.02, 0.98)
    u = rng.random(size=n)
    is_liquidated = (u < p).astype(np.int64)

    return pd.DataFrame(
        {
            "current_health_factor": current_health_factor.astype(np.float64),
            "debt_to_collateral_ratio": debt_to_collateral_ratio.astype(np.float64),
            "recent_borrow_count": recent_borrow_count.astype(np.int64),
            "is_liquidated": is_liquidated,
        }
    )


def main() -> None:
    rng = np.random.default_rng(RNG_SEED)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df = generate_synthetic_frame(N_ROWS, rng)
    df.to_csv(OUTPUT_PATH, index=False)
    print(f"Wrote {len(df)} rows to {OUTPUT_PATH}")
    print(df.describe().to_string())


if __name__ == "__main__":
    main()
