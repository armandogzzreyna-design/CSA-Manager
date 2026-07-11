from __future__ import annotations

from decimal import Decimal

from csa_manager.models import (
    CollateralAllocation,
    InventoryItem,
    MarginCall,
    OptimizationObjective,
    OptimizationResult,
)


class CollateralOptimizationProblem:
    def __init__(
        self,
        margin_call: MarginCall,
        inventory: list[InventoryItem],
        objective: OptimizationObjective,
    ) -> None:
        self.margin_call = margin_call
        self.inventory = inventory
        self.objective = objective


class ProblemValidator:
    def validate(self, problem: CollateralOptimizationProblem) -> list[str]:
        warnings: list[str] = []
        if problem.margin_call.required_amount <= 0:
            warnings.append("Margin call required amount must be positive")
        if not problem.inventory:
            warnings.append("No inventory available")
        for item in problem.inventory:
            if item.available_quantity < 0:
                warnings.append(f"Inventory {item.inventory_id} has negative available quantity")
            if item.unit_collateral_value < 0:
                warnings.append(f"Inventory {item.inventory_id} has negative collateral value")
        return warnings


class GreedyCollateralSolver:
    def solve(self, problem: CollateralOptimizationProblem) -> OptimizationResult:
        validation_warnings = ProblemValidator().validate(problem)
        if validation_warnings:
            return OptimizationResult(
                margin_call_id=problem.margin_call.margin_call_id,
                status="FAILED",
                required_amount=problem.margin_call.required_amount,
                covered_amount=Decimal("0"),
                overcollateralization=Decimal("0"),
                allocations=[],
                warnings=validation_warnings,
            )

        candidates = [
            item for item in problem.inventory
            if item.is_eligible
            and item.currency == problem.margin_call.currency
            and item.counterparty_code == problem.margin_call.counterparty_code
            and item.available_quantity > 0
            and item.unit_collateral_value > 0
        ]

        if problem.objective.preserve_cash:
            candidates.sort(key=lambda item: (item.is_cash, item.opportunity_cost, item.settlement_lag_days))
        else:
            candidates.sort(key=lambda item: (not item.is_cash, item.opportunity_cost, item.settlement_lag_days))

        allocations: list[CollateralAllocation] = []
        covered = Decimal("0")
        required = problem.margin_call.required_amount

        for item in candidates:
            if covered >= required:
                break
            remaining = required - covered
            max_value = item.available_quantity * item.unit_collateral_value
            allocation_value = min(max_value, remaining)
            quantity = allocation_value / item.unit_collateral_value
            covered += allocation_value
            allocations.append(
                CollateralAllocation(
                    inventory_id=item.inventory_id,
                    asset_id=item.asset_id,
                    fund_code=item.fund_code,
                    quantity=quantity,
                    collateral_value=allocation_value,
                    currency=item.currency,
                    explanation=(
                        "Selected because it is eligible, available, matches margin call currency "
                        "and ranked favorably under the configured objective."
                    ),
                )
            )
            if problem.objective.max_line_items and len(allocations) >= problem.objective.max_line_items:
                break

        warnings: list[str] = []
        if covered < required:
            warnings.append("Eligible inventory is insufficient to fully cover the margin call")
            status = "PARTIAL" if covered > 0 else "INFEASIBLE"
        else:
            status = "FEASIBLE"

        return OptimizationResult(
            margin_call_id=problem.margin_call.margin_call_id,
            status=status,
            required_amount=required,
            covered_amount=covered,
            overcollateralization=max(Decimal("0"), covered - required),
            allocations=allocations,
            warnings=warnings,
        )


class CollateralOptimizationEngine:
    def __init__(self, solver: GreedyCollateralSolver | None = None) -> None:
        self.solver = solver or GreedyCollateralSolver()

    def optimize_margin_call(
        self,
        margin_call: MarginCall,
        inventory: list[InventoryItem],
        objective: OptimizationObjective | None = None,
    ) -> OptimizationResult:
        problem = CollateralOptimizationProblem(
            margin_call=margin_call,
            inventory=inventory,
            objective=objective or OptimizationObjective(),
        )
        return self.solver.solve(problem)

