import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from orgpipe import entry


def _run(ds, cfg, smoke):
    from orgpipe import stage_suite2p
    stage_suite2p.run(ds, cfg, smoke)


if __name__ == "__main__":   # Windows spawn re-executes this module in every
    if "--gui" in sys.argv:  # multiprocessing worker; never dispatch on import
        sys.argv.remove("--gui")
        from orgpipe import config as _c
        from orgpipe import stage_suite2p
        cfg = _c.load_config(sys.argv[1])
        ds = _c.resolve_dataset(sys.argv[1], cfg)
        stage_suite2p.launch_gui(ds)
    else:
        entry.main("suite2p", _run)
