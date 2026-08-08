# Physical-Support Confidence Sets for Highly Coherent Dictionaries

This repository is the publication-code release for the paper **Physical-Support Confidence Sets for Highly Coherent Dictionaries**. It exposes the recovered scientific implementation, frozen configurations, compact canonical outputs, deterministic paper-artifact regeneration, and bounded executable checks.

> **SCIENCE CLOSED — MANUSCRIPT MODE.** The repository preserves an already completed study. It is not a venue for retuning, new gates, AEB redesign, continuous-bank claims, off-grid or real-data studies, or manuscript expansion.

No license is granted by this repository at present. Licensing remains an owner decision.

## What is included

- B1.1 global finite-bank implementation: proposal construction, e-process scorer, 1,025/369 candidate banks, projective geometry, proposal-anchor-augmented AEB controller, safe bounds, and 90-decimal replay.
- Formal B2 D2.3 scientific core, byte-identical to its 15-file freeze: four-region D25 application, 72 dictionary states, 216 explanations, split scorer, dual-proposal controller, projections, precision audit, and adjudication helpers.
- The theorem-native numerical illustration implementation. Its frozen status remains `HOLD_NUMERICAL_EVIDENCE`; it is a mechanism illustration, not an implementation of the full continuous confidence correspondence.
- Frozen B1.1 and Formal B2 configurations, case order, gates, seeds, and freeze records.
- The complete compact canonical paper export, including figure data, tables, receipts, validation records, and semantic anchors.
- Two deterministic representative smoke examples, unit/invariant tests, artifact-regeneration scripts, and one release validator.

Historical monitors, recovery wrappers, lifecycle dashboards, infrastructure repair scripts, caches, and raw evidence ZIPs are intentionally excluded.

## Install

Python 3.10 or newer is required. In PowerShell from the repository root:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

On macOS/Linux, replace `.venv\Scripts\python.exe` with `.venv/bin/python`.

## Reproducibility levels

### A. Artifact reproduction

These commands regenerate paper artifacts from immutable canonical exports. They do **not** rerun an experiment.

```powershell
.venv\Scripts\python.exe scripts\regenerate_paper_figures.py
.venv\Scripts\python.exe scripts\regenerate_paper_tables.py
```

Five PNG/PDF figure pairs are written below `build/figure_reproduction/`. Six table files are written below `build/table_reproduction/`. The figure wrapper resolves DejaVu Sans portably through Matplotlib (or `PSC_FONT_REGULAR` / `PSC_FONT_BOLD`) without changing displayed scientific values.

### B. Representative executable verification

The B1.1 example exercises the frozen controller and proposal-anchor geometry on a declared synthetic status vault. It does not run the scorer. The Formal B2 example exercises the actual D25 geometry, 216-candidate bank, split scorer, score-blind controller, lower/possible/exact finite sets, typed outputs, and termination semantics on tiny samples.

```powershell
.venv\Scripts\python.exe scripts\run_representative_example.py --study b11 --output build\representative\b11.json
.venv\Scripts\python.exe scripts\run_representative_example.py --study formal-b2 --output build\representative\formal_b2.json
```

Both are deterministic smoke checks and carry `"scientific_claim": false`. Formal thresholds, reported rates, or frozen case outcomes must not be inferred from them. Its explicit double-precision smoke rule retains `|margin| <= 1e-10` as `INDETERMINATE`; the formal 90-decimal replay semantics remain in the released source.

### C. Full frozen study

The complete 33-case campaign was **not rerun** for this release. Frozen configs, seeds, expected resource scale, historical entrypoints, and expected terminal outputs are documented in [REPRODUCIBILITY_SCOPE.md](docs/REPRODUCIBILITY_SCOPE.md). The historical orchestration entrypoints are provenance-only and are not shipped as public quick commands because lifecycle/recovery infrastructure is deliberately outside this repository.

## Test and validate

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts\validate_release.py
```

The validator checks source freezes and canonical checksums, exact case IDs/counts/denominators/states/nulls, deterministic examples and artifacts, portable regeneration, source-manifest closure, and prohibited paths/caches. It exits nonzero on any mismatch.

## Frozen result summary

### B1.1 global finite-bank study

- terminal status: `PASS_ARA_B11_ORACLE_AUDIT_COMPLETED_AND_B1_VALIDATED`;
- 18 completed finite-bank cases and 54 sealed global controller traces;
- three information conditions × three operating profiles × six seeds;
- all 54 traces sealed before any primary oracle work;
- at budget 0.75: 34 `AMBIGUOUS`, 5 `FINE`, 15 `SECTOR_SAFE`, 0 abstentions;
- 0 structural unsafe decisions, 0 bound violations in the declared audited-prefix scope, and 0 exact-label mismatches.

B1.1 is global finite-bank empirical validation. It is not local-map validation, continuous-space completeness, or an exact selective-risk theorem.

### Formal B2 application

- terminal status: `PASS_ARA_B2_FORMAL_FRESH_APPLICATION_VALIDATED`;
- 15 formal cases, 14 completed exact oracles, one administrative empty profile;
- main exact-profile completion 11/12 and control completion 3/3;
- possible-set violations 0/15;
- completed-prefix bound violations 0/2088 across 14 completed validations;
- unsafe reportable regional outputs 0/56;
- false D-absence controls 0/3.

`FORMAL_WEAK_C_PRESENT_P05` remains `ORACLE_EMPTY_PROFILE_INCOMPLETE`, with exact profile `[]` and physical map `null`. It is not a timeout and not an all-regions-absent result. It is excluded from truth-relative utility and completed-bound denominators, while its 162 Stage-A queries remain in operational cost.

`FINE`, `SECTOR_SAFE`, and `ABSENT_ABOVE_BETA_MIN` are universal assertions over the frozen possible set under the declared retention assumptions. `SUPPORT_AMBIGUOUS` is an epistemic/profile-level conclusion. `ABSTAIN` and `EMPTY_PROFILE` are administrative states.

## Repository map

- `src/physical_support_confidence_sets/b11/`: curated B1.1 scientific core.
- `src/physical_support_confidence_sets/formal_b2/`: exact 15-file Formal B2 D2.3 core.
- `src/physical_support_confidence_sets/original_numerical/`: theorem-native illustration code.
- `configs/`: frozen configurations, seeds, case orders, gates, and freeze records.
- `artifacts/canonical_paper_export/`: immutable compact canonical export.
- `scripts/`: representative examples, artifact reproduction, and validation.
- `docs/`: method map, evidence provenance, scope, semantic anchors, and source manifest.

See [METHOD_TO_CODE_MAP.md](docs/METHOD_TO_CODE_MAP.md), [RESULT_PROVENANCE.md](docs/RESULT_PROVENANCE.md), and [SOURCE_MANIFEST.csv](docs/SOURCE_MANIFEST.csv) for exact mappings.

## Citation and release metadata

The paper title above is the only publication metadata asserted here. This repository does not claim that an arXiv preprint, DOI, version tag, or GitHub Release already exists. A license and a later manuscript-version tag remain owner decisions.

