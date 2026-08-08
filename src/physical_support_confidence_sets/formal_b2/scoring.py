"""Deterministic split e-process scoring for the frozen D2 candidate bank."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import product
import math
import time

import numpy as np

from .bank import CandidateBank
from .constants import (
    ALPHA,
    ANCHOR_ID,
    CHECKPOINT_MINIMUM,
    EXPLANATION_COUNT,
    LATENT_COORDINATE_COUNT,
    MIXTURE_COMPONENT_COUNT,
    NU_CALIBRATION,
    NU_DEPLOYMENT,
    P_CALIBRATION,
    Q,
    TAU_A,
)
from .data import PilotSplits
from .util import readonly_float_array


def binary_masks() -> np.ndarray:
    masks = np.asarray(
        list(product((0, 1), repeat=LATENT_COORDINATE_COUNT)),
        dtype=np.int8,
    )
    masks.setflags(write=False)
    return masks


def mixture_weights(p: float = P_CALIBRATION) -> np.ndarray:
    probability = float(p)
    if not 0.0 < probability < 1.0:
        raise ValueError("mixture probability must belong to (0,1)")
    masks = binary_masks()
    sizes = masks.sum(axis=1)
    weights = probability**sizes * (1.0 - probability) ** (
        LATENT_COORDINATE_COUNT - sizes
    )
    result = np.asarray(weights, dtype=float)
    result.setflags(write=False)
    return result


def frozen_checkpoints(evaluation_size: int) -> np.ndarray:
    size = int(evaluation_size)
    if size <= 0:
        raise ValueError("evaluation size must be positive")
    if size < CHECKPOINT_MINIMUM:
        result = np.asarray([size], dtype=np.int64)
        result.setflags(write=False)
        return result
    values: list[int] = []
    checkpoint = CHECKPOINT_MINIMUM
    while checkpoint <= size:
        values.append(checkpoint)
        checkpoint *= 2
    if values[-1] != size:
        values.append(size)
    result = np.asarray(values, dtype=np.int64)
    result.setflags(write=False)
    return result


def _validate_observations(observations: np.ndarray) -> np.ndarray:
    values = np.asarray(observations, dtype=float)
    if values.ndim != 2 or values.shape[1] != Q or not len(values):
        raise ValueError("observations must have nonempty shape (N,16)")
    if not np.all(np.isfinite(values)):
        raise ValueError("observations must be finite")
    return values


@dataclass(frozen=True)
class _LowRankGaussianKernel:
    atom_indices: tuple[int, ...]
    atom_scales: tuple[float, ...]
    correction: np.ndarray
    log_normalizer: float


def _low_rank_kernel(
    atom_matrix: np.ndarray,
    atom_indices: tuple[int, ...],
    atom_scales: tuple[float, ...],
    *,
    noise: float,
) -> _LowRankGaussianKernel:
    if len(atom_indices) != len(atom_scales):
        raise ValueError("low-rank atom indices/scales mismatch")
    nu = float(noise)
    if not math.isfinite(nu) or nu <= 0.0:
        raise ValueError("noise variance must be positive")
    if atom_indices:
        design = atom_matrix[:, atom_indices] * np.asarray(atom_scales)[None, :]
        middle = np.eye(len(atom_indices)) + design.T @ design / nu
        sign, logdet_middle = np.linalg.slogdet(middle)
        if sign <= 0.0:
            raise ArithmeticError("low-rank Gaussian covariance is not SPD")
        correction = np.linalg.inv(middle) / nu**2
    else:
        logdet_middle = 0.0
        correction = np.empty((0, 0), dtype=float)
    logdet = Q * math.log(nu) + float(logdet_middle)
    log_normalizer = -0.5 * (Q * math.log(2.0 * math.pi) + logdet)
    return _LowRankGaussianKernel(
        atom_indices=tuple(atom_indices),
        atom_scales=tuple(float(value) for value in atom_scales),
        correction=readonly_float_array(correction, ndim=2),
        log_normalizer=float(log_normalizer),
    )


def _evaluate_unique_kernels(
    observations: np.ndarray,
    atom_matrix: np.ndarray,
    kernels: tuple[_LowRankGaussianKernel, ...],
    *,
    noise: float,
) -> np.ndarray:
    values = _validate_observations(observations)
    projections = values @ atom_matrix
    norm_squared = np.sum(values**2, axis=1)
    result = np.empty((len(values), len(kernels)), dtype=float)
    for index, kernel in enumerate(kernels):
        quadratic = norm_squared / float(noise)
        if kernel.atom_indices:
            projected = projections[:, kernel.atom_indices] * np.asarray(
                kernel.atom_scales
            )[None, :]
            quadratic = quadratic - np.einsum(
                "ni,ij,nj->n",
                projected,
                kernel.correction,
                projected,
                optimize=True,
            )
        result[:, index] = kernel.log_normalizer - 0.5 * quadratic
    if not np.all(np.isfinite(result)):
        raise ArithmeticError("Gaussian log likelihood is nonfinite")
    return result


@dataclass(frozen=True)
class CalibrationLikelihoodCache:
    bank: CandidateBank
    kernels: tuple[_LowRankGaussianKernel, ...]
    state_component_indices: np.ndarray
    log_weights: np.ndarray

    @classmethod
    def from_bank(cls, bank: CandidateBank) -> "CalibrationLikelihoodCache":
        atom_ids = bank.geometry.atom_ids
        atom_index = {atom_id: index for index, atom_id in enumerate(atom_ids)}
        masks = binary_masks()
        kernel_by_key: dict[tuple[int, ...], int] = {}
        kernels: list[_LowRankGaussianKernel] = []
        mapping = np.empty(
            (len(bank.dictionary_states), MIXTURE_COMPONENT_COUNT), dtype=np.int64
        )
        for state in bank.dictionary_states:
            state_ids = state.atom_ids + (ANCHOR_ID,)
            for mask_index, mask in enumerate(masks):
                key = tuple(
                    atom_index[atom_id]
                    for atom_id, active in zip(state_ids, mask)
                    if int(active)
                )
                kernel_index = kernel_by_key.get(key)
                if kernel_index is None:
                    kernel_index = len(kernels)
                    kernel_by_key[key] = kernel_index
                    kernels.append(
                        _low_rank_kernel(
                            bank.geometry.atom_matrix,
                            key,
                            (1.0,) * len(key),
                            noise=NU_CALIBRATION,
                        )
                    )
                mapping[state.index, mask_index] = kernel_index
        mapping.setflags(write=False)
        weights = mixture_weights()
        log_weights = np.log(weights)
        log_weights.setflags(write=False)
        return cls(
            bank=bank,
            kernels=tuple(kernels),
            state_component_indices=mapping,
            log_weights=log_weights,
        )

    def logpdf_matrix(self, observations: np.ndarray) -> np.ndarray:
        components = _evaluate_unique_kernels(
            observations,
            self.bank.geometry.atom_matrix,
            self.kernels,
            noise=NU_CALIBRATION,
        )
        result = np.empty(
            (components.shape[0], len(self.bank.dictionary_states)), dtype=float
        )
        for state in self.bank.dictionary_states:
            values = (
                components[:, self.state_component_indices[state.index]]
                + self.log_weights[None, :]
            )
            maxima = np.max(values, axis=1)
            result[:, state.index] = maxima + np.log(
                np.sum(np.exp(values - maxima[:, None]), axis=1)
            )
        if not np.all(np.isfinite(result)):
            raise ArithmeticError("calibration mixture likelihood is nonfinite")
        return result


@dataclass(frozen=True)
class DeploymentLikelihoodCache:
    bank: CandidateBank
    tau_b: float
    tau_c: float
    tau_d_beta: float
    kernels: tuple[_LowRankGaussianKernel, ...]
    explanation_kernel_indices: np.ndarray

    @classmethod
    def from_bank(
        cls,
        bank: CandidateBank,
        *,
        tau_b: float,
        tau_c: float,
        tau_d_beta: float,
    ) -> "DeploymentLikelihoodCache":
        powers = {
            "A": TAU_A,
            "B": float(tau_b),
            "C": float(tau_c),
            "D": float(tau_d_beta),
        }
        if any(not math.isfinite(value) or value <= 0.0 for value in powers.values()):
            raise ValueError("all frozen deployment powers must be positive")
        atom_index = {
            atom_id: index for index, atom_id in enumerate(bank.geometry.atom_ids)
        }
        kernel_by_key: dict[tuple[tuple[int, float], ...], int] = {}
        kernels: list[_LowRankGaussianKernel] = []
        mapping = np.empty(len(bank.explanations), dtype=np.int64)
        for explanation in bank.explanations:
            state = bank.dictionary_states[explanation.dictionary_index]
            support = bank.support_patterns[explanation.support_index]
            key = tuple(
                (
                    atom_index[state.atom_id_for_region(region)],
                    float(powers[region]),
                )
                for region in support.regions
            )
            kernel_index = kernel_by_key.get(key)
            if kernel_index is None:
                kernel_index = len(kernels)
                kernel_by_key[key] = kernel_index
                kernels.append(
                    _low_rank_kernel(
                        bank.geometry.atom_matrix,
                        tuple(item[0] for item in key),
                        tuple(item[1] for item in key),
                        noise=NU_DEPLOYMENT,
                    )
                )
            mapping[explanation.index] = kernel_index
        mapping.setflags(write=False)
        return cls(
            bank=bank,
            tau_b=powers["B"],
            tau_c=powers["C"],
            tau_d_beta=powers["D"],
            kernels=tuple(kernels),
            explanation_kernel_indices=mapping,
        )

    def logpdf_matrix(self, observations: np.ndarray) -> np.ndarray:
        unique = _evaluate_unique_kernels(
            observations,
            self.bank.geometry.atom_matrix,
            self.kernels,
            noise=NU_DEPLOYMENT,
        )
        result = unique[:, self.explanation_kernel_indices]
        if not np.all(np.isfinite(result)):
            raise ArithmeticError("deployment likelihood is nonfinite")
        return np.asarray(result, dtype=float)


@dataclass(frozen=True)
class ProposalSelection:
    calibration_dictionary_index: int
    calibration_dictionary_id: str
    calibration_log_likelihood: float
    deployment_explanation_index: int
    deployment_candidate_id: str
    deployment_log_likelihood: float
    plugin_explanation_index: int
    plugin_candidate_id: str


def select_split_a_proposals(
    bank: CandidateBank,
    calibration_logpdf: np.ndarray,
    deployment_logpdf: np.ndarray,
) -> ProposalSelection:
    calibration = np.asarray(calibration_logpdf, dtype=float)
    deployment = np.asarray(deployment_logpdf, dtype=float)
    if calibration.ndim != 2 or calibration.shape[1] != len(bank.dictionary_states):
        raise ValueError("calibration proposal score matrix has invalid shape")
    if deployment.ndim != 2 or deployment.shape[1] != len(bank.explanations):
        raise ValueError("deployment proposal score matrix has invalid shape")
    calibration_scores = np.sum(calibration, axis=0)
    deployment_scores = np.sum(deployment, axis=0)
    if not np.all(np.isfinite(calibration_scores)) or not np.all(
        np.isfinite(deployment_scores)
    ):
        raise ArithmeticError("split-A proposal score is nonfinite")
    # np.argmax returns the first maximum, hence the lowest canonical index.
    calibration_index = int(np.argmax(calibration_scores))
    deployment_index = int(np.argmax(deployment_scores))
    return ProposalSelection(
        calibration_dictionary_index=calibration_index,
        calibration_dictionary_id=bank.dictionary_states[
            calibration_index
        ].dictionary_id,
        calibration_log_likelihood=float(calibration_scores[calibration_index]),
        deployment_explanation_index=deployment_index,
        deployment_candidate_id=bank.explanations[deployment_index].candidate_id,
        deployment_log_likelihood=float(deployment_scores[deployment_index]),
        plugin_explanation_index=deployment_index,
        plugin_candidate_id=bank.explanations[deployment_index].candidate_id,
    )


def prefix_log_likelihoods(
    logpdf_matrix: np.ndarray, checkpoints: np.ndarray
) -> np.ndarray:
    values = np.asarray(logpdf_matrix, dtype=float)
    points = np.asarray(checkpoints, dtype=np.int64)
    if values.ndim != 2 or not len(values):
        raise ValueError("logpdf matrix must be nonempty and two-dimensional")
    if points.ndim != 1 or not len(points):
        raise ValueError("checkpoints must be nonempty and one-dimensional")
    if (
        np.any(points <= 0)
        or np.any(points > len(values))
        or np.any(np.diff(points) <= 0)
    ):
        raise ValueError("checkpoints must be strictly increasing valid counts")
    return np.cumsum(values, axis=0)[points - 1]


@dataclass(frozen=True)
class JointCheckpoint:
    index: int
    fraction_numerator: int
    fraction_denominator: int
    calibration_checkpoint: int
    deployment_checkpoint: int


def joint_checkpoint_path(
    calibration_checkpoints: np.ndarray,
    calibration_size: int,
    deployment_checkpoints: np.ndarray,
    deployment_size: int,
) -> tuple[JointCheckpoint, ...]:
    calibration = tuple(int(value) for value in calibration_checkpoints)
    deployment = tuple(int(value) for value in deployment_checkpoints)
    cal_size = int(calibration_size)
    dep_size = int(deployment_size)
    if cal_size <= 0 or dep_size <= 0:
        raise ValueError("held-out sizes must be positive")
    if (
        not calibration
        or calibration[-1] != cal_size
        or any(left >= right for left, right in zip(calibration, calibration[1:]))
    ):
        raise ValueError("invalid calibration checkpoint sequence")
    if (
        not deployment
        or deployment[-1] != dep_size
        or any(left >= right for left, right in zip(deployment, deployment[1:]))
    ):
        raise ValueError("invalid deployment checkpoint sequence")
    fractions = sorted(
        {Fraction(value, cal_size) for value in calibration}
        | {Fraction(value, dep_size) for value in deployment}
    )
    pairs: list[tuple[Fraction, int, int]] = []
    for fraction in fractions:
        cal_at = max(
            (value for value in calibration if Fraction(value, cal_size) <= fraction),
            default=0,
        )
        dep_at = max(
            (value for value in deployment if Fraction(value, dep_size) <= fraction),
            default=0,
        )
        pair = (cal_at, dep_at)
        if pairs and pair == pairs[-1][1:]:
            continue
        pairs.append((fraction, cal_at, dep_at))
    return tuple(
        JointCheckpoint(
            index=index,
            fraction_numerator=fraction.numerator,
            fraction_denominator=fraction.denominator,
            calibration_checkpoint=cal_at,
            deployment_checkpoint=dep_at,
        )
        for index, (fraction, cal_at, dep_at) in enumerate(pairs)
    )


@dataclass(frozen=True)
class CandidateScoreTable:
    proposal: ProposalSelection
    calibration_checkpoints: np.ndarray
    deployment_checkpoints: np.ndarray
    joint_checkpoints: tuple[JointCheckpoint, ...]
    checkpoint_log_e: np.ndarray
    maximum_log_e: np.ndarray
    maximum_rejection_margin: np.ndarray
    maximum_checkpoint_index: np.ndarray
    survives_all_checkpoints: np.ndarray
    roundoff_absolute_scale: np.ndarray
    alpha: float


def score_candidate_bank(
    bank: CandidateBank,
    splits: PilotSplits,
    calibration_cache: CalibrationLikelihoodCache,
    deployment_cache: DeploymentLikelihoodCache,
    *,
    alpha: float = ALPHA,
    timings: dict[str, float] | None = None,
) -> CandidateScoreTable:
    risk = float(alpha)
    if not math.isfinite(risk) or not 0.0 < risk < 1.0:
        raise ValueError("alpha must belong to (0,1)")
    if calibration_cache.bank is not bank or deployment_cache.bank is not bank:
        raise ValueError("likelihood caches do not belong to the supplied bank")

    started = time.perf_counter()
    cal_a = calibration_cache.logpdf_matrix(splits.calibration.proposal)
    calibration_proposal_seconds = time.perf_counter() - started
    started = time.perf_counter()
    dep_a = deployment_cache.logpdf_matrix(splits.deployment.proposal)
    deployment_proposal_seconds = time.perf_counter() - started
    started = time.perf_counter()
    proposal = select_split_a_proposals(bank, cal_a, dep_a)
    proposal_selection_seconds = time.perf_counter() - started

    started = time.perf_counter()
    cal_b = calibration_cache.logpdf_matrix(splits.calibration.evaluation)
    calibration_evaluation_seconds = time.perf_counter() - started
    started = time.perf_counter()
    dep_b = deployment_cache.logpdf_matrix(splits.deployment.evaluation)
    deployment_evaluation_seconds = time.perf_counter() - started
    joint_started = time.perf_counter()
    cal_checkpoints = frozen_checkpoints(len(cal_b))
    dep_checkpoints = frozen_checkpoints(len(dep_b))
    cal_prefix = prefix_log_likelihoods(cal_b, cal_checkpoints)
    dep_prefix = prefix_log_likelihoods(dep_b, dep_checkpoints)

    cal_numerator = cal_prefix[:, proposal.calibration_dictionary_index]
    dep_numerator = dep_prefix[:, proposal.deployment_explanation_index]
    # Shapes: state/explanation by factor checkpoint.
    cal_log_e = (cal_numerator[:, None] - cal_prefix).T
    dep_log_e = (dep_numerator[:, None] - dep_prefix).T

    joint = joint_checkpoint_path(
        cal_checkpoints,
        len(cal_b),
        dep_checkpoints,
        len(dep_b),
    )
    cal_lookup = {int(value): index for index, value in enumerate(cal_checkpoints)}
    dep_lookup = {int(value): index for index, value in enumerate(dep_checkpoints)}
    checkpoint_log_e = np.empty((EXPLANATION_COUNT, len(joint)), dtype=float)
    for joint_index, checkpoint in enumerate(joint):
        if checkpoint.calibration_checkpoint:
            factor = cal_log_e[
                [row.dictionary_index for row in bank.explanations],
                cal_lookup[checkpoint.calibration_checkpoint],
            ]
        else:
            factor = np.zeros(EXPLANATION_COUNT, dtype=float)
        if checkpoint.deployment_checkpoint:
            factor = factor + dep_log_e[
                :, dep_lookup[checkpoint.deployment_checkpoint]
            ]
        checkpoint_log_e[:, joint_index] = factor
    if not np.all(np.isfinite(checkpoint_log_e)):
        raise ArithmeticError("joint checkpoint log e-value is nonfinite")
    maximum_indices = np.argmax(checkpoint_log_e, axis=1).astype(np.int64)
    maxima = checkpoint_log_e[np.arange(EXPLANATION_COUNT), maximum_indices]
    margin = maxima - math.log(1.0 / risk)
    survives = margin <= 0.0
    cal_abs_numerator = float(
        np.sum(np.abs(cal_b[:, proposal.calibration_dictionary_index]))
    )
    cal_abs_states = np.sum(np.abs(cal_b), axis=0)
    dep_abs_numerator = float(
        np.sum(np.abs(dep_b[:, proposal.deployment_explanation_index]))
    )
    dep_abs_explanations = np.sum(np.abs(dep_b), axis=0)
    roundoff_scale = np.asarray(
        [
            cal_abs_numerator
            + float(cal_abs_states[row.dictionary_index])
            + dep_abs_numerator
            + float(dep_abs_explanations[row.index])
            + abs(math.log(1.0 / risk))
            for row in bank.explanations
        ],
        dtype=float,
    )
    joint_assembly_seconds = time.perf_counter() - joint_started
    for array in (
        cal_checkpoints,
        dep_checkpoints,
        checkpoint_log_e,
        maximum_indices,
        maxima,
        margin,
        survives,
        roundoff_scale,
    ):
        array.setflags(write=False)
    result = CandidateScoreTable(
        proposal=proposal,
        calibration_checkpoints=cal_checkpoints,
        deployment_checkpoints=dep_checkpoints,
        joint_checkpoints=joint,
        checkpoint_log_e=checkpoint_log_e,
        maximum_log_e=maxima,
        maximum_rejection_margin=margin,
        maximum_checkpoint_index=maximum_indices,
        survives_all_checkpoints=survives,
        roundoff_absolute_scale=roundoff_scale,
        alpha=risk,
    )
    if timings is not None:
        timings.update(
            {
                "calibration_proposal_scoring_seconds": calibration_proposal_seconds,
                "calibration_evaluation_scoring_seconds": calibration_evaluation_seconds,
                "calibration_scoring_seconds": calibration_proposal_seconds
                + calibration_evaluation_seconds,
                "deployment_proposal_scoring_seconds": deployment_proposal_seconds,
                "deployment_evaluation_scoring_seconds": deployment_evaluation_seconds,
                "deployment_scoring_seconds": deployment_proposal_seconds
                + deployment_evaluation_seconds,
                "proposal_selection_seconds": proposal_selection_seconds,
                "joint_checkpoint_assembly_seconds": joint_assembly_seconds,
            }
        )
    return result
