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


def _split_gmm(xy):
    """2-component Gaussian mixture + Mahalanobis reassignment (notebook cell 4)."""
    import scipy.linalg as LA
    from sklearn.mixture import GaussianMixture

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
    return labels


def _split_density(xy, eps=40.0, min_samples=4):
    """Two largest DBSCAN cores as seeds; every ROI joins its nearest seed.

    Handles fields of view where the bodies are spatially separated - including
    a small fragment that a likelihood-based fit would absorb rather than
    isolate. Returns None when fewer than two cores exist (a single fused mass),
    so the caller can fall back.
    """
    from sklearn.cluster import DBSCAN
    lab = DBSCAN(eps=eps, min_samples=min_samples).fit(xy).labels_
    sizes = [(int((lab == c).sum()), c) for c in set(lab) if c != -1]
    if len(sizes) < 2:
        return None
    sizes.sort(reverse=True)
    seeds = [xy[lab == sizes[0][1]], xy[lab == sizes[1][1]]]
    d0 = np.min(np.linalg.norm(xy[:, None, :] - seeds[0][None], axis=2), axis=1)
    d1 = np.min(np.linalg.norm(xy[:, None, :] - seeds[1][None], axis=2), axis=1)
    return (d1 < d0).astype(int)


def _split_axis(xy, axis="x", threshold=None):
    """Straight cut along x or y - the explicit override for a field of view
    where no automatic method gets it right. Threshold defaults to the median."""
    col = 0 if axis == "x" else 1
    v = xy[:, col]
    if threshold is None:
        threshold = float(np.median(v))
    return (v >= threshold).astype(int)


def split_dip(xy, labels):
    """Density minimum between the two groups along their separating axis.

    0.0 means a genuinely empty gap between the bodies; values near 1 mean one
    continuous mass with a line drawn through it. NOTE: a high value is normal
    and expected for fused assembloids, which have no gap by construction - this
    is a diagnostic to look at, not a pass/fail test.
    """
    m0, m1 = xy[labels == 0].mean(0), xy[labels == 1].mean(0)
    ax = m1 - m0
    norm = np.linalg.norm(ax)
    if norm == 0:
        return 1.0
    proj = xy @ (ax / norm)
    hist, edges = np.histogram(proj, bins=40)
    c0, c1 = proj[labels == 0].mean(), proj[labels == 1].mean()
    i0 = int(np.searchsorted(edges, min(c0, c1)))
    i1 = int(np.searchsorted(edges, max(c0, c1)))
    between = hist[i0:i1]
    if not len(between):
        return 1.0
    edge = max(hist[max(i0 - 1, 0)], hist[min(i1, len(hist) - 1)], 1)
    return float(between.min() / edge)


def split_organoids(stat, cfg=None):
    """Assign ROIs to two organoids from their centroids.

    Spatial only, never functional: clustering on activity would make the
    synchrony measurement circular. Returns (idx, xy, labels, info).
    """
    xy = np.array([[s["med"][1], s["med"][0]] for s in stat])   # (x, y)
    spec = (cfg or {}).get("roi", {}).get("split", {})
    requested_method = spec.get("method", "gmm")
    method = requested_method

    if method == "gmm":
        labels = _split_gmm(xy)
    elif method == "density":
        labels = _split_density(xy, spec.get("eps", 40.0))
        if labels is None:
            print("[roi] split: density method found fewer than two cores in "
                  "this field of view - falling back to gmm")
            labels = _split_gmm(xy)
            method = "gmm"
    elif method == "axis":
        labels = _split_axis(xy, spec.get("axis", "x"), spec.get("threshold"))
    else:
        raise ValueError(
            "unknown roi.split.method %r - must be one of: gmm, density, axis"
            % (requested_method,))

    if xy[labels == 0, 1].mean() > xy[labels == 1, 1].mean():
        labels = 1 - labels                                     # label 0 = upper

    idx = {0: np.where(labels == 0)[0], 1: np.where(labels == 1)[0]}

    try:
        from sklearn.cluster import DBSCAN
        core_labels = DBSCAN(eps=40.0, min_samples=4).fit(xy).labels_
        n_density_cores = len(set(core_labels) - {-1})
    except Exception:
        n_density_cores = -1

    info = {
        "method": method,
        "requested_method": requested_method,
        "n_upper": int(idx[0].size),
        "n_lower": int(idx[1].size),
        "minority_fraction": float(min(idx[0].size, idx[1].size)) / float(len(labels)),
        "density_dip": split_dip(xy, labels),
        "n_density_cores": n_density_cores,
    }
    return idx, xy, labels, info


def load_anatomy(ds):
    """suite2p's mean image, for showing the split against real morphology."""
    try:
        ops = np.load(str(layout.plane0(ds) / "ops.npy"), allow_pickle=True).item()
        img = ops.get("meanImg")
        return None if img is None else np.asarray(img)
    except Exception:
        return None


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
            # NOTE: this inner loop is dead by design (breaks without effect) - ported verbatim from the notebook; do not "fix" (changes nothing, but parity is pinned by test)
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


def run(ds, cfg):
    from . import plots

    r = cfg["roi"]
    F, Fneu, stat = load_plane0(ds)
    idx, xy, labels, info = split_organoids(stat, cfg)
    print("[roi] split: method=%s  A=%d B=%d  density_dip=%.2f  cores=%d"
          % (info["method"], info["n_upper"], info["n_lower"],
             info["density_dip"], info["n_density_cores"]))
    anatomy = load_anatomy(ds)
    plots.split_overlay(xy, labels, str(ds / "assembloid_demo.jpg"),
                        background=anatomy, info=info)

    dfz = compute_dfz(F, Fneu, r["neuropil_r"], r["baseline_pctl"])
    good, order = {}, {}
    for k in (0, 1):
        good[k], _, order[k] = select_good(dfz, idx[k], r["amp_min_z"],
                                           r["burst_z"], r["min_gap_fr"])
        print("organoid %d: %d/%d ROIs pass amp >= %s z"
              % (k, good[k].size, idx[k].size, r["amp_min_z"]))
    if good[0].size == 0 or good[1].size == 0:
        raise RuntimeError("an organoid has 0 surviving ROIs - tune amp_min_z "
                           "in %s/assembloid-sync.json" % ds)

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
        "split": info,
        "sca": _jsonable(sca), "iosi": _jsonable(iosi),
    }
    for k in ("cluster_sizes", "SI"):
        if k in sca and hasattr(sca[k], "tolist"):
            results["sca"][k] = sca[k].tolist()
    (ds / "roi_results.json").write_text(json.dumps(results, indent=2),
                                         encoding="utf-8")
    print("\n[roi] corrSYN = %.4f   IOSI = %.4f (z=%.2f, %s)"
          % (results["sca"].get("corrSYN", float("nan")), iosi["IOSI"],
             iosi["z_score"], "significant" if iosi["significant"] else "n.s."))
    return {"dfz": dfz, "idx": idx, "good": good, "order": order,
            "corr_full": corr_full, "corr_sampled": corr_sampled,
            "sca": sca, "iosi": iosi}
