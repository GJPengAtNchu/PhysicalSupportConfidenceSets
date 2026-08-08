# THREE-GATE-SIM-PILOT-R0

Frozen: 2026-07-22 (Asia/Taipei), after an implementation-only exploratory
sanity check and before the confirmatory seeds in `config.json` were used.

## Purpose and claim boundary

This is a synthetic, theorem-native falsification pilot for the SIMODS
manuscript.  It asks whether the three least-favourable comparisons are
numerically visible in the exact low-dimensional experiment.  It does **not**
validate the conservative moment-profile correspondence, a scalable solver,
or a localization application.

The frozen manuscript at
`../idea2_simods_fixed_dimension_repair/` is not modified during this pilot.

## Data-generating experiment

Use the manuscript's balanced hard core with `q=4`, `n=5`, and `r=2`.
The child reference vertices are the regular tetrahedron

```text
(1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1),
```

each divided by `sqrt(3)`, embedded in `U=span(e1,e2,e3)` with `u=e4`.
The anchor is `(u+e1)/sqrt(2)`.  At collision scale `s`,

```text
d_j(s,phi) = sqrt(1-s^2) u + s R_phi v_j,
```

where `R_phi` rotates about `v_1+v_2`; hence it fixes the equal-coefficient
test mean on support `{1,2}`.  Training uses Bernoulli-Gaussian codes with
`p=0.2`, active variance one, and noise variance `nu=0.5`.  Its observed law
is evaluated as the exact 32-component zero-mean Gaussian mixture.

The confirmatory path parameter is `h=0` versus `h=0.25`; its skew generator
is normalized by `max_{j in S} ||Omega v_j||=1`, so the actual rotation angle
is `sqrt(3/2) h`.  The
collision grid, Monte Carlo batches, random seeds, and all thresholds are in
`config.json`.

## Numerically stable mixture diagnostics

Let `P` and `Q` be the two one-observation training mixtures, let
`m=(P+Q)/2`, and write `L=log(dP/dQ)`.  Sampling exactly from `m`, estimate

```text
Jeffreys(P,Q) = 2 E_m[L tanh(L/2)],
1 - affinity(P,Q) = E_m[tanh(L/2)^2 / {1 + sech(L/2)}].
```

Both integrands are nonnegative and quadratic in the small likelihood ratio.
This avoids the exploding relative error of a signed directed-KL average.
For `N` independent training observations, the affinity is raised to the
`N`th power exactly.

## Frozen diagnostics

The confirmatory run uses 128 paired common-random-number blocks of size
8,192, totaling `2^20` midpoint observations at every `s`, with exactly half
from each endpoint in every block.  Tensor Gauss-Hermite orders 10 and 14 at
`s=0.067,0.100` provide a deterministic cross-check.

1. **Cubic score / sixth-order information.**  Regress log Jeffreys and log
   affinity deficit on log `s`.  Check slopes near six, high `R^2`, stable
   scaling by `s^6`, and the local identity
   `Jeffreys / {8(1-affinity)} -> 1`.
2. **Three gates.**  Use the exact Gaussian affinity for the parent and
   wrong-support pairs, and the exact-mixture product affinity for the
   orientation pair.  Plot pairwise Hellinger distinguishability against
   `I_G`, `I_S`, and `I_D=Ns^6`; quantify cross-`s` collapse for the
   dictionary gate.
3. **Task control.**  Verify machine-zero test displacement for equal
   coefficients at every rotation and the manuscript's analytic
   coefficient-profiled residual for nonzero two-atom contrast.
4. **Independent stress check.**  Only after the confirmatory gate passes,
   repeat a lower-cost slope audit over the frozen `p` and `nu` grid.  This
   checks robustness of the exponent, not equality of constants.

## Adjudication

- `GO_FOR_MANUSCRIPT_INTEGRATION` requires every essential confirmatory
  threshold in `config.json` to pass and no numerical-convergence warning.
- `HOLD_NUMERICAL_EVIDENCE` applies if sixth-order scaling passes but curve
  collapse, task controls, or convergence does not.
- `NO_GO_THEOREM_NATIVE_SIMULATION` applies if either the sixth-order scaling
  or equal-coefficient test invariance fails.

Stress-grid failure does not overturn the confirmatory exponent by itself;
it narrows the range that may be illustrated and must be disclosed.
