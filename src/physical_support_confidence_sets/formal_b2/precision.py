"""Independent 90-decimal replay for selected B2-D2 candidate scores."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import mpmath as mp
import numpy as np

from .bank import CandidateBank
from .constants import (
    ANCHOR_ID,
    NU_CALIBRATION,
    NU_DEPLOYMENT,
    P_CALIBRATION,
    Q,
    TAU_A,
)
from .data import PilotSplits
from .scoring import CandidateScoreTable, binary_masks


HP_DECIMAL_DIGITS = 90
NEAR_MARGIN = 0.02


@dataclass(frozen=True)
class HighPrecisionReplayResult:
    candidate_id: int
    explanation_index: int
    maximum_margin_decimal: str
    maximum_margin: float
    maximum_joint_checkpoint_index: int
    survives: bool
    decimal_digits: int


def deterministic_double_error_envelope(
    table: CandidateScoreTable, candidate_index: int
) -> float:
    """Backward-error envelope for a well-conditioned frozen covariance bank.

    Every covariance has eigenvalue floor 0.8 and rank at most five.  The
    factor 2**17 bounds stable low-rank solve, dot-product, exp/logsumexp and
    prefix-addition roundoff; the table retains the observed sum of absolute
    numerator, denominator, and threshold contributions for each candidate;
    and 16 bounds the squared covariance condition factor over the frozen
    bank (the seed-free maximum is below 9).  Joint-path inflation then gives
    a deterministic data-dependent absolute margin envelope.  A
    double rejection is usable only when ``margin - envelope > 0``; otherwise
    90-decimal replay is mandatory.  The constants are deliberately loose and
    frozen before pilots.
    """

    idx = int(candidate_index)
    path = max(1, len(table.joint_checkpoints))
    epsilon = np.finfo(np.float64).eps
    observed_scale = float(table.roundoff_absolute_scale[idx])
    envelope = (
        epsilon
        * float(2**17)
        * observed_scale
        * 16.0
        * (1.0 + path / 16.0)
    )
    if not math.isfinite(envelope) or envelope <= 0.0 or envelope >= 0.02:
        raise ArithmeticError("frozen double error envelope is invalid")
    return float(envelope)


class HighPrecisionReplay:
    """Lazy replay cache over held-out rows only.

    Binary64 values are promoted through their shortest round-trip decimal
    representation, then every covariance kernel and likelihood is rebuilt at
    90 decimal digits.
    """

    def __init__(
        self,
        bank: CandidateBank,
        splits: PilotSplits,
        table: CandidateScoreTable,
        *,
        tau_b: float,
        tau_c: float,
        tau_d_beta: float,
    ):
        self.bank = bank
        self.splits = splits
        self.table = table
        self.tau_b = float(tau_b)
        self.tau_c = float(tau_c)
        self.tau_d_beta = float(tau_d_beta)
        if any(
            not math.isfinite(value) or value <= 0.0
            for value in (self.tau_b, self.tau_c, self.tau_d_beta)
        ):
            raise ValueError("all frozen deployment powers must be positive")
        self._atom_ids = bank.geometry.atom_ids
        self._atom_index = {atom_id: i for i, atom_id in enumerate(self._atom_ids)}
        self._atoms: tuple[tuple[mp.mpf, ...], ...] | None = None
        self._cal_rows: tuple[tuple[mp.mpf, ...], ...] | None = None
        self._dep_rows: tuple[tuple[mp.mpf, ...], ...] | None = None
        self._kernel_cache: dict[tuple, tuple[mp.mpf, mp.matrix, tuple[int, ...], tuple[mp.mpf, ...], mp.mpf]] = {}
        self._cal_component_rows: dict[tuple[int, ...], tuple[mp.mpf, ...]] = {}
        self._cal_state_prefix: dict[int, tuple[mp.mpf, ...]] = {}
        self._dep_explanation_prefix: dict[int, tuple[mp.mpf, ...]] = {}
        self._candidate_cache: dict[int, HighPrecisionReplayResult] = {}

    @staticmethod
    def _m(value: float) -> mp.mpf:
        return mp.mpf(repr(float(value)))

    def _prepare(self) -> None:
        if self._atoms is not None:
            return
        self._atoms = tuple(
            tuple(self._m(value) for value in atom.vector)
            for atom in self.bank.geometry.all_atoms
        )
        self._cal_rows = tuple(
            tuple(self._m(value) for value in row)
            for row in np.asarray(self.splits.calibration.evaluation)
        )
        self._dep_rows = tuple(
            tuple(self._m(value) for value in row)
            for row in np.asarray(self.splits.deployment.evaluation)
        )

    def _kernel(
        self,
        atom_indices: tuple[int, ...],
        scales: tuple[float, ...],
        noise: float,
    ) -> tuple[mp.mpf, mp.matrix, tuple[int, ...], tuple[mp.mpf, ...], mp.mpf]:
        key = (atom_indices, tuple(repr(float(s)) for s in scales), repr(float(noise)))
        cached = self._kernel_cache.get(key)
        if cached is not None:
            return cached
        assert self._atoms is not None
        nu = self._m(noise)
        scale_mp = tuple(self._m(s) for s in scales)
        k = len(atom_indices)
        if k:
            gram = mp.matrix(k, k)
            for i in range(k):
                for j in range(k):
                    gram[i, j] = (
                        scale_mp[i]
                        * scale_mp[j]
                        * mp.fdot(self._atoms[atom_indices[i]], self._atoms[atom_indices[j]])
                    )
            middle = mp.eye(k) + gram / nu
            determinant = mp.det(middle)
            if determinant <= 0:
                raise ArithmeticError("90-decimal covariance kernel is not SPD")
            inverse = middle ** -1
            logdet_middle = mp.log(determinant)
        else:
            inverse = mp.matrix(0, 0)
            logdet_middle = mp.mpf("0")
        logdet = Q * mp.log(nu) + logdet_middle
        log_normalizer = -mp.mpf("0.5") * (
            Q * mp.log(2 * mp.pi) + logdet
        )
        result = (nu, inverse, atom_indices, scale_mp, log_normalizer)
        self._kernel_cache[key] = result
        return result

    def _kernel_logpdf_rows(
        self,
        rows: tuple[tuple[mp.mpf, ...], ...],
        atom_indices: tuple[int, ...],
        scales: tuple[float, ...],
        noise: float,
    ) -> tuple[mp.mpf, ...]:
        assert self._atoms is not None
        nu, inverse, indices, scale_mp, normalizer = self._kernel(
            atom_indices, scales, noise
        )
        out: list[mp.mpf] = []
        for row in rows:
            quadratic = mp.fdot(row, row) / nu
            if indices:
                projected = mp.matrix(
                    [
                        scale_mp[i] * mp.fdot(row, self._atoms[atom_index])
                        for i, atom_index in enumerate(indices)
                    ]
                )
                quadratic -= (projected.T * inverse * projected)[0] / (nu * nu)
            out.append(normalizer - mp.mpf("0.5") * quadratic)
        return tuple(out)

    def _cal_component(self, key: tuple[int, ...]) -> tuple[mp.mpf, ...]:
        cached = self._cal_component_rows.get(key)
        if cached is not None:
            return cached
        assert self._cal_rows is not None
        values = self._kernel_logpdf_rows(
            self._cal_rows, key, (1.0,) * len(key), NU_CALIBRATION
        )
        self._cal_component_rows[key] = values
        return values

    @staticmethod
    def _prefix_at(values: Iterable[mp.mpf], checkpoints: Iterable[int]) -> tuple[mp.mpf, ...]:
        wanted = tuple(int(v) for v in checkpoints)
        out: list[mp.mpf] = []
        total = mp.mpf("0")
        next_index = 0
        for count, value in enumerate(values, 1):
            total += value
            if next_index < len(wanted) and count == wanted[next_index]:
                out.append(+total)
                next_index += 1
        if next_index != len(wanted):
            raise RuntimeError("90-decimal prefix did not reach every checkpoint")
        return tuple(out)

    def _cal_prefix(self, state_index: int) -> tuple[mp.mpf, ...]:
        cached = self._cal_state_prefix.get(state_index)
        if cached is not None:
            return cached
        assert self._cal_rows is not None
        state = self.bank.dictionary_states[state_index]
        state_ids = state.atom_ids + (ANCHOR_ID,)
        masks = binary_masks()
        components: list[tuple[mp.mpf, ...]] = []
        log_weights: list[mp.mpf] = []
        p = self._m(P_CALIBRATION)
        for mask in masks:
            key = tuple(
                self._atom_index[atom_id]
                for atom_id, active in zip(state_ids, mask)
                if int(active)
            )
            components.append(self._cal_component(key))
            size = int(np.sum(mask))
            log_weights.append(size * mp.log(p) + (5 - size) * mp.log(1 - p))
        row_logpdf: list[mp.mpf] = []
        for row_index in range(len(self._cal_rows)):
            terms = [
                log_weights[j] + components[j][row_index]
                for j in range(len(components))
            ]
            maximum = max(terms)
            row_logpdf.append(maximum + mp.log(mp.fsum(mp.exp(v - maximum) for v in terms)))
        result = self._prefix_at(row_logpdf, self.table.calibration_checkpoints)
        self._cal_state_prefix[state_index] = result
        return result

    def _dep_prefix(self, explanation_index: int) -> tuple[mp.mpf, ...]:
        cached = self._dep_explanation_prefix.get(explanation_index)
        if cached is not None:
            return cached
        assert self._dep_rows is not None
        explanation = self.bank.explanations[explanation_index]
        state = self.bank.dictionary_states[explanation.dictionary_index]
        support = self.bank.support_patterns[explanation.support_index]
        powers = {
            "A": TAU_A,
            "B": self.tau_b,
            "C": self.tau_c,
            "D": self.tau_d_beta,
        }
        indices = tuple(
            self._atom_index[state.atom_id_for_region(region)]
            for region in support.regions
        )
        scales = tuple(powers[region] for region in support.regions)
        rows = self._kernel_logpdf_rows(
            self._dep_rows, indices, scales, NU_DEPLOYMENT
        )
        result = self._prefix_at(rows, self.table.deployment_checkpoints)
        self._dep_explanation_prefix[explanation_index] = result
        return result

    def replay(self, candidate_id: int) -> HighPrecisionReplayResult:
        cid = int(candidate_id)
        if not 1 <= cid <= len(self.bank.explanations):
            raise IndexError(cid)
        cached = self._candidate_cache.get(cid)
        if cached is not None:
            return cached
        index = cid - 1
        explanation = self.bank.explanations[index]
        with mp.workdps(HP_DECIMAL_DIGITS):
            self._prepare()
            cal_num = self._cal_prefix(
                self.table.proposal.calibration_dictionary_index
            )
            cal_den = self._cal_prefix(explanation.dictionary_index)
            dep_num = self._dep_prefix(
                self.table.proposal.deployment_explanation_index
            )
            dep_den = self._dep_prefix(index)
            cal_lookup = {
                int(value): i
                for i, value in enumerate(self.table.calibration_checkpoints)
            }
            dep_lookup = {
                int(value): i
                for i, value in enumerate(self.table.deployment_checkpoints)
            }
            threshold = mp.log(1 / self._m(self.table.alpha))
            margins: list[mp.mpf] = []
            for checkpoint in self.table.joint_checkpoints:
                value = mp.mpf("0")
                if checkpoint.calibration_checkpoint:
                    i = cal_lookup[checkpoint.calibration_checkpoint]
                    value += cal_num[i] - cal_den[i]
                if checkpoint.deployment_checkpoint:
                    i = dep_lookup[checkpoint.deployment_checkpoint]
                    value += dep_num[i] - dep_den[i]
                margins.append(value - threshold)
            max_index = max(range(len(margins)), key=margins.__getitem__)
            maximum = margins[max_index]
            result = HighPrecisionReplayResult(
                candidate_id=cid,
                explanation_index=index,
                maximum_margin_decimal=mp.nstr(maximum, HP_DECIMAL_DIGITS),
                maximum_margin=float(maximum),
                maximum_joint_checkpoint_index=max_index,
                survives=bool(maximum <= 0),
                decimal_digits=HP_DECIMAL_DIGITS,
            )
        self._candidate_cache[cid] = result
        return result
