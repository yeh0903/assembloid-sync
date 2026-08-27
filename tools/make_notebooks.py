"""Generate notebooks/denoise.ipynb and notebooks/ROI_analysis.ipynb.
Single source of truth for the interactive notebooks; re-run after editing."""
import nbformat as nbf
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "notebooks"
OUT.mkdir(exist_ok=True)

BOOT = '''\
import os, sys
from pathlib import Path

# Locate the repo from the notebook's working directory (works anywhere).
for _c in (Path.cwd(), *Path.cwd().parents):
    if (_c / "assembloid_sync" / "__init__.py").exists():
        sys.path.insert(0, str(_c)); break
else:
    raise SystemExit("Run this notebook from inside the repo, or add it to sys.path manually")

# Point this at your dataset folder (or set ASSEMBLOID_SYNC_DATASET):
DATASET = os.environ.get("ASSEMBLOID_SYNC_DATASET", "")
if not DATASET:
    raise SystemExit("Set DATASET above, or the ASSEMBLOID_SYNC_DATASET environment variable")

from assembloid_sync import config, layout
ds = Path(DATASET)
cfg = config.load_config(ds)
print("dataset:", ds.name, "| frame rate:", config.resolve_frame_rate(ds, cfg))'''


def nb(cells, path):
    n = nbf.v4.new_notebook()
    n.cells = [nbf.v4.new_code_cell(c, id="cell-%d" % i) for i, c in enumerate(cells)]
    nbf.write(n, str(path))
    print("wrote", path)


nb([
    BOOT,
    """\
# --- run CNMF-E (identical to the batch stage) ---
import os
temp = layout.caiman_temp(ds); temp.mkdir(parents=True, exist_ok=True)
os.environ["CAIMAN_TEMP"] = str(temp)
from assembloid_sync import stage_denoise
cnm = stage_denoise.fit(ds, cfg)""",
    """\
# --- inspect components (the old notebook's cell 3, interactive-only) ---
import matplotlib.pyplot as plt
import caiman as cm
# first 1000 frames is plenty for a correlation-image preview; if this recording
# is shorter than that, narrow the range below.
movie = cm.load(str(layout.raw_tif(ds)), subindices=range(0, 1000))
corr_img = movie.local_correlations(swap_dim=False)
if cnm.estimates.idx_components is not None and len(cnm.estimates.idx_components):
    cnm.estimates.plot_contours(img=corr_img, idx=cnm.estimates.idx_components)
plt.show()
cnm.estimates.view_components(img=corr_img)""",
    """\
# --- save the denoised movie (chunked float32) ---
stage_denoise.write_denoised(cnm, layout.denoised_tif(ds), chunk=cfg["denoise"]["chunk_size"])
print("saved", layout.denoised_tif(ds))""",
], OUT / "denoise.ipynb")

nb([
    BOOT,
    """\
# --- load + organoid split ---
from assembloid_sync import stage_roi, plots
import matplotlib.pyplot as plt
F, Fneu, stat = stage_roi.load_plane0(ds)
idx, xy, labels, info = stage_roi.split_organoids(stat, cfg)
anatomy = stage_roi.load_anatomy(ds)
plots.split_overlay(xy, labels, str(ds / "assembloid_demo.jpg"), background=anatomy, info=info)
print({0: idx[0].size, 1: idx[1].size}, info)""",
    """\
# --- dF/F z-scores + TUNING: look at these histograms, then set amp_min_z /
# burst_z in <dataset>/assembloid-sync.json, then re-run the FIRST cell and this one ---
r = cfg["roi"]
dfz = stage_roi.compute_dfz(F, Fneu, r["neuropil_r"], r["baseline_pctl"])
fig = plots.amp_histograms(dfz); plt.show()""",
    """\
# --- filter + latency-sorted traces ---
import numpy as np
good, order = {}, {}
for k in (0, 1):
    good[k], _, order[k] = stage_roi.select_good(dfz, idx[k], r["amp_min_z"],
                                                 r["burst_z"], r["min_gap_fr"])
    print("organoid", k, ":", good[k].size, "kept")
    fig = plots.trace_stack(dfz, order[k]); plt.show()""",
    """\
# --- full analysis (same code path as `assembloid-sync analyze`) ---
bundle = stage_roi.run(ds, cfg)""",
], OUT / "ROI_analysis.ipynb")
