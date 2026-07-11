from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "examples" / "data"

COLLATERAL_POSITIONS_FILE = DATA_DIR / "collateral_positions.csv"
MARKET_PRICES_FILE = DATA_DIR / "market_prices.csv"
FX_RATES_FILE = DATA_DIR / "fx_rates.csv"
HAIRCUT_RULES_FILE = DATA_DIR / "haircut_rules.csv"
INVENTORY_FILE = DATA_DIR / "inventory.csv"
MARGIN_CALLS_FILE = DATA_DIR / "margin_calls.csv"

DEFAULT_BUSINESS_DATE = "2026-07-10"
DEFAULT_ENVIRONMENT = "LOCAL"

