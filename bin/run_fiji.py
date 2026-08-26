import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from assembloid_sync import entry


def _run(ds, cfg):
    from assembloid_sync import stage_fiji
    stage_fiji.run(ds, cfg)


if __name__ == "__main__":
    entry.main("fiji", _run)
