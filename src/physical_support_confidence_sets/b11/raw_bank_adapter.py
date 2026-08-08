"""Explicit raw-coordinate port for B0.1's declared finite-bank carriers.

The inherited continuous transform and exact scientific modules remain
byte-identical to B0.  Some frozen MEDIUM/NARROW grids contain positive noise
values below the continuous proposal shell, so those candidate-local calls
must bypass the normalized transform without changing the likelihood or
e-process mathematics.
"""

from __future__ import annotations

from dataclasses import replace
from types import FunctionType
from typing import Any

import mpmath as mp
import numpy as np

from .scientific_core import mixture as exact_mixture
from .query_replay.scenario_replay import (
    SCENARIO_REPLAY_DECIMAL_DIGITS,
    ScenarioReplayResult,
    _ScenarioMPMixture,
    _mp,
)
from .scientific_core.config import FROZEN


_FINITE_BANK_FROZEN = replace(FROZEN, nu_left=0.70)
_RAW_GLOBALS = dict(exact_mixture.__dict__)
_RAW_GLOBALS["FROZEN"] = _FINITE_BANK_FROZEN
_EXACT_RAW_EVALUATE = FunctionType(
    exact_mixture.VariableMixtureCache.evaluate_raw.__code__,
    _RAW_GLOBALS,
    name="evaluate_declared_finite_bank_raw",
)


def _raw_key(value: Any) -> tuple[float, float, float]:
    point = np.asarray(value, dtype=float)
    if point.shape != (3,) or not np.all(np.isfinite(point)):
        raise ValueError("finite-bank raw coordinate must be finite shape-(3,)")
    return tuple(float(item) for item in point)


def _x_key(value: Any) -> tuple[float, float, float]:
    point = np.asarray(value, dtype=float)
    if point.shape != (3,) or not np.all(np.isfinite(point)):
        raise ValueError("finite-bank display coordinate must be finite shape-(3,)")
    return tuple(float(item) for item in point)


class FiniteBankEProcessPort:
    """Delegate in-shell calls and expose exact raw finite-bank evaluation."""

    def __init__(self, base: Any, bank: Any) -> None:
        self._base = base
        self._allowed = {
            _raw_key(candidate.raw): _x_key(candidate.x)
            for candidate in bank.candidates
        }
        if len(self._allowed) != len(bank.candidates):
            raise ValueError("finite-bank raw carrier is not unique")

    @property
    def checkpoints(self) -> np.ndarray:
        return self._base.checkpoints

    def evaluate(
        self,
        x: np.ndarray,
        *,
        derivatives: bool = False,
    ) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None]:
        return self._base.evaluate(x, derivatives=derivatives)

    def evaluate_finite_bank_raw(
        self,
        raw: np.ndarray,
        *,
        derivatives: bool = False,
    ) -> tuple[np.ndarray, None, None]:
        if derivatives:
            raise ValueError(
                "finite-bank raw e-process evaluation is derivative-free"
            )
        key = _raw_key(raw)
        if key not in self._allowed:
            raise ValueError("raw coordinate is not in the declared role bank")
        values, gradient, hessian = _EXACT_RAW_EVALUATE(
            self._base.cache_b,
            key[0],
            key[1],
            key[2],
            derivatives=False,
        )
        if gradient is not None or hessian is not None:
            raise ArithmeticError(
                "finite-bank derivative-free kernel returned derivatives"
            )
        indices = np.asarray(self._base.checkpoints, dtype=int) - 1
        denominator = np.cumsum(np.asarray(values, dtype=float))[indices]
        return self._base.numerator_loglikelihood - denominator, None, None


class FiniteBankReplayPort:
    """Delegate normalized replay and add declared-bank raw replay."""

    def __init__(self, base: Any, bank: Any) -> None:
        self._base = base
        self._allowed = {
            _raw_key(candidate.raw): _x_key(candidate.x)
            for candidate in bank.candidates
        }
        self._cache: dict[
            tuple[float, float, float], ScenarioReplayResult
        ] = {}

    def replay(self, x: np.ndarray) -> ScenarioReplayResult:
        return self._base.replay(x)

    def replay_proposal(self) -> ScenarioReplayResult:
        return self._base.replay_proposal()

    def replay_finite_bank_raw(
        self,
        raw: np.ndarray,
        *,
        x: np.ndarray,
    ) -> ScenarioReplayResult:
        raw_value = _raw_key(raw)
        x_value = _x_key(x)
        if self._allowed.get(raw_value) != x_value:
            raise ValueError(
                "raw/display coordinates are not one declared bank candidate"
            )
        cached = self._cache.get(raw_value)
        if cached is not None:
            return cached
        with mp.workdps(SCENARIO_REPLAY_DECIMAL_DIGITS):
            denominator = self._base._prefixes(
                _ScenarioMPMixture(
                    raw_value[0],
                    raw_value[1],
                    raw_value[2],
                    base_dictionary=self._base._dictionary(),
                ),
                self._base._mp_observations(),
                self._base._checkpoints,
            )
            numerator = self._base._numerator_prefixes()
            boundary = mp.log(1 / _mp(self._base._alpha_d))
            log_e = tuple(
                numerator_value - denominator_value
                for numerator_value, denominator_value in zip(
                    numerator, denominator
                )
            )
            scores = tuple(value - boundary for value in log_e)
            maximum_index = max(
                range(len(scores)), key=lambda index: scores[index]
            )
            digits = SCENARIO_REPLAY_DECIMAL_DIGITS
            result = ScenarioReplayResult(
                x=x_value,
                raw=raw_value,
                scenario_s=self._base._scenario_s,
                log_e=tuple(mp.nstr(value, n=digits) for value in log_e),
                scores=tuple(mp.nstr(value, n=digits) for value in scores),
                maximum_score=mp.nstr(scores[maximum_index], n=digits),
                maximum_checkpoint=int(
                    self._base._checkpoints[maximum_index]
                ),
                survives_all_checkpoints=bool(scores[maximum_index] <= 0),
            )
            self._cache[raw_value] = result
            return result
