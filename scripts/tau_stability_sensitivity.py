"""Sensitivity of coalition stability to the tau_0 redistribution parameter.

This is a post-processing script for the reviewer-response analysis. It uses
the Shapley costs, standalone storage costs, and centered allocation
coefficients reported in the manuscript table. It does not rerun Gurobi.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


# ----------------------------- Parameters ---------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "reviewer_response"

PLANTS = ["PV1", "PV2", "PV3"]

# Values from the manuscript allocation table, in kUSD.
SHAPLEY_COST_KUSD = np.array([266.22, 345.16, 377.12], dtype=float)
INDEPENDENT_STORAGE_COST_KUSD = np.array([467.20, 503.26, 562.64], dtype=float)

def load_annual_q_star() -> np.ndarray:
    """Load the full-precision annual coefficients used by the allocation table."""
    weights = pd.read_csv(OUTPUT_DIR / "seasonal_weights_by_plant.csv")
    annual = weights[weights["season"] == "Annual"].set_index("plant")
    return annual.loc[PLANTS, "Q_star"].to_numpy(dtype=float)


# Use the full-precision values; rounding is reserved for table presentation.
Q_STAR = load_annual_q_star()

TAU_MIN = 0.0
TAU_MAX = 8.0
TAU_STEP = 0.1
KEY_TAU_VALUES = [0.0, 1.0, 2.0, 4.0, 6.0, 6.5, 6.6, 7.0]


# ------------------------------ Methods -----------------------------------
def adjusted_costs(tau: float) -> np.ndarray:
    """Return budget-balanced adjusted storage costs for a tau value."""
    raw = SHAPLEY_COST_KUSD * (1.0 + tau * Q_STAR)
    if np.any(raw <= 0.0):
        raise ValueError(f"tau={tau} gives non-positive raw adjusted costs.")

    grand_cost = float(SHAPLEY_COST_KUSD.sum())
    return grand_cost * raw / float(raw.sum())


def plant_stability_boundary(plant_index: int) -> float | None:
    """Solve C_i*(tau) = standalone_i analytically for one plant.

    Returns None if no positive crossing exists.
    """
    grand_cost = float(SHAPLEY_COST_KUSD.sum())
    denominator_at_zero = grand_cost
    denominator_slope = float(np.dot(SHAPLEY_COST_KUSD, Q_STAR))

    shapley_i = float(SHAPLEY_COST_KUSD[plant_index])
    q_i = float(Q_STAR[plant_index])
    standalone_i = float(INDEPENDENT_STORAGE_COST_KUSD[plant_index])

    # grand_cost * shapley_i * (1 + tau*q_i)
    #     = standalone_i * (denominator_at_zero + tau*denominator_slope)
    lhs_0 = grand_cost * shapley_i
    lhs_1 = grand_cost * shapley_i * q_i
    rhs_0 = standalone_i * denominator_at_zero
    rhs_1 = standalone_i * denominator_slope

    denom = lhs_1 - rhs_1
    if abs(denom) < 1e-12:
        return None

    tau = (rhs_0 - lhs_0) / denom
    if tau <= 0.0:
        return None

    return float(tau)


def build_long_table(tau_values: np.ndarray) -> pd.DataFrame:
    rows = []
    for tau in tau_values:
        costs = adjusted_costs(float(tau))
        savings = INDEPENDENT_STORAGE_COST_KUSD - costs
        saving_rates = savings / INDEPENDENT_STORAGE_COST_KUSD
        stable_by_plant = savings > 0.0
        stable_coalition = bool(stable_by_plant.all())

        for idx, plant in enumerate(PLANTS):
            rows.append(
                {
                    "tau_0": round(float(tau), 10),
                    "plant": plant,
                    "shapley_cost_kusd": SHAPLEY_COST_KUSD[idx],
                    "q_star": Q_STAR[idx],
                    "adjusted_cost_kusd": costs[idx],
                    "independent_storage_cost_kusd": INDEPENDENT_STORAGE_COST_KUSD[idx],
                    "cost_saving_kusd": savings[idx],
                    "cost_saving_rate": saving_rates[idx],
                    "plant_stable": bool(stable_by_plant[idx]),
                    "coalition_stable": stable_coalition,
                }
            )
    return pd.DataFrame(rows)


def build_summary_table(long_table: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for tau, group in long_table.groupby("tau_0", sort=True):
        min_idx = group["cost_saving_kusd"].idxmin()
        min_rate_idx = group["cost_saving_rate"].idxmin()
        rows.append(
            {
                "tau_0": tau,
                "coalition_stable": bool(group["coalition_stable"].all()),
                "total_adjusted_cost_kusd": group["adjusted_cost_kusd"].sum(),
                "min_saving_kusd": group.loc[min_idx, "cost_saving_kusd"],
                "binding_plant_by_saving": group.loc[min_idx, "plant"],
                "min_saving_rate": group.loc[min_rate_idx, "cost_saving_rate"],
                "binding_plant_by_rate": group.loc[min_rate_idx, "plant"],
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    tau_grid = np.round(np.arange(TAU_MIN, TAU_MAX + TAU_STEP / 2.0, TAU_STEP), 10)
    boundary_values = {
        plant: plant_stability_boundary(idx) for idx, plant in enumerate(PLANTS)
    }
    positive_boundaries = {
        plant: value for plant, value in boundary_values.items() if value is not None
    }
    global_boundary = min(positive_boundaries.values()) if positive_boundaries else None

    extra_tau = [v for v in KEY_TAU_VALUES if TAU_MIN <= v <= TAU_MAX]
    if global_boundary is not None and TAU_MIN <= global_boundary <= TAU_MAX:
        extra_tau.append(global_boundary)
    tau_values = np.array(sorted(set(np.r_[tau_grid, extra_tau])), dtype=float)

    long_table = build_long_table(tau_values)
    summary_table = build_summary_table(long_table)

    boundary_table = pd.DataFrame(
        [
            {
                "plant": plant,
                "stability_boundary_tau_0": boundary_values[plant],
                "is_global_binding": (
                    boundary_values[plant] is not None
                    and global_boundary is not None
                    and abs(boundary_values[plant] - global_boundary) < 1e-9
                ),
            }
            for plant in PLANTS
        ]
    )

    key_table = long_table[long_table["tau_0"].isin(np.round(extra_tau, 10))].copy()

    long_table.to_csv(OUTPUT_DIR / "tau_sensitivity_long.csv", index=False)
    summary_table.to_csv(OUTPUT_DIR / "tau_sensitivity_summary.csv", index=False)
    boundary_table.to_csv(OUTPUT_DIR / "tau_stability_boundary.csv", index=False)
    key_table.to_csv(OUTPUT_DIR / "tau_sensitivity_key_values.csv", index=False)

    nominal = long_table[long_table["tau_0"] == 2.0][
        ["plant", "adjusted_cost_kusd", "cost_saving_kusd", "cost_saving_rate"]
    ]

    print("tau_0 stability sensitivity complete.")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Grand-coalition storage cost: {SHAPLEY_COST_KUSD.sum():.2f} kUSD")
    if global_boundary is not None:
        binding = boundary_table.loc[
            boundary_table["is_global_binding"], "plant"
        ].iloc[0]
        print(f"Stability boundary: tau_0 = {global_boundary:.4f} ({binding} binds)")
    print("Nominal tau_0 = 2 allocation:")
    print(nominal.to_string(index=False, float_format=lambda x: f"{x:.4f}"))


if __name__ == "__main__":
    main()

