"""Frozen B1 design constants."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
ARTIFACT_ROOT = ROOT / "artifacts" / "la1_3_ara_b1"
HANDOFF_ROOT = ROOT / "_historical_handoff_not_distributed"
SEED_FILE = ROOT / "configs" / "b11_global" / "frozen_seeds.json"
PROFILE_FILE = ROOT / "configs" / "b11_global" / "selected_operating_points.json"
CONFIG_FILE = ROOT / "configs" / "b11_global" / "b1_frozen_config.yaml"

PROFILES = (
    "RISK_CONSERVATIVE",
    "BALANCED",
    "RESOLUTION_FAVORING",
)
PROFILE_PARAMETERS = {
    "RISK_CONSERVATIVE": (0.025, 0.40, 0.50),
    "BALANCED": (0.077, 0.35, 0.60),
    "RESOLUTION_FAVORING": (0.15, 0.25, 0.40),
}
BUDGETS = (0.10, 0.20, 0.35, 0.50, 0.75, 1.00)
BASELINES = (
    "ARA_LOWER_ONLY",
    "STATIC_FARTHEST",
    "CANONICAL_GROUP_ORDER",
    "RANDOM_HASH_ORDER",
)
NEAR_THRESHOLD = 0.10
HP_DIGITS = 90
FAR_AUDIT_COUNT = 32


@dataclass(frozen=True)
class Condition:
    name: str
    sample_size: int
    scale: float
    truth_nu: float
    bank_template: str
    candidate_count: int
    oracle_cap_seconds: float


CONDITIONS = (
    Condition(
        "LOW_INFORMATION_F0", 4096, 0.35, 1.20, "FULL", 1025, 1200.0
    ),
    Condition(
        "INTERMEDIATE_INFORMATION_S3",
        65536,
        0.50,
        0.90,
        "FULL",
        1025,
        3000.0,
    ),
    Condition(
        "HIGH_INFORMATION_R3",
        131072,
        0.50,
        0.80,
        "NARROW",
        369,
        4200.0,
    ),
)

SMOKE = Condition("SMOKE", 1024, 0.35, 1.20, "FULL", 1025, 1800.0)
SMOKE_SEEDS = (2026080101, 9026080101)
REGRESSION_SEEDS = (2026072831, 9026072831)

EXPECTED_EXTERNAL_ZIPS = {
    "B01": "4038e2b211e1068c1735c49846032286b08c4c39838c1bbb96703ed26d44f2aa",
    "B1D0": "9f6f57d8546a6c97c5a92a0aa966ac15b1d29a2d5ecac6bd6d3459b72dbbac55",
    "B1P0": "1394630102aa0db5d61fe5af50b343afc34983fe8a8bfe8843271114c1e5ada0",
    "B1P0L": "f08144c534bfb6f2c1cf00b239a374c290a9094c7675ac33dca5534dfbe83294",
}
EXPECTED_FREEZES = {
    "design": "bb00e447e6f7e4fa242b4774a504d4bfd524ff18dc73c799d1e50247fbec0be7",
    "policy": "fb2778d8cd773af010d62c52d9cee7b2b2779cb86de1f52f7cdb6f7deb777316",
}
EXPECTED_POLICY_SOURCE_HASHES = {
    "ara_controller.py": "3ce69d27e4b36732c6c76f5de769ee5a0f5cb6de4f228283061ceb2a9230d69f",
    "evidence.py": "e2addc287aea1e7714bd3f4eee5a2873ae8e0bb34f848b795d931c0db5faf312",
    "geometry.py": "c0fe734f1d545c1ba48efbd9f8962ee16ec1942c8b6108b96c38811d99434245",
    "guards.py": "69b7edaeb3fb49794e2585a98ae4df6f470ca38c04bdaebb566997c1bba603f4",
    "sealed_query.py": "047f5f3200ff0831544d7887e501a24490e7f66f47573fa4f76938eacefe880e",
}
