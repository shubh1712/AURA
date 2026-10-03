"""AURA Decision Model Schema.

Defines the canonical, strongly-typed decomposition structure representing
an analyzed decision problem. Serves as the structured interface between
intake/decomposition and downstream cognitive/deterministic engines.
"""

from enum import Enum
from typing import Any, List, Optional, Set, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ------------------------------------------------------------------------------
# Enums
# ------------------------------------------------------------------------------

class ProvenanceType(str, Enum):
    """Epistemic origin and audit classification of decision model information."""
    USER_PROVIDED = "user_provided"  # Directly and explicitly stated by the user
    INFERRED = "inferred"            # Deduced, synthesized, or projected by AI/heuristics
    UNKNOWN = "unknown"              # Explicitly identified as missing, unverified, or unresolved


class DecisionType(str, Enum):
    """Categorical taxonomy of the decision domain."""
    RESOURCE_ALLOCATION = "resource_allocation"      # Headcount, budget, infrastructure
    STRATEGIC_DIRECTION = "strategic_direction"      # Market entry, business model, pricing
    ARCHITECTURE_TECH = "architecture_technology"    # Tech stack, framework, migration
    OPERATIONAL_POLICY = "operational_policy"        # Release cadence, remote work, SLAs
    PRODUCT_ROADMAP = "product_roadmap"              # Feature prioritization, MVP scope
    GENERAL_CHOICE = "general_choice"                # Fallback categorical selection


class TimeHorizon(str, Enum):
    """Estimated operational timeframe over which consequences unfold."""
    IMMEDIATE = "immediate"      # Days to 1 month
    SHORT_TERM = "short_term"    # 1 to 6 months
    MEDIUM_TERM = "medium_term"  # 6 to 18 months
    LONG_TERM = "long_term"      # 18+ months


class ComplexityLevel(str, Enum):
    """Assessed overall decision complexity."""
    LOW = "low"          # Isolated decision with few variables and localized impact
    MEDIUM = "medium"    # Multi-variable under uncertainty; moderate blast radius
    HIGH = "high"        # Systemic, multi-stakeholder, high-irreversibility


class ReversibilityLevel(str, Enum):
    """Ease and cost of unwinding the decision once executed."""
    REVERSIBLE = "reversible"                # Two-way door: low cost to revert
    PARTIALLY_REVERSIBLE = "partially_reversible"  # Moderate cost/friction to unwind
    IRREVERSIBLE = "irreversible"            # One-way door: near-impossible or fatal to reverse


class VariableType(str, Enum):
    """Data type classification for a decision parameter."""
    PERCENTAGE = "percentage"    # e.g., -20%
    CURRENCY = "currency"        # e.g., $40,000
    NUMERIC = "numeric"          # e.g., 5 nodes, 10 headcount
    BOOLEAN = "boolean"          # e.g., True / False toggle
    CATEGORICAL = "categorical"  # e.g., "Postgres" vs "CockroachDB"
    QUALITATIVE = "qualitative"  # Descriptive state with no direct numeric mapping


class CriticalityLevel(str, Enum):
    """Importance or severity level for variables, stakeholders, or unknowns."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ConfidenceLevel(str, Enum):
    """Level of empirical certainty behind an assumption."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNTESTED = "untested"


# ------------------------------------------------------------------------------
# Nested Domain Models
# ------------------------------------------------------------------------------

class Decision(BaseModel):
    """Core decision statement and scope classification."""
    model_config = ConfigDict(str_strip_whitespace=True)

    raw_prompt: str = Field(
        ...,
        min_length=5,
        description="Original, verbatim user question or prompt.",
    )
    summary: str = Field(
        ...,
        min_length=5,
        description="Concise, unambiguous statement of the central decision being made.",
    )
    decision_type: DecisionType = Field(
        ...,
        description="Domain categorization for routing to specialized heuristic playbooks.",
    )
    time_horizon: TimeHorizon = Field(
        ...,
        description="Operational timeframe over which consequences are modeled.",
    )


class Complexity(BaseModel):
    """Evaluation of structural difficulty, coupling, and reversibility."""
    model_config = ConfigDict(str_strip_whitespace=True)

    level: ComplexityLevel = Field(
        ...,
        description="Categorical assessment of complexity (low, medium, high).",
    )
    reasoning: str = Field(
        ...,
        min_length=5,
        description="Explanation of factors driving the complexity rating.",
    )
    reversibility: ReversibilityLevel = Field(
        ...,
        description="Ease and cost of unwinding the decision (one-way vs two-way door).",
    )
    score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Deterministic complexity score between 0.0 and 100.0.",
    )


class Objective(BaseModel):
    """Specific goal or target outcome the decision seeks to achieve."""
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique identifier (e.g. 'obj_primary', 'obj_2').",
    )
    description: str = Field(
        ...,
        min_length=3,
        description="Natural-language definition of the objective.",
    )
    is_primary: bool = Field(
        default=False,
        description="True if this is the foundational objective; False if secondary.",
    )
    target_metric: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Optional quantifiable metric indicating success (e.g. '+30% acquisition').",
    )
    provenance: ProvenanceType = Field(
        default=ProvenanceType.INFERRED,
        description="Epistemic provenance (user_provided, inferred, unknown).",
    )


class Variable(BaseModel):
    """A parameter, lever, or changing factor that governs the decision."""
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique identifier (e.g. 'var_price_discount').",
    )
    name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Human-readable variable label.",
    )
    description: str = Field(
        ...,
        min_length=3,
        description="Detailed description of the role this variable plays in the decision.",
    )
    variable_type: VariableType = Field(
        ...,
        description="Data type classification for mathematical simulation.",
    )
    baseline_value: Optional[Union[float, int, str, bool]] = Field(
        default=None,
        description="Status-quo value prior to decision execution.",
    )
    proposed_value: Optional[Union[float, int, str, bool]] = Field(
        default=None,
        description="Candidate value under consideration.",
    )
    unit: Optional[str] = Field(
        default=None,
        max_length=30,
        description="Unit of measurement (e.g. '%', 'USD', 'users', 'ms').",
    )
    is_controllable: bool = Field(
        default=True,
        description="True if internal lever controlled by decision-maker; False if external factor.",
    )
    provenance: ProvenanceType = Field(
        default=ProvenanceType.INFERRED,
        description="Epistemic provenance of variable identification (user_provided, inferred, unknown).",
    )
    baseline_provenance: Optional[ProvenanceType] = Field(
        default=None,
        description="Provenance of baseline_value (user_provided, inferred, unknown).",
    )
    proposed_provenance: Optional[ProvenanceType] = Field(
        default=None,
        description="Provenance of proposed_value (user_provided, inferred, unknown).",
    )


class Constraint(BaseModel):
    """A boundary, restriction, or threshold that candidate options must satisfy."""
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique identifier (e.g. 'cnstr_margin').",
    )
    name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Short label for the constraint.",
    )
    description: str = Field(
        ...,
        min_length=3,
        description="Statement of the constraint condition.",
    )
    is_hard_constraint: bool = Field(
        default=False,
        description="True if non-negotiable boundary; False if soft preference.",
    )
    threshold_expression: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Mathematical/logical bound for deterministic evaluation (e.g. 'gross_margin >= 0.65').",
    )
    source: str = Field(
        default="user_specified",
        max_length=50,
        description="Origin of constraint ('user_specified', 'inferred_operational', 'regulatory').",
    )
    provenance: ProvenanceType = Field(
        default=ProvenanceType.INFERRED,
        description="Epistemic provenance (user_provided, inferred, unknown).",
    )

    @model_validator(mode="after")
    def sync_provenance_and_source(self) -> "Constraint":
        """Synchronizes source and provenance to avoid inconsistencies."""
        if self.source == "user_specified" and self.provenance == ProvenanceType.INFERRED:
            self.provenance = ProvenanceType.USER_PROVIDED
        elif self.source != "user_specified" and self.provenance == ProvenanceType.USER_PROVIDED:
            self.source = "user_specified"
        return self


class Stakeholder(BaseModel):
    """An internal or external party affected by the decision."""
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique identifier (e.g. 'stk_customers').",
    )
    group: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Name of the stakeholder group or organizational role.",
    )
    impact_nature: str = Field(
        ...,
        min_length=3,
        description="Description of how this group is impacted.",
    )
    influence_level: CriticalityLevel = Field(
        default=CriticalityLevel.MEDIUM,
        description="Influence of stakeholder group on the success of the decision.",
    )
    provenance: ProvenanceType = Field(
        default=ProvenanceType.INFERRED,
        description="Epistemic provenance (user_provided, inferred, unknown).",
    )


class Tradeoff(BaseModel):
    """An explicit tension between competing advantages and disadvantages."""
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique identifier (e.g. 'trd_margin_vs_volume').",
    )
    upside: str = Field(
        ...,
        min_length=3,
        description="What is gained or optimized by this path.",
    )
    downside: str = Field(
        ...,
        min_length=3,
        description="What is sacrificed or risked by this path.",
    )
    affected_variable_ids: List[str] = Field(
        default_factory=list,
        description="IDs of Variables directly involved in this tension.",
    )
    provenance: ProvenanceType = Field(
        default=ProvenanceType.INFERRED,
        description="Epistemic provenance (user_provided, inferred, unknown).",
    )


class Unknown(BaseModel):
    """A missing piece of empirical information critical to resolving the decision."""
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique identifier (e.g. 'unk_competitor_reaction').",
    )
    question: str = Field(
        ...,
        min_length=5,
        description="The specific factual unknown question that needs investigation.",
    )
    criticality: CriticalityLevel = Field(
        default=CriticalityLevel.MEDIUM,
        description="Importance of resolving this unknown before commitment.",
    )
    potential_sources: List[str] = Field(
        default_factory=list,
        description="Potential evidence or data sources for investigation.",
    )
    provenance: ProvenanceType = Field(
        default=ProvenanceType.UNKNOWN,
        description="Epistemic provenance (always unknown for information gaps).",
    )


class Assumption(BaseModel):
    """An unverified belief taken for granted without empirical backing."""
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique identifier (e.g. 'asm_elasticity').",
    )
    statement: str = Field(
        ...,
        min_length=5,
        description="The assumed premise.",
    )
    confidence: ConfidenceLevel = Field(
        default=ConfidenceLevel.UNTESTED,
        description="Current confidence level in this assumption.",
    )
    falsification_condition: Optional[str] = Field(
        default=None,
        description="Specific metric or event that would prove this assumption false.",
    )
    provenance: ProvenanceType = Field(
        default=ProvenanceType.INFERRED,
        description="Epistemic provenance (unverified premise, always inferred).",
    )


# ------------------------------------------------------------------------------
# Top-Level Canonical DecisionModel
# ------------------------------------------------------------------------------

class DecisionModel(BaseModel):
    """Canonical domain representation of a decomposed decision problem.

    Provides the structured schema consumed by downstream cognitive reasoning
    and deterministic simulation engines.
    """
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Globally unique identifier for this decomposed decision model.",
    )
    decision: Decision = Field(
        ...,
        description="Core decision statement, scope, and categorization.",
    )
    complexity: Complexity = Field(
        ...,
        description="Structural complexity and reversibility assessment.",
    )
    objectives: List[Objective] = Field(
        ...,
        min_length=1,
        description="Goal hierarchy (must contain at least one primary objective).",
    )
    variables: List[Variable] = Field(
        ...,
        min_length=1,
        description="Controllable parameters and environmental variables.",
    )
    constraints: List[Constraint] = Field(
        default_factory=list,
        description="Hard boundaries and soft preferences.",
    )
    stakeholders: List[Stakeholder] = Field(
        default_factory=list,
        description="Internal and external affected groups.",
    )
    tradeoffs: List[Tradeoff] = Field(
        ...,
        min_length=1,
        description="Inherent trade-offs and tensions between options.",
    )
    assumptions: List[Assumption] = Field(
        default_factory=list,
        description="Unverified premises accepted as true.",
    )
    unknowns: List[Unknown] = Field(
        default_factory=list,
        description="High-impact information gaps requiring empirical evidence.",
    )
    key_questions: List[str] = Field(
        ...,
        min_length=1,
        description="Crucial sub-questions that must be answered to reach a resolution.",
    )

    @model_validator(mode="after")
    def validate_primary_objective_exists(self) -> "DecisionModel":
        """Ensures that exactly one or more objectives are marked as primary."""
        has_primary = any(obj.is_primary for obj in self.objectives)
        if not has_primary:
            raise ValueError(
                "DecisionModel must contain at least one primary objective (is_primary=True)."
            )
        return self

    @model_validator(mode="after")
    def validate_entity_ids_unique(self) -> "DecisionModel":
        """Enforces ID uniqueness within each individual collection."""
        collections = {
            "objectives": [o.id for o in self.objectives],
            "variables": [v.id for v in self.variables],
            "constraints": [c.id for c in self.constraints],
            "stakeholders": [s.id for s in self.stakeholders],
            "tradeoffs": [t.id for t in self.tradeoffs],
            "assumptions": [a.id for a in self.assumptions],
            "unknowns": [u.id for u in self.unknowns],
        }

        for collection_name, ids in collections.items():
            seen: Set[str] = set()
            for entity_id in ids:
                if entity_id in seen:
                    raise ValueError(
                        f"Duplicate ID '{entity_id}' found in '{collection_name}' collection."
                    )
                seen.add(entity_id)

        return self

    @model_validator(mode="after")
    def validate_tradeoff_variable_references(self) -> "DecisionModel":
        """Ensures that affected_variable_ids in tradeoffs reference valid variables."""
        valid_variable_ids = {v.id for v in self.variables}
        for tradeoff in self.tradeoffs:
            for var_id in tradeoff.affected_variable_ids:
                if var_id not in valid_variable_ids:
                    raise ValueError(
                        f"Tradeoff '{tradeoff.id}' references non-existent variable ID '{var_id}'."
                    )
        return self
