"""Export reviewer-response table linking allocation and storage operation.

The shared-storage model has plant-level charging variables Pcharge1, Pcharge2,
and Pcharge3, while discharge and SOC are shared-system variables. Therefore the
plant-level operation indicators exported here use charging power/energy.
"""

from __future__ import annotations

from pathlib import Path
import re

import gurobipy as gp
from gurobipy import GRB
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "outputs" / "reviewer_response"

PLANTS = [
    ("PV1", "723035.csv", "overbuild_723035.csv"),
    ("PV2", "747910.csv", "overbuild_747910.csv"),
    ("PV3", "747915.csv", "overbuild_747915.csv"),
]

N_HOURS = 8760
COST_PV = 691 * 1000
COST_BATTERY = 115 * 1000
MAINTENANCE_COST_PV = 0.01
MAINTENANCE_COST_BATTERY = 0.0002
DISCOUNT_RATE = 0.08
LIFE_PV = 30
LIFE_BATTERY = 15
SELF_DISCHARGE_RATE = 0.01 / 100
CHARGE_DISCHARGE_EFFICIENCY = 0.95

SHAPLEY_COST_KUSD = {"PV1": 266.22, "PV2": 345.16, "PV3": 377.12}
TAU_0 = 2.0


def capital_recovery_factor(life: int) -> float:
    r = DISCOUNT_RATE
    return (r * (1 + r) ** life) / ((1 + r) ** life - 1)


def optimized_multiplier(path: Path) -> float:
    header = pd.read_csv(path, nrows=0).columns[-1]
    match = re.search(r"_x([0-9]+(?:\.[0-9]+)?)$", header)
    if not match:
        raise ValueError(f"Cannot parse optimized multiplier from {path}: {header}")
    return float(match.group(1))


def load_inputs() -> list[dict]:
    inputs = []
    for plant, hourly_file, overbuilt_file in PLANTS:
        df = pd.read_csv(ROOT / hourly_file, index_col=0)
        load = df.iloc[:, 0].astype(float).reset_index(drop=True)
        pv = df.iloc[:, 1].astype(float).reset_index(drop=True)
        rated_power = float(load.sum() / pv.sum())
        inputs.append(
            {
                "plant": plant,
                "load": load,
                "pv": pv,
                "rated_power": rated_power,
                "multiplier_start": optimized_multiplier(ROOT / overbuilt_file),
            }
        )
    return inputs


def solve_joint_storage(inputs: list[dict]) -> dict:
    crf_pv = capital_recovery_factor(LIFE_PV)
    crf_battery = capital_recovery_factor(LIFE_BATTERY)

    model = gp.Model("reviewer_joint_storage_operation")
    model.Params.OutputFlag = 0

    p_charge = [
        model.addVars(N_HOURS, vtype=GRB.CONTINUOUS, lb=0, name=f"Pcharge_{i + 1}")
        for i in range(3)
    ]
    p_discharge = model.addVars(N_HOURS, vtype=GRB.CONTINUOUS, lb=0, name="Pdischarge")
    b_charge = model.addVars(N_HOURS, vtype=GRB.BINARY, name="Bcharge")
    b_discharge = model.addVars(N_HOURS, vtype=GRB.BINARY, name="Bdischarge")
    s_battery = model.addVar(vtype=GRB.CONTINUOUS, lb=0, name="Sbattery")
    s_storage = model.addVars(N_HOURS, vtype=GRB.CONTINUOUS, lb=0, name="Sstorage")
    multipliers = [
        model.addVar(
            vtype=GRB.CONTINUOUS,
            lb=0,
            name=f"multiplier_{i + 1}",
        )
        for i in range(3)
    ]
    p_curt = [
        model.addVars(N_HOURS, vtype=GRB.CONTINUOUS, lb=0, name=f"Pcurt_{i + 1}")
        for i in range(3)
    ]
    p_pv_to_load = [
        model.addVars(N_HOURS, vtype=GRB.CONTINUOUS, lb=0, name=f"Ppvtoload_{i + 1}")
        for i in range(3)
    ]

    model.setObjective(
        gp.quicksum(
            (crf_pv + MAINTENANCE_COST_PV)
            * data["rated_power"]
            * COST_PV
            * multipliers[i]
            for i, data in enumerate(inputs)
        )
        + crf_battery * COST_BATTERY * s_battery
        + MAINTENANCE_COST_BATTERY
        * COST_BATTERY
        * gp.quicksum(p_charge[i][t] for i in range(3) for t in range(N_HOURS)),
        GRB.MINIMIZE,
    )

    for i, data in enumerate(inputs):
        multipliers[i].Start = data["multiplier_start"]

    for t in range(N_HOURS):
        model.addConstr(b_charge[t] + b_discharge[t] <= 1)
        model.addConstr(
            gp.quicksum(p_charge[i][t] for i in range(3)) <= b_charge[t] * s_battery / 4
        )
        model.addConstr(p_discharge[t] <= b_discharge[t] * s_battery / 4)
        model.addConstr(s_storage[t] <= s_battery)
        model.addConstr(
            gp.quicksum(p_pv_to_load[i][t] for i in range(3)) + p_discharge[t]
            == sum(float(data["load"].iloc[t]) for data in inputs)
        )
        for i, data in enumerate(inputs):
            model.addConstr(
                p_pv_to_load[i][t] + p_charge[i][t] + p_curt[i][t]
                == multipliers[i] * data["rated_power"] * float(data["pv"].iloc[t])
            )

    model.addConstr(s_storage[0] == 0.8 * s_battery)
    for t in range(N_HOURS - 1):
        model.addConstr(
            s_storage[t + 1]
            == (1 - SELF_DISCHARGE_RATE) * s_storage[t]
            + gp.quicksum(p_charge[i][t] for i in range(3)) * CHARGE_DISCHARGE_EFFICIENCY
            - p_discharge[t] / CHARGE_DISCHARGE_EFFICIENCY
        )
    model.addConstr(
        s_storage[0]
        == (1 - SELF_DISCHARGE_RATE) * s_storage[N_HOURS - 1]
        + gp.quicksum(p_charge[i][N_HOURS - 1] for i in range(3))
        * CHARGE_DISCHARGE_EFFICIENCY
        - p_discharge[N_HOURS - 1] / CHARGE_DISCHARGE_EFFICIENCY
    )

    model.optimize()
    if model.Status != GRB.OPTIMAL:
        raise RuntimeError(f"Gurobi did not find an optimal solution: status={model.Status}")

    p_charge_values = {
        inputs[i]["plant"]: [p_charge[i][t].X for t in range(N_HOURS)] for i in range(3)
    }
    storage_values = [s_storage[t].X for t in range(N_HOURS)]
    discharge_values = [p_discharge[t].X for t in range(N_HOURS)]
    return {
        "objective": model.ObjVal,
        "storage_capacity_mwh": s_battery.X,
        "multipliers": {inputs[i]["plant"]: multipliers[i].X for i in range(3)},
        "p_charge": p_charge_values,
        "p_discharge": discharge_values,
        "s_storage": storage_values,
    }


def budget_balanced_adjusted_costs(annual: pd.DataFrame) -> dict[str, float]:
    """Apply the two-step, budget-balanced improved Shapley allocation."""
    shapley = pd.Series(SHAPLEY_COST_KUSD, dtype=float)
    q_star = annual.loc[shapley.index, "Q_star"].astype(float)
    raw_cost = shapley * (1.0 + TAU_0 * q_star)
    if (raw_cost <= 0.0).any():
        raise ValueError("The selected tau_0 produces a non-positive adjusted cost.")

    adjusted = shapley.sum() * raw_cost / raw_cost.sum()
    return adjusted.to_dict()

def build_table(solution: dict) -> pd.DataFrame:
    annual = pd.read_csv(OUT_DIR / "seasonal_weights_by_plant.csv")
    annual = annual[annual["season"] == "Annual"].set_index("plant")
    adjusted_costs = budget_balanced_adjusted_costs(annual)

    total_charge = sum(sum(values) for values in solution["p_charge"].values())
    rows = []
    for plant, _, _ in PLANTS:
        charge_values = solution["p_charge"][plant]
        annual_charge = float(sum(charge_values))
        rows.append(
            {
                "plant": plant,
                "expanded_rated_capacity_mw": float(
                    annual.loc[plant, "expanded_rated_capacity_mw"]
                ),
                "shapley_cost_kusd": SHAPLEY_COST_KUSD[plant],
                "similarity_adjustment_Q_star": float(annual.loc[plant, "Q_star"]),
                "adjusted_cost_kusd": adjusted_costs[plant],
                "cost_change_from_shapley_kusd": adjusted_costs[plant]
                - SHAPLEY_COST_KUSD[plant],
                "max_charge_power_mw": max(charge_values),
                "annual_charge_energy_mwh": annual_charge,
                "charge_throughput_share": annual_charge / total_charge if total_charge else 0.0,
            }
        )

    table = pd.DataFrame(rows)
    table.attrs["shared_storage_capacity_mwh"] = solution["storage_capacity_mwh"]
    table.attrs["shared_max_discharge_power_mw"] = max(solution["p_discharge"])
    table.attrs["shared_annual_discharge_energy_mwh"] = sum(solution["p_discharge"])
    table.attrs["shared_soc_min_mwh"] = min(solution["s_storage"])
    table.attrs["shared_soc_max_mwh"] = max(solution["s_storage"])
    return table


def latex_table(table: pd.DataFrame) -> str:
    rounded = table.copy()
    for col in rounded.columns:
        if col != "plant":
            rounded[col] = rounded[col].astype(float)
    lines = [
        r"\begin{tabular}{lrrrrrrrr}",
        r"\toprule",
        (
            r"PV plant & Expanded capacity (MW) & Shapley cost (kUSD) & $Q^*$ "
            r"& Adjusted cost (kUSD) & $\Delta C$ (kUSD) & Max $P_{\rm ch}$ (MW) "
            r"& Annual $E_{\rm ch}$ (MWh) & Charge share \\"
        ),
        r"\midrule",
    ]
    for _, row in rounded.iterrows():
        lines.append(
            f"{row['plant']} & "
            f"{row['expanded_rated_capacity_mw']:.2f} & "
            f"{row['shapley_cost_kusd']:.2f} & "
            f"{row['similarity_adjustment_Q_star']:.4f} & "
            f"{row['adjusted_cost_kusd']:.2f} & "
            f"{row['cost_change_from_shapley_kusd']:.2f} & "
            f"{row['max_charge_power_mw']:.2f} & "
            f"{row['annual_charge_energy_mwh']:.2f} & "
            f"{row['charge_throughput_share']:.2%} \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    return "\n".join(lines)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    inputs = load_inputs()
    solution = solve_joint_storage(inputs)
    table = build_table(solution)

    csv_path = OUT_DIR / "allocation_operation_validation_table.csv"
    final_csv_path = OUT_DIR / "allocation_operation_validation_final.csv"
    latex_path = OUT_DIR / "allocation_operation_validation_table.tex"
    meta_path = OUT_DIR / "allocation_operation_validation_meta.csv"

    table.to_csv(csv_path, index=False)
    table.to_csv(final_csv_path, index=False)
    latex_path.write_text(latex_table(table), encoding="utf-8")
    pd.DataFrame(
        [
            {
                "tau_0": TAU_0,
                "total_shapley_cost_kusd": sum(SHAPLEY_COST_KUSD.values()),
                "total_adjusted_cost_kusd": table["adjusted_cost_kusd"].sum(),
                "shared_storage_capacity_mwh": table.attrs["shared_storage_capacity_mwh"],
                "shared_max_discharge_power_mw": table.attrs[
                    "shared_max_discharge_power_mw"
                ],
                "shared_annual_discharge_energy_mwh": table.attrs[
                    "shared_annual_discharge_energy_mwh"
                ],
                "shared_soc_min_mwh": table.attrs["shared_soc_min_mwh"],
                "shared_soc_max_mwh": table.attrs["shared_soc_max_mwh"],
                "objective_usd_per_year": solution["objective"],
                **{
                    f"{plant}_optimized_multiplier": value
                    for plant, value in solution["multipliers"].items()
                },
            }
        ]
    ).to_csv(meta_path, index=False)

    print(f"Wrote {csv_path}")
    print(f"Wrote {final_csv_path}")
    print(f"Wrote {latex_path}")
    print(f"Wrote {meta_path}")
    print(table.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    print("Shared-system operation summary:")
    for key, value in table.attrs.items():
        print(f"  {key}: {value:.4f}")


if __name__ == "__main__":
    main()



