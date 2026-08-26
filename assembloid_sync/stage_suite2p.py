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


def run(ds, cfg, smoke=False):
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
        try:
            shutil.rmtree(str(s2p_out))
        except PermissionError:
            print("[suite2p] cannot remove %s - close the suite2p GUI if it has this dataset open" % s2p_out)
            raise
    try:
        import torch
        print("[suite2p] torch %s cuda_available=%s" % (torch.__version__, torch.cuda.is_available()))
    except ImportError:
        pass
    from suite2p import run_s2p
    run_s2p(ops=ops, db=db)
    print("[suite2p] output -> %s" % layout.plane0(ds))


def launch_gui(ds):
    """Open the suite2p GUI with this dataset loaded. Blocks until closed."""
    from suite2p.gui import gui2p
    gui2p.run(str(layout.plane0(ds) / "stat.npy"))
