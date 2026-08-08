"""Persistent/optional finite-bank projections for frozen B2-D2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


REGIONS = ("A", "B", "C", "D")
PERSISTENT_REGIONS = frozenset({"A", "B"})
OPTIONAL_REGIONS = frozenset({"C", "D"})
FINE_TOLERANCES = {"A": 0.035, "B": 0.020, "C": 0.035, "D": 0.030}
POSSIBLE_STATUSES = frozenset({"UNKNOWN", "ADMISSIBLE", "INDETERMINATE"})
OPTIONAL_ABSENCE_LABEL = "ABSENT_ABOVE_BETA_MIN"
COARSENESS_RANK = {
    "ABSTAIN": 0,
    "SUPPORT_AMBIGUOUS": 1,
    "LOCAL_AMBIGUOUS": 2,
    "SECTOR_SAFE": 3,
    "ABSENT_ABOVE_BETA_MIN": 4,
    "FINE": 4,
}


@dataclass(frozen=True)
class RegionProjection:
    region: str
    label: str
    possible_present: int
    possible_absent: int
    witness_present: int
    witness_absent: int
    upper_locations: tuple[float, ...]
    lower_locations: tuple[float, ...]
    endpoint_candidate_ids: tuple[int, ...]


def _support(candidate: object) -> frozenset[str]:
    value = getattr(candidate, "support", getattr(candidate, "support_regions", None))
    if value is None and isinstance(candidate, Mapping):
        value = candidate.get("support", candidate.get("support_regions"))
    return frozenset(value)


def _support_id(candidate: object) -> str | None:
    value = getattr(candidate, "support_id", None)
    if value is None and isinstance(candidate, Mapping):
        value = candidate.get("support_id")
    return None if value is None else str(value)


def _candidate_id(candidate: object) -> int:
    value = getattr(candidate, "candidate_id", None)
    if value is None and isinstance(candidate, Mapping):
        value = candidate["candidate_id"]
    return int(value)


def _location(candidate: object, region: str) -> float:
    value = getattr(candidate, "locations", None)
    if value is None and isinstance(candidate, Mapping):
        value = candidate["locations"]
    return float(value[region])


def _diameter(values: Sequence[float]) -> float:
    return 0.0 if len(values) < 2 else float(max(values) - min(values))


def _endpoint_ids(candidates: Sequence[object], region: str) -> tuple[int, ...]:
    if not candidates:
        return ()
    locations = tuple(sorted({_location(candidate, region) for candidate in candidates}))
    result: list[int] = []
    for location in (locations[0], locations[-1]):
        if result and location == locations[0]:
            continue
        result.append(
            min(
                _candidate_id(candidate)
                for candidate in candidates
                if _location(candidate, region) == location
            )
        )
    return tuple(sorted(set(result)))


def _c_absent_witness(candidate: object) -> bool:
    """D2 freezes C ambiguity witnesses to the AB/ABC pair."""

    support_id = _support_id(candidate)
    if support_id is not None:
        return support_id == "P01_AB"
    return _support(candidate) == frozenset({"A", "B"})


def safe_partial_projection(
    candidates: Sequence[object], statuses: Mapping[int, str], region: str
) -> RegionProjection:
    """Project only queried evidence and public persistent/optional semantics.

    A and B are persistent application assumptions rather than empirical
    support claims.  A deliberately remains ABSTAIN until its possible
    location set is fine (or admissible endpoints prove local ambiguity); B
    has the frozen safe macro-region fallback.  C and D retain candidate-wise
    support certification, and every unqueried/indeterminate explanation
    remains possible.
    """

    if region not in REGIONS:
        raise KeyError(region)
    possible = [
        candidate
        for candidate in candidates
        if statuses.get(_candidate_id(candidate), "UNKNOWN") in POSSIBLE_STATUSES
    ]
    if not possible:
        raise RuntimeError("empty global possible explanation set")
    witnesses = [
        candidate
        for candidate in candidates
        if statuses.get(_candidate_id(candidate)) == "ADMISSIBLE"
    ]
    present = [candidate for candidate in possible if region in _support(candidate)]
    absent = [candidate for candidate in possible if region not in _support(candidate)]
    witness_present = [
        candidate for candidate in witnesses if region in _support(candidate)
    ]
    if region == "C":
        witness_absent = [candidate for candidate in witnesses if _c_absent_witness(candidate)]
    else:
        witness_absent = [
            candidate for candidate in witnesses if region not in _support(candidate)
        ]
    upper = tuple(sorted({_location(candidate, region) for candidate in present}))
    lower = tuple(sorted({_location(candidate, region) for candidate in witness_present}))

    if region == "A":
        if _diameter(upper) <= FINE_TOLERANCES[region]:
            label = "FINE"
        elif _diameter(lower) > FINE_TOLERANCES[region]:
            label = "LOCAL_AMBIGUOUS"
        else:
            label = "ABSTAIN"
    elif region == "B":
        label = (
            "FINE"
            if _diameter(upper) <= FINE_TOLERANCES[region]
            else "SECTOR_SAFE"
        )
    elif witness_present and witness_absent:
        label = "SUPPORT_AMBIGUOUS"
    elif not present:
        label = OPTIONAL_ABSENCE_LABEL
    elif absent:
        label = "ABSTAIN"
    elif _diameter(upper) <= FINE_TOLERANCES[region]:
        label = "FINE"
    elif upper:
        label = "SECTOR_SAFE"
    else:
        label = "ABSTAIN"

    return RegionProjection(
        region=region,
        label=label,
        possible_present=len(present),
        possible_absent=len(absent),
        witness_present=len(witness_present),
        witness_absent=len(witness_absent),
        upper_locations=upper,
        lower_locations=lower,
        endpoint_candidate_ids=_endpoint_ids(present, region),
    )


def exact_oracle_projection(
    candidates: Sequence[object], admissible_ids: Iterable[int]
) -> dict[str, RegionProjection]:
    """Project the complete replay-aware 216-candidate finite oracle."""

    admissible = frozenset(int(candidate_id) for candidate_id in admissible_ids)
    survivors = [
        candidate for candidate in candidates if _candidate_id(candidate) in admissible
    ]
    if not survivors:
        raise RuntimeError("exact finite-bank oracle has no surviving explanation")
    result: dict[str, RegionProjection] = {}
    for region in REGIONS:
        present = [candidate for candidate in survivors if region in _support(candidate)]
        absent = [candidate for candidate in survivors if region not in _support(candidate)]
        upper = tuple(sorted({_location(candidate, region) for candidate in present}))
        if region in PERSISTENT_REGIONS:
            if not present:
                raise RuntimeError("persistent region disappeared from D2 oracle bank")
            label = (
                "FINE"
                if _diameter(upper) <= FINE_TOLERANCES[region]
                else "SECTOR_SAFE"
            )
        elif not present:
            label = OPTIONAL_ABSENCE_LABEL
        elif absent:
            label = "SUPPORT_AMBIGUOUS"
        elif _diameter(upper) <= FINE_TOLERANCES[region]:
            label = "FINE"
        elif upper:
            label = "SECTOR_SAFE"
        else:
            label = "LOCAL_AMBIGUOUS"
        result[region] = RegionProjection(
            region=region,
            label=label,
            possible_present=len(present),
            possible_absent=len(absent),
            witness_present=len(present),
            witness_absent=len(absent),
            upper_locations=upper,
            lower_locations=upper,
            endpoint_candidate_ids=_endpoint_ids(present, region),
        )
    return result


def projection_payload(projection: Mapping[str, RegionProjection]) -> dict[str, dict]:
    return {
        region: {
            "label": value.label,
            "possible_present": value.possible_present,
            "possible_absent": value.possible_absent,
            "witness_present": value.witness_present,
            "witness_absent": value.witness_absent,
            "upper_locations": list(value.upper_locations),
            "lower_locations": list(value.lower_locations),
            "endpoint_candidate_ids": list(value.endpoint_candidate_ids),
        }
        for region, value in projection.items()
    }


def global_summary(projection: Mapping[str, object]) -> dict[str, object]:
    """Return the non-adjudicative coarsest local output, A-D tie break."""

    rows: list[tuple[int, int, str, str]] = []
    for tie, region in enumerate(REGIONS):
        value = projection[region]
        if isinstance(value, RegionProjection):
            label = value.label
        elif isinstance(value, Mapping):
            label = str(value["label"])
        else:
            label = str(value)
        if label not in COARSENESS_RANK:
            raise ValueError(f"unknown region-map label: {label}")
        rows.append((COARSENESS_RANK[label], tie, region, label))
    rank, _, region, label = min(rows)
    return {"label": label, "region": region, "coarseness_rank": rank}
