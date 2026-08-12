# Reproducibility scope

## Supported public workflows

1. **Artifact reproduction:** regenerate the three conceptual Figure 1 panels,
   eight empirical main-paper panels, one supplementary diagnostic, and six
   table files from `artifacts/canonical_paper_export/`.
2. **Representative verification:** run one bounded B1.1 controller example and one bounded Formal B2 scientific-core example.
3. **Invariant validation:** verify source freezes, canonical hashes, exact counts/states/nulls, deterministic outputs, and repository hygiene.

These are the commands in the README and are the workflows tested in a fresh checkout.

## Full frozen study provenance

The complete study was not rerun while preparing this release.

### B1.1

Historical scientific entrypoint: `python run_b1.py` followed by the B1.1 replay-completion/readjudication entrypoint `python run_b11.py`. Frozen inputs are released under `configs/b11_global/`. Expected scale:

- LOW: 6 cases at N=4,096 with a 1,025-candidate bank;
- INTERMEDIATE: 6 cases at N=65,536 with a 1,025-candidate bank;
- HIGH: 6 cases at N=131,072 with a 369-candidate bank;
- three controller profiles and six budget fractions, yielding 54 traces and 324 budget rows;
- 90-decimal mandatory replays near numerical thresholds.

Expected terminal output is `PASS_ARA_B11_ORACLE_AUDIT_COMPLETED_AND_B1_VALIDATED`, with all 54 traces sealed before primary oracle work. The historical lifecycle and completion wrappers are intentionally not copied because they are infrastructure, not the reader-facing scientific implementation. Consequently the historical commands above are provenance, not supported quick-run commands in this repository.

### Formal B2

Historical formal entrypoint: `python run_formal_b2f01.py --project-root <workspace> --execute-once`. Frozen inputs are under `configs/formal_b2/`. Expected design is D25: h=0.085, calibration N=4,096, deployment T=192, tau_B=0.8, tau_C=0.1, tau_D-beta=1.0, alpha=0.077, 216 explanations, and query cap 162. It seals all 15 Stage-A traces before Stage B and all Stage-B terminals before plug-in/final adjudication.

Expected terminal output is `PASS_ARA_B2_FORMAL_FRESH_APPLICATION_VALIDATED`: 14 completed exact oracles plus P05 as `ORACLE_EMPTY_PROFILE_INCOMPLETE`. Formal orchestration and recovery adapters are intentionally excluded. The command is archival provenance and is not claimed as a public one-click rerun.

## Historical environments

B1/B1.1 was frozen on CPython 3.9.13, NumPy 1.21.5, SciPy 1.9.1, mpmath 1.2.1, and Matplotlib 3.5.2, with numerical library thread counts fixed to one. The publication package supports Python 3.10+ and verifies semantics on the dependency ranges in `pyproject.toml`; this does not claim bitwise equality across BLAS/font/platform implementations.

Exact comparisons are used for case IDs, integer counts, denominators, status strings, nulls, frozen hashes, bank order, and generated JSON. Floating-point scientific constants are read from frozen configs. The representative double-precision smoke example uses an explicit `1e-10` indeterminate margin only to avoid presenting a near-threshold double result as final; formal 90-decimal behavior is preserved in source and is not replaced by this tolerance.

## Explicit nonclaims

The repository does not implement the full continuous confidence correspondence, prove off-bank completeness, validate real data, establish arbitrary-source absence, or claim universal superiority over plug-in methods. Formal B2 is one frozen synthetic four-region finite-bank application. B1.1 is global-only finite-bank empirical validation.
