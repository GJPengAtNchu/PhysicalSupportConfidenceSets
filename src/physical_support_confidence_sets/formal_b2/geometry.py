"""Deterministic four-region sensor-response geometry."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from .constants import ANCHOR_ID, Q, REGION_ATOMS, TARGET_ATOM_COUNT
from .util import hash_array, readonly_float_array


@dataclass(frozen=True)
class ResponseAtom:
    region: str
    atom_id: str
    location: float | None
    vector: np.ndarray


@dataclass(frozen=True)
class ApplicationGeometry:
    response_width: float
    sensor_locations: np.ndarray
    target_atoms: tuple[ResponseAtom, ...]
    anchor: ResponseAtom

    @property
    def all_atoms(self) -> tuple[ResponseAtom, ...]:
        return self.target_atoms + (self.anchor,)

    @property
    def atom_ids(self) -> tuple[str, ...]:
        return tuple(atom.atom_id for atom in self.all_atoms)

    @property
    def atom_matrix(self) -> np.ndarray:
        matrix = np.column_stack([atom.vector for atom in self.all_atoms])
        matrix.setflags(write=False)
        return matrix

    def atom(self, atom_id: str) -> ResponseAtom:
        matches = [atom for atom in self.all_atoms if atom.atom_id == atom_id]
        if len(matches) != 1:
            raise KeyError(f"unknown or duplicate atom ID: {atom_id}")
        return matches[0]

    def atoms_for_region(self, region: str) -> tuple[ResponseAtom, ...]:
        return tuple(atom for atom in self.target_atoms if atom.region == region)

    def coherence_matrix(self) -> np.ndarray:
        matrix = np.abs(self.atom_matrix.T @ self.atom_matrix)
        matrix.setflags(write=False)
        return matrix

    def manifest(self) -> dict[str, object]:
        matrix = self.atom_matrix
        return {
            "response_width": self.response_width,
            "sensor_locations": self.sensor_locations.tolist(),
            "atom_ids": list(self.atom_ids),
            "atom_locations": {
                atom.atom_id: atom.location for atom in self.all_atoms
            },
            "atom_matrix_sha256": hash_array(matrix),
            "coherence_matrix_sha256": hash_array(self.coherence_matrix()),
            "maximum_anchor_inner_product": max(
                abs(float(atom.vector @ self.anchor.vector))
                for atom in self.target_atoms
            ),
        }


def sensor_locations() -> np.ndarray:
    values = (np.arange(Q, dtype=float) + 0.5) / float(Q)
    values.setflags(write=False)
    return values


def response_atom(location: float, response_width: float) -> np.ndarray:
    x = float(location)
    h = float(response_width)
    if not math.isfinite(x) or not 0.0 <= x <= 1.0:
        raise ValueError("location must belong to [0,1]")
    if not math.isfinite(h) or h <= 0.0:
        raise ValueError("response width must be positive")
    sensors = sensor_locations()
    displacement = sensors - x
    raw = np.exp(-(displacement**2) / (2.0 * h**2)) + 0.12 * np.cos(
        2.0 * math.pi * displacement
    )
    norm = float(np.linalg.norm(raw))
    if not math.isfinite(norm) or norm <= 0.0:
        raise ArithmeticError("response atom has invalid norm")
    return readonly_float_array(raw / norm, ndim=1)


def _orthogonal_anchor(target_matrix: np.ndarray) -> np.ndarray:
    matrix = np.asarray(target_matrix, dtype=float)
    if matrix.shape != (Q, TARGET_ATOM_COUNT):
        raise ValueError("target matrix must have shape (16,12)")
    if int(np.linalg.matrix_rank(matrix)) != TARGET_ATOM_COUNT:
        raise ArithmeticError("target atoms are not full column rank")
    alternating = np.where(np.arange(Q) % 2 == 0, 1.0, -1.0)
    # A reduced QR gives the projector onto the complete target-atom span.
    basis, _ = np.linalg.qr(matrix, mode="reduced")
    residual = alternating - basis @ (basis.T @ alternating)
    # One deterministic re-projection suppresses accumulated roundoff.
    residual = residual - basis @ (basis.T @ residual)
    norm = float(np.linalg.norm(residual))
    if not math.isfinite(norm) or norm <= 1.0e-12:
        raise ArithmeticError("fixed anchor is degenerate after projection")
    anchor = residual / norm
    maximum_inner = float(np.max(np.abs(matrix.T @ anchor)))
    if maximum_inner > 5.0e-13:
        raise ArithmeticError("fixed anchor is not orthogonal to target span")
    return readonly_float_array(anchor, ndim=1)


def build_geometry(response_width: float) -> ApplicationGeometry:
    h = float(response_width)
    atoms = tuple(
        ResponseAtom(
            region=region,
            atom_id=atom_id,
            location=float(location),
            vector=response_atom(float(location), h),
        )
        for region, atom_id, location in REGION_ATOMS
    )
    if len(atoms) != TARGET_ATOM_COUNT:
        raise AssertionError("frozen target atom count changed")
    target_matrix = np.column_stack([atom.vector for atom in atoms])
    anchor = ResponseAtom(
        region="ANCHOR",
        atom_id=ANCHOR_ID,
        location=None,
        vector=_orthogonal_anchor(target_matrix),
    )
    return ApplicationGeometry(
        response_width=h,
        sensor_locations=sensor_locations(),
        target_atoms=atoms,
        anchor=anchor,
    )
