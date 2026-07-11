# CSA Manager

CSA Manager is a professional starter repository for an institutional Middle Office platform focused on OTC derivatives, CSA collateral valuation and collateral optimization.

This first version intentionally separates responsibilities:

- `app.py` is a Streamlit presentation layer only.
- `src/csa_manager/importers.py` reads and normalizes data.
- `src/csa_manager/valuation_engine.py` contains pure financial valuation rules.
- `src/csa_manager/optimization_engine.py` contains collateral optimization architecture and a deterministic greedy solver.
- `src/csa_manager/services.py` orchestrates modules for the UI.

No Streamlit page contains financial logic.

## Quick Start

```bash
cd CSA_Manager
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
streamlit run app.py
```

On Windows PowerShell:

```powershell
cd CSA_Manager
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest
streamlit run app.py
```

## Repository Structure

```text
CSA_Manager/
  app.py
  requirements.txt
  pyproject.toml
  README.md
  .gitignore
  config/
    settings.py
  examples/
    data/
      collateral_positions.csv
      market_prices.csv
      fx_rates.csv
      haircut_rules.csv
      inventory.csv
      margin_calls.csv
  src/
    csa_manager/
      __init__.py
      models.py
      importers.py
      valuation_engine.py
      optimization_engine.py
      services.py
  tests/
    test_importers.py
    test_valuation_engine.py
    test_optimization_engine.py
```

## Design Principles

- Excel and CSV are inputs/outputs, not business engines.
- Importers do not contain financial logic.
- Valuation calculations are deterministic and side-effect free.
- Optimization consumes already-valued collateral and margin calls.
- Streamlit only consumes application services.

## Current Scope

Implemented:

- CSV importers for normalized sample data.
- Financial valuation rules matching the current notebook behavior:
  - substring price selection
  - BBVA FX exception
  - non-BBVA price conversion using FIX
  - maturity parsing from `YYMMDD` suffix
  - 30/360 US day count with absolute value
  - counterparty haircut tables
  - collateral value after haircut
- Collateral optimization architecture:
  - eligible inventory candidates
  - hard coverage constraint
  - cash preservation objective
  - deterministic greedy solver
- Tests for importers, valuation and optimization.

Planned:

- Excel-specific Aladdin importers.
- Full CSA margin engine.
- Reconciliation and dispute workflow.
- Maker/checker approvals.
- Persistence and audit trail.

