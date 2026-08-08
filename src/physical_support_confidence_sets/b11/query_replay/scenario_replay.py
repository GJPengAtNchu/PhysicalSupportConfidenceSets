"""Scenario-aware independent 90-decimal replay for ARA-B0.

The inherited G0.1 replay hard-codes ``s=0.4``.  B0 has three frozen collision
scales, so this module repeats the independent scalar calculation with the
scenario scale supplied explicitly.  It performs no search and has no access
to the finite-bank collection.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import product
import math
from typing import Any

import mpmath as mp
import numpy as np

from ..scientific_core.config import FROZEN
from ..scientific_core.transforms import normalized_to_raw


SCENARIO_REPLAY_DECIMAL_DIGITS = 90


def _mp(value: float) -> mp.mpf:
    """Convert one binary float through its deterministic decimal spelling."""
    return mp.mpf(repr(float(value)))


def _validated_point(value: np.ndarray, *, label: str) -> np.ndarray:
    point = np.asarray(value, dtype=float)
    if point.shape != (3,):
        raise ValueError(f"{label} must have shape (3,)")
    if not np.all(np.isfinite(point)):
        raise ValueError(f"{label} must be finite")
    if np.any(point < -1.0) or np.any(point > 1.0):
        raise ValueError(f"{label} must belong to [-1,1]^3")
    result = point.copy()
    result.setflags(write=False)
    return result


def _validated_checkpoints(
    checkpoints: np.ndarray, observation_count: int
) -> np.ndarray:
    raw = np.asarray(checkpoints)
    if raw.ndim != 1 or not len(raw):
        raise ValueError("checkpoints must be a nonempty one-dimensional array")
    if not np.issubdtype(raw.dtype, np.integer):
        if not np.all(np.isfinite(raw)) or not np.all(raw == np.floor(raw)):
            raise ValueError("checkpoints must contain exact integers")
    values = raw.astype(int)
    if (
        np.any(values <= 0)
        or np.any(values > int(observation_count))
        or np.any(np.diff(values) <= 0)
    ):
        raise ValueError(
            "checkpoints must be strictly increasing observation counts"
        )
    result = values.copy()
    result.setflags(write=False)
    return result


def _base_dictionary(scale_value: float) -> mp.matrix:
    """Construct the inherited tetrahedral dictionary at a supplied scale."""
    scale = _mp(scale_value)
    height = mp.sqrt(1 - scale**2)
    root_three = mp.sqrt(3)
    vertices = (
        (1, 1, 1),
        (1, -1, -1),
        (-1, 1, -1),
        (-1, -1, 1),
    )
    design = mp.matrix(4, 5)
    for column, vertex in enumerate(vertices):
        design[0, column] = scale * mp.mpf(vertex[0]) / root_three
        design[1, column] = scale * mp.mpf(vertex[1]) / root_three
        design[2, column] = scale * mp.mpf(vertex[2]) / root_three
        design[3, column] = height
    design[0, 4] = 1 / mp.sqrt(2)
    design[1, 4] = 0
    design[2, 4] = 0
    design[3, 4] = 1 / mp.sqrt(2)
    return design


def _rotated_observation(
    values: tuple[mp.mpf, mp.mpf, mp.mpf, mp.mpf], phi: mp.mpf
) -> tuple[mp.mpf, mp.mpf, mp.mpf, mp.mpf]:
    cosine = mp.cos(phi)
    sine = mp.sin(phi)
    return (
        values[0],
        cosine * values[1] + sine * values[2],
        -sine * values[1] + cosine * values[2],
        values[3],
    )


class _ScenarioMPMixture:
    """One scenario-specific high-precision mixture candidate."""

    def __init__(
        self,
        phi: float,
        p: float,
        nu: float,
        *,
        base_dictionary: mp.matrix,
    ) -> None:
        self.phi = _mp(phi)
        probability = _mp(p)
        noise = _mp(nu)
        identity = mp.eye(FROZEN.q)
        masks = product((0, 1), repeat=FROZEN.n)
        self.inverse_coefficients: list[tuple[mp.mpf, ...]] = []
        self.constants: list[mp.mpf] = []
        for mask in masks:
            covariance = noise * identity
            for column, active in enumerate(mask):
                if active:
                    vector = base_dictionary[:, column]
                    covariance = covariance + vector * vector.T
            inverse = covariance**-1
            determinant = mp.det(covariance)
            size = sum(mask)
            weight = probability**size * (1 - probability) ** (
                FROZEN.n - size
            )
            constant = mp.log(weight) - mp.mpf("0.5") * (
                FROZEN.q * mp.log(2 * mp.pi) + mp.log(determinant)
            )
            self.inverse_coefficients.append(
                (
                    inverse[0, 0],
                    inverse[1, 1],
                    inverse[2, 2],
                    inverse[3, 3],
                    2 * inverse[0, 1],
                    2 * inverse[0, 2],
                    2 * inverse[0, 3],
                    2 * inverse[1, 2],
                    2 * inverse[1, 3],
                    2 * inverse[2, 3],
                )
            )
            self.constants.append(constant)

    def logpdf(
        self, row: tuple[mp.mpf, mp.mpf, mp.mpf, mp.mpf]
    ) -> mp.mpf:
        y = _rotated_observation(row, self.phi)
        monomials = (
            y[0] * y[0],
            y[1] * y[1],
            y[2] * y[2],
            y[3] * y[3],
            y[0] * y[1],
            y[0] * y[2],
            y[0] * y[3],
            y[1] * y[2],
            y[1] * y[3],
            y[2] * y[3],
        )
        values = [
            constant
            - mp.mpf("0.5") * mp.fdot(coefficients, monomials)
            for constant, coefficients in zip(
                self.constants, self.inverse_coefficients
            )
        ]
        maximum = max(values)
        return maximum + mp.log(
            sum(mp.exp(value - maximum) for value in values)
        )


@dataclass(frozen=True)
class ScenarioReplayResult:
    """A pointwise scenario-aware high-precision replay result."""

    x: tuple[float, float, float]
    raw: tuple[float, float, float]
    scenario_s: float
    log_e: tuple[str, ...]
    scores: tuple[str, ...]
    maximum_score: str
    maximum_checkpoint: int
    survives_all_checkpoints: bool
    decimal_digits: int = SCENARIO_REPLAY_DECIMAL_DIGITS

    def to_json(self) -> dict[str, Any]:
        record = asdict(self)
        record["x"] = list(self.x)
        record["raw"] = list(self.raw)
        record["log_e"] = list(self.log_e)
        record["scores"] = list(self.scores)
        return record


class ScenarioHighPrecisionReplay:
    """Independent replay with fixed data, proposal, and scenario scale."""

    __slots__ = (
        "_alpha_d",
        "_base_dictionary",
        "_checkpoints",
        "_numerator",
        "_observation_rows",
        "_observations",
        "_proposal_result",
        "_proposal_x",
        "_replay_cache",
        "_scenario_s",
    )

    def __init__(
        self,
        observations: np.ndarray,
        checkpoints: np.ndarray,
        proposal_x: np.ndarray,
        *,
        scenario_s: float,
        alpha_d: float = FROZEN.alpha_d,
    ) -> None:
        values = np.asarray(observations, dtype=float)
        if values.ndim != 2 or values.shape[1] != FROZEN.q:
            raise ValueError("observations must have shape (N,4)")
        if not len(values) or not np.all(np.isfinite(values)):
            raise ValueError("observations must be nonempty and finite")
        scale = float(scenario_s)
        if not math.isfinite(scale) or not 0.0 < scale < 1.0:
            raise ValueError("scenario_s must belong to (0,1)")
        alpha = float(alpha_d)
        if not math.isfinite(alpha) or not 0.0 < alpha < 1.0:
            raise ValueError("alpha_d must belong to (0,1)")
        self._observations = values.copy()
        self._observations.setflags(write=False)
        self._checkpoints = _validated_checkpoints(
            checkpoints, len(self._observations)
        )
        self._proposal_x = _validated_point(
            proposal_x, label="proposal_x"
        )
        self._scenario_s = scale
        self._alpha_d = alpha
        self._base_dictionary: mp.matrix | None = None
        self._observation_rows: (
            tuple[tuple[mp.mpf, mp.mpf, mp.mpf, mp.mpf], ...] | None
        ) = None
        self._numerator: tuple[mp.mpf, ...] | None = None
        self._proposal_result: ScenarioReplayResult | None = None
        self._replay_cache: dict[
            tuple[float, float, float], ScenarioReplayResult
        ] = {}

    def validate_compatibility(
        self,
        observations: np.ndarray,
        checkpoints: np.ndarray,
        proposal_x: np.ndarray,
        *,
        scenario_s: float,
        alpha_d: float = FROZEN.alpha_d,
    ) -> None:
        """Reject reuse unless every fixed scientific input is identical."""
        values = np.asarray(observations, dtype=float)
        checkpoint_values = _validated_checkpoints(checkpoints, len(values))
        proposal = _validated_point(proposal_x, label="proposal_x")
        if (
            values.shape != self._observations.shape
            or not np.array_equal(values, self._observations)
            or not np.array_equal(checkpoint_values, self._checkpoints)
            or not np.array_equal(proposal, self._proposal_x)
            or float(scenario_s) != self._scenario_s
            or float(alpha_d) != self._alpha_d
        ):
            raise ValueError(
                "preconstructed high-precision replay input mismatch"
            )

    def _dictionary(self) -> mp.matrix:
        if self._base_dictionary is None:
            self._base_dictionary = _base_dictionary(self._scenario_s)
        return self._base_dictionary

    def _mp_observations(
        self,
    ) -> tuple[tuple[mp.mpf, mp.mpf, mp.mpf, mp.mpf], ...]:
        if self._observation_rows is None:
            self._observation_rows = tuple(
                tuple(_mp(value) for value in row)  # type: ignore[misc]
                for row in self._observations
            )
        return self._observation_rows

    @staticmethod
    def _prefixes(
        mixture: _ScenarioMPMixture,
        observations: tuple[
            tuple[mp.mpf, mp.mpf, mp.mpf, mp.mpf], ...
        ],
        checkpoints: np.ndarray,
    ) -> tuple[mp.mpf, ...]:
        targets = {int(value): index for index, value in enumerate(checkpoints)}
        result: list[mp.mpf | None] = [None] * len(checkpoints)
        cumulative = mp.mpf(0)
        for index, row in enumerate(observations, start=1):
            cumulative += mixture.logpdf(row)
            location = targets.get(index)
            if location is not None:
                result[location] = +cumulative
        if any(value is None for value in result):
            raise ValueError("checkpoint outside replay observations")
        return tuple(value for value in result if value is not None)

    def _mixture(self, x: np.ndarray) -> _ScenarioMPMixture:
        raw = normalized_to_raw(x)
        return _ScenarioMPMixture(
            *raw,
            base_dictionary=self._dictionary(),
        )

    def _numerator_prefixes(self) -> tuple[mp.mpf, ...]:
        if self._numerator is None:
            self._numerator = self._prefixes(
                self._mixture(self._proposal_x),
                self._mp_observations(),
                self._checkpoints,
            )
        return self._numerator

    def prepare(self) -> None:
        """Prepare only the fixed proposal numerator; never inspect a bank."""
        with mp.workdps(SCENARIO_REPLAY_DECIMAL_DIGITS):
            self._mp_observations()
            self._numerator_prefixes()

    def replay_proposal(self) -> ScenarioReplayResult:
        """Replay the continuous numerator without recomputing a denominator."""
        with mp.workdps(SCENARIO_REPLAY_DECIMAL_DIGITS):
            if self._proposal_result is None:
                # Preparing the numerator is the only scientific likelihood
                # computation required.  The proposal divided by that same
                # frozen numerator is identically one at every checkpoint.
                self._numerator_prefixes()
                raw = normalized_to_raw(self._proposal_x)
                threshold = mp.log(1 / _mp(self._alpha_d))
                zero = mp.mpf(0)
                score = -threshold
                digits = SCENARIO_REPLAY_DECIMAL_DIGITS
                self._proposal_result = ScenarioReplayResult(
                    x=tuple(float(value) for value in self._proposal_x),
                    raw=tuple(float(value) for value in raw),
                    scenario_s=self._scenario_s,
                    log_e=tuple(
                        mp.nstr(zero, n=digits)
                        for _ in self._checkpoints
                    ),
                    scores=tuple(
                        mp.nstr(score, n=digits)
                        for _ in self._checkpoints
                    ),
                    maximum_score=mp.nstr(score, n=digits),
                    maximum_checkpoint=int(self._checkpoints[0]),
                    survives_all_checkpoints=True,
                )
                self._replay_cache[self._proposal_result.x] = (
                    self._proposal_result
                )
            return self._proposal_result

    def replay(self, x: np.ndarray) -> ScenarioReplayResult:
        """Replay exactly one supplied point at 90 decimal digits."""
        with mp.workdps(SCENARIO_REPLAY_DECIMAL_DIGITS):
            point = _validated_point(x, label="replay x")
            if np.array_equal(point, self._proposal_x):
                return self.replay_proposal()
            key = tuple(float(value) for value in point)
            cached = self._replay_cache.get(key)
            if cached is not None:
                return cached
            raw = normalized_to_raw(point)
            denominator = self._prefixes(
                self._mixture(point),
                self._mp_observations(),
                self._checkpoints,
            )
            numerator = self._numerator_prefixes()
            threshold = mp.log(1 / _mp(self._alpha_d))
            log_e = tuple(
                numerator_value - denominator_value
                for numerator_value, denominator_value in zip(
                    numerator, denominator
                )
            )
            scores = tuple(value - threshold for value in log_e)
            maximum_index = max(
                range(len(scores)), key=lambda index: scores[index]
            )
            digits = SCENARIO_REPLAY_DECIMAL_DIGITS
            result = ScenarioReplayResult(
                x=tuple(float(value) for value in point),
                raw=tuple(float(value) for value in raw),
                scenario_s=self._scenario_s,
                log_e=tuple(mp.nstr(value, n=digits) for value in log_e),
                scores=tuple(mp.nstr(value, n=digits) for value in scores),
                maximum_score=mp.nstr(scores[maximum_index], n=digits),
                maximum_checkpoint=int(self._checkpoints[maximum_index]),
                survives_all_checkpoints=bool(scores[maximum_index] <= 0),
            )
            self._replay_cache[key] = result
            return result
