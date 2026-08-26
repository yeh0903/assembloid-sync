import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("MPLBACKEND", "Agg")  # headless batch; notebooks stay inline
from assembloid_sync import entry


def _run(ds, cfg):
    from assembloid_sync import stage_roi
    stage_roi.run(ds, cfg)


if __name__ == "__main__":
    entry.main("roi", _run)
