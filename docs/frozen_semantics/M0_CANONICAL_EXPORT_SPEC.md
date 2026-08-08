# M0-A Canonical Paper Export Specification

Status: **APPROVED AND FROZEN**  
Execution phase: M0-B authorized

This specification defines a deterministic, read-only transformation from
immutable source/evidence bundles into paper-facing metrics, macros, tables,
figures, and provenance. It does not authorize manuscript prose edits or new
scientific choices.

## 1. Immutable inputs

| Input | SHA-256 |
|---|---|
| `Honest_Collision_Aware_Dictionary_Refinement_V2_SOURCE.zip` | `8ab580ae47fe83455814f840b6bf32133bf074c7f388eec7f170523b3f85f872` |
| `B11_GLOBAL_FINAL_EVIDENCE.zip` | `2095d8c17081cc9e574f5e052b2a1100864eff499610c45ef2c999905bf67c83` |
| `FORMAL_B2_FINAL_EVIDENCE.zip` | `89649c27c956a2ade19ea2fe16ef549b4a028d7d544fd5eeef47a1dd4bddc738` |
| `ORIGINAL_THREE_GATE_EXPERIMENT_EVIDENCE.zip` | `cb99fc8fda7efa3872185f0ca1460de262fdc201d2a1996182e74b47a00b8379` |

M0-B must verify these outer digests, extract into new read-only working
directories, and verify every inner checksum manifest before deriving output.

## 2. Evidence precedence rules

### 2.1 Formal B2

Use the B2-F0.3 safety closure for:

- terminal status;
- P05 native status;
- empty-profile semantics;
- zero possible-set violations;
- zero completed-prefix bound violations;
- unsafe-output and false-D-absence safety values.

Use the sealed predecessor metrics for:

- coverage;
- A/B/C/D utility;
- plug-in false precision;
- primary and secondary query metrics;
- case rows and frozen representatives.

The legacy `paper_export/formal_b2_summary_metrics.json` may supply only
non-safety values. Its safety `null` fields, 14-trace possible-set denominator,
timeout token, HOLD terminal status, and stale traceability rows must never be
copied into canonical output.

### 2.2 B1.1

Use the final B1.1 18-case/54-trace re-adjudication. Earlier B1 HOLD reports
may appear only in provenance and may not supply paper numbers.

### 2.3 Original numerical experiment

Use R0 `adjudication.json` for confirmatory status and primary values. Use
post-hoc artifacts only in fields whose names and manuscript labels explicitly
contain `posthoc` or `robustness`. The canonical status remains
`HOLD_NUMERICAL_EVIDENCE`.

### 2.4 Development experiments

D0--D2.3 may be listed in provenance but must not appear in confirmatory
numerators, denominators, rates, tables, or figures.

## 3. Required output tree

```text
canonical_paper_export/
  README.md
  provenance/
    immutable_inputs.json
    evidence_precedence.md
    source_artifact_manifest.csv
    checksums.sha256
  theory/
    canonical_theorem_claims.yaml
    theorem_numeric_macros.tex
  original_numerical/
    canonical_summary.json
    canonical_summary.csv
    figure_data/
  b11_global/
    canonical_summary.json
    budget_metrics.csv
    profile_condition_metrics.csv
    safety_metrics.json
    empirical_risk_metrics.csv
    figure_data/
  formal_b2/
    canonical_merged_summary.json
    canonical_case_rows.csv
    primary_budget_metrics.json
    secondary_prefix_metrics.json
    plugin_false_precision_metrics.json
    safety_closure_metrics.json
    empty_profile_disclosure.json
    representative_examples.json
    figure_data/
  paper/
    numeric_macros.tex
    tables/
    figure_manifest.csv
    claim_evidence_matrix.csv
  validation/
    invariant_checks.json
    denominator_checks.json
    stale_field_rejection.json
    representative_rule_check.json
    final_validation_report.md
```

The exact filenames may change only before M0-B begins; after implementation
they become part of the deterministic export contract.

## 4. Canonical merge for Formal B2

Create `canonical_merged_summary.json` from named source fields, not by
blindly patching the legacy summary.

### Required top-level fields

- `terminal_status = PASS_ARA_B2_FORMAL_FRESH_APPLICATION_VALIDATED`;
- `formal_case_count = 15`;
- `completed_exact_oracle_count = 14`;
- `administrative_empty_profile_count = 1`;
- `native_status_counts = {COMPLETE: 14,
  ORACLE_EMPTY_PROFILE_INCOMPLETE: 1}`;
- `development_case_count = 0`.

### Required safety fields

- `unsafe_outputs = 0/56`;
- `possible_set_violations = 0/15`;
- `bound_violations = 0/2088`, scope `completed_validations_only`;
- `control_false_D_absence = 0/3`;
- `p05_possible_set_prefix_count = 162`;
- `p05_bound_imputed = false`.

### Required P05 fields

- `case_id = FORMAL_WEAK_C_PRESENT_P05`;
- `native_status = ORACLE_EMPTY_PROFILE_INCOMPLETE`;
- `exact_profile_candidate_ids = []`;
- `oracle_map = null`;
- `physical_map_imputed = false`;
- `scientific_quantity_imputed = false`;
- `truth_relative_utility_eligible = false`;
- `bound_validation_included = false`;
- `stage_a_query_count = 162`.

### Required invariance check

Every non-safety metric copied from the predecessor must match its sealed
source byte-for-byte or value-for-value. The B2-F0.3 overlay must not overwrite
or recompute non-safety science.

## 5. Canonical B1.1 extraction

Extract paper-facing rows by exact keys:

- terminal status from `terminal_status.json`;
- 18 cases/54 traces and safety values from final audit/safety artifacts;
- pooled budgets 0.50 and 0.75 from
  `operational_controller_metrics.csv` where
  `scope=POOLED`, `profile=ALL`, and `condition=ALL`;
- exact labels/diameters from `exact_validation_metrics.csv`;
- profile/condition tables from the corresponding scoped rows;
- empirical risk from `empirical_risk_metrics.csv`;
- cost decomposition from the frozen runtime artifact.

Validate:

- three conditions × six datasets × three profiles = 54 traces;
- 18 completed exact finite-bank cases;
- full-budget label mismatch count = 0;
- structural unsafe count = 0;
- bound violation count = 0;
- no row from development comparison files enters a canonical rate.

## 6. Canonical original-experiment extraction

Required fields from frozen R0:

- status;
- Jeffreys and affinity-deficit slopes and intervals;
- \(R^2\);
- maximum and median collapse spreads;
- failed criterion name/value/threshold;
- task-control residuals;
- Gauss--Hermite check.

Required fields from post-hoc:

- `posthoc_h_slope`;
- `posthoc_h_r_squared`;
- `posthoc_stress_slope_min/max`;
- `posthoc_quadrature_slope`;
- interpretation `R0_HOLD_BUT_GEOMETRY_ROBUST`.

Validation must fail if any generated caption, macro, or summary assigns PASS
to the original numerical experiment.

## 7. Paper-facing number rules

1. Store exact integers and full-precision source values in JSON/CSV.
2. Generate LaTeX macros from those canonical files only.
3. Use count/denominator in paper tables and captions.
4. Rate macros must carry a documented rounding format; do not round before
   validation.
5. Keep different conditional denominators separate.
6. Missing values remain null and may not be converted to zero.
7. Offline audit and orchestration cost fields must have names containing
   `offline` or `audit` and may not feed deployment-latency claims.

## 8. Figure generation contract

Every figure row in `paper/figure_manifest.csv` must record:

- figure ID and panel ID;
- generator script;
- canonical data inputs;
- source artifact hashes;
- frozen representative case if applicable;
- whether the panel is theorem, confirmatory, descriptive, or post-hoc;
- required caption qualifier;
- output PDF and PNG hashes.

Formal B2 representatives are fixed:

- persistent-only `FORMAL_PERSISTENT_ONLY_P02`;
- weak-C `FORMAL_WEAK_C_PRESENT_P01`;
- D-control `FORMAL_DETECTABLE_D_PRESENT_CONTROL_P01`.

No alternative representative may be substituted. P05 may appear only in an
empty-profile disclosure, not in a physical map panel.

## 9. Claim-evidence integration

Copy the approved `M0_CLAIM_EVIDENCE_MATRIX.csv` into the export and add only
machine fields:

- canonical artifact path;
- canonical field/key;
- rendered macro/table/figure location;
- validation status.

M0-B may not change exact claim wording, claim type, scope qualifier, or
prohibited stronger wording.

## 10. Mandatory invariant checks

The export fails closed unless all checks pass:

1. outer and inner checksums verify;
2. B1.1 terminal status is the final PASS;
3. B1.1 cases/traces equal 18/54;
4. Formal B2 terminal status is the B2-F0.3 PASS;
5. Formal B2 safety equals 0/56, 0/15, 0/2088, and 0/3;
6. Formal B2 completed/empty counts equal 14/1;
7. P05 map is null and native status is not timeout;
8. P05 is absent from truth-relative utility and completed bound denominators;
9. P05 Stage-A query count remains in cost reporting;
10. Formal B2 non-safety metrics match predecessor artifacts;
11. no D0--D2.3 row enters confirmatory output;
12. original numerical status remains HOLD;
13. post-hoc values are labeled post-hoc;
14. representative case IDs match the frozen rule;
15. every paper number resolves to one canonical source field;
16. every generated file is covered by the final checksum manifest.

## 11. Prohibited M0-B actions

- no experiment, scoring, replay, proposal, controller, or oracle execution;
- no denominator change or missing-oracle imputation;
- no favorable case selection;
- no alteration of evidence or predecessor paper exports;
- no inference that the finite bank covers continuous space;
- no new scientific claim or venue-driven strengthening;
- no manuscript prose or proof editing;
- no conversion of P05 into an absence label;
- no suppression of the theorem-native HOLD disclosure.

## 12. M0-B terminal outcomes

### Pass

`PASS_M0B_CANONICAL_PAPER_EXPORT_VERIFIED`

### Hold

`HOLD_M0B_CANONICAL_SOURCE_CONFLICT`

Use when an approved claim cannot be mapped uniquely to existing immutable
evidence without scientific reinterpretation.

### Fail

`FAIL_M0B_EVIDENCE_INTEGRITY_OR_INVARIANT_VIOLATION`

Use for checksum failure, stale-field leakage, denominator drift, forbidden
imputation, representative substitution, or any other contract violation.
