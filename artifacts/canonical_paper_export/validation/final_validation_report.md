# M0-B Final Validation Report

## Executive conclusion

- Terminal status: `PASS_M0B_CANONICAL_PAPER_EXPORT_VERIFIED`
- Approved title: **Physical-Support Confidence Sets for Highly Coherent Dictionaries**
- New scientific executions: 0
- Manuscript LaTeX/proof edits: 0

## Integrity

All four outer SHA-256 values and ZIP CRCs match. Active B1.1, Formal B2-F0.3, embedded B2-F0.2, and original-experiment checksum manifests verify. The manuscript source ZIP contains no inner manifest; this is disclosed rather than misreported, and its outer hash, CRC, and computed per-member hash closure verify.

## Canonical evidence

- Original numerical layer remains `HOLD_NUMERICAL_EVIDENCE` and discloses the sole frozen failure, median product-affinity spread `0.016697583490912993 > 0.015`.
- B1.1 is `PASS_ARA_B11_ORACLE_AUDIT_COMPLETED_AND_B1_VALIDATED` with 18 complete cases, 54 global traces, zero structural unsafe decisions, and zero audited-prefix bound violations (no invented denominator).
- Formal B2 is `PASS_ARA_B2_FORMAL_FRESH_APPLICATION_VALIDATED` with 14 completed exact oracles and one administrative empty profile. Safety is 0/56, 0/15, 0/2088, and 0/3 under their distinct scopes.
- P05 is `ORACLE_EMPTY_PROFILE_INCOMPLETE`, has an empty exact finite profile and null map, is excluded from utility/completed-bound denominators, and retains 162 Stage-A queries in cost reporting.

## Scope

The export supports M1 manuscript rewriting only. It does not establish real-data validation, continuous candidate-space coverage or completeness, arbitrary-support recovery, high-dimensional/polynomial-time computation, or exact selective-risk control for the empirical controller.
