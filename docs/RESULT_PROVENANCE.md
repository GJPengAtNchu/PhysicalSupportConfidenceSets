# Result provenance

## Authoritative archives

The release engineer independently verified outer SHA-256, ZIP CRC, duplicate-member absence, and each self-contained checksum tree before selecting public files.

| Archive | SHA-256 | Integrity result | Public role |
|---|---|---|---|
| `B11_GLOBAL_FINAL_EVIDENCE.zip` | `2095d8c17081cc9e574f5e052b2a1100864eff499610c45ef2c999905bf67c83` | 3,636 members; root tree 3,635/3,635 exact | Final B1.1 results and provenance |
| `FORMAL_B2_FINAL_EVIDENCE.zip` | `89649c27c956a2ade19ea2fe16ef549b4a028d7d544fd5eeef47a1dd4bddc738` | 58 members; root tree 57/57 exact | Final Formal B2 plus native P05 safety closure |
| `ORIGINAL_THREE_GATE_EXPERIMENT_EVIDENCE.zip` | `cb99fc8fda7efa3872185f0ca1460de262fdc201d2a1996182e74b47a00b8379` | 53 members; inner tree 52/52 exact | Theorem-native numerical illustration |
| `Honest_Collision_Aware_Dictionary_Refinement_V2_SOURCE.zip` | `8ab580ae47fe83455814f840b6bf32133bf074c7f388eec7f170523b3f85f872` | 25 members; CRC/duplicates clean | Earlier manuscript implementation source |
| `Physical_Support_Confidence_Sets_Source_V1.zip` | `8b2a6888cf0b40bf874f92452bc6362365f55de6c48f7272c28ef2322f9cbe48` | 131 members; canonical subtree 70/70 exact | Manuscript source and canonical paper export |

Large evidence ZIPs are not committed. Their names, hashes, roles, selected source members, and file-level hashes are recorded here and in `SOURCE_MANIFEST.csv`.

The current manuscript presentation renderer additionally consumes the compact
324-row B1.1 controller result table and the 54-row exact-validation table now
under `artifacts/canonical_paper_export/b11_global/figure_data/`.  It joins
those saved rows only to reproduce the displayed status categories; it does
not rerun a controller or oracle.

## Code freezes

- Original B1 scientific freeze: `a263cc2fe0a97a448b66722608494ed88908994088c219bceccfa79bd1e6390f`.
- B1.1 completion/readjudication freeze: `742bf3baba3126cafbe30ae2b8ce05d5b71be57a9b75d174c338fbee04b705ee`.
- Formal B2 D2.3 scientific freeze: `f824de383e8b236f23f2ed5ee413b36e2ac9461a783bad956110053f00e68f30`.
- Formal B2 F0.1 code/task freeze: `a6f3c954bf1d41549eb8843893c11d1eadf2f38d5ca42f35919c8aaa787c3a5e`.
- Original canonical paper export checksum manifest:
  `3845204e78236164afac879c3ed9023fe95e1552393e5fa5278635a5f631ae88`
  (70/70 original payloads verified).
- Publication-presentation extension checksum manifest:
  `194bda3f4bd0e8fed993dfc962181c07db926d6932c3bb14cc78b72426302789`
  (74/74; all original payload bytes preserved, with only three Figure 1
  TikZ sources and one compact saved B1.1 controller table added).

The 15 Formal B2 files under `src/physical_support_confidence_sets/formal_b2/` are byte-identical to the successor D2.3 core recorded in the F0.1 freeze. B1.1 files are namespaced for publication; `SOURCE_MANIFEST.csv` records each original hash and the import-only cleanup.

## Evidence precedence

1. M0 scientific claim freeze.
2. M0 canonical results.
3. M0 claim-evidence matrix.
4. M0 canonical export specification.
5. Final B1.1 evidence.
6. Final Formal B2 evidence and safety closure.
7. Frozen configurations, seeds, and artifacts.
8. Recovered scientific-core source.

The preserved predecessor Formal B2 summary that still says HOLD/timeout is not used alone. Current final semantics require the final adjudication, native empty-profile audit, possible-set proof, and safety-closure overlay together.

## Canonical counts and exclusions

B1.1 contains 18 datasets, 18 completed oracles, and 54 immutable traces. Formal B2 contains 15 cases, with 14 completed exact oracles and one native administrative empty profile. P05 is excluded from truth-relative utility and completed-bound denominators without imputation, while its 162 Stage-A queries remain in cost. The completed-prefix denominator is 2,088, not an imputed 15-case denominator.
