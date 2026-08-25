import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from orgpipe import entry, layout


def _run(ds, cfg, smoke):
    temp = layout.caiman_temp(ds)
    temp.mkdir(parents=True, exist_ok=True)
    os.environ["CAIMAN_TEMP"] = str(temp)
    from orgpipe import stage_denoise
    stage_denoise.run(ds, cfg, smoke)


if __name__ == "__main__":
    entry.main("denoise", _run)
