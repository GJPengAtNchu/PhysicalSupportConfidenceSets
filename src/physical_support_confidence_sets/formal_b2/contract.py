"""Render the post-selection formal B2 execution contract for B2-D2.

The renderer is deliberately declarative.  It materializes the supplied D2
template after a development row has passed, but it neither creates formal B2
seeds nor authorizes formal execution.  In particular, the D2 handoff names
two sensitivity profiles without assigning alpha values to them; this module
must not manufacture those missing scientific choices.
"""

from __future__ import annotations

import re
from typing import Mapping


# Kept under the historical public name because the finalization lifecycle
# records this mapping in the design freeze.  These are the complete formal
# B2 gates supplied by FORMAL_B2_EXECUTION_TEMPLATE.md, not empirical D2
# development results.
FRESH_B2_UTILITY_GATES = {
    "maximum_unsafe_region_outputs": 0,
    "maximum_possible_set_or_bound_violations": 0,
    "exact_oracle_coverage_min_of_12_main_cases": 11,
    "A_oracle_FINE_min_of_12_main_cases": 10,
    "weak_C_B_oracle_SECTOR_SAFE_min_of_6": 4,
    "weak_C_C_oracle_SUPPORT_AMBIGUOUS_min_of_6": 5,
    "D_oracle_ABSENT_ABOVE_BETA_MIN_min_of_12_main_cases": 10,
    "controller_recall_min_for_each_intended_certificate": 0.70,
    "plugin_B_false_FINE_rate_min_among_oracle_sector_weak_cases": 0.80,
    "plugin_C_false_certainty_rate_min_among_oracle_ambiguous_weak_cases": 0.80,
    "median_logical_query_fraction_max": 0.75,
    "D_present_control_false_absence_outputs_max": 0,
    "D_present_control_nonabstaining_D_outputs_min_of_3": 2,
}


_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_REQUIRED_ROW_FIELDS = (
    "row_id",
    "h",
    "calibration_size",
    "deployment_size",
    "tau_b",
    "tau_c",
    "tau_d_beta",
)


def _sha256(value: object, name: str) -> str:
    """Return a canonical digest or reject an unbound contract input."""

    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase 64-character SHA-256")
    return value


def _selected_row(selected_design: Mapping[str, object]) -> Mapping[str, object]:
    row = selected_design.get("row")
    if not isinstance(row, Mapping):
        raise TypeError("selected design row is missing")
    missing = [field for field in _REQUIRED_ROW_FIELDS if field not in row]
    if missing:
        raise ValueError(f"selected design row is missing fields: {missing}")
    declared_digest = selected_design.get("selected_design_sha256")
    if declared_digest is not None:
        _sha256(declared_digest, "selected_design['selected_design_sha256']")
    return row


def render_b2_execution_contract(
    selected_design: Mapping[str, object],
    *,
    pre_pilot_source_freeze_sha256: str,
    selected_design_sha256: str,
    b1_freeze_sha256: str,
    b11_freeze_sha256: str,
) -> str:
    """Materialize the frozen D2 formal-B2 template.

    ``selected_design`` is the already-adjudicated D2 design record.  Digest
    arguments bind the contract to that record, the D2 pre-pilot source, and
    the locked B1/B1.1 predecessors.  The eventual D2 design-freeze digest is
    intentionally not an input: that freeze contains the hash of this very
    contract, so accepting it here would introduce a digest cycle.
    """

    if not isinstance(selected_design, Mapping):
        raise TypeError("selected_design must be a mapping")
    row = _selected_row(selected_design)
    source_digest = _sha256(
        pre_pilot_source_freeze_sha256, "pre_pilot_source_freeze_sha256"
    )
    design_digest = _sha256(selected_design_sha256, "selected_design_sha256")
    b1_digest = _sha256(b1_freeze_sha256, "b1_freeze_sha256")
    b11_digest = _sha256(b11_freeze_sha256, "b11_freeze_sha256")
    declared_digest = selected_design.get("selected_design_sha256")
    if declared_digest is not None and declared_digest != design_digest:
        raise ValueError("selected-design digest does not match the selected record")

    gates = "\n".join(
        f"- `{name}`: `{value}`" for name, value in FRESH_B2_UTILITY_GATES.items()
    )

    return f"""# LA1.3-ARA-B2 Formal Execution Contract

## Authority and immutable predecessor

This document freezes a design for a later, separately authorized formal B2
handoff. It does not authorize formal B2 execution and it contains no formal
B2 primary seed. The later run must bind byte-for-byte to D2 pre-pilot source
freeze `{source_digest}`, selected-design digest `{design_digest}`, B1
scientific freeze `{b1_digest}`, and B1.1 freeze `{b11_digest}`. B1, B1.1,
and the D2 development cases are immutable predecessors and may not be rerun,
rewritten, or re-adjudicated.

## Selected application design

- selected D2 row: `{row['row_id']}`;
- response width: `{row['h']}`;
- calibration snapshots: `{row['calibration_size']}` with the frozen 45/55
  split;
- deployment snapshots: `{row['deployment_size']}` with the frozen 40/60
  split;
- persistent-source power tau_B: `{row['tau_b']}`;
- weak optional-source power tau_C: `{row['tau_c']}`;
- D beta-min power tau_D_beta: `{row['tau_d_beta']}`;
- geometry: q=16, four regions, twelve target atoms, one fixed anchor, and 72
  dictionary states;
- support family, in canonical order: `AB`, `ABC`, `ABD`;
- finite candidate bank: 72 dictionary states x 3 support patterns = 216
  explanations;
- controller: `PERSISTENT_OPTIONAL_AEB_MAP`;
- exact selective replay: 90 decimal digits under the frozen checkpoint and
  threshold conventions.

Every candidate contains persistent A and B. The controller therefore reports
physical resolution, not empirical support, for A and B. C and D are optional;
`ABSENT_ABOVE_BETA_MIN` excludes only the corresponding optional explanations
at the declared finite-model power and does not claim absence of arbitrarily
weak or unrestricted-support sources. No geometry, bank, score kernel,
proposal, replay, controller, threshold, operating point, ordering rule, or
gate may be retuned after formal data are generated.

## Main fresh datasets and positive controls

Generate exactly 12 fresh main datasets:

- 6 `PERSISTENT_ONLY`;
- 6 `WEAK_C_PRESENT`.

Generate exactly 3 separate `DETECTABLE_D_PRESENT_CONTROL` datasets. The
positive controls audit false D absence and are not substituted into the 12
main-case denominators. Formal B2 primary seeds must be created, committed,
and supplied only in a separate later handoff; none is selected or created by
this contract.

## Profiles and budgets

- `BALANCED` is the primary profile and retains frozen alpha=0.077;
- `RISK_CONSERVATIVE` is a named sensitivity profile;
- `STRICT_RESOLUTION` is a named sensitivity profile;
- primary query budget: 0.75 of the 216-candidate bank;
- secondary query budget: 0.50 of the 216-candidate bank.

The supplied D2 template defines no alpha value for either sensitivity
profile. This contract does not infer or invent either value. Any later
authorization must bind those two numerical profile definitions before formal
seed access and without changing the selected D2 design.

## Trace, oracle, and plug-in lifecycle

For every fresh case and every frozen profile, generate the maximal 0.75
controller trace and deterministically derive the 0.50 prefix output. Every
controller trace and prefix record across all 15 fresh cases must seal before
any exact oracle artifact, oracle score, or oracle survivor set is opened.
Only after that global all-traces-before-any-oracle barrier may the complete
exact 216-candidate finite-bank oracle be computed for a case/profile. No
candidate may be omitted, and no oracle information may feed back into a
controller trace.

The plug-in singleton is computed only after all main-case traces seal. It is
independent of controller decisions and reports no uncertainty. A failed or
indeterminate numerical query remains possible; unqueried candidates remain
possible; no partial elimination certifies A FINE or optional-source absence;
and no trace, seed, case, or output may be selected, replaced, or rerun.

## Frozen formal gates

Zero-unsafe and zero-possible-set/bound gates apply across every generated
profile/budget output. The remaining utility and coverage gates are
adjudicated on the `BALANCED` primary 0.75 outputs; sensitivity-profile and
0.50-prefix results are reported in full and are not silently given additional
utility thresholds. Adjudicate the following exact gates:

{gates}

In prose, the same frozen gates are: zero unsafe region outputs; zero
possible-set or bound violations; exact-oracle coverage of at least 11/12
main cases; A oracle FINE in at least 10/12; weak-C B oracle SECTOR_SAFE in at
least 4/6; weak-C C oracle SUPPORT_AMBIGUOUS in at least 5/6; D oracle
ABSENT_ABOVE_BETA_MIN in at least 10/12 main cases; controller recall of at
least 0.70 for each intended certificate; plug-in B false-FINE rate at least
0.80 among oracle-sector weak cases; plug-in C false-certainty rate at least
0.80 among oracle-ambiguous weak cases; median logical query fraction at most
0.75; zero false-absence output in D-present controls; and non-abstaining D
outputs in at least 2/3 controls.

Missing or incomplete oracle quantities remain missing and are never imputed.
Safety and bound failures are terminal and cannot be averaged away. Query
fraction means distinct logical candidate queries divided by 216.

## Execution and claim boundaries

Formal B2 is synthetic, finite-bank, and global-only. It may claim only a
resolution-aware four-region map conditional on persistent A/B presence and
the declared finite optional-source powers. It may not claim unrestricted-
support recovery, arbitrary-weak-source absence, or equivalence to the earlier
nine-pattern 648-explanation problem.

No B1/B1.1 or D2 development rerun, predecessor re-adjudication, continuous or
local oracle, real-data access, manuscript edit, B2 extension, seed
replacement, outcome selection, automatic recovery, or unlisted scientific
work is authorized. Finalization must report all profiles, budgets, missing
oracles, query counts, abstentions, controls, safety outcomes, checksum trees,
and an externally hashed evidence bundle.
"""
