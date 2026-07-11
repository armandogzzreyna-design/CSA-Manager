from datetime import date
from decimal import Decimal

from csa_manager.models import InventoryItem, MarginCall, OptimizationObjective
from csa_manager.optimization_engine import CollateralOptimizationEngine


def test_optimizer_preserves_cash_when_requested() -> None:
    margin_call = MarginCall("MC1", "DBBNP", "CSA1", Decimal("100"), "USD", "DELIVER", date(2026, 7, 11))
    inventory = [
        InventoryItem("CASH1", "CASH", "DBBNP", "SIEFORE 65", "CASH", "USD", Decimal("1000"), Decimal("1"), True, True, Decimal("1"), 0),
        InventoryItem("SEC1", "BONO", "DBBNP", "SIEFORE 65", "SECURITY", "USD", Decimal("100"), Decimal("2"), False, True, Decimal("0.1"), 1),
    ]
    result = CollateralOptimizationEngine().optimize_margin_call(
        margin_call,
        inventory,
        OptimizationObjective(preserve_cash=True),
    )
    assert result.status == "FEASIBLE"
    assert result.allocations[0].inventory_id == "SEC1"
    assert result.covered_amount == Decimal("100")

