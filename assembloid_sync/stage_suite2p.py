"""suite2p stage: run_s2p on the caiman image sequence with settings_ver1.0.npy
plus exactly the decided overrides (fs from Experiment.xml, tau=1.0). Every
changed key is printed so no parameter moves silently."""
import numpy as np

from . import config as _config
from . import layout


def build_ops(ds, cfg, fs):
    """Returns (ops, db, diffs) - diffs maps every changed/added key to its value."""
    ops_path = _config.REPO_ROOT / cfg["suite2p"]["ops_file"]
    ops = np.load(str(ops_path), allow_pickle=True).item()
    baseline = dict(ops)
    ops["fs"] = float(fs)
    ops["tau"] = float(cfg["suite2p"]["tau"])
    for k, v in cfg["suite2p"].get("ops_overrides", {}).items():
        ops[k] = v
    cai = str(layout.caiman_dir(ds))
    db = {"data_path": [cai], "save_path0": cai}
    diffs = {k: ops[k] for k in ops if not np.array_equal(ops[k], baseline.get(k))}
    diffs.update(db)
    return ops, db, diffs


def run(ds, cfg):
    fs = _config.resolve_frame_rate(ds, cfg)
    ops, db, diffs = build_ops(ds, cfg, fs)
    print("[suite2p] ops diffs vs %s:" % cfg["suite2p"]["ops_file"])
    for k in sorted(diffs):
        print("    %-14s = %r" % (k, diffs[k]))
    s2p_out = layout.caiman_dir(ds) / "suite2p"
    if s2p_out.exists():
        import shutil
        print("[suite2p] removing stale output %s (run_s2p would silently reuse its binaries)" % s2p_out)
        if layout.is_curated(ds):
            print("[suite2p] WARNING: discarding human curation in %s" % s2p_out)
        marker = layout.curated_marker(ds)
        if marker.exists():
            marker.unlink()
            print("[suite2p] cleared curation marker (detection is being redone)")
        try:
            shutil.rmtree(str(s2p_out))
        except PermissionError:
            print("[suite2p] cannot remove %s - close the suite2p GUI if it has this dataset open" % s2p_out)
            raise
    try:
        import torch
        cuda = torch.cuda.is_available()
        print("[suite2p] torch %s cuda_available=%s" % (torch.__version__, cuda))
        if not cuda:
            print("[suite2p] " + "!" * 62)
            print("[suite2p] WARNING: Cellpose detection will run on the CPU.")
            print("[suite2p]   This is the slow path - seconds on a GPU versus hours on CPU.")
            print("[suite2p]   The environment files install the CPU build of torch by")
            print("[suite2p]   default, because the CUDA wheel is only on PyTorch's own")
            print("[suite2p]   index. To enable the GPU, see docs/SETUP.md section 5:")
            print("[suite2p]     pip install torch --index-url https://download.pytorch.org/whl/cu124")
            print("[suite2p]     python tools/patch_suite2p_gpu.py <env-name>")
            print("[suite2p] " + "!" * 62)
    except ImportError:
        pass
    from suite2p import run_s2p
    run_s2p(ops=ops, db=db)
    print("[suite2p] output -> %s" % layout.plane0(ds))


def launch_gui(ds):
    """Open the suite2p GUI with this dataset loaded. Blocks until closed."""
    from suite2p.gui import gui2p
    gui2p.run(str(layout.plane0(ds) / "stat.npy"))
