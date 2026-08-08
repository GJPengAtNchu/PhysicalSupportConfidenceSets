"""Raw/numerical coordinate maps for `(phi,p,nu)`."""

from __future__ import annotations

import math

import numpy as np

from .config import FROZEN


_A_LEFT = math.log(FROZEN.p_left / (1.0 - FROZEN.p_left))
_A_RIGHT = math.log(FROZEN.p_right / (1.0 - FROZEN.p_right))
_A_MIDDLE = 0.5 * (_A_LEFT + _A_RIGHT)
_A_HALF = 0.5 * (_A_RIGHT - _A_LEFT)
_B_LEFT = math.log(FROZEN.nu_left)
_B_RIGHT = math.log(FROZEN.nu_right)
_B_MIDDLE = 0.5 * (_B_LEFT + _B_RIGHT)
_B_HALF = 0.5 * (_B_RIGHT - _B_LEFT)


def raw_to_normalized(phi: float, p: float, nu: float) -> np.ndarray:
    """Map raw candidate parameters into the frozen cube `[-1,1]^3`."""
    if not (
        FROZEN.phi_left <= float(phi) <= FROZEN.phi_right
        and FROZEN.p_left <= float(p) <= FROZEN.p_right
        and FROZEN.nu_left <= float(nu) <= FROZEN.nu_right
    ):
        raise ValueError("candidate lies outside the frozen R1 shell")
    logit = math.log(float(p) / (1.0 - float(p)))
    result = np.asarray(
        [
            float(phi) / 0.4,
            (logit - _A_MIDDLE) / _A_HALF,
            (math.log(float(nu)) - _B_MIDDLE) / _B_HALF,
        ],
        dtype=float,
    )
    return np.clip(result, -1.0, 1.0)


def normalized_to_raw(x: np.ndarray) -> tuple[float, float, float]:
    """Map one normalized cube coordinate to raw `(phi,p,nu)`."""
    value = np.asarray(x, dtype=float)
    if (
        value.shape != (3,)
        or np.any(value < -1.0 - FROZEN.transform_tolerance)
        or np.any(value > 1.0 + FROZEN.transform_tolerance)
    ):
        raise ValueError("normalized coordinate must belong to [-1,1]^3")
    value = np.clip(value, -1.0, 1.0)
    phi = 0.4 * float(value[0])
    logit = _A_MIDDLE + _A_HALF * float(value[1])
    p = 1.0 / (1.0 + math.exp(-logit))
    nu = math.exp(_B_MIDDLE + _B_HALF * float(value[2]))
    return phi, p, nu


def raw_derivatives_from_normalized(
    x: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Return diagonal first/second derivatives of raw coordinates in `x`."""
    _, p, nu = normalized_to_raw(np.asarray(x, dtype=float))
    first = np.asarray(
        [
            0.4,
            _A_HALF * p * (1.0 - p),
            _B_HALF * nu,
        ],
        dtype=float,
    )
    second = np.asarray(
        [
            0.0,
            _A_HALF**2 * p * (1.0 - p) * (1.0 - 2.0 * p),
            _B_HALF**2 * nu,
        ],
        dtype=float,
    )
    return first, second


def raw_box_widths(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """Return raw `(phi,p,nu)` widths of one normalized box."""
    raw_left = np.asarray(normalized_to_raw(np.asarray(left, dtype=float)))
    raw_right = np.asarray(normalized_to_raw(np.asarray(right, dtype=float)))
    return raw_right - raw_left
