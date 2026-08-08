"""Typed B0.1 settings over the inherited exact scientific kernel."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "artifacts" / "la1_3_ara_b01"
FROZEN_CONFIG = ROOT / "configs" / "ara_b01_frozen_config.yaml"
FROZEN_SEEDS = ROOT / "configs" / "frozen_seeds.json"
SCENARIO_LADDER = ROOT / "tables" / "scenario_ladder.csv"
BANK_TEMPLATES = ROOT / "tables" / "bank_templates.csv"
CONTINUOUS_DEMO = ROOT / "reference" / "CONTINUOUS_DEMO_SUMMARY.json"
PAIRED_SCHEMA = ROOT / "schemas" / "paired_result_schema.json"

EXPERIMENT_ID = "LA1_3_ARA_B01"
VERSION = "B0.1"
PRIMARY_ALPHA = 0.077
ALPHA_GRID = (0.025, 0.05, 0.077, 0.10, 0.15)
RESOLUTION_FRACTIONS = (0.10, 0.20, 0.30, 0.40, 0.50)
CANDIDATE_COUNT = 1025  # inherited FULL-bank compatibility constant
MAXIMUM_UNIQUE_QUERIES = 320
MAXIMUM_HIGH_PRECISION_REPLAYS = 48
MAXIMUM_ACCEPTED_WITNESSES = 16
MAXIMUM_ANCHORS = 4
ARA_WALL_SECONDS = 900.0
MEMORY_GB = 8.0
NEAR_SHELL_STOP_FRACTION = 0.98
IMPROVEMENT_TOLERANCE_FRACTION = 1.0e-4
ORACLE_NEAR_SCORE = 0.10
ORACLE_FAR_AUDIT_COUNT = 32
DIAMETER_TOLERANCE = 1.0e-12


@dataclass(frozen=True)
class Scenario:
    name: str
    sample_size: int
    collision_scale: float
    truth_nu: float
    oracle_wall_seconds: float
    bank_template: str = "FULL"
    candidate_id: str = ""


PRIMARY_ROLES = ("FULL", "SECTOR", "RESOLVED")
PRIMARY_REPLICATE_IDS = tuple(
    f"{role}_{index}"
    for role in PRIMARY_ROLES
    for index in range(1, 5)
)
ORACLE_WALL_BY_ROLE = {
    "FULL": 1200.0,
    "SECTOR": 2400.0,
    "RESOLVED": 3600.0,
}


def threshold(alpha: float = PRIMARY_ALPHA) -> float:
    return math.log(1.0 / float(alpha))
