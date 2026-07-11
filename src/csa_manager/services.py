from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal

import pandas as pd

from config import settings
from csa_manager.importers import (
    CollateralPositionImporter,
    FXRateImporter,
    HaircutRuleImporter,
    InventoryImporter,
    MarginCallImporter,
    MarketPriceImporter,
)
from csa_manager.models import (
    CollateralPositionInput,
    FXRate,
    HaircutRule,
    InventoryItem,
    MarginCall,
    MarketPrice,
    OptimizationObjective,
)
from csa_manager.optimization_engine import CollateralOptimizationEngine
from csa_manager.valuation_engine import CollateralValuationEngine


class DataLoadService:
    def load_collateral_positions(self) -> pd.DataFrame:
        return CollateralPositionImporter().import_file(settings.COLLATERAL_POSITIONS_FILE).dataframe

    def load_market_prices(self) -> pd.DataFrame:
        return MarketPriceImporter().import_file(settings.MARKET_PRICES_FILE).dataframe

    def load_fx_rates(self) -> pd.DataFrame:
        return FXRateImporter().import_file(settings.FX_RATES_FILE).dataframe

    def load_haircut_rules(self) -> pd.DataFrame:
        return HaircutRuleImporter().import_file(settings.HAIRCUT_RULES_FILE).dataframe

    def load_inventory(self) -> pd.DataFrame:
        return InventoryImporter().import_file(settings.INVENTORY_FILE).dataframe

    def load_margin_calls(self) -> pd.DataFrame:
        return MarginCallImporter().import_file(settings.MARGIN_CALLS_FILE).dataframe


class MappingService:
    @staticmethod
    def positions_from_dataframe(df: pd.DataFrame) -> list[CollateralPositionInput]:
        return [
            CollateralPositionInput(
                position_id=row.position_id,
                counterparty_code=row.counterparty_code,
                fund_code=row.fund_code,
                portfolio_code=row.portfolio_code,
                instrument_code=row.instrument_code,
                quantity=row.quantity,
                valuation_date=row.valuation_date,
                source=row.source,
            )
            for row in df.itertuples(index=False)
        ]

    @staticmethod
    def prices_from_dataframe(df: pd.DataFrame) -> list[MarketPrice]:
        return [
            MarketPrice(
                price_id=row.price_id,
                emission_code=row.emission_code,
                dirty_price=row.dirty_price,
                currency=row.currency,
                valuation_date=row.valuation_date,
                source=row.source,
                isin=None if pd.isna(row.isin) else row.isin,
            )
            for row in df.itertuples(index=False)
        ]

    @staticmethod
    def fx_from_dataframe(df: pd.DataFrame) -> FXRate:
        row = df.iloc[0]
        return FXRate(
            rate_date=row["rate_date"],
            base_currency=row["base_currency"],
            quote_currency=row["quote_currency"],
            rate=row["rate"],
            source=row["source"],
        )

    @staticmethod
    def haircut_rules_from_dataframe(df: pd.DataFrame) -> list[HaircutRule]:
        rules: list[HaircutRule] = []
        for row in df.itertuples(index=False):
            min_days = None if pd.isna(row.min_days_to_maturity) else int(row.min_days_to_maturity)
            max_days = None if pd.isna(row.max_days_to_maturity) else int(row.max_days_to_maturity)
            rules.append(
                HaircutRule(
                    rule_id=row.rule_id,
                    counterparty_pattern=row.counterparty_pattern,
                    match_type=row.match_type,
                    min_days_to_maturity=min_days,
                    max_days_to_maturity=max_days,
                    factor=row.factor,
                    priority=row.priority,
                    description=row.description,
                )
            )
        return rules

    @staticmethod
    def inventory_from_dataframe(df: pd.DataFrame) -> list[InventoryItem]:
        return [
            InventoryItem(
                inventory_id=row.inventory_id,
                asset_id=row.asset_id,
                counterparty_code=row.counterparty_code,
                fund_code=row.fund_code,
                asset_type=row.asset_type,
                currency=row.currency,
                available_quantity=row.available_quantity,
                unit_collateral_value=row.unit_collateral_value,
                is_cash=row.is_cash,
                is_eligible=row.is_eligible,
                opportunity_cost=row.opportunity_cost,
                settlement_lag_days=row.settlement_lag_days,
            )
            for row in df.itertuples(index=False)
        ]

    @staticmethod
    def margin_calls_from_dataframe(df: pd.DataFrame) -> list[MarginCall]:
        return [
            MarginCall(
                margin_call_id=row.margin_call_id,
                counterparty_code=row.counterparty_code,
                csa_id=row.csa_id,
                required_amount=row.required_amount,
                currency=row.currency,
                direction=row.direction,
                due_date=row.due_date,
            )
            for row in df.itertuples(index=False)
        ]


class ValuationService:
    def run_collateral_valuation(self) -> pd.DataFrame:
        loader = DataLoadService()
        mapper = MappingService()
        positions = mapper.positions_from_dataframe(loader.load_collateral_positions())
        prices = mapper.prices_from_dataframe(loader.load_market_prices())
        fx_rate = mapper.fx_from_dataframe(loader.load_fx_rates())
        rules = mapper.haircut_rules_from_dataframe(loader.load_haircut_rules())
        engine = CollateralValuationEngine()
        results = [engine.value_position(position, prices, fx_rate, rules) for position in positions]
        return pd.DataFrame(
            [
                {
                    "position_id": result.position_id,
                    "counterparty_code": result.counterparty_code,
                    "fund_code": result.fund_code,
                    "instrument_code": result.instrument_code,
                    "quantity": result.quantity,
                    "dirty_price": result.dirty_price,
                    "price_usd": result.price_usd,
                    "days_to_maturity": result.days_to_maturity,
                    "haircut_factor": result.haircut_factor,
                    "haircut_price": result.haircut_price,
                    "collateral_value": result.collateral_value,
                    "status": result.status,
                    "warnings": "; ".join(result.warnings),
                }
                for result in results
            ]
        )


class OptimizationService:
    def optimize_first_margin_call(self, preserve_cash: bool = True) -> tuple[pd.DataFrame, dict[str, str]]:
        loader = DataLoadService()
        mapper = MappingService()
        margin_calls = mapper.margin_calls_from_dataframe(loader.load_margin_calls())
        inventory = mapper.inventory_from_dataframe(loader.load_inventory())
        engine = CollateralOptimizationEngine()
        result = engine.optimize_margin_call(
            margin_call=margin_calls[0],
            inventory=inventory,
            objective=OptimizationObjective(preserve_cash=preserve_cash),
        )
        allocations = pd.DataFrame([asdict(allocation) for allocation in result.allocations])
        summary = {
            "status": result.status,
            "required_amount": str(result.required_amount),
            "covered_amount": str(result.covered_amount),
            "overcollateralization": str(result.overcollateralization),
            "warnings": "; ".join(result.warnings),
        }
        return allocations, summary

