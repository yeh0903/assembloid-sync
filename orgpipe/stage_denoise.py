"""Denoise stage: CNMF-E (identical params to denoise.ipynb cells 0-2) plus a
chunked float32 writer (the notebook's commented cell-5 approach, promoted).

Memory: the old cell-4 path materialised the full movie (~25-30 GB peak, saved
float64). Chunked float32 peaks at ~210 MB/chunk and halves the file; float32
is lossless because A, C, b, f are float32 (spec: 'Deliberate divergences' and
'Fidelity' sections).
"""
import shutil

import numpy as np

from . import config as _config
from . import layout


def write_denoised(cnm, out_path, chunk=200):
    import tifffile
    est = cnm.estimates
    A, C, b, f = est.A, est.C, est.b, est.f
    dims = est.dims
    T = C.shape[1]
    with tifffile.TiffWriter(str(out_path), bigtiff=True) as tif:
        for t0 in range(0, T, chunk):
            t1 = min(t0 + chunk, T)
            block = np.asarray(A @ C[:, t0:t1] + b @ f[:, t0:t1])
            block = block.reshape(dims + (t1 - t0,), order="F")
            block = block.transpose(2, 0, 1).astype(np.float32)
            tif.write(block, contiguous=True, metadata=None)
    return T


def make_smoke_input(ds, n_frames=300):
    import tifffile
    out = layout.orgpipe_dir(ds) / "smoke_input.tif"
    layout.orgpipe_dir(ds).mkdir(parents=True, exist_ok=True)
    with tifffile.TiffFile(str(layout.raw_tif(ds))) as t:
        n = min(n_frames, len(t.pages))
        frames = np.stack([t.pages[i].asarray() for i in range(n)])
    tifffile.imwrite(str(out), frames)
    return out


def fit(ds, cfg, smoke=False):
    """Run CNMF-E exactly as denoise.ipynb cells 0-2. Returns the fitted cnm.

    Caller (bin/run_denoise.py) must set CAIMAN_TEMP before this import runs.
    """
    import caiman as cm
    from caiman.source_extraction.cnmf import cnmf as cnmf_mod
    from caiman.source_extraction.cnmf.params import CNMFParams

    fname = make_smoke_input(ds) if smoke else layout.raw_tif(ds)
    fr = _config.resolve_frame_rate(ds, cfg)
    d = cfg["denoise"]
    params_dict = {
        "fnames": [str(fname)],
        "fr": fr,
        "decay_time": d["decay_time"],
        "p": d["p"],
        "gSig": tuple(d["gSig"]),
        "rf": d["rf"],
        "stride": d["stride"],
        "K": d["K"],
        "ssub": d["ssub"],
        "tsub": d["tsub"],
        "method_init": d["method_init"],
        "merge_thr": d["merge_thr"],
        "min_SNR": d["min_SNR"],
        "rval_thr": d["rval_thr"],
        "use_cnn": d["use_cnn"],
        "cnn_thr": d["cnn_thr"],
        "min_fitness_raw": d["min_fitness_raw"],
        "nb": d["nb"],
        "ring_size_factor": d["ring_size_factor"],
        "motion_correct": False,
    }
    opts = CNMFParams(params_dict=params_dict)
    c, dview, n_processes = cm.cluster.setup_cluster(
        backend="local", n_processes=None, single_thread=False)
    try:
        cnm = cnmf_mod.CNMF(n_processes=n_processes, params=opts, dview=dview)
        cnm.fit_file(motion_correct=False)
    finally:
        cm.stop_server(dview=dview)  # the notebook never shut its cluster down
    return cnm


def run(ds, cfg, smoke=False):
    cnm = fit(ds, cfg, smoke)
    T = write_denoised(cnm, layout.denoised_tif(ds), chunk=cfg["denoise"]["chunk_size"])
    print("[denoise] wrote %d frames -> %s" % (T, layout.denoised_tif(ds)))
    if not cfg.get("keep_temp", False):
        shutil.rmtree(layout.caiman_temp(ds), ignore_errors=True)
        print("[denoise] cleaned caiman_temp")
