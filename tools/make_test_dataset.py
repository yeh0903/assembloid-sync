"""Build a small test dataset by truncating a real one.

The result is an ordinary dataset folder, so it runs through the normal
pipeline with no special flags and cannot overwrite real output.

    python tools/make_test_dataset.py <source-dataset> <destination> [--frames 300]
"""
import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
import tifffile
from assembloid_sync import config, layout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", help="dataset folder holding the raw tif and Experiment.xml")
    ap.add_argument("dest", help="folder to create")
    ap.add_argument("--frames", type=int, default=300)
    args = ap.parse_args()

    src, dst = Path(args.source), Path(args.dest)
    cfg = config.load_config(src)
    raw = layout.raw_tif(src, cfg)
    xml = layout.experiment_xml(src, cfg)
    for p in (raw, xml):
        if not p.exists():
            sys.exit("missing %s" % p)
    dst.mkdir(parents=True, exist_ok=True)

    with tifffile.TiffFile(str(raw)) as t:
        total = len(t.pages)
        n = min(args.frames, total)
        frames = np.stack([t.pages[i].asarray() for i in range(n)])
    tifffile.imwrite(str(layout.raw_tif(dst, cfg)), frames)
    shutil.copy2(str(xml), str(layout.experiment_xml(dst, cfg)))
    print("wrote %d of %d frames -> %s" % (n, total, dst))
    print("run it with:  assembloid-sync run %s" % dst)


if __name__ == "__main__":
    main()
