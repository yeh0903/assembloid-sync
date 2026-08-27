# Methods

What the analysis stage actually computes, in enough detail to check the science
against — every formula, where it lives in code, and (§6) the audit behind the one
deliberate deviation from the reference implementation.

Implementation: `assembloid_sync/stage_roi.py` (dF/F, filtering, orchestration),
`assembloid_sync/_sca_reference.py` (corrSYN / SCA), `assembloid_sync/sync.py` (IOSI).
Parameter defaults below are from `defaults.json`'s `roi` block.

---

## 1. Overview

```
F, Fneu, stat  (suite2p output, curated ROIs only)
     │                              │
     │ fluorescence                 │ spatial: ROI centroid ("med")
     ▼                              ▼
   dFz = zscore(ΔF/F)      split_organoids(stat)   ← GMM + Mahalanobis, position only
     │                              │
     └──────────────┬───────────────┘
                     ▼
      select_good(dFz, idx[k])  per organoid k     activity filter + latency order
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
 balanced subsample          full surviving sets
 min(n_A,n_B) per organoid   good[0], good[1]
        │                         │
        ▼                         ▼
  corr_sampled (M×M)        cross_corr(A, B)  (M_A×M_B)
        │                         │
        ▼                         ▼
   corrSYN  (§4, SCA)         IOSI  (§5)
```

Two numbers come out: **corrSYN**, network synchronization within the imaged
population (eigenvalue structure of the ROI-ROI correlation matrix), and **IOSI**,
coupling *between* the two organoids specifically. Both are gated against an
AAFT-surrogate null so a reported value means "more synchronized than phase-randomized
chance," not just "correlated."

**Design constraint: the organoid split must be spatial only.** `split_organoids`
(`assembloid_sync/stage_roi.py`) clusters ROI centroid position — `stat[i]["med"]`,
pixel (x, y) — with a 2-component Gaussian mixture, then reassigns boundary cases by
Mahalanobis distance. It never sees `F`, `Fneu`, or `dFz`. This has to hold: if the
split used activity or correlation instead, IOSI would be measuring coupling between
two groups that were *defined* by their activity relationship, which makes "are the
organoids synchronized" circular — the answer would be baked into the grouping. Keeping
the split purely spatial is what makes IOSI an empirical question instead of a
tautology.

corrSYN uses a **balanced subsample** (equal ROI counts drawn from each organoid) so
the larger organoid can't dominate the eigen-spectrum. IOSI doesn't need that — it's
already a rectangular between-group block, not a joint eigendecomposition — so it runs
on the **full** surviving ROI set per organoid instead.

---

## 2. ΔF/F and normalization

```
Fcorr = F − r · Fneu                    neuropil subtraction, r = neuropil_r = 0.4
F0    = P8(Fcorr)   (per ROI, over time)     baseline = 8th percentile, baseline_pctl = 8
ΔF/F  = (Fcorr − F0) / F0
dFz   = zscore(ΔF/F, axis=time)         per-ROI z-score
```

`Fcorr` removes out-of-focus / neuropil contamination using a fixed 0.4 coefficient.
`F0` uses a low percentile rather than a minimum so a single noise trough doesn't set
the baseline. The z-score is what makes ROIs *comparable*: raw ΔF/F amplitude depends
on indicator expression level, which varies cell to cell and carries no biological
signal. Every downstream threshold (`amp_min_z`, `burst_z`) is expressed in z-units
uniformly across ROIs; without normalizing first, a threshold that correctly separates
active from quiet cells in a dim ROI would misclassify every cell in a bright one.
(Pearson correlation is already scale-invariant, so z-scoring doesn't change
`corr_full`/`corr_sampled` themselves — it matters for every threshold-based step, not
the correlation computation.)

---

## 3. Activity filter

```
amp_i = P98(dFz_i) − P02(dFz_i)          robust per-ROI amplitude
keep i if amp_i ≥ amp_min_z              default amp_min_z = 3.75
```

P98−P02 instead of max−min so one outlier frame can't pass an otherwise-quiet ROI.

Surviving ROIs are then ordered by **first-burst latency** — the first frame where
`dFz > burst_z` (default `burst_z = 2.5`); ROIs that never cross it sort last. This
ordering only feeds the trace plots (it's what makes propagation visible across the
junction); it has no effect on the correlation matrices or on corrSYN/IOSI.

---

## 4. corrSYN — Synchronization Cluster Analysis

Follows the SCA method of Li et al. (network synchrony via correlation-matrix
eigenstructure) as implemented in FluoroSNNAP (Patel et al. 2015). This pipeline
implements FluoroSNNAP's **`'correlation'`** SCA variant (`sca_type == 2`);
FluoroSNNAP's own default is **`'phase'`** (`params.sca_type = 1`), which this
pipeline does not implement.

**Observed spectrum.** Eigendecompose the balanced-subsample correlation matrix
(M = 2 × `min(n_good_A, n_good_B)`), then explicitly sort both eigenvalues and
eigenvectors descending (§7 explains why this sort is required, not decorative).

**Surrogate null.** Generate `n_surrogates` (default 200) surrogate copies of every
trace in the subsample (`aaft_surrogate`, §6), take each surrogate set's correlation
matrix, eigendecompose and sort it the same way, and collect the per-rank mean
λ̄_sur and standard deviation SD_sur (`ddof=1`) across all `n_surrogates` runs.

**Significance index**, per eigenvalue rank i:

```
SI_i = (λ_i − λ̄_sur,i) / (M − λ̄_sur,i)     if  λ_i > λ̄_sur,i + k · SD_sur,i
     = 0                                     otherwise
```

k = `sca_significance_threshold`, default 2.0 (a 2-SD gate). **corrSYN = SI_0** — how
far the *leading* eigenvalue exceeds its surrogate null, normalized so 1.0 would mean
perfect synchrony (all M ROIs in one mode).

**Clusters.** Eigenvector i is a candidate cluster if `SI_i ≥ 0.01`. Its participation
index over ROIs is

```
PI_k[j] = λ_k · v_k[j]²
```

Each ROI is assigned to `argmax_k PI_k[j]`, giving a size per candidate cluster. A
cluster is kept only if

```
cluster_size > min_cluster_size          default min_cluster_size = 3 → keeps size ≥ 4
```

— strict `>`, matching FluoroSNNAP's MATLAB `nnz(Cluster_size>params.sca_size)` (see
§7; this was previously `>=` and has been corrected). The reported membership list for
a kept cluster is a *separate* threshold, `{j : PI_k[j] ≥ 0.05}` — not the same set as
the argmax assignment used for sizing, so a ROI can be the argmax-assigned member of a
cluster without appearing in that cluster's reported contents if its own participation
is below 0.05. This is the original algorithm's behavior, carried through unchanged.

**The cluster-size filter affects `n_clusters` / `assembly_contents` only.** `corrSYN`
is `SI[0]`, computed earlier in the function and untouched by cluster filtering.

---

## 5. IOSI — Inter-Organoid Synchronization Index

IOSI is **introduced in this pipeline**, adapted from corrSYN's surrogate-normalized
pattern (observed statistic vs. an AAFT null, gated at a SD threshold, normalized to a
0–1-ish scale) applied to a between-organoid cross-correlation block instead of a
within-population eigendecomposition. Treat the novelty claim as unverified against the
broader literature — it has not been exhaustively checked against prior art, and an
equivalent construction may already exist under another name.

**Cross-correlation.** `cross_corr(A, B)` is the Pearson r between every ROI in
organoid A and every ROI in organoid B (`assembloid_sync/sync.py`) — an M_A×M_B block
containing *only* between-organoid pairs, so within-organoid synchrony cannot leak in.

**Observed statistic.** SVD of the cross-correlation block; its dominant singular value
normalized by √(M_A·M_B):

```
S_obs = σ_0(cross_corr(A, B)) / √(M_A · M_B)
```

**Surrogate null.** `n_surrogates` AAFT-surrogates of organoid **B only** (A held
fixed) — destroying A↔B timing while preserving each B trace's own spectrum — giving a
distribution of the same statistic, S̄_sur / SD_sur.

**Gate and normalize:**

```
IOSI = (S_obs − S̄_sur) / (1 − S̄_sur)     if S_obs > S̄_sur + 2·SD_sur, else 0
z    = (S_obs − S̄_sur) / SD_sur
p    = 1 − Φ(z)                            upper-tail normal
significant = z > 2
```

The 2-SD gate here is a hardcoded constant in `sync.py`, not a config parameter (unlike
corrSYN's `sca_significance_threshold`). A parallel, unused-for-gating statistic
(`IOSI_mean` / `z_score_mean`) is computed the same way from the plain mean of
`cross_corr_AB` instead of its dominant singular value, and is carried in the results
dict for reference but is not what's reported as `IOSI`.

---

## 6. Surrogate data

This is the section the numerical audit backs.

**Textbook AAFT**, in three steps: (1) rank-map the data onto a matched Gaussian
("Gaussianize"), (2) phase-randomize *that* Gaussian proxy's Fourier phases, (3)
invert, then re-impose the original amplitude distribution by rank substitution.
FluoroSNNAP's `AAFTsur.m` is a faithful implementation of this. **iAAFT** iterates
steps 2–3 to jointly satisfy both the power spectrum and the amplitude distribution.

**`aaft_surrogate` here is not a port of `AAFTsur.m`.** It skips the Gaussianization
step entirely: phases come from the FFT of a *fresh, independent* Gaussian
(`np.random.randn`), applied directly to the real data's own Fourier amplitudes, then
inverse-FFT'd and rank-matched back onto the original sorted values (that last
rank-substitution step is identical to textbook AAFT).

```
sorted_original  = sort(data)
phases           = angle(fft(randn(len(data))))     ← independent Gaussian, not data-derived
surrogate_fft     = |fft(data)| · exp(i · phases)
surrogate         = real(ifft(surrogate_fft))
final_surrogate   = sorted_original[rankdata(surrogate)]
```

**Why it's still valid.** The FFT of a real-valued Gaussian sequence has phases that
are, up to floating-point error (the ifft's imaginary part is ~1e-16 of signal scale),
exactly Hermitian-symmetric — uniform random and antisymmetric about the Nyquist
frequency, which is precisely the property phase-randomization needs to keep the
inverse transform real. The final amplitude distribution is exactly preserved (it's a
straight rank substitution against the sorted original data, unchanged from textbook
AAFT). What's given up is deriving the randomized phases from a Gaussianized version of
*this* data's own spectrum; instead they come from an unrelated Gaussian draw every
call.

**Measured on 50 real traces:**

| variant | spectrum relative L2 error | ACF correlation |
|---|---|---|
| shipped (`aaft_surrogate`) | 25.2% | 0.9800 |
| textbook AAFT | 31.9% | 0.9541 |
| iAAFT | 0.2% | 0.9896 |

The shipped variant *outperforms* textbook AAFT on both measures on these non-Gaussian
calcium traces — skipping Gaussianization removes a distortion source rather than
adding one (confirmed on synthetic data, where the mechanism is unambiguous).

**Effect on results, real data:**

| | shipped | textbook AAFT | iAAFT |
|---|---|---|---|
| corrSYN z | 97.5 | 93.8 | 105.5 |
| IOSI z | 86.7 | 86.4 | 82.6 |

The surrogate null's mean shifts modestly and monotonically in the theoretically
expected direction across the sweep. For IOSI, the null dominant-mode strength goes
0.1624 → 0.1680 → 0.1734 (shipped → textbook → iAAFT); for corrSYN, the null largest
eigenvalue goes 10.94 → 11.62 → 12.32. Both rise as spectral preservation improves,
which is what theory predicts: a surrogate with more realistic autocorrelation has
fewer effective independent samples and so shows more coincidental correlation under
the null. But the shift is only ~13%, so the choice of surrogate method is not what
drives the reported synchrony results.

**Cost.** iAAFT's iterative refinement costs ≈2.4 h per dataset at `n_surrogates=200`,
versus a couple of minutes for the shipped or textbook variant — roughly **25–60×**
slower.

**Decision: keep `aaft_surrogate` as shipped.** It's valid (amplitude distribution
exactly preserved, phases exactly Hermitian-symmetric), it empirically outperforms the
textbook variant it simplifies on this project's data, and the ~13% null-mean shift
across all three variants doesn't change which recordings come out significant, at
25–60× the runtime cost for iAAFT. Caveat: that 13% is an average effect — on a dataset
whose z-score sits right at the 2-SD gate, the choice of surrogate could plausibly flip
significance, so a marginal result is worth rerunning with iAAFT as a check. iAAFT is a
drop-in upgrade if that's ever needed: `aaft_surrogate` in `_sca_reference.py` is the
only function either metric calls for surrogate generation.

Surrogate-data method: Theiler et al. 1992. Iterative refinement (iAAFT):
Schreiber & Schmitz 1996.

---

## 7. Fidelity to the MATLAB original

A line-by-line audit against FluoroSNNAP's `SCA.m` / `AAFTsur.m` found:

- **The SCA port is faithful** — every formula matches line-for-line — with one
  exception: cluster-size filtering used `>=` where `SCA.m` uses strict `>`
  (`nnz(Cluster_size>params.sca_size)`). **Fixed** (§4); a `min_cluster_size` of 3 now
  keeps clusters of 4 or more, matching MATLAB, instead of 3 or more.
- **`aaft_surrogate` is not a port of `AAFTsur.m`** — see §6 for what it does instead
  and why it was kept.
- **`SCA.m` itself has an internal inconsistency the port does not inherit.** It mixes
  MATLAB's N−1 (sample) `zscore` convention with a `1/T` correlation formula elsewhere,
  so `SCA.m`'s own correlation-matrix diagonal comes out to 0.99981, not 1.0. The
  Python port is exactly self-consistent (verified on real data, maximum diagonal
  deviation 1.1e-15 — floating-point noise). The scale factor cancels out of `SI` (it
  appears in both the observed and surrogate eigenvalues identically), so it doesn't
  bias corrSYN — but the port's raw eigenvalues are not bit-for-bit comparable to
  `SCA.m`'s.
- **The explicit descending eigenvalue sort is load-bearing.** `scipy.linalg.eig`
  (a general, non-symmetric eigensolver — used even though correlation matrices here
  are always symmetric) gives no ordering guarantee on its output; the audit verified
  this empirically, finding unordered results in 30/30 trials on random symmetric
  matrices. Both the observed spectrum and every one of the `n_surrogates` surrogate
  spectra are explicitly sorted descending before use. Without that sort, `SI_i` would
  pair arbitrary eigenvalue ranks against each other instead of "i-th largest vs.
  i-th largest," silently corrupting every `SI` value — this is a correctness
  requirement, not a style choice.

---

## References

- Synchronization Cluster Analysis (method) — Li et al. *J Neurophysiol*
  2007;98:3341–3348, and *Biophysical Journal* 2010;99:1733–1741.
- FluoroSNNAP (software implementing SCA, and the reference this pipeline's SCA and
  AAFT code trace to) — Patel TP, Man K, Firestein BL, Meaney DF. Automated
  quantification of neuronal networks and single-cell calcium dynamics using calcium
  imaging. *Journal of Neuroscience Methods* 2015;243:26–38.
- AAFT surrogate data — Theiler J, Eubank S, Longtin A, Galdrikian B, Farmer JD.
  Testing for nonlinearity in time series: the method of surrogate data. *Physica D*
  1992;58:77–94.
- iAAFT — Schreiber T, Schmitz A. Improved surrogate data for nonlinearity tests.
  *Physical Review Letters* 1996;77:635–638.

See also: [README.md](../README.md) for the pipeline overview and the rest of the
reference list (imaging/segmentation tools, indicator kinetics).
