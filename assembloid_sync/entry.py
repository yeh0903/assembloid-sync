"""Shared main() for bin/run_<stage>.py entry scripts. Tier 1: stdlib only.

Usage in an entry script:

    from assembloid_sync import entry
    def _run(ds, cfg):   # heavy imports happen inside _run
        ...
    entry.main("denoise", _run)
"""
import argparse
import sys
import traceback

from . import config, layout, state


def main(stage_name, run_fn):
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    cfg = config.load_config(args.dataset)
    ds = config.resolve_dataset(args.dataset, cfg)
    cfg = config.load_config(ds)  # reload so <ds>/assembloid-sync.json is honoured

    if layout.is_b3(ds):
        print("REFUSING: %s is a B3 dataset (out of scope)" % ds)
        sys.exit(2)
    if not ds.is_dir():
        print("ERROR: dataset folder does not exist: %s" % ds)
        sys.exit(2)
    if not args.force and state.is_done(ds, stage_name):
        print("[%s] already done for %s - skipping (--force to redo)" % (stage_name, ds.name))
        sys.exit(0)

    state.mark(ds, stage_name, "running")
    removed = state.clear_downstream(ds, stage_name)
    if removed:
        print("[%s] cleared downstream state: %s (their inputs are changing)" % (stage_name, ", ".join(removed)))
    try:
        run_fn(ds, cfg)
    except Exception:
        tb = traceback.format_exc()
        state.mark(ds, stage_name, "failed", error=tb)
        print(tb, file=sys.stderr)
        sys.exit(1)
    state.mark(ds, stage_name, "done")
    print("[%s] done: %s" % (stage_name, ds.name))
