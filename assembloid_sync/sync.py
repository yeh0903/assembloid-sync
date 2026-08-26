"""Synchronization metrics. IOSI is the reference notebook's cell 11 with the
two O(M_A*M_B) corrcoef loops replaced by one matmul (identical values; the
unit test pins cross_corr against the loop). AAFT surrogates are kept verbatim
via _sca_reference - unseeded np.random, exactly as the notebook runs them."""
import numpy as np
from scipy import stats

from ._sca_reference import aaft_surrogate, calculate_synchronicity_index  # noqa: F401


def cross_corr(A, B):
    """Pearson r between every row of A and every row of B: (M_A, M_B)."""
    T = A.shape[1]
    Az = (A - A.mean(1, keepdims=True)) / A.std(1, keepdims=True)
    Bz = (B - B.mean(1, keepdims=True)) / B.std(1, keepdims=True)
    return (Az @ Bz.T) / T


def calculate_inter_organoid_index(fluorescence_A, fluorescence_B, n_surrogates=20,
                                   verbose=True):
    """Inter-Organoid Synchronization Index (IOSI). Port of the reference
    notebook; docstring trimmed, logic unchanged apart from vectorization."""
    M_A, T = fluorescence_A.shape
    M_B = fluorescence_B.shape[0]
    if verbose:
        print("Calculating Inter-Organoid Synchronization Index...")
        print("Organoid A: %d neurons\nOrganoid B: %d neurons\nTimepoints: %d"
              % (M_A, M_B, T))

    cross_corr_AB = cross_corr(fluorescence_A, fluorescence_B)

    observed_mean = np.mean(cross_corr_AB)
    U, S, Vt = np.linalg.svd(cross_corr_AB, full_matrices=False)
    observed_singular = S[0] / np.sqrt(M_A * M_B)
    observed_frobenius = np.linalg.norm(cross_corr_AB, "fro") / np.sqrt(M_A * M_B)

    surrogate_means = np.zeros(n_surrogates)
    surrogate_singulars = np.zeros(n_surrogates)
    surrogate_frobenius = np.zeros(n_surrogates)
    if verbose:
        print("Generating %d surrogates for significance testing..." % n_surrogates)
    for n in range(n_surrogates):
        if verbose and (n + 1) % 5 == 0:
            print("  Surrogate %d/%d" % (n + 1, n_surrogates))
        F_B_surrogate = np.empty_like(fluorescence_B)
        for i in range(M_B):
            F_B_surrogate[i, :] = aaft_surrogate(fluorescence_B[i, :])
        cc_surr = cross_corr(fluorescence_A, F_B_surrogate)
        surrogate_means[n] = np.mean(cc_surr)
        _, S_s, _ = np.linalg.svd(cc_surr, full_matrices=False)
        surrogate_singulars[n] = S_s[0] / np.sqrt(M_A * M_B)
        surrogate_frobenius[n] = np.linalg.norm(cc_surr, "fro") / np.sqrt(M_A * M_B)

    mean_surr = np.mean(surrogate_means)
    std_surr = np.std(surrogate_means, ddof=1)
    singular_surr = np.mean(surrogate_singulars)
    singular_std = np.std(surrogate_singulars, ddof=1)

    if observed_mean > (mean_surr + 2 * std_surr):
        IOSI_mean = (observed_mean - mean_surr) / (1.0 - mean_surr)
    else:
        IOSI_mean = 0.0
    if observed_singular > (singular_surr + 2 * singular_std):
        IOSI_dominant = (observed_singular - singular_surr) / (1.0 - singular_surr)
    else:
        IOSI_dominant = 0.0
    z_score_mean = (observed_mean - mean_surr) / std_surr if std_surr > 0 else 0
    z_score_singular = ((observed_singular - singular_surr) / singular_std
                        if singular_std > 0 else 0)

    A_coupling_strength = np.mean(np.abs(cross_corr_AB), axis=1)
    B_coupling_strength = np.mean(np.abs(cross_corr_AB), axis=0)
    flat_idx = np.argmax(np.abs(cross_corr_AB))
    max_A_idx, max_B_idx = np.unravel_index(flat_idx, cross_corr_AB.shape)

    results = {
        "IOSI": IOSI_dominant,
        "IOSI_mean": IOSI_mean,
        "observed_mean_corr": observed_mean,
        "observed_dominant_mode": observed_singular,
        "observed_frobenius": observed_frobenius,
        "surrogate_mean": mean_surr,
        "surrogate_std": std_surr,
        "surrogate_dominant": singular_surr,
        "surrogate_dominant_std": singular_std,
        "z_score": z_score_singular,
        "z_score_mean": z_score_mean,
        "p_value": 1 - stats.norm.cdf(z_score_singular),
        "significant": z_score_singular > 2.0,
        "cross_corr_matrix": cross_corr_AB,
        "A_coupling_strength": A_coupling_strength,
        "B_coupling_strength": B_coupling_strength,
        "strongest_pair": (int(max_A_idx), int(max_B_idx),
                           float(cross_corr_AB[max_A_idx, max_B_idx])),
        "surrogate_means_dist": surrogate_means,
        "surrogate_singulars_dist": surrogate_singulars,
    }
    if verbose:
        print("IOSI (dominant mode): %.4f   z=%.2f   significant: %s"
              % (results["IOSI"], results["z_score"],
                 "YES" if results["significant"] else "NO"))
    return results
