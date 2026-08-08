# M0-A Canonical Results

Status: **APPROVED AND FROZEN**  
Purpose: one human-readable source for every headline theorem statement and
empirical number permitted in the manuscript.

## 1. Evidence precedence

1. Formal B2 safety, P05 semantics, and terminal status:
   `FORMAL_B2_FINAL_EVIDENCE.zip`, `formal_adjudication.json`,
   `contract_faithful_safety_audit.json`, and
   `paper_export/b2f03_safety_closure_summary.json`.
2. Formal B2 non-safety metrics: the sealed predecessor
   `primary_budget_metrics.json`, `secondary_budget_metrics.json`,
   `plugin_false_precision_metrics.json`, and representative-selection
   artifacts, subject to item 1.
3. B1.1: the final 18-case/54-trace bundle and B1.1 re-adjudication, not earlier
   B1 HOLD summaries.
4. Original theorem-native experiment: frozen R0 adjudication for confirmatory
   status; post-hoc files only for explicitly labeled robustness.
5. D0--D2.3: provenance only; excluded from confirmatory rates.

## 2. Canonical theory

### Model and target

- Fixed dimension: \(q\ge4\), dictionary size \(n=q+1\), and fixed support
  cardinality \(2\le r\le q-1\).
- Supplied collision shell: \(s\in(0,s_0]\), with one coherent child block
  and one separated anchor.
- Training: \(N\) independent latent sparse Gaussian mixtures.
- Test: \(T\) independent replicates of one fixed sparse mean.
- Target: marked compact sets of physical rays modulo sign and child
  permutation.

### Coverage

The exact unknown-\(p\) correspondence obeys

\[
\Pr_{\rm train}\!\left[
  \Pr_{\rm test}\{\vartheta_\star\in\widehat{\mathfrak C}\mid Y^N\}
  \ge 1-\alpha_T
\right]\ge 1-\alpha_D.
\]

By independence, its marginal coverage is at least
\((1-\alpha_D)(1-\alpha_T)=1-\alpha\).

### Three information gates

\[
I_G^{(r)}=\frac{Tr^2\beta_-^2}{\sigma_+^2},\qquad
I_S=\frac{T\beta_-^2s^2}{\sigma_+^2},\qquad
I_D=Ns^6.
\]

No \(NT\) product gate is claimed.

### Resolved minimax rate

Once the parent and support gates exceed their fixed upper thresholds,

\[
\mathcal R_{N,T}^{(q,r)}(s)
\asymp
s\wedge\frac{1}{\sqrt N\,s^2}.
\]

This is a constant-factor result on one supplied fixed shell. It is not a
sharp transition-constant theorem and not adaptation over unknown \(s\).

### Task-dependent test information

The local general-\(r\) efficient information is

\[
I_{\Omega\mid x}^{\rm test}
=\frac{Ts^2}{\sigma^2}\chi_{\rm tan}^2.
\]

The finite matching train-test rate is restricted to the declared
one-dimensional orbit:

\[
\mathcal R_{N,T}^{\rm task}
\asymp
s\wedge\frac{s}{
\sqrt{Ns^6+T\chi_s^2s^2/\sigma^2}}.
\]

For two active atoms, the amplitude-contrast crossover is

\[
|d_0|\asymp \sigma\sqrt{N/T}\,s^2.
\]

The equal-coefficient slice is exactly test-invariant.

## 3. B1.1 global-controller validation

Final status:
`PASS_ARA_B11_ORACLE_AUDIT_COMPLETED_AND_B1_VALIDATED`.

### Scope

| Item | Canonical value |
|---|---:|
| Complete finite-bank cases | 18 |
| Information conditions | 3 |
| Operating profiles | 3 |
| Sealed controller traces | 54 |
| Full finite-bank candidate evaluations | 14,514 |
| Existing/new high-precision replay payloads used in completed audit | 1,097 / 3,223 |
| Structural unsafe decisions | 0 |
| Trace-prefix bound violations | 0 |
| Full-budget exact-label mismatches | 0 |

### Frozen conditions and operating profiles

| Condition | \(N\) | \(s\) | Training noise | Bank size |
|---|---:|---:|---:|---:|
| LOW_INFORMATION_F0 | 4,096 | 0.35 | 1.20 | 1,025 |
| INTERMEDIATE_INFORMATION_S3 | 65,536 | 0.50 | 0.90 | 1,025 |
| HIGH_INFORMATION_R3 | 131,072 | 0.50 | 0.80 | 369 |

| Profile | \(\alpha\) | Fine threshold fraction | Sector threshold fraction |
|---|---:|---:|---:|
| RISK_CONSERVATIVE | 0.025 | 0.40 | 0.50 |
| BALANCED | 0.077 | 0.35 | 0.60 |
| RESOLUTION_FAVORING | 0.150 | 0.25 | 0.40 |

### Frozen pooled budget results

| Metric | Budget 0.50 | Budget 0.75 |
|---|---:|---:|
| Output counts | 13 ABSTAIN, 33 AMBIGUOUS, 8 SECTOR_SAFE | 34 AMBIGUOUS, 5 FINE, 15 SECTOR_SAFE |
| Non-abstain yield | 41/54 = 0.7593 | 54/54 = 1.0000 |
| AMBIGUOUS recall | 33/34 = 0.9706 | 34/34 = 1.0000 |
| FINE recall | 0/7 = 0 | 5/7 = 0.7143 |
| Safe nonambiguous rate | 8/20 = 0.4000 | 20/20 = 1.0000 |
| Median logical query fraction | 0.2088 | 0.2088 |
| Worst logical query fraction | 0.4995 | 0.7493 |

The 0.75 empirical wrong-FINE and wrong-SECTOR marginal counts are 0/18 for
each profile, but the upper end of the exact 95% binomial interval is 0.1853.
These are descriptive diagnostics, not exact selective-risk guarantees.

Offline B1/B1.1 audit time and replay work must not be described as controller
deployment latency.

## 4. Formal B2 application validation

Final status:
`PASS_ARA_B2_FORMAL_FRESH_APPLICATION_VALIDATED`.

### Frozen application

| Item | Canonical value |
|---|---:|
| Synthetic regions | A, B, C, D |
| Target response atoms | 12 |
| Dictionary states | 72 |
| Support patterns | AB, ABC, ABD |
| Candidate explanations | 216 |
| Calibration size \(N\) | 4,096 |
| Deployment size \(T\) | 192 |
| Response width \(h\) | 0.085 |
| Frozen \(\alpha\) | 0.077 |
| Frozen B/C thresholds | `tau_B = 0.80`; `tau_C = 0.10` |
| Primary query cap | 162/216 = 0.75 |
| Secondary descriptive prefix | 108/216 = 0.50 |
| D absence threshold | `tau_D_beta = 1.00` |
| Fresh formal datasets | 15 |
| Completed exact oracles | 14/15 |
| Administrative empty profiles | 1/15 overall; 1/6 weak-C cases |

### Safety

| Gate | Result | Scope |
|---|---:|---|
| Unsafe outputs | 0/56 | 14 completed oracle maps × 4 regions |
| Possible-set violations | 0/15 traces | includes 162 sealed P05 prefixes |
| Prefix-bound violations | 0/2,088 | 14 completed validations only |
| False D absence in controls | 0/3 | D-present controls |

### Coverage, utility, and cost

| Gate | Canonical result |
|---|---:|
| Main oracle coverage | 11/12 = 0.9167 |
| Control oracle coverage | 3/3 = 1.0000 |
| Exact A FINE in main cases | 11/12 = 0.9167 |
| Controller A FINE recall | 10/11 = 0.9091 |
| Weak-C exact B SECTOR_SAFE | 5/6 = 0.8333 |
| Controller B sector recall | 5/5 = 1.0000 |
| Weak-C exact C SUPPORT_AMBIGUOUS | 5/6 = 0.8333 |
| Controller C ambiguity recall | 5/5 = 1.0000 |
| Main exact D ABSENT_ABOVE_BETA_MIN | 10/12 = 0.8333 |
| Controller D-absence recall | 10/10 = 1.0000 |
| D-control nonabstaining | 3/3 = 1.0000 |
| Complete intended weak-C maps | 5/6 = 0.8333 |
| Plug-in B false FINE among eligible cases | 5/5 = 1.0000 |
| Plug-in C false certainty among eligible cases | 5/5 = 1.0000 |
| Median primary logical query fraction | 148/216 = 0.6852 |

### Primary controller output distribution across 15 traces

| Region | Output distribution |
|---|---|
| A | 10 FINE; 5 ABSTAIN |
| B | 15 SECTOR_SAFE |
| C | 11 SUPPORT_AMBIGUOUS; 4 ABSENT_ABOVE_BETA_MIN |
| D | 10 ABSENT_ABOVE_BETA_MIN; 4 SECTOR_SAFE; 1 SUPPORT_AMBIGUOUS |

The 108-query state is descriptive and was derived from the primary traces;
no separate secondary controller was run.

### Empty profile P05

- Case: `FORMAL_WEAK_C_PRESENT_P05`.
- Native status: `ORACLE_EMPTY_PROFILE_INCOMPLETE`.
- Exact finite profile: empty.
- Physical map: null.
- Physical/scientific quantity imputed: no.
- Truth-relative utility eligible: no.
- Completed bound validation included: no.
- Possible-set proof: 0 violations across all 162 Stage-A prefixes.
- Stage-A query count: 162, retained in query-cost reporting.

P05 must not be called a timeout and must not be described as “all regions
absent.”

## 5. Original theorem-native numerical illustration

Frozen status: `HOLD_NUMERICAL_EVIDENCE`.  
Post-hoc interpretation: `R0_HOLD_BUT_GEOMETRY_ROBUST`.

| Metric | Canonical value | Reporting status |
|---|---:|---|
| Jeffreys \(s\)-exponent | 5.9354751272 | Illustration |
| Paired-bootstrap 95% CI | [5.9248953685, 5.9467826530] | Illustration |
| \(R^2\) | 0.9999901714 | Illustration |
| Product-affinity maximum spread | 0.0243306516 | Frozen PASS criterion |
| Product-affinity median spread | 0.0166975835 vs 0.015 | Frozen FAIL criterion |
| Equal-coefficient residual | \(6.8235\times10^{-16}\) | Frozen PASS criterion |
| Two-atom contrast relative error | \(7.0119\times10^{-15}\) | Frozen PASS criterion |
| Post-hoc \(h\)-exponent | 1.9431 | Post-hoc only |
| Post-hoc stress-grid \(s\)-exponents | 5.7592 to 5.9604 | Post-hoc only |
| Descriptive all-\(s\) order-14 exponent | 5.9342 | Post-hoc only |

Permitted summary: exact-mixture calculations in the stated \(q=4\)
Bernoulli--Gaussian hard core exhibit the predicted sixth-order orientation
information and approximate product-experiment collapse; the frozen
median-spread criterion missed narrowly, so the experiment remains HOLD.

## 6. Canonical reporting rules

1. Always report count/denominator before a rounded rate.
2. Use four decimals in tables when the denominator does not communicate the
   value more clearly; use one decimal percentage in prose only when paired
   with the exact fraction.
3. Do not average conditional metrics across incompatible denominators.
4. Do not use legacy Formal B2 safety `null` fields, the stale timeout label,
   or the legacy HOLD terminal status.
5. Do not insert D0--D2.3 development outcomes into any final numerator or
   denominator.
6. Preserve the original theorem-native HOLD status in every table, caption,
   macro, and abstract/introduction reference.
7. Treat representative Formal B2 cases as descriptive displays selected by
   the frozen lowest-seed-after-seal rule; never select a more favorable case.
