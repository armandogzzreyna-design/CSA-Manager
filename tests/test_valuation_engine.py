from datetime import date
from decimal import Decimal

from csa_manager.models import FXRate, HaircutRule
from csa_manager.valuation_engine import DayCountCalculator, FXConverter, HaircutEngine, MaturityResolver


def test_maturity_resolver_uses_yymmdd_suffix() -> None:
    maturity, warnings, _ = MaturityResolver().resolve("BONO M 260915")
    assert maturity == date(2026, 9, 15)
    assert warnings == []


def test_day_count_uses_30_360_us_absolute() -> None:
    days = DayCountCalculator().days_360_us(date(2026, 9, 15), date(2026, 7, 10))
    assert days == 65


def test_fx_converter_preserves_bbva_price() -> None:
    price, fx_used, _ = FXConverter().price_to_usd(
        "BBVA",
        Decimal("99.80"),
        FXRate(date(2026, 7, 10), "USD", "MXN", Decimal("18.25"), "BANXICO"),
    )
    assert price == Decimal("99.80")
    assert fx_used is None


def test_haircut_engine_preserves_bbva_overlap_priority() -> None:
    rules = [
        HaircutRule("A", "BBVA", "CONTAINS", 1, 364, Decimal("0.99"), 10, "first"),
        HaircutRule("B", "BBVA", "CONTAINS", 361, 1092, Decimal("0.98"), 20, "second"),
    ]
    factor, rule, warnings, _ = HaircutEngine().resolve("BBVA", 362, rules)
    assert factor == Decimal("0.99")
    assert rule is not None
    assert rule.rule_id == "A"
    assert warnings == []

