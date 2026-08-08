"""Canonical 72-state, three-support, 216-explanation D2 finite bank."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import numpy as np

from .constants import (
    ANCHOR_ID,
    DICTIONARY_STATE_COUNT,
    EXPLANATION_COUNT,
    REGION_ORDER,
    SUPPORT_PATTERN_COUNT,
    SUPPORT_PATTERNS,
    TRUE_ATOM_IDS,
)
from .geometry import ApplicationGeometry
from .util import digest_json, readonly_float_array


@dataclass(frozen=True)
class DictionaryState:
    index: int
    dictionary_id: str
    atom_ids: tuple[str, str, str, str]
    matrix: np.ndarray

    def atom_id_for_region(self, region: str) -> str:
        try:
            return self.atom_ids[REGION_ORDER.index(region)]
        except ValueError as error:
            raise KeyError(region) from error


@dataclass(frozen=True)
class SupportPattern:
    index: int
    support_id: str
    regions: tuple[str, ...]


@dataclass(frozen=True)
class CandidateExplanation:
    index: int
    candidate_id: str
    dictionary_index: int
    support_index: int


@dataclass(frozen=True)
class PublicCandidate:
    """Geometry-only candidate view available to the controller."""

    candidate_id: int
    candidate_code: str
    explanation_index: int
    dictionary_index: int
    support_index: int
    support: tuple[str, ...]
    locations: dict[str, float]


@dataclass(frozen=True)
class CandidateBank:
    geometry: ApplicationGeometry
    dictionary_states: tuple[DictionaryState, ...]
    support_patterns: tuple[SupportPattern, ...]
    explanations: tuple[CandidateExplanation, ...]

    @property
    def true_dictionary_index(self) -> int:
        truth = tuple(TRUE_ATOM_IDS[region] for region in REGION_ORDER)
        matches = [state.index for state in self.dictionary_states if state.atom_ids == truth]
        if len(matches) != 1:
            raise RuntimeError("true dictionary state is not unique")
        return matches[0]

    def explanation(self, index: int) -> CandidateExplanation:
        value = int(index)
        if not 0 <= value < len(self.explanations):
            raise IndexError(value)
        return self.explanations[value]

    def public_candidates(self) -> tuple[PublicCandidate, ...]:
        rows: list[PublicCandidate] = []
        for explanation in self.explanations:
            state = self.dictionary_states[explanation.dictionary_index]
            support = self.support_patterns[explanation.support_index]
            locations = {
                region: float(
                    self.geometry.atom(state.atom_id_for_region(region)).location
                )
                for region in REGION_ORDER
            }
            rows.append(
                PublicCandidate(
                    candidate_id=explanation.index + 1,
                    candidate_code=explanation.candidate_id,
                    explanation_index=explanation.index,
                    dictionary_index=explanation.dictionary_index,
                    support_index=explanation.support_index,
                    support=support.regions,
                    locations=locations,
                )
            )
        return tuple(rows)

    def manifest(self) -> dict[str, object]:
        core = {
            "dictionary_states": [
                {
                    "index": state.index,
                    "dictionary_id": state.dictionary_id,
                    "atom_ids": list(state.atom_ids),
                }
                for state in self.dictionary_states
            ],
            "support_patterns": [
                {
                    "index": support.index,
                    "support_id": support.support_id,
                    "regions": list(support.regions),
                }
                for support in self.support_patterns
            ],
            "explanations": [
                {
                    "index": explanation.index,
                    "candidate_id": explanation.candidate_id,
                    "dictionary_index": explanation.dictionary_index,
                    "support_index": explanation.support_index,
                }
                for explanation in self.explanations
            ],
        }
        return {**core, "bank_sha256": digest_json(core)}


def build_candidate_bank(geometry: ApplicationGeometry) -> CandidateBank:
    regional_atoms = [
        tuple(atom.atom_id for atom in geometry.atoms_for_region(region))
        for region in REGION_ORDER
    ]
    states: list[DictionaryState] = []
    for index, chosen in enumerate(product(*regional_atoms)):
        atom_ids = tuple(chosen)
        matrix = np.column_stack(
            [geometry.atom(atom_id).vector for atom_id in atom_ids]
            + [geometry.atom(ANCHOR_ID).vector]
        )
        states.append(
            DictionaryState(
                index=index,
                dictionary_id=f"G{index + 1:03d}",
                atom_ids=atom_ids,  # type: ignore[arg-type]
                matrix=readonly_float_array(matrix, ndim=2),
            )
        )
    supports = tuple(
        SupportPattern(index=index, support_id=support_id, regions=regions)
        for index, (support_id, regions) in enumerate(SUPPORT_PATTERNS)
    )
    explanations = tuple(
        CandidateExplanation(
            index=state.index * len(supports) + support.index,
            candidate_id=f"E{state.index * len(supports) + support.index + 1:04d}",
            dictionary_index=state.index,
            support_index=support.index,
        )
        for state in states
        for support in supports
    )
    if len(states) != DICTIONARY_STATE_COUNT:
        raise AssertionError("frozen dictionary-state count changed")
    if len(supports) != SUPPORT_PATTERN_COUNT:
        raise AssertionError("frozen support-pattern count changed")
    if len(explanations) != EXPLANATION_COUNT:
        raise AssertionError("frozen explanation count changed")
    if [row.index for row in explanations] != list(range(EXPLANATION_COUNT)):
        raise AssertionError("candidate explanation order is noncanonical")
    return CandidateBank(
        geometry=geometry,
        dictionary_states=tuple(states),
        support_patterns=supports,
        explanations=explanations,
    )
