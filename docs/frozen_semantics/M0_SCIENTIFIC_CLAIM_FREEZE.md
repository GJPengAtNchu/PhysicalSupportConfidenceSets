# M0-A Scientific Claim Freeze

Status: **APPROVED AND FROZEN**  
Phase: M0-A complete; M0-B authorized  
Target narrative: IEEE Transactions on Signal Processing  
Evidence cutoff: 2026-08-06

This document freezes the scientific story before any venue conversion or
manuscript rewriting. Nothing here authorizes M0-B, a new experiment, or a
change to the immutable evidence.

## 1. Proposed title

**Physical-Support Confidence Sets for Highly Coherent Dictionaries**

This title follows the author's established IEEE/SIAM pattern: one central
inferential object and one signal-processing setting, expressed as a short
nominal phrase without a subtitle. The standard term ``confidence sets''
states the paper's output directly, while ``highly coherent dictionaries''
names the operational difficulty in familiar sparse-representation language.
Honesty, collision geometry, minimax resolution, and the finite-bank
controller remain central contributions in the abstract and contribution
statement. The title change does not broaden the frozen claim: the fixed-shell
theory, finite-bank computational scope, and synthetic validation boundaries
below remain unchanged.

## 2. Central problem

A sparse solver can select a precise coordinate support in one fitted
dictionary even when the calibration sample remains compatible with other
dictionaries whose corresponding atoms point in different physical
directions. Near a collision of coherent atoms, coordinate identifiability in
the fitted frame is therefore not the same as physical-atom identifiability.
The paper asks what resolution of the active physical components is jointly
justified by the latent calibration data and the replicated test signal.

## 3. Target estimand

The target is the active set of physical rays, not the numbered coordinates
of one fitted dictionary. Rays are defined modulo sign, and supports are
transported jointly under child-atom relabeling. The statistical answer is a
set-valued confidence correspondence over marked physical-ray sets.

The exact theory concerns a supplied, fixed-dimensional, fixed-shell local
collision experiment with a coherent child block and a separated anchor. The
operational experiments concern frozen finite candidate banks. The two levels
share a validity principle but are not asserted to be the same computational
object.

## 4. Central paper claim

> Near a collision in a learned dictionary, honest support inference must
> adapt its physical resolution to three distinct information bottlenecks:
> locating the active block, distinguishing supports within that block, and
> calibrating the physical orientation of its children. In the supplied
> fixed-shell Gaussian experiment, an exact cross-dictionary confidence
> correspondence is training-conditionally honest and, once the two test-side
> gates are open, attains the minimax physical-resolution scale
> \(s\wedge(\sqrt N s^2)^{-1}\). A separately constructed finite-bank
> controller realizes the same retain-or-abstain validity contract on frozen
> candidate libraries; exact finite-bank audits validate its global behavior
> and its use in one fixed synthetic persistent-plus-optional sensor-response
> application. No continuous-space computational guarantee or real-data
> validation is claimed.

## 5. Frozen contribution structure

### C1. Invariant target and exact honest benchmark

Define physical-ray support modulo sign and dictionary relabeling, and
construct a cross-dictionary confidence correspondence that retains every
training-compatible dictionary and test-compatible sparse representation. It
has two-level training-conditional/test coverage and a marginal coverage
corollary in the fixed-dimensional unknown-\(p\) model.

Claim type: theorem and inferential formulation.

### C2. Collision information geometry and minimax resolution

Separate the parent, support, and dictionary gates. Establish the
orientation-information scale \(I_D=Ns^6\), the test-side gates
\(I_G^{(r)}\) and \(I_S\), and matching fixed-shell upper and lower physical
resolution

\[
s\wedge\frac{1}{\sqrt N\,s^2}
\]

once the test-side gates are open. Show that the dictionary bottleneck
persists under extensive oracle assistance. Characterize when a profiled test
secant adds orientation information and when equal coefficients leave the
test law invariant.

Claim type: theorem and information limit.

### C3. Certified finite-bank realization of the validity contract

Introduce an active endpoint-bracketing (AEB) controller for a frozen finite
candidate bank. At every queried prefix, the controller maintains a witnessed
lower set of admissible explanations and an upper possible set containing all
not-yet-rejected explanations. It emits a fine, sector-safe, or ambiguous
label only when the finite-bank bounds certify that label; otherwise it
abstains.

This is an exact finite-bank claim. It is not a claim that AEB computes or
outer-approximates the full continuous confidence correspondence, and it is
not a polynomial-time complexity theorem.

Claim type: computational method and finite-bank certificate.

### C4. Confirmatory global and application evidence

Use B1.1 to validate the frozen **global** AEB controller across three
information conditions, three operating profiles, and predeclared query
budgets. Separately use Formal B2 to validate a frozen
**application-specific local-map policy** in one synthetic four-region
persistent-plus-optional sensor-response library, including exact-oracle
comparison, plug-in false precision, safety, coverage, utility, and query
cost.

B1.1 does not authorize local-map claims; Formal B2 supplies the separate,
narrow local application evidence. Neither experiment validates the
continuous theoretical profile.

Claim type: empirical finite-bank validation.

## 6. Frozen theorem claims

1. Observable second- and fourth-order training invariants identify the
   relevant quotient coordinates under the stated fixed-law or
   Bernoulli--Gaussian conditions.
2. Residual orientation enters the latent training law at cubic order in
   \(s\), producing nuisance-profiled information of order \(s^6\).
3. The exact correspondence has training-conditional test coverage at least
   \(1-\alpha_T\) with probability at least \(1-\alpha_D\) over training,
   uniformly on the fixed-shell unknown-\(p\) class.
4. Its physical diameter has order-one, order-\(s\), and
   order-\(s\wedge(\sqrt N s^2)^{-1}\) regimes controlled by the parent,
   support, and dictionary gates.
5. The three lower pairs make these coarsenings unavoidable; after the first
   two gates open, the fixed-shell rate is minimax-optimal up to constants.
6. The general-\(r\) task result is local efficient information. A finite
   matching train-test rate is claimed only on the separately declared
   one-dimensional orientation orbit.
7. For two active atoms, nonzero amplitude contrast opens the profiled test
   secant, whereas the equal-coefficient slice is exactly test-invariant for
   every number of replicates.

## 7. Frozen computational claims

1. AEB is executable on a finite bank and maintains lower/upper candidate-set
   certificates at every prefix.
2. Its positive labels are finite-bank safe relative to those certified
   bounds; incomplete certificates produce ABSTAIN.
3. Query savings are empirical properties of the frozen banks and budgets,
   not a worst-case complexity rate.
4. B1.1 evaluates the frozen global `AEB_FINE_SEEKING` policy. Formal B2
   evaluates the frozen application policy
   `PERSISTENT_OPTIONAL_AEB_MAP_DUAL_PROPOSAL_WITNESS`. They share certificate
   logic but must not be described as one identical policy.
5. Offline exact-oracle and high-precision audit work is not deployment
   latency.

## 8. Frozen empirical claims

### Theorem-native illustration

The original experiment remains `HOLD_NUMERICAL_EVIDENCE`. It may illustrate
the predicted sixth-order geometry and task invariance, with its frozen
median-spread near-miss disclosed. Post-hoc robustness may be described only
as `R0_HOLD_BUT_GEOMETRY_ROBUST`.

### B1.1 global validation

The final status is
`PASS_ARA_B11_ORACLE_AUDIT_COMPLETED_AND_B1_VALIDATED`. The evidence covers 18
complete finite-bank cases and 54 sealed global-controller traces. It supports
zero observed structural unsafe decisions, zero trace-prefix bound
violations, exact finite-bank agreement at full budget, and the frozen
risk-resolution-yield metrics. It does not establish exact selective-risk
control or continuous completeness.

### Formal B2 application validation

The final status is
`PASS_ARA_B2_FORMAL_FRESH_APPLICATION_VALIDATED`. The evidence covers 15 fresh
datasets in one frozen synthetic four-region application, 14 completed exact
oracles, and one administrative empty profile. The B2-F0.3 safety overlay is
authoritative for safety, P05, and terminal status. Formal B2 supports the
frozen safety, coverage, utility, plug-in false-precision, and query-cost
claims only in this application bank.

## 9. Application interpretation

The synthetic response library contains 12 atoms across four spatial regions,
72 dictionary states, and support patterns AB, ABC, and ABD, yielding 216
candidate explanations. The frozen design uses \(N=4096\) calibration samples,
\(T=192\) deployment replicates, response width \(h=0.085\), a primary cap of
162/216 queries, and `tau_D_beta=1.00` for D-absence claims.

- A: persistent isolated component; exact and controller output is often FINE.
- B: persistent coherent component; the justified output is SECTOR_SAFE.
- C: weak optional component; presence/absence uncertainty is reported as
  SUPPORT_AMBIGUOUS when both remain possible.
- D: detectable optional interferer; absence means only
  ABSENT_ABOVE_BETA_MIN under the frozen threshold.
- ABSTAIN: the available query budget did not complete a positive certificate.
- EMPTY_PROFILE: the complete finite bank is incompatible with the data; no
  physical map is returned.

These labels are operational summaries of a frozen finite bank, not new
theorems about arbitrary sources or continuous physical space.

## 10. Empty-profile semantics

The mathematical correspondence uses a fixed fallback singleton only to make
the random set total and measurable. The observable empty-profile flag removes
all substantive interpretation from that fallback.

The operational interface therefore reports `EMPTY_PROFILE` with a null
physical map. P05 (`FORMAL_WEAK_C_PRESENT_P05`) is an administrative empty
profile, not a timeout and not evidence that all regions are absent. It is
excluded from truth-relative utility denominators and completed-oracle bound
validation, while its Stage-A query count and all-trace possible-set audit
remain reportable.

## 11. Required non-claims

- No real-data validation.
- No DOA, localization, spectral-unmixing, or source-separation transfer
  theorem.
- No arbitrary-support, arbitrary-cardinality, arbitrary weak-source, or
  unrestricted absence claim.
- No unknown-shell adaptation or general hierarchy discovery.
- No claim that the observed child block is a regular simplex; the regular
  simplex is a coordinate frame and a least-favourable centered core, while
  the fitted local chart permits anisotropy through an unrestricted invertible
  map subject to bounded conditioning.
- No separate fixed-known-law minimax theorem beyond the explicitly stated
  training-geometry branch.
- No continuous-space computational completeness.
- No polynomial-time or high-dimensional upper algorithm.
- No claim that the finite candidate bank outer-covers the continuous model.
- No claim that B1.1 empirical zero errors imply exact selective-risk control.
- No claim that every dataset yields a physical map.
- No interpretation of the theoretical fallback singleton as evidence.
- No use of D0--D2.3 development rates in confirmatory numerators or
  denominators.
- No relabeling of the theorem-native numerical HOLD as a confirmatory pass.
- No conversion of B1.1 global evidence into per-region/local-map evidence.
- No pooled marginal-to-training-conditional coverage leap for the empirical
  controller.

## 12. M0-A decisions proposed for approval

1. Use the revised title in Section 1.
2. Keep one compact theorem-native three-gate figure in the main paper with an
   explicit HOLD disclosure; move post-hoc robustness to the supplement.
3. Give B1.1 one main validation subsection and Formal B2 one main application
   subsection; detailed audit tables move to the supplement.
4. Present AEB as a finite-bank realization of the computational validity
   contract, not as a numerical implementation of the continuous exact
   correspondence.
5. Keep every headline theorem statement in the main paper, with complete
   proofs and technical expansions in the supplement.

Approval of this document freezes scientific wording and authorizes only the
construction of a deterministic canonical paper export in M0-B.
