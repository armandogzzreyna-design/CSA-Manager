from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from csa_manager.models import (
    CalculationTrace,
    CollateralPositionInput,
    CollateralValuationResult,
    FXRate,
    HaircutRule,
    MarketPrice,
)


class PriceSelector:
    def select(self, instrument_code: str, prices: list[MarketPrice]) -> tuple[MarketPrice | None, list[str], CalculationTrace]:
        matches = [price for price in prices if instrument_code in price.emission_code]
        warnings: list[str] = []
        trace = CalculationTrace().add(
            "price_selection",
            instrument_code=instrument_code,
            match_count=len(matches),
            method="SUBSTRING_FIRST_MATCH",
        )
        if not matches:
            warnings.append(f"No price found for instrument {instrument_code}")
            return None, warnings, trace
        if len(matches) > 1:
            warnings.append(f"Multiple prices found for instrument {instrument_code}; first match used")
        selected = matches[0]
        trace = trace.add(
            "price_selected",
            price_id=selected.price_id,
            emission_code=selected.emission_code,
            dirty_price=str(selected.dirty_price),
        )
        return selected, warnings, trace


class MaturityResolver:
    def resolve(self, instrument_code: str) -> tuple[date | None, list[str], CalculationTrace]:
        trace = CalculationTrace().add("maturity_resolution", method="YYMMDD_SUFFIX", instrument_code=instrument_code)
        match = re.search(r"(\d{6})\s*$", instrument_code.strip())
        if not match:
            return None, [f"No maturity suffix found for {instrument_code}"], trace
        yy, mm, dd = match.group(1)[0:2], match.group(1)[2:4], match.group(1)[4:6]
        try:
            maturity = date(int("20" + yy), int(mm), int(dd))
        except ValueError:
            return None, [f"Invalid maturity suffix for {instrument_code}"], trace
        return maturity, [], trace.add("maturity_resolved", maturity_date=maturity.isoformat())


class DayCountCalculator:
    def days_360_us(self, start: date, end: date, use_absolute: bool = True) -> int:
        sy, sm, sd = start.year, start.month, start.day
        ey, em, ed = end.year, end.month, end.day
        if sd == 31:
            sd = 30
        if ed == 31 and sd in (30, 31):
            ed = 30
        days = (ey - sy) * 360 + (em - sm) * 30 + (ed - sd)
        return abs(days) if use_absolute else days


class FXConverter:
    def price_to_usd(
        self,
        counterparty_code: str,
        dirty_price: Decimal,
        fx_rate: FXRate,
    ) -> tuple[Decimal, Decimal | None, CalculationTrace]:
        if "BBVA" in counterparty_code.upper():
            return dirty_price, None, CalculationTrace().add(
                "fx_conversion",
                rule="BBVA_KEEP_DIRTY_PRICE",
                price_usd=str(dirty_price),
            )
        price_usd = dirty_price / fx_rate.rate
        return price_usd, fx_rate.rate, CalculationTrace().add(
            "fx_conversion",
            rule="NON_BBVA_DIVIDE_BY_FIX",
            fx_rate=str(fx_rate.rate),
            price_usd=str(price_usd),
        )


class HaircutEngine:
    def resolve(
        self,
        counterparty_code: str,
        days_to_maturity: int | None,
        rules: list[HaircutRule],
    ) -> tuple[Decimal, HaircutRule | None, list[str], CalculationTrace]:
        if days_to_maturity is None:
            return Decimal("1.0"), None, ["No days to maturity; default haircut 1.0 used"], CalculationTrace().add(
                "haircut_resolution",
                factor="1.0",
                reason="MISSING_DAYS",
            )

        applicable: list[HaircutRule] = []
        normalized_counterparty = counterparty_code.upper().strip()
        for rule in rules:
            pattern = rule.counterparty_pattern.upper().strip()
            exact_match = rule.match_type == "EXACT" and normalized_counterparty == pattern
            contains_match = rule.match_type == "CONTAINS" and pattern in normalized_counterparty
            min_ok = rule.min_days_to_maturity is None or days_to_maturity >= rule.min_days_to_maturity
            max_ok = rule.max_days_to_maturity is None or days_to_maturity <= rule.max_days_to_maturity
            if (exact_match or contains_match) and min_ok and max_ok:
                applicable.append(rule)

        if not applicable:
            return Decimal("1.0"), None, [f"No haircut rule found for {counterparty_code}; factor 1.0 used"], CalculationTrace().add(
                "haircut_resolution",
                factor="1.0",
                reason="NO_RULE",
            )

        selected = sorted(applicable, key=lambda rule: rule.priority)[0]
        return selected.factor, selected, [], CalculationTrace().add(
            "haircut_resolution",
            rule_id=selected.rule_id,
            factor=str(selected.factor),
            days_to_maturity=days_to_maturity,
        )


class CollateralValuationEngine:
    def __init__(self) -> None:
        self.price_selector = PriceSelector()
        self.maturity_resolver = MaturityResolver()
        self.day_count = DayCountCalculator()
        self.fx_converter = FXConverter()
        self.haircuts = HaircutEngine()

    def value_position(
        self,
        position: CollateralPositionInput,
        prices: list[MarketPrice],
        fx_rate: FXRate,
        haircut_rules: list[HaircutRule],
    ) -> CollateralValuationResult:
        warnings: list[str] = []
        trace = CalculationTrace()

        selected_price, price_warnings, price_trace = self.price_selector.select(position.instrument_code, prices)
        warnings.extend(price_warnings)
        trace = CalculationTrace([*trace.steps, *price_trace.steps])
        if selected_price is None:
            return CollateralValuationResult(
                position_id=position.position_id,
                counterparty_code=position.counterparty_code,
                fund_code=position.fund_code,
                instrument_code=position.instrument_code,
                quantity=position.quantity,
                dirty_price=None,
                dirty_price_currency=None,
                price_usd=None,
                fx_rate_used=None,
                maturity_date=None,
                days_to_maturity=None,
                haircut_factor=None,
                haircut_price=None,
                gross_value=None,
                collateral_value=None,
                valuation_date=position.valuation_date,
                status="FAILED",
                warnings=warnings,
                trace=trace,
            )

        gross_value = selected_price.dirty_price * position.quantity
        price_usd, fx_used, fx_trace = self.fx_converter.price_to_usd(
            position.counterparty_code,
            selected_price.dirty_price,
            fx_rate,
        )
        trace = CalculationTrace([*trace.steps, *fx_trace.steps])

        maturity, maturity_warnings, maturity_trace = self.maturity_resolver.resolve(position.instrument_code)
        warnings.extend(maturity_warnings)
        trace = CalculationTrace([*trace.steps, *maturity_trace.steps])
        days_to_maturity = self.day_count.days_360_us(maturity, position.valuation_date) if maturity else None

        haircut_factor, _, haircut_warnings, haircut_trace = self.haircuts.resolve(
            position.counterparty_code,
            days_to_maturity,
            haircut_rules,
        )
        warnings.extend(haircut_warnings)
        trace = CalculationTrace([*trace.steps, *haircut_trace.steps])

        haircut_price = price_usd * haircut_factor
        collateral_value = haircut_price * position.quantity
        trace = trace.add(
            "collateral_valuation",
            gross_value=str(gross_value),
            haircut_price=str(haircut_price),
            collateral_value=str(collateral_value),
        )

        return CollateralValuationResult(
            position_id=position.position_id,
            counterparty_code=position.counterparty_code,
            fund_code=position.fund_code,
            instrument_code=position.instrument_code,
            quantity=position.quantity,
            dirty_price=selected_price.dirty_price,
            dirty_price_currency=selected_price.currency,
            price_usd=price_usd,
            fx_rate_used=fx_used,
            maturity_date=maturity,
            days_to_maturity=days_to_maturity,
            haircut_factor=haircut_factor,
            haircut_price=haircut_price,
            gross_value=gross_value,
            collateral_value=collateral_value,
            valuation_date=position.valuation_date,
            status="VALUED",
            warnings=warnings,
            trace=trace,
        )

