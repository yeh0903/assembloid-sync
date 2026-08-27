"""Figures shared by stage_roi and notebooks/ROI_analysis.ipynb.

Do NOT force a matplotlib backend here - the notebooks need inline display.
Headless batch runs set MPLBACKEND=Agg in bin/run_roi.py instead."""
import matplotlib.pyplot as plt
import numpy as np


def split_overlay(xy, labels, save_path, background=None, info=None):
    """ROI centroids coloured by organoid, over the anatomy when available.

    The background is what makes a wrong split obvious at a glance.
    """
    labels = np.asarray(labels)
    fig, ax = plt.subplots()
    if background is not None:
        lo, hi = np.percentile(background, [1, 99.5])
        ax.imshow(background, cmap="gray", vmin=lo, vmax=hi)
    else:
        ax.invert_yaxis()
    colors = ["#1b9e77" if l == 0 else "#d95f02" for l in labels]
    ax.scatter(xy[:, 0], xy[:, 1], c=colors, s=14, edgecolors="none")
    ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([])
    n0, n1 = int((labels == 0).sum()), int((labels == 1).sum())
    title = "Organoid A (upper) %d  |  Organoid B (lower) %d" % (n0, n1)
    if info is not None:
        title += "\nmethod=%s  density_dip=%.2f  cores=%d" % (
            info.get("method"), info.get("density_dip", float("nan")),
            info.get("n_density_cores", -1))
    ax.set_title(title)
    fig.savefig(save_path)
    plt.close(fig)


def corr_heatmap(corr, sep, save_path, dpi=1500):
    import seaborn as sns
    fig = plt.figure(figsize=(9, 8))
    sns.heatmap(corr, cmap="coolwarm", vmin=-1, vmax=1, square=True,
                xticklabels=False, yticklabels=False,
                cbar_kws={"label": "Pearson r"})
    plt.axhline(sep, color="w", lw=2)
    plt.axvline(sep, color="w", lw=2)
    plt.title("ROI-ROI correlation\nOrg-A first, Org-B second")
    plt.tight_layout()
    fig.savefig(save_path, dpi=dpi)
    plt.close(fig)


def amp_histograms(dfz):
    """Tuning aid (notebook cell 6): robust amplitude + P99 distributions."""
    import seaborn as sns
    amp = np.percentile(dfz, 98, axis=1) - np.percentile(dfz, 2, axis=1)
    peak = np.percentile(dfz, 99, axis=1)
    fig, ax = plt.subplots(1, 2, figsize=(10, 4))
    sns.histplot(amp, ax=ax[0], bins=50, kde=True, color="royalblue")
    ax[0].set_title("robust amp (P98-P02)"); ax[0].set_xlabel("z")
    ax[0].axvline(amp.mean(), c="k", ls="--")
    sns.histplot(peak, ax=ax[1], bins=50, kde=True, color="darkorange")
    ax[1].set_title("99th-percentile per ROI"); ax[1].set_xlabel("z")
    ax[1].axvline(peak.mean(), c="k", ls="--")
    plt.tight_layout()
    return fig


def trace_stack(dfz, order, window=slice(0, 2700), plot_n=500, offset=5):
    """Latency-sorted trace stack for one organoid (notebook cell 7)."""
    fig, ax = plt.subplots(figsize=(12, 8))
    for rank, rr in enumerate(order[:plot_n]):
        ax.plot(dfz[rr, window] + rank * offset, color="tab:blue", lw=0.6)
    ax.set_ylim(-offset, plot_n * offset)
    ax.set_yticks([])
    return fig
