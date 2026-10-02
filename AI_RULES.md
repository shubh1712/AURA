# AURA AI Development Rules

## General

AURA is a decision-intelligence platform.

Code should prioritize:
- correctness
- modularity
- explainability
- testability
- maintainability

## Before coding

The AI must:
1. Understand the existing architecture.
2. Identify files that need modification.
3. Avoid unnecessary rewrites.
4. Explain the proposed changes.

## During coding

The AI must:
1. Make minimal changes.
2. Follow existing architecture.
3. Avoid unnecessary dependencies.
4. Use strong typing.
5. Keep business logic separate from UI.
6. Keep API routes thin.
7. Validate external input.
8. Never invent unavailable data.

## After coding

The AI must:
1. Run tests.
2. Run linting/build.
3. Report failures.
4. Fix confirmed failures.
5. Summarize changed files.

## AURA-specific

LLMs should handle:
- interpretation
- qualitative reasoning
- hypothesis generation
- scenario narratives

Deterministic code should handle:
- calculations
- thresholds
- constraints
- sensitivity analysis
- resilience evaluation
- numerical comparisons

Evidence must be distinguishable from:
- assumptions
- inferences
- user-provided information

Never claim an assumption is a fact.