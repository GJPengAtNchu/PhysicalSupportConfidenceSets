from __future__ import annotations

import hashlib
import json
from pathlib import Path

from physical_support_confidence_sets.formal_b2.bank import build_candidate_bank
from physical_support_confidence_sets.formal_b2.constants import (
    ALPHA,
    CONTROLLER_QUERY_CAP,
    DESIGN_LADDER,
    EXPLANATION_COUNT,
)
from physical_support_confidence_sets.formal_b2.geometry import build_geometry
from physical_support_confidence_sets.formal_b2.projection import safe_partial_projection


REPOSITORY = Path(__file__).resolve().parents[1]


def test_formal_b2_core_is_byte_identical_to_freeze() -> None:
    freeze = json.loads(
        (REPOSITORY / "configs/formal_b2/b2f01_code_freeze.json").read_text(
            encoding="utf-8"
        )
    )
    expected = freeze["successor_d2d23_core_file_sha256"]
    source = REPOSITORY / "src/physical_support_confidence_sets/formal_b2"
    assert len(expected) == 15
    for key, digest in expected.items():
        path = source / Path(key).name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest


def test_d25_bank_counts_order_and_constants() -> None:
    d25 = next(row for row in DESIGN_LADDER if row[0] == "D25")
    assert d25 == ("D25", 0.085, 4096, 192, 0.80, 0.10, 1.00, 5)
    assert ALPHA == 0.077
    assert CONTROLLER_QUERY_CAP == 162
    bank = build_candidate_bank(build_geometry(0.085))
    public = bank.public_candidates()
    assert len(bank.dictionary_states) == 72
    assert len(bank.support_patterns) == 3
    assert len(public) == EXPLANATION_COUNT == 216
    assert [row.candidate_id for row in public] == list(range(1, 217))
    assert [(row.dictionary_index, row.support_index) for row in public[:6]] == [
        (0, 0),
        (0, 1),
        (0, 2),
        (1, 0),
        (1, 1),
        (1, 2),
    ]


def test_possible_set_and_typed_projection_semantics() -> None:
    public = build_candidate_bank(build_geometry(0.085)).public_candidates()
    statuses = {row.candidate_id: "UNKNOWN" for row in public}
    a = safe_partial_projection(public, statuses, "A")
    b = safe_partial_projection(public, statuses, "B")
    c = safe_partial_projection(public, statuses, "C")
    d = safe_partial_projection(public, statuses, "D")
    assert a.label == "ABSTAIN"
    assert b.label == "SECTOR_SAFE"
    assert c.label == d.label == "ABSTAIN"
    assert a.possible_present == 216 and a.possible_absent == 0
    assert c.possible_present == 72 and c.possible_absent == 144
    assert d.possible_present == 72 and d.possible_absent == 144

