import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from orgpipe import entry


def _run(ds, cfg, smoke):
    from orgpipe import stage_fiji
    stage_fiji.run(ds, cfg, smoke)


if __name__ == "__main__":
    entry.main("fiji", _run)
