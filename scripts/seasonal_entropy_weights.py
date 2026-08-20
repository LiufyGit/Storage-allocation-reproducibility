"""Seasonal behavior of waveform and capacity weights w1 and w2.

Post-processing script for the reviewer response. For each season, the
load-following equivalent PV curve is reconstructed independently under the
seasonal equal-energy constraint. The capacity coefficient Q_P uses the expanded
rated capacity, i.e., the base rated capacity multiplied by the optimized
overbuilding ratio exported by the planning model.
"""

from __future__ import annotations

from pathlib import Path
import re

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOTALDATA_PATH = PROJECT_ROOT / "totaldata.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "reviewer_response"

PLANTS = [
    {
        "plant": "PV1",
        "overbuilt_col": "obpv1",
        "hourly_file": "723035.csv",
        "overbuilt_file": "overbuild_723035.csv",
    },
    {
        "plant": "PV2",
        "overbuilt_col": "obpv2",
        "hourly_file": "747910.csv",
        "overbuilt_file": "overbuild_747910.csv",
    },
    {
        "plant": "PV3",
        "overbuilt_col": "obpv3",
        "hourly_file": "747915.csv",
        "overbuilt_file": "overbuild_747915.csv",
    },
]

SEASONS = {
    "Annual": list(range(1, 13)),
    "Winter": [12, 1, 2],
    "Spring": [3, 4, 5],
    "Summer": [6, 7, 8],
    "Autumn": [9, 10, 11],
}

# Annual R values in the submitted Solar Energy manuscript table. The daily
# energy-scale factors below are calibrated once against the annual table and
# then kept fixed for every seasonal profile.
MANUSCRIPT_ANNUAL_R = {"PV1": 0.4368, "PV2": 0.4439, "PV3": 0.4724}
EPS = 1e-12


def load_totaldata() -> pd.DataFrame:
    df = pd.read_csv(TOTALDATA_PATH)
    df["Time"] = pd.to_datetime(df["Time"])
    df["month"] = df["Time"].dt.month
    return df


def base_rated_power_from_hourly_file(path: Path) -> float:
    df = pd.read_csv(path, index_col=0)
    load = df.iloc[:, 0].astype(float)
    pv = df.iloc[:, 1].astype(float)
    return float(load.sum() / pv.sum())


def optimized_multiplier_from_overbuilt_file(path: Path) -> float:
    header = pd.read_csv(path, nrows=0).columns[-1]
    match = re.search(r"_x([0-9]+(?:\.[0-9]+)?)$", header)
    if match is None:
        raise ValueError(f"Cannot parse optimized multiplier from {path}: {header}")
    return float(match.group(1))


def equal_energy_follow_load_ratio(
    pv_series: pd.Series, load_series: pd.Series, eps: float = EPS
) -> pd.Series:
    """Legacy daily equal-energy load-following curve, applied per sample set."""
    pv, load = pv_series.align(load_series, join="inner")
    pv = pv.astype(float).clip(lower=0)
    load = load.astype(float).clip(lower=0)

    if len(pv) == 0:
        return pv.copy()

    load_safe = load.replace(0, np.nan)
    ratio = load_safe / load_safe.shift(1)
    ratio = ratio.ffill().fillna(1.0)
    ratio = ratio.replace([np.inf, -np.inf], 1.0).fillna(1.0)

    profile = pd.Series(index=pv.index, dtype=float)
    profile.iloc[0] = 1.0
    for i in range(1, len(profile)):
        profile.iloc[i] = profile.iloc[i - 1] * float(ratio.iloc[i])

    sum_profile = float(profile.sum())
    sum_pv = float(pv.sum())
    if sum_profile <= eps or sum_pv <= eps:
        return pv.copy() * 0.0 if sum_pv <= eps else pv.copy()

    return (sum_pv / sum_profile * profile).rename((pv_series.name or "pv") + "_eq")


def supported_arrays(
    pv_series: pd.Series, eq_series: pd.Series
) -> tuple[np.ndarray, np.ndarray, int]:
    pv, eq = pv_series.align(eq_series, join="inner")
    pv = pv.astype(float)
    eq = eq.astype(float)
    support = (pv > 0.0) & (eq > 0.0)
    return (
        pv.loc[support].to_numpy(dtype=float),
        eq.loc[support].to_numpy(dtype=float),
        int(support.sum()),
    )


def cosine_similarity(p: np.ndarray, q: np.ndarray) -> float:
    norm_p = float(np.linalg.norm(p))
    norm_q = float(np.linalg.norm(q))
    if norm_p <= EPS or norm_q <= EPS:
        return np.nan
    return float(np.dot(p, q) / (norm_p * norm_q))


def symmetric_entropy_average(p: np.ndarray, q: np.ndarray, n_support: int) -> float:
    if n_support == 0:
        return np.nan
    k_pq = float(np.sum(np.abs(p * np.log2(p / q))))
    k_qp = float(np.sum(np.abs(q * np.log2(q / p))))
    return (k_pq + k_qp) / (2.0 * n_support)


def build_capacity_inputs(annual_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for plant in PLANTS:
        plant_id = plant["plant"]
        base_capacity = base_rated_power_from_hourly_file(
            PROJECT_ROOT / plant["hourly_file"]
        )
        optimized_multiplier = optimized_multiplier_from_overbuilt_file(
            PROJECT_ROOT / plant["overbuilt_file"]
        )
        expanded_capacity = base_capacity * optimized_multiplier

        annual_eq = equal_energy_follow_load_ratio(
            annual_df[plant["overbuilt_col"]], annual_df["total_loadh"]
        )
        p, q, n_support = supported_arrays(annual_df[plant["overbuilt_col"]], annual_eq)
        annual_rt = cosine_similarity(p, q)
        annual_raw_ra = symmetric_entropy_average(p, q, n_support)
        target_ra = annual_rt - MANUSCRIPT_ANNUAL_R[plant_id]
        if target_ra <= EPS:
            raise ValueError(f"Published annual R is not below R_t for {plant_id}.")
        daily_energy_scale = annual_raw_ra / (expanded_capacity * target_ra)

        rows.append(
            {
                "plant": plant_id,
                "hourly_file": plant["hourly_file"],
                "overbuilt_file": plant["overbuilt_file"],
                "base_rated_capacity_mw": base_capacity,
                "optimized_overbuilding_ratio": optimized_multiplier,
                "expanded_rated_capacity_mw": expanded_capacity,
                "annual_R_t_check": annual_rt,
                "target_annual_R": MANUSCRIPT_ANNUAL_R[plant_id],
                "daily_energy_scale_for_R_a": daily_energy_scale,
            }
        )

    table = pd.DataFrame(rows)
    table["Q_P"] = table["expanded_rated_capacity_mw"] / table[
        "expanded_rated_capacity_mw"
    ].sum()
    return table


def waveform_similarity(
    pv_series: pd.Series,
    load_series: pd.Series,
    rated_power: float,
    daily_energy_scale: float,
) -> dict[str, float]:
    eq_series = equal_energy_follow_load_ratio(pv_series, load_series)
    p, q, n_support = supported_arrays(pv_series, eq_series)
    if n_support == 0:
        return {"R_t": np.nan, "R_a": np.nan, "R": np.nan, "n_support": 0}

    r_t = cosine_similarity(p, q)
    raw_ra = symmetric_entropy_average(p, q, n_support)
    denominator_capacity = rated_power * daily_energy_scale
    if not np.isfinite(r_t) or denominator_capacity <= EPS:
        return {
            "R_t": np.nan,
            "R_a": np.nan,
            "R": np.nan,
            "n_support": n_support,
        }

    r_a = raw_ra / denominator_capacity
    return {"R_t": r_t, "R_a": r_a, "R": r_t - r_a, "n_support": n_support}


def minmax_by_column(values: np.ndarray) -> np.ndarray:
    out = np.zeros_like(values, dtype=float)
    for col_idx in range(values.shape[1]):
        col = values[:, col_idx]
        col_min = float(np.nanmin(col))
        col_max = float(np.nanmax(col))
        if abs(col_max - col_min) <= EPS:
            out[:, col_idx] = 1.0
        else:
            out[:, col_idx] = (col - col_min) / (col_max - col_min)
    return out


def entropy_weights(q_matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    normalized = minmax_by_column(q_matrix)
    entropies = []
    sample_count = q_matrix.shape[0]

    for col_idx in range(q_matrix.shape[1]):
        col = normalized[:, col_idx]
        col_sum = float(np.sum(col))
        if col_sum <= EPS:
            proportions = np.full(sample_count, 1.0 / sample_count)
        else:
            proportions = col / col_sum

        positive = proportions > 0.0
        entropy = -float(
            np.sum(proportions[positive] * np.log(proportions[positive]))
        ) / np.log(sample_count)
        entropies.append(entropy)

    entropies_array = np.array(entropies, dtype=float)
    diversity = 1.0 - entropies_array
    if float(diversity.sum()) <= EPS:
        weights = np.full_like(diversity, 1.0 / len(diversity))
    else:
        weights = diversity / float(diversity.sum())
    return weights, entropies_array


def allocation_indicators(
    season_df: pd.DataFrame, capacity_inputs: pd.DataFrame
) -> pd.DataFrame:
    rows = []
    for plant in PLANTS:
        row = capacity_inputs.loc[capacity_inputs["plant"] == plant["plant"]].iloc[0]
        metrics = waveform_similarity(
            season_df[plant["overbuilt_col"]],
            season_df["total_loadh"],
            float(row["expanded_rated_capacity_mw"]),
            float(row["daily_energy_scale_for_R_a"]),
        )
        rows.append(
            {
                "plant": plant["plant"],
                "n_days": int(len(season_df)),
                "n_support": int(metrics["n_support"]),
                "R_t": metrics["R_t"],
                "R_a": metrics["R_a"],
                "R": metrics["R"],
                "expanded_rated_capacity_mw": float(row["expanded_rated_capacity_mw"]),
                "Q_P": float(row["Q_P"]),
            }
        )

    table = pd.DataFrame(rows)
    r_values = table["R"].to_numpy(dtype=float)
    if np.any(~np.isfinite(r_values)) or np.any(r_values <= 0.0):
        raise ValueError("R must be positive and finite to calculate Q_R.")

    q_r = (1.0 / r_values) / float(np.sum(1.0 / r_values))
    q_p = table["Q_P"].to_numpy(dtype=float)
    q_matrix = np.column_stack([q_r, q_p])
    weights, entropies = entropy_weights(q_matrix)
    q_combined = q_matrix @ weights
    q_star = q_combined / float(q_combined.sum()) - 1.0 / len(PLANTS)

    table["Q_R"] = q_r
    table["w1_waveform"] = weights[0]
    table["w2_capacity"] = weights[1]
    table["entropy_Q_R"] = entropies[0]
    table["entropy_Q_P"] = entropies[1]
    table["Q"] = q_combined
    table["Q_star"] = q_star
    return table


def build_compact_q_summary(by_plant: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for value_col in ["R_t", "R_a", "R", "Q_R", "Q_P", "Q", "Q_star"]:
        pivot = by_plant.pivot(index="season", columns="plant", values=value_col)
        pivot = pivot.rename(columns={col: f"{value_col}_{col}" for col in pivot.columns})
        parts.append(pivot)

    weights = by_plant.groupby("season", sort=False)[["w1_waveform", "w2_capacity"]].first()
    compact = pd.concat([weights] + parts, axis=1).reset_index()
    compact["season"] = pd.Categorical(compact["season"], categories=list(SEASONS), ordered=True)
    return compact.sort_values("season").reset_index(drop=True)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_totaldata()
    capacity_inputs = build_capacity_inputs(df)

    seasonal_tables = []
    for season, months in SEASONS.items():
        season_df = df[df["month"].isin(months)].copy()
        indicators = allocation_indicators(season_df, capacity_inputs)
        indicators.insert(0, "season", season)
        seasonal_tables.append(indicators)

    by_plant = pd.concat(seasonal_tables, ignore_index=True)
    summary = (
        by_plant.groupby("season", sort=False)
        .agg(
            w1_waveform=("w1_waveform", "first"),
            w2_capacity=("w2_capacity", "first"),
            entropy_Q_R=("entropy_Q_R", "first"),
            entropy_Q_P=("entropy_Q_P", "first"),
            R_min=("R", "min"),
            R_max=("R", "max"),
            R_range=("R", lambda x: float(x.max() - x.min())),
            days=("n_days", "first"),
        )
        .reset_index()
    )
    compact_q = build_compact_q_summary(by_plant)

    by_plant.to_csv(OUTPUT_DIR / "seasonal_weights_by_plant.csv", index=False)
    summary.to_csv(OUTPUT_DIR / "seasonal_weight_summary.csv", index=False)
    compact_q.to_csv(OUTPUT_DIR / "seasonal_q_summary.csv", index=False)
    capacity_inputs.to_csv(OUTPUT_DIR / "seasonal_rated_power_inputs.csv", index=False)

    annual = by_plant[by_plant["season"] == "Annual"]
    annual_check = annual[
        ["plant", "R_t", "R_a", "R", "Q_R", "Q_P", "w1_waveform", "w2_capacity", "Q", "Q_star"]
    ]

    print("Seasonal entropy-weight analysis complete.")
    print(f"Output directory: {OUTPUT_DIR}")
    print("Capacity inputs used for Q_P and R_a:")
    print(capacity_inputs.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    print("Annual reproducibility check:")
    print(annual_check.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    print("Seasonal Q and Q* summary:")
    print(
        compact_q[
            [
                "season",
                "w1_waveform",
                "w2_capacity",
                "Q_R_PV1",
                "Q_R_PV2",
                "Q_R_PV3",
                "Q_P_PV1",
                "Q_P_PV2",
                "Q_P_PV3",
                "Q_PV1",
                "Q_PV2",
                "Q_PV3",
                "Q_star_PV1",
                "Q_star_PV2",
                "Q_star_PV3",
            ]
        ].to_string(index=False, float_format=lambda x: f"{x:.4f}")
    )


if __name__ == "__main__":
    main()

