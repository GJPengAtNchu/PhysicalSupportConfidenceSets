# Publication release manifest

## Identity

- Manuscript title: **Physical-Support Confidence Sets for Highly Coherent Dictionaries**
- Repository: <https://github.com/GJPengAtNchu/PhysicalSupportConfidenceSets>
- Release source baseline: `fe9c3eedfb35200f76f3799e28288567920d1b5a`
- Synchronization branch: `publication-sync-2026-08-12`

The machine-readable companion is `artifacts/release_manifest.json`.  Its
`source_commit` field records the immutable baseline from which this
publication synchronization was prepared; the final pushed commit is reported
by Git history and the task handoff, avoiding a self-referential commit hash
inside the commit payload.

## Frozen scientific status

| Component | Terminal status | Scope |
|---|---|---|
| B1.1 global finite-bank study | `PASS_ARA_B11_ORACLE_AUDIT_COMPLETED_AND_B1_VALIDATED` | 18 cases, 54 global traces; same-bank/global-only validation |
| Formal B2 four-region application | `PASS_ARA_B2_FORMAL_FRESH_APPLICATION_VALIDATED` | 15 cases; 14 completed exact profiles plus one administrative empty profile |
| Theory-guided numerical illustration | `HOLD_NUMERICAL_EVIDENCE` | controlled mechanism illustration, not the full continuous correspondence |

P05 remains `ORACLE_EMPTY_PROFILE_INCOMPLETE` with exact profile `[]` and a
null physical map.  It is not imputed or converted to all-regions absent.

## Released components

- Scientific source: `src/physical_support_confidence_sets/{b11,formal_b2,original_numerical}/`
- Frozen configurations and seeds: `configs/{b11_global,formal_b2,original_numerical}/`
  - B1.1: `frozen_seeds.json`, `b1_frozen_config.yaml`,
    `information_conditions.csv`, `selected_operating_points.json`, and
    `B1_CODE_FREEZE.json`;
  - Formal B2: `formal_primary_seeds.json`, `formal_case_order.csv`,
    `b2f01_frozen_config.json`, and `b2f01_code_freeze.json`;
  - numerical illustration: `config.json` (with environment and protocol
    companions in the same directory).
  The machine-readable manifest enumerates all 18 released configuration,
  seed, policy, gate, environment, and protocol files explicitly.
- Compact canonical outputs: `artifacts/canonical_paper_export/`
- Conceptual Figure 1 sources:
  `artifacts/canonical_paper_export/paper/figure_sources/figure1/`
- Reproduction/validation entrypoints:
  - `scripts/regenerate_conceptual_figure.py`
  - `scripts/regenerate_paper_figures.py`
  - `scripts/regenerate_paper_tables.py`
  - `scripts/run_representative_example.py`
  - `scripts/validate_release.py`
- Invariant tests: `tests/`

## Compact-artifact identities

| Artifact | SHA-256 |
|---|---|
| Extended canonical export checksum tree (74/74) | `194bda3f4bd0e8fed993dfc962181c07db926d6932c3bb14cc78b72426302789` |
| B1.1 canonical summary | `90a12ba9af0410b56419e2e679d7de4778b3026ac6195ed2eb80e33f4586067a` |
| Formal B2 canonical summary | `11ac10a1a2261965ba721f2e24beca27ff7164404f545c625e11f854140f8ea5` |
| Formal B2 empty-profile disclosure | `1c05020f084e65c49c7a0a1ef52e5fa6d401467b478ceb8b01cb71298f1d2d67` |
| Theory-guided numerical summary | `ad6fbed5f4dd5b3e72f059f1b9e256bee21ba2730ae0429e37eab8d968889f9f` |
| B1.1 frozen seeds | `86d73f373644ef036e878a5c6ca3d29ba13370ac566485ba5fb230aa00249c98` |
| Formal B2 primary seeds | `fda39941ec5578046349f25c56ad29a697c1c7495227ed8de60c7793b27b9d82` |
| Numerical-illustration config | `259511dbf58d9703c177c333a2de5c718a4ec3bac619c463cf6fc8efcadf68c8` |

## Validation commands

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts\validate_release.py
.venv\Scripts\python.exe scripts\regenerate_conceptual_figure.py
.venv\Scripts\python.exe scripts\regenerate_paper_figures.py
.venv\Scripts\python.exe scripts\regenerate_paper_tables.py
```

The two representative checks are documented in the README.  They exercise
bounded executable semantics and explicitly carry `scientific_claim=false`;
they do not reproduce or redefine the formal reported rates.

The original 70-file canonical export closed under checksum-manifest SHA-256
`3845204e78236164afac879c3ed9023fe95e1552393e5fa5278635a5f631ae88`.
This publication sync preserves all 70 payload bytes and extends the tree only
with the three conceptual-panel TikZ sources and the compact saved 324-row
B1.1 controller table needed by the current presentation renderer.

## Deliberate exclusions

The release excludes raw evidence ZIPs, complete historical orchestration,
recovery wrappers, monitors, heartbeat/lifecycle logs, private machine paths,
virtual environments, caches, temporary previews, and duplicate research
worktrees.  It also makes no claim of a DOI, arXiv identifier, release tag,
GitHub Release, license, full continuous-correspondence implementation,
off-bank validity, or real-data validation.
