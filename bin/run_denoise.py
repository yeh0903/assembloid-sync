import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from assembloid_sync import entry, layout


def _run(ds, cfg):
    temp = layout.caiman_temp(ds, cfg)
    temp.mkdir(parents=True, exist_ok=True)
    os.environ["CAIMAN_TEMP"] = str(temp)
    print("[denoise] memmap scratch -> %s" % temp)
    from assembloid_sync import stage_denoise
    stage_denoise.run(ds, cfg)


if __name__ == "__main__":
    entry.main("denoise", _run)
