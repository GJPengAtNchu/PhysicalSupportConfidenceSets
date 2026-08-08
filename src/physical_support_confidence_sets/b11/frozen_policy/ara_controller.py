"""Frozen AEB_FINE_SEEKING controller over public bank geometry."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
from typing import Any, Callable, Iterable

from .evidence import PROFILE_PARAMETERS, PublicCandidate, PublicCaseManifest
from .geometry import canonical_diameter, physical_distance
from .sealed_query import CandidateStatus, QueryReceipt, SealedQueryCapability


TOLERANCE = 1.0e-12


class OrientationState(str, Enum):
    UNKNOWN = "UNKNOWN"
    SURVIVOR = "SURVIVOR"
    ELIMINATED = "ELIMINATED"


@dataclass(frozen=True)
class OrientationGroup:
    index: int
    phi: float
    candidates: tuple[PublicCandidate, ...]
    nuisance_order: tuple[str, ...]


@dataclass(frozen=True)
class BoundState:
    lower: float
    upper: float
    lower_endpoints: tuple[Any, ...]
    upper_endpoints: tuple[Any, ...]


@dataclass(frozen=True)
class TraceSeal:
    case_id: str
    profile: str
    trace_sha256: str
    canonical_payload: str


@dataclass
class MaximalTrace:
    case_id: str
    profile: str
    bank_size: int
    d_shell: float
    delta_f: float
    delta_s: float
    initial_state: dict[str, Any]
    rows: list[dict[str, Any]]
    terminal_output: str
    terminal_query_count: int
    completed_actions: int
    provisional_sector_query: int | None
    seal: TraceSeal | None = None

    def seal_trace(self) -> TraceSeal:
        if self.seal is not None:
            return self.seal
        payload = {
            "case_id": self.case_id,
            "profile": self.profile,
            "bank_size": self.bank_size,
            "d_shell": self.d_shell,
            "delta_f": self.delta_f,
            "delta_s": self.delta_s,
            "initial_state": self.initial_state,
            "rows": self.rows,
            "terminal_output": self.terminal_output,
            "terminal_query_count": self.terminal_query_count,
            "completed_actions": self.completed_actions,
            "provisional_sector_query": self.provisional_sector_query,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        self.seal = TraceSeal(self.case_id, self.profile, digest, canonical)
        return self.seal


class AEBFineSeekingController:
    """Controller state contains public geometry and queried outcomes only."""

    def __init__(self, manifest: PublicCaseManifest, profile: str):
        if profile not in PROFILE_PARAMETERS:
            raise KeyError(profile)
        _, delta_f_fraction, delta_s_fraction = PROFILE_PARAMETERS[profile]
        self.case_id = manifest.case_id
        self.profile = profile
        self.scale = manifest.scale
        self.target_raw = manifest.target_raw
        self.d_shell = manifest.d_shell
        self.delta_f = delta_f_fraction * manifest.d_shell
        self.delta_s = delta_s_fraction * manifest.d_shell
        self.bank_size = len(manifest.candidates)
        self.groups = _build_groups(manifest)
        self.group_by_index = {group.index: group for group in self.groups}
        self.candidate_to_group = {
            candidate.candidate_id: group.index
            for group in self.groups
            for candidate in group.candidates
        }
        self.states = {group.index: OrientationState.UNKNOWN for group in self.groups}
        self.queried: dict[str, CandidateStatus] = {}
        self.witness_indices: set[int] = set()
        self.rejected_by_group = {group.index: set() for group in self.groups}
        self.completed_actions = 0
        self.provisional_sector_query: int | None = None

    def bounds(self) -> BoundState:
        witnessed = [("PROPOSAL", self.target_raw[0])]
        witnessed.extend(
            (("ORIENTATION", index), self.group_by_index[index].phi)
            for index in sorted(self.witness_indices)
        )
        possible = [("PROPOSAL", self.target_raw[0])]
        possible.extend(
            (("ORIENTATION", group.index), group.phi)
            for group in self.groups
            if self.states[group.index] is not OrientationState.ELIMINATED
        )
        lower, lower_endpoints = canonical_diameter(self.scale, witnessed)
        upper, upper_endpoints = canonical_diameter(self.scale, possible)
        return BoundState(lower, upper, lower_endpoints, upper_endpoints)

    def choose_orientation(self) -> int:
        current = self.bounds()
        endpoint_unknown: list[int] = []
        for endpoint in current.upper_endpoints:
            if (
                isinstance(endpoint, tuple)
                and len(endpoint) == 2
                and endpoint[0] == "ORIENTATION"
                and self.states[int(endpoint[1])] is OrientationState.UNKNOWN
            ):
                endpoint_unknown.append(int(endpoint[1]))
        if endpoint_unknown:
            return min(
                endpoint_unknown,
                key=lambda index: (
                    self._remaining_count(index),
                    -self._possible_lower_gain(index, current),
                    -self._possible_upper_drop(index, current),
                    -physical_distance(
                        self.scale, self.target_raw[0], self.group_by_index[index].phi
                    ),
                    index,
                ),
            )
        unknown = [
            group.index
            for group in self.groups
            if self.states[group.index] is OrientationState.UNKNOWN
        ]
        if not unknown:
            raise RuntimeError("no unknown orientation remains")
        return min(
            unknown,
            key=lambda index: (
                -self._possible_upper_drop(index, current),
                -self._possible_lower_gain(index, current),
                self._remaining_count(index),
                index,
            ),
        )

    def _remaining_count(self, index: int) -> int:
        return sum(
            candidate.candidate_id not in self.queried
            for candidate in self.group_by_index[index].candidates
        )

    def _possible_lower_gain(self, index: int, current: BoundState) -> float:
        points = [("PROPOSAL", self.target_raw[0])]
        points.extend(
            (("ORIENTATION", item), self.group_by_index[item].phi)
            for item in sorted(self.witness_indices | {index})
        )
        candidate_lower, _ = canonical_diameter(self.scale, points)
        return max(0.0, candidate_lower - current.lower)

    def _possible_upper_drop(self, index: int, current: BoundState) -> float:
        points = [("PROPOSAL", self.target_raw[0])]
        points.extend(
            (("ORIENTATION", group.index), group.phi)
            for group in self.groups
            if (
                self.states[group.index] is not OrientationState.ELIMINATED
                and group.index != index
            )
        )
        candidate_upper, _ = canonical_diameter(self.scale, points)
        return max(0.0, current.upper - candidate_upper)

    def terminal_decision(self) -> str | None:
        state = self.bounds()
        if state.lower > self.delta_s:
            return "AMBIGUOUS"
        if state.upper <= self.delta_f:
            return "FINE"
        if (
            abs(state.lower - state.upper) <= TOLERANCE
            and self.delta_f < state.upper <= self.delta_s
        ):
            return "SECTOR_SAFE"
        return None

    def budget_decision(self) -> str:
        state = self.bounds()
        if state.lower > self.delta_s:
            return "AMBIGUOUS"
        if state.upper <= self.delta_f:
            return "FINE"
        if state.upper <= self.delta_s:
            return "SECTOR_SAFE"
        return "ABSTAIN"

    def run_maximal(
        self,
        capability: SealedQueryCapability,
        orientation_selector: Callable[["AEBFineSeekingController"], int] | None = None,
    ) -> MaximalTrace:
        initial = self._snapshot()
        rows: list[dict[str, Any]] = []
        terminal = self.terminal_decision()
        while terminal is None:
            if all(state is not OrientationState.UNKNOWN for state in self.states.values()):
                terminal = self.budget_decision()
                break
            index = (
                orientation_selector(self)
                if orientation_selector is not None
                else self.choose_orientation()
            )
            action_complete = False
            for candidate_id in self.group_by_index[index].nuisance_order:
                if candidate_id in self.queried:
                    continue
                pre = self._snapshot()
                receipt = capability.query(candidate_id)
                self._observe(index, receipt)
                action_complete = self.states[index] is not OrientationState.UNKNOWN
                if action_complete:
                    self.completed_actions += 1
                post = self._snapshot()
                if self.provisional_sector_query is None and post["upper"] <= self.delta_s:
                    self.provisional_sector_query = receipt.query_number
                decision = self.terminal_decision() if action_complete else None
                rows.append(
                    {
                        "query_number": receipt.query_number,
                        "action_number": self.completed_actions
                        if action_complete
                        else self.completed_actions + 1,
                        "candidate_id": receipt.candidate_id,
                        "orientation_index": index,
                        "orientation_phi": self.group_by_index[index].phi,
                        "returned_status": receipt.status.value,
                        "pre_lower": pre["lower"],
                        "pre_upper": pre["upper"],
                        "post_lower": post["lower"],
                        "post_upper": post["upper"],
                        "pre_orientation_state": pre["orientation_states"][str(index)],
                        "post_orientation_state": post["orientation_states"][str(index)],
                        "action_complete": action_complete,
                        "controller_output_after_action": decision,
                        "queried_survivor_count": post["queried_survivor_count"],
                        "eliminated_orientation_count": post[
                            "eliminated_orientation_count"
                        ],
                        "completed_orientation_actions": self.completed_actions,
                    }
                )
                if action_complete:
                    terminal = decision
                    break
            if not action_complete:
                raise AssertionError(f"orientation action did not complete: {index}")
        capability.seal()
        if terminal is None:
            terminal = self.budget_decision()
        return MaximalTrace(
            case_id=self.case_id,
            profile=self.profile,
            bank_size=self.bank_size,
            d_shell=self.d_shell,
            delta_f=self.delta_f,
            delta_s=self.delta_s,
            initial_state=initial,
            rows=rows,
            terminal_output=terminal,
            terminal_query_count=len(rows),
            completed_actions=self.completed_actions,
            provisional_sector_query=self.provisional_sector_query,
        )

    def _observe(self, expected_index: int, receipt: QueryReceipt) -> None:
        actual_index = self.candidate_to_group.get(receipt.candidate_id)
        if actual_index != expected_index:
            raise RuntimeError("query receipt orientation mismatch")
        if receipt.candidate_id in self.queried:
            raise RuntimeError("duplicate query receipt")
        self.queried[receipt.candidate_id] = receipt.status
        if receipt.status is CandidateStatus.ADMISSIBLE:
            self.states[expected_index] = OrientationState.SURVIVOR
            self.witness_indices.add(expected_index)
            return
        self.rejected_by_group[expected_index].add(receipt.candidate_id)
        group_ids = {
            candidate.candidate_id
            for candidate in self.group_by_index[expected_index].candidates
        }
        if self.rejected_by_group[expected_index] == group_ids:
            self.states[expected_index] = OrientationState.ELIMINATED

    def _snapshot(self) -> dict[str, Any]:
        bounds = self.bounds()
        return {
            "lower": bounds.lower,
            "upper": bounds.upper,
            "lower_endpoints": list(bounds.lower_endpoints),
            "upper_endpoints": list(bounds.upper_endpoints),
            "orientation_states": {
                str(index): self.states[index].value for index in sorted(self.states)
            },
            "queried_count": len(self.queried),
            "queried_survivor_count": sum(
                status is CandidateStatus.ADMISSIBLE for status in self.queried.values()
            ),
            "eliminated_orientation_count": sum(
                state is OrientationState.ELIMINATED for state in self.states.values()
            ),
        }


def replay_budget(trace: MaximalTrace, budget_fraction: float) -> dict[str, Any]:
    if trace.seal is None:
        raise RuntimeError("budget replay requires a sealed trace")
    cap = max(1, math.floor(budget_fraction * trace.bank_size))
    used = min(cap, len(trace.rows))
    if used == 0:
        state = trace.initial_state
        action_output = None
    else:
        row = trace.rows[used - 1]
        state = {
            "lower": row["post_lower"],
            "upper": row["post_upper"],
        }
        action_output = row["controller_output_after_action"]
    if used == len(trace.rows):
        output = trace.terminal_output
    elif action_output is not None:
        output = action_output
    elif state["lower"] > trace.delta_s:
        output = "AMBIGUOUS"
    elif state["upper"] <= trace.delta_f:
        output = "FINE"
    elif state["upper"] <= trace.delta_s:
        output = "SECTOR_SAFE"
    else:
        output = "ABSTAIN"
    row_at_cut = trace.rows[used - 1] if used else None
    return {
        "case_id": trace.case_id,
        "profile": trace.profile,
        "budget_fraction": budget_fraction,
        "budget_cap": cap,
        "queries": used,
        "query_fraction": used / trace.bank_size,
        "output": output,
        "lower": state["lower"],
        "upper": state["upper"],
        "completed_orientation_actions": (
            row_at_cut["completed_orientation_actions"] if row_at_cut else 0
        ),
        "queried_survivor_count": (
            row_at_cut["queried_survivor_count"] if row_at_cut else 0
        ),
        "eliminated_orientation_count": (
            row_at_cut["eliminated_orientation_count"] if row_at_cut else 0
        ),
        "partial_orientation_at_boundary": bool(
            row_at_cut is not None
            and not row_at_cut["action_complete"]
            and used < len(trace.rows)
        ),
        "trace_sha256": trace.seal.trace_sha256,
    }


def _build_groups(manifest: PublicCaseManifest) -> tuple[OrientationGroup, ...]:
    by_phi: dict[float, list[PublicCandidate]] = {}
    for candidate in manifest.candidates:
        by_phi.setdefault(candidate.phi, []).append(candidate)
    groups: list[OrientationGroup] = []
    for index, phi in enumerate(sorted(by_phi)):
        candidates = tuple(sorted(by_phi[phi], key=lambda item: int(item.candidate_id)))
        groups.append(
            OrientationGroup(
                index=index,
                phi=phi,
                candidates=candidates,
                nuisance_order=_nuisance_order(candidates, manifest.target_raw[1:]),
            )
        )
    return tuple(groups)


def _nuisance_order(
    candidates: Iterable[PublicCandidate],
    target: tuple[float, float],
) -> tuple[str, ...]:
    rows = tuple(candidates)
    first_grid = sorted({row.nuisance[0] for row in rows})
    second_grid = sorted({row.nuisance[1] for row in rows})
    first_span = first_grid[-1] - first_grid[0]
    second_span = second_grid[-1] - second_grid[0]

    def distance(row: PublicCandidate) -> float:
        left = (row.nuisance[0] - target[0]) / first_span if first_span else 0.0
        right = (row.nuisance[1] - target[1]) / second_span if second_span else 0.0
        return math.hypot(left, right)

    ordered: list[PublicCandidate] = []

    def add(items: Iterable[PublicCandidate]) -> None:
        for item in items:
            if item not in ordered:
                ordered.append(item)

    add(sorted(rows, key=lambda row: (distance(row), int(row.candidate_id)))[:1])
    center = (first_grid[len(first_grid) // 2], second_grid[len(second_grid) // 2])
    add(
        sorted(
            rows,
            key=lambda row: (
                math.hypot(row.nuisance[0] - center[0], row.nuisance[1] - center[1]),
                int(row.candidate_id),
            ),
        )[:1]
    )
    corner_values = {
        (first_grid[0], second_grid[0]),
        (first_grid[0], second_grid[-1]),
        (first_grid[-1], second_grid[0]),
        (first_grid[-1], second_grid[-1]),
    }
    add(
        sorted(
            (row for row in rows if row.nuisance in corner_values),
            key=lambda row: (distance(row), int(row.candidate_id)),
        )
    )
    add(sorted(rows, key=lambda row: (distance(row), int(row.candidate_id))))
    if len(ordered) != len(rows):
        raise AssertionError("nuisance ordering lost candidates")
    return tuple(row.candidate_id for row in ordered)


def fixed_order_selector(order: tuple[int, ...]):
    def select(controller: AEBFineSeekingController) -> int:
        for index in order:
            if controller.states[index] is OrientationState.UNKNOWN:
                return index
        raise RuntimeError("fixed orientation order exhausted")

    return select


def static_farthest_order(controller: AEBFineSeekingController) -> tuple[int, ...]:
    return tuple(
        sorted(
            (group.index for group in controller.groups),
            key=lambda index: (
                -physical_distance(
                    controller.scale,
                    controller.target_raw[0],
                    controller.group_by_index[index].phi,
                ),
                index,
            ),
        )
    )


def hash_order(case_id: str, profile: str, indices: Iterable[int]) -> tuple[int, ...]:
    return tuple(
        sorted(
            indices,
            key=lambda index: (
                hashlib.sha256(
                    f"{case_id}|{profile}|{index}".encode("utf-8")
                ).hexdigest(),
                index,
            ),
        )
    )

