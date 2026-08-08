# Repository instructions

`SCIENCE CLOSED — MANUSCRIPT MODE`

## Layout

- `src/physical_support_confidence_sets/`: recovered scientific implementation.
- `configs/`: frozen study inputs and freeze records.
- `artifacts/canonical_paper_export/`: immutable paper-facing outputs.
- `scripts/`: bounded smoke checks, artifact regeneration, and release validation.
- `tests/`: seed-free unit and invariant checks.
- `docs/`: scope, provenance, and source mapping.

## Standard commands

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts\validate_release.py
```

## Frozen constraints

- Preserve canonical numbers, denominators, case IDs, status strings, nulls, seeds, thresholds, policy order, bank order, and replay semantics.
- Treat `artifacts/canonical_paper_export/` and frozen configs as immutable inputs.
- P05 stays an administrative empty profile with exact profile `[]` and physical map `null`; do not impute it.
- Keep the theorem-native illustration at `HOLD_NUMERICAL_EVIDENCE`.
- Keep B1.1 global-only and Formal B2 application-specific.

## Prohibited expansion

Do not add or run full campaigns, new gates, retuning, AEB redesign, continuous-bank computation, off-grid or real-data studies, adaptive refinement, AEB-v2, historical monitoring/recovery infrastructure, or manuscript edits.

## Completion for future changes

Run tests and `scripts\validate_release.py`, regenerate `docs\SOURCE_MANIFEST.csv` when public files change, confirm `git diff --check`, review the staged tree, and verify the pushed commit. Do not add a license, DOI, preprint claim, tag, or GitHub Release without owner instruction.

