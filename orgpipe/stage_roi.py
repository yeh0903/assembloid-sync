"""ROI stage: organoid split, dF/F z-scoring, correlation, corrSYN + IOSI.
Ports 250514_B2_000/ROI_analysis.ipynb cells 2/4/5/8/9/10/11; parameters come
from config (defaults = that notebook's values)."""
import json

import numpy as np
from scipy.stats import zscore

from . import layout
from .sync import calculate_inter_organoid_index, calculate_synchronicity_index, cross_corr  # noqa: F401


def load_plane0(ds):
    p0 = layout.plane0(ds)
    F = np.load(str(p0 / "F.npy"), allow_pickle=True)
    Fneu = np.load(str(p0 / "Fneu.npy"), allow_pickle=True)
    iscell = np.load(str(p0 / "iscell.npy"))[:, 0].astype(bool)
    stat = np.load(str(p0 / "stat.npy"), allow_pickle=True)
    return F[iscell], Fneu[iscell], stat[iscell]


def split_organoids(stat):
    """GMM + Mahalanobis split (notebook cell 4, verbatim logic).
    Returns ({0: idx_upper, 1: idx_lower}, xy, labels)."""
    import scipy.linalg as LA
    from sklearn.mixture import GaussianMixture

    xy = np.array([[s["med"][1], s["med"][0]] for s in stat])   # (x, y)
    gmm = GaussianMixture(2, covariance_type="full", n_init=10,
                          random_state=0).fit(xy)
    labels = gmm.predict(xy)
    means, covs = gmm.means_, gmm.covariances_
    inv0, inv1 = LA.inv(covs[0]), LA.inv(covs[1])

    def maha(p, mu, inv):
        d = p - mu
        return np.einsum("...i,ij,...j->...", d, inv, d)

    d0, d1 = maha(xy, means[0], inv0), maha(xy, means[1], inv1)
    labels = np.where((labels == 0) & (d1 < d0), 1,
                      np.where((labels == 1) & (d0 < d1), 0, labels))
    if xy[labels == 0, 1].mean() > xy[labels == 1, 1].mean():
        labels = 1 - labels                                     # label 0 = upper
    return {0: np.where(labels == 0)[0], 1: np.where(labels == 1)[0]}, xy, labels


def compute_dfz(F, Fneu, neuropil_r, baseline_pctl):
    Fcorr = F - neuropil_r * Fneu
    F0 = np.percentile(Fcorr, baseline_pctl, axis=1, keepdims=True)
    return zscore((Fcorr - F0) / F0, axis=1)


def select_good(dfz, roi, amp_min_z, burst_z, min_gap_fr):
    """Amplitude filter + first-burst latency ordering (notebook cell 5)."""
    amp = np.percentile(dfz[roi], 98, 1) - np.percentile(dfz[roi], 2, 1)
    good = roi[amp >= amp_min_z]
    lat = np.full(good.size, np.inf)
    for i, r in enumerate(good):
        above = np.where(dfz[r] > burst_z)[0]
        if above.size:
            first = above[0]
            for j in above[1:]:
                if j - first > min_gap_fr:
                    break
            lat[i] = first
    order = good[np.argsort(lat)]
    return good, lat, order


def _jsonable(d):
    out = {}
    for k, v in d.items():
        if isinstance(v, (bool, int, float, str)):
            out[k] = v
        elif isinstance(v, (np.bool_,)):
            out[k] = bool(v)
        elif isinstance(v, (np.integer, np.floating)):
            out[k] = v.item()
        elif isinstance(v, tuple):
            out[k] = list(v)
    return out


def run(ds, cfg, smoke=False):
    from . import plots

    r = cfg["roi"]
    F, Fneu, stat = load_plane0(ds)
    idx, xy, labels = split_organoids(stat)
    print("organoids: upper=%d lower=%d" % (idx[0].size, idx[1].size))
    plots.gmm_scatter(xy, labels, str(ds / "assembloid_demo.jpg"))

    dfz = compute_dfz(F, Fneu, r["neuropil_r"], r["baseline_pctl"])
    good, order = {}, {}
    for k in (0, 1):
        good[k], _, order[k] = select_good(dfz, idx[k], r["amp_min_z"],
                                           r["burst_z"], r["min_gap_fr"])
        print("organoid %d: %d/%d ROIs pass amp >= %s z"
              % (k, good[k].size, idx[k].size, r["amp_min_z"]))
    if good[0].size == 0 or good[1].size == 0:
        raise RuntimeError("an organoid has 0 surviving ROIs - tune amp_min_z "
                           "in %s/orgpipe.json" % ds)

    order_full = np.concatenate([good[0], good[1]])
    corr_full = np.corrcoef(dfz[order_full])

    # subsample: min of the two organoids (derived, not hand-set); seed as notebook
    sample_size = min(good[0].size, good[1].size)
    rng = np.random.default_rng(r["seed"])
    sample_A = rng.choice(good[0], size=sample_size, replace=False)
    sample_B = rng.choice(good[1], size=sample_size, replace=False)
    sampled = np.concatenate([sample_A, sample_B])
    corr_sampled = np.corrcoef(dfz[sampled])
    plots.corr_heatmap(corr_sampled, sample_A.size, str(ds / "correlation.tif"))

    print("=" * 60)
    sca = calculate_synchronicity_index(
        corr_sampled, fluorescence_data=dfz[sampled],
        n_surrogates=r["n_surrogates"],
        min_cluster_size=r["sca_min_cluster_size"],
        significance_threshold=r["sca_significance_threshold"], verbose=True)
    print("=" * 60)
    iosi = calculate_inter_organoid_index(
        dfz[good[0]], dfz[good[1]], n_surrogates=r["n_surrogates"], verbose=True)

    np.save(str(ds / "corr_full.npy"), corr_full)
    np.save(str(ds / "corr_sampled.npy"), corr_sampled)
    results = {
        "n_upper": int(idx[0].size), "n_lower": int(idx[1].size),
        "n_good_upper": int(good[0].size), "n_good_lower": int(good[1].size),
        "sample_size": int(sample_size),
        "sca": _jsonable(sca), "iosi": _jsonable(iosi),
    }
    (ds / "roi_results.json").write_text(json.dumps(results, indent=2),
                                         encoding="utf-8")
    print("\n[roi] corrSYN = %.4f   IOSI = %.4f (z=%.2f, %s)"
          % (results["sca"].get("corrSYN", float("nan")), iosi["IOSI"],
             iosi["z_score"], "significant" if iosi["significant"] else "n.s."))
    return {"dfz": dfz, "idx": idx, "good": good, "order": order,
            "corr_full": corr_full, "corr_sampled": corr_sampled,
            "sca": sca, "iosi": iosi}
