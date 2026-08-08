from __future__ import annotations

import hashlib
from pathlib import Path

from physical_support_confidence_sets.b11.public_bank.bank import role_bank
from physical_support_confidence_sets.b11.query_replay.scenario_replay import (
    SCENARIO_REPLAY_DECIMAL_DIGITS,
)
from physical_support_confidence_sets.b11.study.constants import (
    BUDGETS,
    PROFILE_PARAMETERS,
)


def test_frozen_b11_operating_points_and_precision() -> None:
    assert PROFILE_PARAMETERS == {
        "RISK_CONSERVATIVE": (0.025, 0.40, 0.50),
        "BALANCED": (0.077, 0.35, 0.60),
        "RESOLUTION_FAVORING": (0.15, 0.25, 0.40),
    }
    assert BUDGETS == (0.10, 0.20, 0.35, 0.50, 0.75, 1.00)
    assert SCENARIO_REPLAY_DECIMAL_DIGITS == 90


def test_b11_banks_are_canonical_and_truth_containing() -> None:
    full = role_bank("FULL", 1.2)
    narrow = role_bank("NARROW", 0.8)
    assert len(full) == 1025
    assert len(narrow) == 369
    assert full.contains_truth(1.2)
    assert narrow.contains_truth(0.8)
    assert [row.candidate_id for row in full] == list(range(1025))
    assert [row.candidate_id for row in narrow] == list(range(369))


def test_frozen_policy_files_retain_original_hashes() -> None:
    package = Path(__file__).resolve().parents[1] / "src/physical_support_confidence_sets/b11/frozen_policy"
    expected = {
        "ara_controller.py": "3ce69d27e4b36732c6c76f5de769ee5a0f5cb6de4f228283061ceb2a9230d69f",
        "evidence.py": "e2addc287aea1e7714bd3f4eee5a2873ae8e0bb34f848b795d931c0db5faf312",
        "geometry.py": "c0fe734f1d545c1ba48efbd9f8962ee16ec1942c8b6108b96c38811d99434245",
        "sealed_query.py": "047f5f3200ff0831544d7887e501a24490e7f66f47573fa4f76938eacefe880e",
    }
    for name, digest in expected.items():
        assert hashlib.sha256((package / name).read_bytes()).hexdigest() == digest

