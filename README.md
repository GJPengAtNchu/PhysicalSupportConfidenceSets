# Physical-Support Confidence Sets for Highly Coherent Dictionaries

This repository accompanies the manuscript **Physical-Support Confidence Sets
for Highly Coherent Dictionaries**. It studies uncertainty in inverse problems
where several highly coherent dictionary representations fit the observations
nearly equally well but imply different physical supports.

The central principle is to report only the physical conclusions shared by the
representations that remain statistically compatible. The theory describes a
continuous confidence correspondence; the executable method, active
endpoint-bracketing (AEB), realizes the same retain--project--coarsen logic on a
declared finite candidate bank.

The manuscript, including its supplementary material, is available as
[arXiv:2608.20295](https://arxiv.org/abs/2608.20295).

## What the paper contributes

- **A physical-support confidence target.** Dictionary atoms, coefficient
  supports, and physical support are kept distinct, so representation
  uncertainty is not silently converted into physical certainty.
- **An information-resolution theory.** For local coherence scale `s` and
  calibration size `N`, the characteristic calibration information is
  `N s^6`, with the localization scale
  `min{s, 1 / (sqrt(N) s^2)}` under the stated local model. Deployment data
  resolve orientation only when the coefficient profile exposes that
  direction.
- **A finite-bank reporting procedure.** AEB adaptively evaluates candidate
  explanations, maintains lower and possible sets, projects them to physical
  conclusions, and either reports a justified fine/coarse conclusion or
  abstains.
- **Reproducible numerical evidence.** The repository includes the scientific
  implementations, recorded configurations and seeds, compact canonical
  outputs, deterministic figure/table generators, and validation tests used
  for the manuscript.

## Numerical studies represented in the manuscript

### Information mechanism

For exact 32-component mixture densities evaluated on six separation scales,
the estimated Jeffreys-divergence log--log slope is **5.935**
(`R^2 = 0.99999`). A 2,000-replicate paired-batch calculation gives the
central 95% Monte Carlo stability range **[5.925, 5.947]**. This is a numerical
integration stability diagnostic conditional on the fixed model and grid, not
a confidence interval across independent datasets.

The accompanying deployment calculation confirms the coefficient-profile
mechanism: the equal-coefficient residual stays at machine precision
(`6.8e-16` over the stored grid), while the analytical unequal-coefficient
identity agrees to relative error `7.0e-15`.

### Four-region finite-bank application

The synthetic application has four physical regions, 12 response atoms,
72 dictionary states, and 216 dictionary--support explanations. Across 15
datasets, the exhaustive same-bank reference is nonempty for 14 profiles
(11/12 main profiles and 3/3 controls); the remaining profile is an
administrative empty profile and therefore has a null physical map.

Relative to the completed same-bank references, AEB reports:

- fine localization in region A for **10/11** eligible profiles; in the
  remaining profile it abstains rather than returning an incorrect fine
  location;
- the correct group-level conclusion in region B for **5/5** eligible weak-C
  profiles;
- support ambiguity in region C for **5/5** eligible weak-C profiles;
- represented-scale absence in region D for **10/10** eligible main profiles,
  with **0/3** false absence conclusions in the controls.

A point-valued proposal-split maximum-likelihood plug-in selector is
overprecise in the same weak-C profiles: **5/5** unsupported fine region-B
conclusions and **5/5** false-certainty region-C conclusions. These comparisons
are relative to exhaustive evaluation of the same represented finite bank.

### Global query--resolution study

The global study contains 18 independent cases and three reporting profiles,
for 54 traces evaluated at six query-budget fractions. At budget 0.50, AEB is
non-abstaining on **41/54** traces, recovers **33/34** ambiguity references and
**0/7** fine references. At budget 0.75, the corresponding counts are
**54/54**, **34/34**, and **5/7**. The two remaining fine references are
reported safely at a coarser level.

Across all 324 stored budget results there are no unsupported finer-than-
reference decisions. The median trace-specific query fraction is **0.209** at
both highlighted budgets; the larger budget changes the upper tail and fine
recovery rather than the middle order statistics.

## Installation

Python 3.10 or newer is required. From the repository root in PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

On macOS or Linux, replace `.venv\Scripts\python.exe` with
`.venv/bin/python`.

Regenerating the conceptual figure also requires a TeX installation providing
`pdflatex` and Poppler tools providing `pdftops` and `pdftoppm`. The empirical
figure renderer and table generator use the declared Python dependencies.

## Reproduce the manuscript artifacts

The following commands regenerate the manuscript figures and tables from the
compact canonical exports. They do not rerun the numerical studies.

```powershell
.venv\Scripts\python.exe scripts\regenerate_conceptual_figure.py
.venv\Scripts\python.exe scripts\regenerate_paper_figures.py
.venv\Scripts\python.exe scripts\regenerate_paper_tables.py
```

The conceptual figure is generated as three independent TikZ panels. The
empirical displays are generated as eight independent main-paper panels plus
one supplementary diagnostic. Each panel is exported as vector PDF, EPS, and
300-dpi PNG; panel identifiers and titles are supplied by the LaTeX subfigure
captions rather than embedded in the artwork. The generators verify their
inputs before rendering and preserve all displayed numerical values.

## Test the release

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts\validate_release.py
```

The validation command checks source and artifact hashes, result dimensions
and denominators, deterministic examples, regenerated figures/tables, manifest
closure, and repository hygiene. It exits nonzero on any mismatch.

## Repository layout

- `src/physical_support_confidence_sets/` -- numerical mechanism, finite-bank
  scoring, AEB, physical projection, and application implementations.
- `configs/` -- recorded study designs, policies, budgets, environments, seeds,
  and protocols.
- `artifacts/canonical_paper_export/` -- compact data, metrics, tables, figure
  inputs, receipts, and checksums used by the manuscript.
- `scripts/` -- deterministic artifact regeneration, representative executable
  checks, manifest construction, and release validation.
- `tests/` -- unit, invariant, regeneration, and publication-integrity tests.
- `docs/` -- method-to-code map, result provenance, reproducibility scope, and
  release manifests.

The application comparator implemented here jointly maximizes the deployment
proposal likelihood over the represented 216 dictionary--support explanations
and returns the selected explanation as a point-valued physical map. It is not
OMP, Lasso, or a two-stage calibration-dictionary pursuit.

For exact source/result mappings, see
[METHOD_TO_CODE_MAP.md](docs/METHOD_TO_CODE_MAP.md),
[RESULT_PROVENANCE.md](docs/RESULT_PROVENANCE.md),
[REPRODUCIBILITY_SCOPE.md](docs/REPRODUCIBILITY_SCOPE.md), and
[SOURCE_MANIFEST.csv](docs/SOURCE_MANIFEST.csv).

## Scope

The empirical conclusions are conditional on the declared synthetic models
and represented finite candidate banks. The repository does not claim
continuous-bank completeness, off-bank guarantees, real-data validation,
arbitrary-source absence, or universal superiority over point-valued methods.
The compact release supports artifact reproduction and bounded executable
checks; it does not package the historical long-running orchestration or raw
evidence archives.

## Citation

If you use this software, please cite the accompanying manuscript:

> Guan-Ju Peng, *Physical-Support Confidence Sets for Highly Coherent
> Dictionaries*.

Machine-readable citation metadata is provided in [CITATION.cff](CITATION.cff).
This repository does not currently assert a publisher DOI, version tag, or
GitHub Release. No license is granted by this repository at present.
