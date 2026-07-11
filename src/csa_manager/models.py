from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any


Money = Decimal


@dataclass(frozen=True)
class CollateralPositionInput:
    position_id: str
    counterparty_code: str
    fund_code: str
    portfolio_code: str
    instrument_code: str
    quantity: Decimal
    valuation_date: date
    source: str = "NORMALIZED_INPUT"


@dataclass(frozen=True)
class MarketPrice:
    price_id: str
    emission_code: str
    dirty_price: Decimal
    currency: str
    valuation_date: date
    source: str
    isin: str | None = None


@dataclass(frozen=True)
class FXRate:
    rate_date: date
    base_currency: str
    quote_currency: str
    rate: Decimal
    source: str


@dataclass(frozen=True)
class HaircutRule:
    rule_id: str
    counterparty_pattern: str
    match_type: str
    min_days_to_maturity: int | None
    max_days_to_maturity: int | None
    factor: Decimal
    priority: int
    description: str


@dataclass(frozen=True)
class CalculationTrace:
    steps: list[dict[str, Any]] = field(default_factory=list)

    def add(self, step: str, **details: Any) -> "CalculationTrace":
        return CalculationTrace([*self.steps, {"step": step, **details}])


@dataclass(frozen=True)
class CollateralValuationResult:
    position_id: str
    counterparty_code: str
    fund_code: str
    instrument_code: str
    quantity: Decimal
    dirty_price: Decimal | None
    dirty_price_currency: str | None
    price_usd: Decimal | None
    fx_rate_used: Decimal | None
    maturity_date: date | None
    days_to_maturity: int | None
    haircut_factor: Decimal | None
    haircut_price: Decimal | None
    gross_value: Decimal | None
    collateral_value: Decimal | None
    valuation_date: date
    status: str
    warnings: list[str]
    trace: CalculationTrace


@dataclass(frozen=True)
class InventoryItem:
    inventory_id: str
    asset_id: str
    counterparty_code: str
    fund_code: str
    asset_type: str
    currency: str
    available_quantity: Decimal
    unit_collateral_value: Decimal
    is_cash: bool
    is_eligible: bool
    opportunity_cost: Decimal
    settlement_lag_days: int


@dataclass(frozen=True)
class MarginCall:
    margin_call_id: str
    counterparty_code: str
    csa_id: str
    required_amount: Decimal
    currency: str
    direction: str
    due_date: date


@dataclass(frozen=True)
class OptimizationObjective:
    preserve_cash: bool = True
    minimize_overcollateralization: bool = True
    max_line_items: int | None = None


@dataclass(frozen=True)
class CollateralAllocation:
    inventory_id: str
    asset_id: str
    fund_code: str
    quantity: Decimal
    collateral_value: Decimal
    currency: str
    explanation: str


@dataclass(frozen=True)
class OptimizationResult:
    margin_call_id: str
    status: str
    required_amount: Decimal
    covered_amount: Decimal
    overcollateralization: Decimal
    allocations: list[CollateralAllocation]
    warnings: list[str]

