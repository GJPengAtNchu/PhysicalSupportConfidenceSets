# Post-hoc robustness diagnostic R0.1

This diagnostic was frozen only after `THREE-GATE-SIM-PILOT-R0` returned
`HOLD_NUMERICAL_EVIDENCE`.  It cannot change that confirmatory status.

The sole R0 failure was a transition-band median product-affinity spread of
`0.0166976` against a frozen `0.015` threshold.  All sixth-order, precision,
maximum-spread, Gauss-Hermite, task-invariance, and matching checks passed.

R0.1 asks whether the near-miss is accompanied by a broader instability:

1. At `s=0.082`, estimate Jeffreys divergence on path parameters
   `h={0.10,0.15,0.20,0.25,0.35,0.45}` with the same normalized generator.
   Use 32 paired blocks of size 8,192 and seed 2026072221.  A diagnostic pass
   requires a log-log slope in `[1.85,2.10]`, `R^2 >= 0.995`, and a maximum
   ratio of `J/h^2` no larger than `1.20`.
2. Run the already frozen low-cost stress grid in `config.json` over
   `p={0.1,0.2,0.35}` and `nu={0.3,0.5,1.0}`.  Each fitted `s` exponent must
   remain in `[5.4,6.6]`.

If both pass, the scientific interpretation is
`R0_HOLD_BUT_GEOMETRY_ROBUST`: integration may be considered only with the
R0 near-miss disclosed and without relabeling R0 as a pass.  Otherwise the
interpretation remains `HOLD_NUMERICAL_EVIDENCE`.
