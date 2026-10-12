"""Deterministic Decision Integrity Calculation Engine (Day 8G-A).

Implements precision-safe numerical calculations, unit-aware conversions, and
domain arithmetic evaluation using Python Decimal. Never invents missing values;
returns explicit CalculationStatus.UNRESOLVED with missing variable names when
inputs are absent.
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.decision_integrity import (
    CalculationResult,
    CalculationStatus,
)
from app.schemas.decision_model import DecisionModel
from app.schemas.recommendation import DecisionRecommendation

logger = logging.getLogger(__name__)


def _to_decimal(val: Any) -> Optional[Decimal]:
    """Safely converts string, int, float, or dict to Decimal."""
    if val is None:
        return None
    if isinstance(val, Decimal):
        return val
    if isinstance(val, (int, float)):
        return Decimal(str(val))
    if isinstance(val, str):
        cleaned = re.sub(r"[^\d.-]", "", val.strip())
        if not cleaned or cleaned in ("-", ".", "-."):
            return None
        try:
            return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            return None
    return None


def _format_float(dec: Optional[Decimal]) -> Optional[float]:
    """Converts Decimal to round float for API serialization."""
    if dec is None:
        return None
    try:
        return float(dec.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))
    except Exception:
        return float(dec)


class DeterministicCalculator:
    """Evaluates mathematical feasibility and arithmetic consistency deterministically."""

    def evaluate_all(
        self,
        decision_model: DecisionModel,
        recommendation: DecisionRecommendation,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[CalculationResult]:
        """Runs all applicable deterministic calculations across the decision model and context."""
        results: List[CalculationResult] = []
        ctx = context or {}

        # 1. Net Support / Automation Savings calculation
        results.append(self._calculate_net_support_savings(decision_model, ctx))

        # 2. Annualized vs Monthly Operational Cost calculation
        results.append(self._calculate_annualized_cost(decision_model, ctx))

        # 3. Budget / Cost Ceiling Feasibility
        results.append(self._calculate_cost_ceiling_feasibility(decision_model, ctx))

        return results

    def _calculate_net_support_savings(
        self,
        decision_model: DecisionModel,
        context: Dict[str, Any],
    ) -> CalculationResult:
        """Evaluates net annual savings:

        annual_gross_savings = annual_eligible_support_cost * realized_deflection_fraction * avoidable_cost_fraction
        annual_cloud_cost = monthly_cloud_cost * 12
        annual_net_savings = annual_gross_savings - annual_cloud_cost - other_recurring_costs
        net_savings_rate = annual_net_savings / annual_baseline_support_cost
        """
        calc_id = "calc_net_savings"
        formula = (
            "annual_net_savings = (annual_eligible_cost * deflection * avoidable_fraction) "
            "- (monthly_cloud_cost * 12) - other_recurring_costs"
        )

        # Extract available values from context or decision model variables
        eligible_cost = _to_decimal(
            context.get("annual_eligible_support_cost")
            or context.get("support_budget")
            or context.get("current_support_cost")
            or context.get("annual_support_cost")
        )
        deflection = _to_decimal(
            context.get("realized_deflection_fraction")
            or context.get("deflection_rate")
            or context.get("target_deflection")
        )
        avoidable = _to_decimal(
            context.get("avoidable_cost_fraction")
            or context.get("avoidable_fraction")
        )
        monthly_cloud = _to_decimal(
            context.get("monthly_cloud_cost")
            or context.get("monthly_tool_cost")
            or context.get("monthly_infrastructure_cost")
        )
        other_costs = _to_decimal(
            context.get("other_incremental_annual_costs")
            or context.get("maintenance_cost")
            or Decimal("0")
        )

        input_values: Dict[str, Any] = {}
        missing_inputs: List[str] = []

        if eligible_cost is not None:
            input_values["annual_eligible_support_cost"] = float(eligible_cost)
        else:
            missing_inputs.append("annual_eligible_support_cost")

        if deflection is not None:
            # If provided as percentage > 1 (e.g. 35 for 35%), normalize to fraction
            if deflection > 1:
                deflection = deflection / Decimal("100")
            input_values["realized_deflection_fraction"] = float(deflection)
        else:
            missing_inputs.append("realized_deflection_fraction")

        if avoidable is not None:
            if avoidable > 1:
                avoidable = avoidable / Decimal("100")
            input_values["avoidable_cost_fraction"] = float(avoidable)
        else:
            # Avoidable cost fraction is often omitted; we must NOT assume 100% avoidable
            missing_inputs.append("avoidable_cost_fraction (unresolved: non-deflected labor reallocation unknown)")

        if monthly_cloud is not None:
            input_values["monthly_cloud_cost"] = float(monthly_cloud)
        else:
            missing_inputs.append("monthly_cloud_cost")

        if missing_inputs:
            return CalculationResult(
                calculation_id=calc_id,
                title="Annual Net Savings Calculation",
                category="net_savings",
                status=CalculationStatus.UNRESOLVED,
                formula_expression=formula,
                input_values=input_values,
                missing_inputs=missing_inputs,
                assumptions=[
                    "Deflection does not equal 100% labor savings unless avoidable cost fraction is explicitly proven.",
                    "Cloud and infrastructure costs compound monthly and must be annualized (x12).",
                ],
                explanation=(
                    f"Calculation unresolved because essential variables ({', '.join(missing_inputs)}) "
                    "are not provided in structured data. Gross savings cannot be conflated with net savings."
                ),
            )

        # Full deterministic calculation
        annual_gross = eligible_cost * deflection * avoidable
        annual_cloud = monthly_cloud * Decimal("12")
        annual_net = annual_gross - annual_cloud - (other_costs or Decimal("0"))

        status = CalculationStatus.FEASIBLE if annual_net > Decimal("0") else CalculationStatus.INFEASIBLE

        return CalculationResult(
            calculation_id=calc_id,
            title="Annual Net Savings Calculation",
            category="net_savings",
            status=status,
            value=_format_float(annual_net),
            unit="USD",
            currency="USD",
            formula_expression=formula,
            input_values=input_values,
            missing_inputs=[],
            assumptions=[
                f"Avoidable cost fraction confirmed at {float(avoidable * 100):.1f}%.",
                f"Monthly cloud expense annualized to ${float(annual_cloud):,.2f}.",
            ],
            explanation=(
                f"Projected net annual savings is ${float(annual_net):,.2f} "
                f"(Gross savings ${float(annual_gross):,.2f} minus annualized costs ${float(annual_cloud):,.2f})."
            ),
        )

    def _calculate_annualized_cost(
        self,
        decision_model: DecisionModel,
        context: Dict[str, Any],
    ) -> CalculationResult:
        """Evaluates annualized operating costs from recurring monthly expenses."""
        calc_id = "calc_annualized_cost"
        formula = "annual_operating_cost = monthly_recurring_cost * 12 + annual_fixed_overhead"

        monthly = _to_decimal(
            context.get("monthly_cost")
            or context.get("monthly_cloud_cost")
            or context.get("monthly_subscription")
        )
        overhead = _to_decimal(context.get("annual_overhead") or Decimal("0"))

        input_values: Dict[str, Any] = {}
        missing_inputs: List[str] = []

        if monthly is not None:
            input_values["monthly_recurring_cost"] = float(monthly)
        else:
            missing_inputs.append("monthly_recurring_cost")

        if missing_inputs:
            return CalculationResult(
                calculation_id=calc_id,
                title="Annualized Operating Cost",
                category="annualized_cost",
                status=CalculationStatus.UNRESOLVED,
                formula_expression=formula,
                input_values=input_values,
                missing_inputs=missing_inputs,
                assumptions=["Monthly operational costs must be multiplied by 12 to compare against annual budgets."],
                explanation="Cannot compute annualized operating cost: recurring monthly cost input is absent.",
            )

        annual_total = (monthly * Decimal("12")) + (overhead or Decimal("0"))

        return CalculationResult(
            calculation_id=calc_id,
            title="Annualized Operating Cost",
            category="annualized_cost",
            status=CalculationStatus.FEASIBLE,
            value=_format_float(annual_total),
            unit="USD",
            currency="USD",
            formula_expression=formula,
            input_values=input_values,
            missing_inputs=[],
            assumptions=["12 billing periods per calendar year."],
            explanation=f"Annualized recurring operational expense is ${float(annual_total):,.2f}.",
        )

    def _calculate_cost_ceiling_feasibility(
        self,
        decision_model: DecisionModel,
        context: Dict[str, Any],
    ) -> CalculationResult:
        """Compares estimated project/operating cost against stated budget ceiling."""
        calc_id = "calc_cost_ceiling_feasibility"
        formula = "budget_surplus = stated_cost_ceiling - estimated_total_cost"

        # Search for ceiling in context or constraints
        ceiling = _to_decimal(
            context.get("budget_usd")
            or context.get("budget")
            or context.get("cost_ceiling")
            or context.get("max_cost")
        )
        estimated_cost = _to_decimal(
            context.get("estimated_cost")
            or context.get("project_cost")
            or context.get("total_cost")
        )

        # Inspect constraints for budget figures if missing from context
        if ceiling is None:
            for cnstr in decision_model.constraints:
                stmt = getattr(cnstr, "statement", None) or getattr(cnstr, "description", "")
                match = re.search(r"\$?\s*(\d+[\d,]*(\.\d+)?)\s*(k|m|thousand|million)?", stmt, re.I)
                if match:
                    base_str = match.group(1).replace(",", "")
                    mult = match.group(3)
                    try:
                        val = Decimal(base_str)
                        if mult and mult.lower() in ("k", "thousand"):
                            val *= Decimal("1000")
                        elif mult and mult.lower() in ("m", "million"):
                            val *= Decimal("1000000")
                        ceiling = val
                        break
                    except Exception:
                        pass

        input_values: Dict[str, Any] = {}
        missing_inputs: List[str] = []

        if ceiling is not None:
            input_values["stated_cost_ceiling"] = float(ceiling)
        else:
            missing_inputs.append("stated_cost_ceiling")

        if estimated_cost is not None:
            input_values["estimated_total_cost"] = float(estimated_cost)
        else:
            missing_inputs.append("estimated_total_cost")

        if missing_inputs:
            return CalculationResult(
                calculation_id=calc_id,
                title="Cost Ceiling Feasibility",
                category="cost_ceiling",
                status=CalculationStatus.UNRESOLVED,
                formula_expression=formula,
                input_values=input_values,
                missing_inputs=missing_inputs,
                assumptions=["Cost ceiling must be explicitly bounded by stated financial constraint."],
                explanation=f"Cannot determine budget feasibility: missing {', '.join(missing_inputs)}.",
            )

        diff = ceiling - estimated_cost
        status = CalculationStatus.FEASIBLE if diff >= Decimal("0") else CalculationStatus.INFEASIBLE

        return CalculationResult(
            calculation_id=calc_id,
            title="Cost Ceiling Feasibility",
            category="cost_ceiling",
            status=status,
            value=_format_float(diff),
            unit="USD",
            currency="USD",
            formula_expression=formula,
            input_values=input_values,
            missing_inputs=[],
            assumptions=["Estimated total cost includes implementation and first-year run costs."],
            explanation=(
                f"Budget surplus of ${float(diff):,.2f} relative to ceiling ${float(ceiling):,.2f}."
                if diff >= 0
                else f"Budget deficit of ${float(abs(diff)):,.2f}! Stated ceiling ${float(ceiling):,.2f} breached."
            ),
        )
