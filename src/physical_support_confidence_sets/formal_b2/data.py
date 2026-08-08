"""Frozen synthetic data generation and proposal/evaluation splitting."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from .bank import CandidateBank, DictionaryState
from .constants import (
    CALIBRATION_PROPOSAL_FRACTION,
    DEPLOYMENT_PROPOSAL_FRACTION,
    NU_CALIBRATION,
    NU_DEPLOYMENT,
    P_CALIBRATION,
    Q,
    SCENE_SUPPORTS,
    TAU_A,
)
from .util import readonly_float_array


@dataclass(frozen=True)
class SplitSample:
    proposal: np.ndarray
    evaluation: np.ndarray
    proposal_indices: np.ndarray
    evaluation_indices: np.ndarray


@dataclass(frozen=True)
class PilotData:
    calibration: np.ndarray
    deployment: np.ndarray


@dataclass(frozen=True)
class PilotSplits:
    calibration: SplitSample
    deployment: SplitSample


def _validated_size(size: int) -> int:
    if isinstance(size, bool) or int(size) != size or int(size) <= 0:
        raise ValueError("sample size must be a positive integer")
    return int(size)


def split_sample(
    observations: np.ndarray,
    *,
    proposal_fraction: float,
    rng: np.random.Generator,
) -> SplitSample:
    values = np.asarray(observations, dtype=float)
    fraction = float(proposal_fraction)
    if values.ndim != 2 or values.shape[1] != Q or not len(values):
        raise ValueError("observations must have nonempty shape (N,16)")
    if not np.all(np.isfinite(values)):
        raise ValueError("observations must be finite")
    if not 0.0 < fraction < 1.0:
        raise ValueError("proposal fraction must belong to (0,1)")
    permutation = np.asarray(rng.permutation(len(values)), dtype=np.int64)
    proposal_size = int(math.floor(fraction * len(values)))
    if proposal_size <= 0 or proposal_size >= len(values):
        raise ValueError("split must leave both proposal and evaluation rows")
    proposal_indices = permutation[:proposal_size].copy()
    evaluation_indices = permutation[proposal_size:].copy()
    proposal_indices.setflags(write=False)
    evaluation_indices.setflags(write=False)
    return SplitSample(
        proposal=readonly_float_array(values[proposal_indices], ndim=2),
        evaluation=readonly_float_array(values[evaluation_indices], ndim=2),
        proposal_indices=proposal_indices,
        evaluation_indices=evaluation_indices,
    )


def split_pilot_data(data: PilotData, split_seed: int) -> PilotSplits:
    calibration_seed, deployment_seed = np.random.SeedSequence(
        int(split_seed)
    ).spawn(2)
    return PilotSplits(
        calibration=split_sample(
            data.calibration,
            proposal_fraction=CALIBRATION_PROPOSAL_FRACTION,
            rng=np.random.default_rng(calibration_seed),
        ),
        deployment=split_sample(
            data.deployment,
            proposal_fraction=DEPLOYMENT_PROPOSAL_FRACTION,
            rng=np.random.default_rng(deployment_seed),
        ),
    )


def sample_calibration(
    dictionary_state: DictionaryState,
    size: int,
    *,
    rng: np.random.Generator,
) -> np.ndarray:
    count = _validated_size(size)
    design = np.asarray(dictionary_state.matrix, dtype=float)
    if design.shape != (Q, 5):
        raise ValueError("calibration dictionary must have shape (16,5)")
    indicators = rng.random((count, 5)) < P_CALIBRATION
    coefficients = indicators * rng.standard_normal((count, 5))
    noise = math.sqrt(NU_CALIBRATION) * rng.standard_normal((count, Q))
    return readonly_float_array(coefficients @ design.T + noise, ndim=2)


def deployment_covariance(
    bank: CandidateBank,
    dictionary_state: DictionaryState,
    regions: tuple[str, ...],
    *,
    tau_b: float,
    tau_c: float,
    tau_d_beta: float,
) -> np.ndarray:
    powers = {
        "A": TAU_A,
        "B": float(tau_b),
        "C": float(tau_c),
        "D": float(tau_d_beta),
    }
    if any(not math.isfinite(value) or value <= 0.0 for value in powers.values()):
        raise ValueError("all frozen deployment powers must be positive")
    covariance = NU_DEPLOYMENT * np.eye(Q)
    for region in regions:
        if region not in powers:
            raise ValueError(f"unknown deployment region: {region}")
        atom = bank.geometry.atom(dictionary_state.atom_id_for_region(region)).vector
        covariance = covariance + powers[region] ** 2 * np.outer(atom, atom)
    return readonly_float_array(covariance, ndim=2)


def sample_deployment(
    bank: CandidateBank,
    dictionary_state: DictionaryState,
    regions: tuple[str, ...],
    size: int,
    *,
    tau_b: float,
    tau_c: float,
    tau_d_beta: float,
    rng: np.random.Generator,
) -> np.ndarray:
    count = _validated_size(size)
    covariance = deployment_covariance(
        bank,
        dictionary_state,
        tuple(regions),
        tau_b=float(tau_b),
        tau_c=float(tau_c),
        tau_d_beta=float(tau_d_beta),
    )
    factor = np.linalg.cholesky(covariance)
    values = rng.standard_normal((count, Q)) @ factor.T
    return readonly_float_array(values, ndim=2)


def generate_pilot_data(
    bank: CandidateBank,
    scene: str,
    *,
    calibration_size: int,
    deployment_size: int,
    tau_b: float,
    tau_c: float,
    tau_d_beta: float,
    data_seed: int,
) -> PilotData:
    if scene not in SCENE_SUPPORTS:
        raise ValueError(f"unknown frozen scene: {scene}")
    calibration_seed, deployment_seed = np.random.SeedSequence(
        int(data_seed)
    ).spawn(2)
    truth = bank.dictionary_states[bank.true_dictionary_index]
    return PilotData(
        calibration=sample_calibration(
            truth,
            calibration_size,
            rng=np.random.default_rng(calibration_seed),
        ),
        deployment=sample_deployment(
            bank,
            truth,
            SCENE_SUPPORTS[scene],
            deployment_size,
            tau_b=float(tau_b),
            tau_c=float(tau_c),
            tau_d_beta=float(tau_d_beta),
            rng=np.random.default_rng(deployment_seed),
        ),
    )
