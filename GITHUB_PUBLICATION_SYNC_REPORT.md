# GitHub publication synchronization report

Date: 2026-08-12

Repository: `https://github.com/GJPengAtNchu/PhysicalSupportConfidenceSets`

Working branch: `publication-sync-2026-08-12`

Baseline remote commit: `fe9c3eedfb35200f76f3799e28288567920d1b5a`

## Safety and scope

- The existing repository and remote were used; `git init` was not run.
- The working branch was created only after the clean local `main` was
  verified to equal `origin/main` at the baseline commit above.
- No scientific source under `src/`, frozen configuration under `configs/`,
  seed, bank, threshold, budget, decision rule, eligibility rule, numerator,
  denominator, or terminal scientific status was changed.
- No B1.1 or Formal B2 scientific case was executed.  Only representative
  executable checks, artifact renderers, unit/invariant tests, and release
  validation were run.
- No force push, destructive reset, release tag, DOI, arXiv identifier,
  version, release date, or license was introduced.

## Commands executed in the clean release environment

The repository-local `.venv` was recreated from Python 3.12 because the old
ignored environment referenced an unavailable interpreter.  It remains
ignored and is not part of the release.

```text
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts\run_representative_example.py --study b11 --output build\manual_validation\b11.json
.venv\Scripts\python.exe scripts\run_representative_example.py --study formal-b2 --output build\manual_validation\formal_b2.json
.venv\Scripts\python.exe scripts\regenerate_conceptual_figure.py --output-dir build\manual_validation\figure1
.venv\Scripts\python.exe scripts\regenerate_paper_figures.py --output-dir build\manual_validation\figures
.venv\Scripts\python.exe scripts\regenerate_paper_tables.py --output-dir build\manual_validation\tables
.venv\Scripts\python.exe scripts\build_source_manifest.py
.venv\Scripts\python.exe scripts\validate_release.py
git diff --check
```

## Validation results

- Pytest: **14 passed**.
- Release validator: **PASS_PUBLICATION_RELEASE_VALIDATED**.
- Representative executable checks: B1.1 and Formal B2 each ran twice under
  the validator and reproduced byte-identical outputs within the clean
  environment.
- Tables: six files regenerated twice and matched byte-for-byte; canonical
  values were independently checked by the table renderer.
- Conceptual Figure 1: three independently authored TikZ panels regenerated
  twice as PDF, EPS, and 300-dpi PNG; all nine outputs were deterministic.
- Empirical main figures: eight independent panel canvases regenerated twice
  as PDF, EPS, and 300-dpi PNG; the supplementary collapse diagnostic was also
  regenerated in all three formats.  All 27 empirical outputs were
  byte-identical across the two clean-environment runs.
- The validator reproduced 11 main-manuscript panels, one supplementary
  diagnostic, and six table files without running a frozen scientific study.
- The compact controller table contains one header and exactly 324 stored
  budget rows.  Its public copy differs from the read-only source only by
  CRLF-to-LF normalization; the row values and the six-budget/54-trace
  scientific contents are unchanged.
- P05 remains the single administrative empty profile with a null physical
  map.  Development-only evidence is not used in any final numerator.

The publication renderer verifies every pinned source hash before and after
rendering and asserts the stored scientific invariants.  Its empirical PDFs
are not byte-identical to the already compiled manuscript PDFs because the
clean publication environment uses its recorded Matplotlib dependency build.
All eight PDFs are, however, regenerated from the same pinned arrays and
transformations and pass the same exact numerical assertions.  Determinism is
required and achieved within the documented release environment; PDF byte
identity across different Matplotlib builds is not claimed.

## Canonical provenance update

Every payload covered by the original 70-entry canonical checksum tree remains
byte-identical to the baseline commit.  The checksum tree itself was extended
with four compact, publication-facing inputs:

1. `b11_global/figure_data/controller_results.csv` (324 stored rows);
2. `paper/figure_sources/figure1/conceptual_pipeline_panel_a.tex`;
3. `paper/figure_sources/figure1/conceptual_pipeline_panel_b.tex`;
4. `paper/figure_sources/figure1/conceptual_pipeline_panel_c.tex`.

The extended canonical checksum tree now verifies 74 of 74 entries and has
SHA-256
`194bda3f4bd0e8fed993dfc962181c07db926d6932c3bb14cc78b72426302789`.
The compact controller table has SHA-256
`c1f9d342465fe116f7dfe2c796a6889e81e9467d5e1a193c4bde38585977f211`.

## Files synchronized

Added:

- `CITATION.cff` with only verified title, author, ORCID, repository URL, and
  software type;
- `artifacts/release_manifest.json`;
- `docs/PUBLICATION_RELEASE_MANIFEST.md`;
- the four compact canonical inputs listed above;
- `scripts/manuscript_panel_renderer.py`;
- `scripts/regenerate_conceptual_figure.py`;
- `tests/test_publication_manifest.py`;
- this report.

Updated:

- `.gitignore`;
- `README.md`;
- `docs/METHOD_TO_CODE_MAP.md`;
- `docs/REPRODUCIBILITY_SCOPE.md`;
- `docs/RESULT_PROVENANCE.md`;
- `docs/SOURCE_MANIFEST.csv`;
- `scripts/build_source_manifest.py`;
- `scripts/regenerate_paper_figures.py`;
- `scripts/validate_release.py`;
- `tests/test_canonical_exports.py`;
- `artifacts/canonical_paper_export/provenance/checksums.sha256`.

## Intentionally excluded

- `.venv/`, `build/`, Python caches, pytest caches, editor temporary files,
  and locally rendered validation outputs;
- raw evidence ZIP files and large historical bundles;
- recovery wrappers, monitors, heartbeat and lifecycle logs, and private run
  logs;
- duplicate scientific worktrees and development-only outputs;
- machine-local absolute paths, credentials, API keys, and tokens;
- continuous-confidence-correspondence computation, unrestricted off-bank
  validation, and real-data work;
- any license, DOI, arXiv record, GitHub Release, or release tag.

The source manifest was regenerated after this report was present, so its
final tree closure includes the report itself.  Pytest and the full release
validator were then executed again immediately before commit and push.
