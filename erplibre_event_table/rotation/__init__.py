# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from .bounds import pair_floor, precheck
from .construct import build_design, build_greedy, design_applicable
from .galois import IRREDUCIBLES, gf_tables, is_prime_power
from .generate import generate
from .metrics import distance, evaluate, signature, table_conflicts
from .model import (
    Combination,
    Diagnostic,
    Generation,
    Indicators,
    Options,
    Person,
    Placement,
    Problem,
    Table,
    TableConflict,
    validate_problem,
)
from .search import search
from .seats import assign_seats
from .state import RotationState
from .targets import table_targets
from .text import normalize_company

__all__ = [
    "Combination",
    "Diagnostic",
    "Generation",
    "IRREDUCIBLES",
    "Indicators",
    "Options",
    "Person",
    "Placement",
    "Problem",
    "RotationState",
    "Table",
    "TableConflict",
    "assign_seats",
    "build_design",
    "build_greedy",
    "design_applicable",
    "distance",
    "evaluate",
    "generate",
    "gf_tables",
    "is_prime_power",
    "normalize_company",
    "pair_floor",
    "precheck",
    "search",
    "signature",
    "table_conflicts",
    "table_targets",
    "validate_problem",
]
