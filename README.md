# Reproducibility files

This directory contains the legacy Gurobi implementation used for the numerical results reported in the manuscript, *Cooperative cost allocation for shared storage in flexible photovoltaic clusters*.

## Requirements

- Python 3.10 or later
- Gurobi Optimizer with a valid license
- Python packages: `gurobipy`, `pandas`, and `numpy`

Install the non-solver dependencies with:

```bash
pip install -r requirements.txt
```

## Run order

Run commands from this directory:

```bash
python modify_separate.py
python scripts/abbattery.py
python scripts/acbattery.py
python scripts/bcbattery.py
python scripts/seasonal_entropy_weights.py
python scripts/tau_stability_sensitivity.py
```

The first script solves the three independent planning cases. `abbattery.py`, `acbattery.py`, and `bcbattery.py` solve the pairwise PV1+PV2, PV1+PV3, and PV2+PV3 coalitions, respectively. `seasonal_entropy_weights.py` calculates waveform-similarity and entropy-weight coefficients. The final script evaluates the `tau_0` stability range.

Generated files are written to `results/` for the verified tables, and the scripts recreate any needed intermediate outputs when run in order.






