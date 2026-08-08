# Method-to-code map

| Scientific component | Public implementation | Frozen role |
|---|---|---|
| B1.1 candidate representation and finite banks | `src/physical_support_confidence_sets/b11/public_bank/bank.py` | Canonical FULL=1,025 and NARROW=369 candidate banks |
| B1.1 projective geometry | `b11/public_bank/geometry.py`; `b11/frozen_policy/geometry.py` | Sign/relabel-invariant orientation distance and shell diameter |
| B1.1 data and split likelihoods | `b11/scientific_core/generator.py`; `mixture.py`; `runtime/science.py` | Frozen finite-dimensional synthetic model and split construction |
| B1.1 proposal | `b11/scientific_core/proposal.py`; `proposal_3d.py`; `safe_bounds.py` | Deterministic Sobol/start ordering with safe optimization fallbacks |
| B1.1 scorer | `b11/scientific_core/eprocess_3d.py`; `b11/raw_bank_adapter.py` | Candidate checkpoint e-process and raw finite-bank adapter |
| B1.1 high-precision replay | `b11/query_replay/scenario_replay.py` | Mandatory 90-decimal near-threshold replay semantics |
| B1.1 controller | `b11/frozen_policy/ara_controller.py`; `sealed_query.py` | Proposal-anchor-augmented lower/possible geometry; `AEB_FINE_SEEKING`; one-way queried-status capability |
| B1.1 exhaustive finite oracle | `b11/study/oracle_stage.py` | Exhaustive use of the same scorer/replay semantics after the trace barrier |
| Formal B2 geometry and application | `formal_b2/constants.py`; `geometry.py`; `data.py` | D25 four-region synthetic application and frozen source scales |
| Formal B2 candidate bank | `formal_b2/bank.py` | 72 dictionary states × AB/ABC/ABD = 216 explanations |
| Formal B2 scorer/proposals | `formal_b2/scoring.py`; `precision.py` | Calibration/deployment split proposals, joint checkpoints, e-values, high-precision audit |
| Formal B2 lower/possible/exact sets | `formal_b2/projection.py` | Safe partial projections and completed finite-oracle projection |
| Formal B2 query ordering/controller | `formal_b2/controller.py` | Dual-proposal C-witness seeding followed by frozen shared priority; cap 162 |
| Formal B2 predicates and adjudication helpers | `formal_b2/contract.py`; `pilot.py`; `finalize.py` | Typed regional assertions, gates, metrics, and fixed application reporting |
| Theorem-native numerical illustration | `original_numerical/exact_mixture.py`; `geometry.py`; `run_pilot.py`; `run_posthoc.py` | Mechanism illustration only; status remains `HOLD_NUMERICAL_EVIDENCE` |
| Paper figures | `scripts/regenerate_paper_figures.py` plus canonical generator | Formatting-only reproduction from frozen export inputs |
| Paper tables | `scripts/regenerate_paper_tables.py` | Re-derivation/copy of frozen table values and layouts |

The Formal B2 P05 empty-profile adapter is represented by canonical evidence, not folded into the byte-frozen D2.3 scientific core. This preserves the distinction between scientific computation and the later administrative null-map interface.

