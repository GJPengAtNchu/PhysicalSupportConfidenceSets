"""Canonical score-free carriers for B0.1's frozen role-specific banks."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
import math
from typing import Iterator, Sequence


def _canonical_decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return f"{normalized:.1f}"
    return format(normalized, "f")


PHI_GRID_TEXT = tuple(
    _canonical_decimal_text(
        Decimal("-0.40") + Decimal("0.02") * index
    )
    for index in range(41)
)
FULL_P_GRID_TEXT = tuple(
    _canonical_decimal_text(Decimal(value))
    for value in ("0.15", "0.175", "0.20", "0.25", "0.30")
)
FULL_NU_GRID_TEXT = tuple(
    _canonical_decimal_text(Decimal(value))
    for value in ("0.80", "0.90", "1.00", "1.10", "1.20")
)
MEDIUM_P_GRID_TEXT = tuple(
    _canonical_decimal_text(Decimal(value))
    for value in ("0.175", "0.20", "0.25")
)
NARROW_P_GRID_TEXT = tuple(
    _canonical_decimal_text(Decimal(value))
    for value in ("0.19", "0.20", "0.21")
)

# Backward-readable aliases for the inherited FULL carrier only. Operational
# B0.1 code reads the immutable grids from each PublicBank instance.
P_GRID_TEXT = FULL_P_GRID_TEXT
NU_GRID_TEXT = FULL_NU_GRID_TEXT
CARRIER_ROUNDING_TOLERANCE = 5.0e-14


def canonical_candidate_id(
    phi_index: int,
    p_index: int,
    nu_index: int,
    *,
    p_count: int = len(FULL_P_GRID_TEXT),
    nu_count: int = len(FULL_NU_GRID_TEXT),
) -> int:
    if not 0 <= int(phi_index) < len(PHI_GRID_TEXT):
        raise IndexError("phi_index outside the frozen bank")
    if not 0 <= int(p_index) < int(p_count):
        raise IndexError("p_index outside the frozen bank")
    if not 0 <= int(nu_index) < int(nu_count):
        raise IndexError("nu_index outside the frozen bank")
    return (
        (int(phi_index) * int(p_count)) + int(p_index)
    ) * int(nu_count) + int(nu_index)


@dataclass(frozen=True)
class BankCandidate:
    candidate_id: int
    phi_index: int
    p_index: int
    nu_index: int
    phi_text: str
    p_text: str
    nu_text: str

    @property
    def phi(self) -> float:
        return float(self.phi_text)

    @property
    def p(self) -> float:
        return float(self.p_text)

    @property
    def nu(self) -> float:
        return float(self.nu_text)

    @property
    def raw(self) -> tuple[float, float, float]:
        return (self.phi, self.p, self.nu)

    @property
    def x(self) -> tuple[float, float, float]:
        """Map to the unchanged global normalized shell."""
        p_left = 0.15
        p_right = 0.30
        nu_left = 0.80
        nu_right = 1.20
        logit_left = math.log(p_left / (1.0 - p_left))
        logit_right = math.log(p_right / (1.0 - p_right))
        logit_middle = 0.5 * (logit_left + logit_right)
        logit_half = 0.5 * (logit_right - logit_left)
        log_nu_middle = 0.5 * (math.log(nu_left) + math.log(nu_right))
        log_nu_half = 0.5 * (math.log(nu_right) - math.log(nu_left))
        values = (
            self.phi / 0.4,
            (math.log(self.p / (1.0 - self.p)) - logit_middle)
            / logit_half,
            (math.log(self.nu) - log_nu_middle) / log_nu_half,
        )
        return tuple(
            (
                -1.0
                if -1.0 - CARRIER_ROUNDING_TOLERANCE <= value < -1.0
                else (
                    1.0
                    if 1.0 < value <= 1.0 + CARRIER_ROUNDING_TOLERANCE
                    else float(value)
                )
            )
            for value in values
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "phi_index": self.phi_index,
            "p_index": self.p_index,
            "nu_index": self.nu_index,
            "phi": self.phi_text,
            "p": self.p_text,
            "nu": self.nu_text,
            "raw": list(self.raw),
            "x": list(self.x),
        }


@dataclass(frozen=True)
class PublicBank:
    """One complete immutable role-specific finite bank."""

    template: str
    p_grid_text: tuple[str, ...]
    nu_grid_text: tuple[str, ...]
    candidates: tuple[BankCandidate, ...]

    def __post_init__(self) -> None:
        expected = (
            len(PHI_GRID_TEXT)
            * len(self.p_grid_text)
            * len(self.nu_grid_text)
        )
        if len(self.candidates) != expected:
            raise ValueError("B0.1 bank candidate count is inconsistent")
        if expected not in (1025, 369):
            raise ValueError("B0.1 bank must contain 1025 or 369 candidates")
        for expected_id, candidate in enumerate(self.candidates):
            if candidate.candidate_id != expected_id:
                raise ValueError("B0.1 candidates are not in canonical order")
            if candidate.candidate_id != self.candidate_id(
                candidate.phi_index,
                candidate.p_index,
                candidate.nu_index,
            ):
                raise ValueError("candidate identifier/index mismatch")
            if candidate.phi_text != PHI_GRID_TEXT[candidate.phi_index]:
                raise ValueError("candidate phi coordinate mismatch")
            if candidate.p_text != self.p_grid_text[candidate.p_index]:
                raise ValueError("candidate p coordinate mismatch")
            if candidate.nu_text != self.nu_grid_text[candidate.nu_index]:
                raise ValueError("candidate nu coordinate mismatch")

    @property
    def phi_grid_text(self) -> tuple[str, ...]:
        return PHI_GRID_TEXT

    @property
    def nuisance_count(self) -> int:
        return len(self.p_grid_text) * len(self.nu_grid_text)

    def __len__(self) -> int:
        return len(self.candidates)

    def __iter__(self) -> Iterator[BankCandidate]:
        return iter(self.candidates)

    def candidate_id(
        self, phi_index: int, p_index: int, nu_index: int
    ) -> int:
        return canonical_candidate_id(
            phi_index,
            p_index,
            nu_index,
            p_count=len(self.p_grid_text),
            nu_count=len(self.nu_grid_text),
        )

    def candidate(self, candidate_id: int) -> BankCandidate:
        if isinstance(candidate_id, bool) or not isinstance(candidate_id, int):
            raise IndexError("candidate_id must be an exact integer")
        if not 0 <= candidate_id < len(self.candidates):
            raise IndexError("candidate_id outside the frozen bank")
        return self.candidates[candidate_id]

    def at(
        self, phi_index: int, p_index: int, nu_index: int
    ) -> BankCandidate:
        return self.candidate(
            self.candidate_id(phi_index, p_index, nu_index)
        )

    def nearest_orientation_index(self, phi: float) -> int:
        value = float(phi)
        return min(
            range(len(PHI_GRID_TEXT)),
            key=lambda index: (abs(float(PHI_GRID_TEXT[index]) - value), index),
        )

    def orientation_candidates(
        self, phi_index: int
    ) -> tuple[BankCandidate, ...]:
        if not 0 <= int(phi_index) < len(PHI_GRID_TEXT):
            raise IndexError("phi_index outside the frozen bank")
        start = self.candidate_id(int(phi_index), 0, 0)
        return self.candidates[start : start + self.nuisance_count]

    def contains_truth(self, nu_truth: float) -> bool:
        target = (0.0, 0.20, float(nu_truth))
        return any(candidate.raw == target for candidate in self.candidates)


def _decimal_grid(
    center: float, offsets: Sequence[str]
) -> tuple[str, ...]:
    base = Decimal(str(float(center)))
    return tuple(
        _canonical_decimal_text(base + Decimal(offset)) for offset in offsets
    )


@lru_cache(maxsize=None)
def role_bank(template: str, nu_truth: float) -> PublicBank:
    name = str(template).upper()
    if name == "FULL":
        p_grid = FULL_P_GRID_TEXT
        nu_grid = FULL_NU_GRID_TEXT
    elif name == "MEDIUM":
        p_grid = MEDIUM_P_GRID_TEXT
        nu_grid = _decimal_grid(nu_truth, ("-0.10", "0.0", "0.10"))
    elif name == "NARROW":
        p_grid = NARROW_P_GRID_TEXT
        nu_grid = _decimal_grid(nu_truth, ("-0.05", "0.0", "0.05"))
    else:
        raise ValueError(f"unknown B0.1 bank template {template!r}")
    if (
        float(nu_grid[0]) <= 0.0
        or "0.2" not in p_grid
        or _canonical_decimal_text(Decimal(str(float(nu_truth)))) not in nu_grid
    ):
        raise ValueError("role-specific grid violates the frozen template")
    rows: list[BankCandidate] = []
    for phi_index, phi_text in enumerate(PHI_GRID_TEXT):
        for p_index, p_text in enumerate(p_grid):
            for nu_index, nu_text in enumerate(nu_grid):
                rows.append(
                    BankCandidate(
                        candidate_id=canonical_candidate_id(
                            phi_index,
                            p_index,
                            nu_index,
                            p_count=len(p_grid),
                            nu_count=len(nu_grid),
                        ),
                        phi_index=phi_index,
                        p_index=p_index,
                        nu_index=nu_index,
                        phi_text=phi_text,
                        p_text=p_text,
                        nu_text=nu_text,
                    )
                )
    return PublicBank(
        template=name,
        p_grid_text=tuple(p_grid),
        nu_grid_text=tuple(nu_grid),
        candidates=tuple(rows),
    )


@lru_cache(maxsize=1)
def frozen_bank() -> PublicBank:
    """Return the inherited FULL bank for compatibility fixtures."""
    return role_bank("FULL", 1.0)
