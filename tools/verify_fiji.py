"""Pixel-compare automated Fiji output against the hand-made 250514_B2_000/caiman.

Runs the macro on the real denoised movie into a scratch dir, then compares
every frame's pixels exactly and the display range to float32 precision.
READ-ONLY on the dataset. Usage: python tools/verify_fiji.py [--frames N]
"""
import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
import tifffile
from orgpipe import config, stage_fiji

DS = Path(r"Z:\Joseph\250514_B2_000")
MANUAL = DS / "caiman"
MANUAL_RANGE = (149.92518615722656, 887.4190063476562)  # recorded in the hand-made frames


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=0, help="0 = all 5400")
    args = ap.parse_args()

    cfg = config.load_config(DS)
    out = Path(tempfile.mkdtemp(prefix="orgpipe_fiji_verify_"))
    print("output ->", out)
    n = stage_fiji.split(DS / "denoised_movie_reconstructed.tif", out,
                         "denoised_movie_reconstructed", cfg, timeout_s=3600)
    print("macro wrote", n, "frames")

    with tifffile.TiffFile(str(out / "denoised_movie_reconstructed0000.tif")) as t:
        m = t.imagej_metadata
    drift = max(abs(m["min"] - MANUAL_RANGE[0]), abs(m["max"] - MANUAL_RANGE[1]))
    print("display range: (%.8f, %.8f)  drift vs manual: %.3g" % (m["min"], m["max"], drift))
    assert drift < 0.01, "auto_bc no longer replicates the manual Auto B&C"

    check = range(n) if args.frames == 0 else range(min(args.frames, n))
    bad = 0
    for i in check:
        name = "denoised_movie_reconstructed%04d.tif" % i
        a = tifffile.imread(str(out / name))
        b = tifffile.imread(str(MANUAL / name))
        if not np.array_equal(a, b):
            bad += 1
            print("MISMATCH:", name)
    print("compared %d frames, %d mismatches" % (len(check), bad))
    assert bad == 0
    print("VERIFY_FIJI: PASS")


if __name__ == "__main__":
    main()
