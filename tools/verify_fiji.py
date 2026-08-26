"""Pixel-compare automated Fiji output against a hand-made <dataset>/caiman reference.

Runs the macro on the real denoised movie into a scratch dir, then compares
every frame's pixels exactly and (optionally) the display range to float32
precision. READ-ONLY on the dataset.
Usage: python tools/verify_fiji.py <dataset> [--frames N] [--expect-range MIN MAX]
"""
import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
import tifffile
from assembloid_sync import config, stage_fiji

# recorded display range from the hand-made reference for 250514_B2_000;
# pass to --expect-range to check a dataset's drift against it
MANUAL_RANGE = (149.92518615722656, 887.4190063476562)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", help="dataset folder holding both "
                    "denoised_movie_reconstructed.tif and a hand-made caiman/ to compare against")
    ap.add_argument("--frames", type=int, default=0, help="0 = all 5400")
    ap.add_argument("--expect-range", nargs=2, type=float, default=None, metavar=("MIN", "MAX"),
                    help="assert the auto-B&C display range matches this pair within 0.01 "
                         "(e.g. MANUAL_RANGE above); omit to just print the observed range")
    args = ap.parse_args()

    DS = Path(args.dataset)
    MANUAL = DS / "caiman"

    cfg = config.load_config(DS)
    out = Path(tempfile.mkdtemp(prefix="assembloid_sync_fiji_verify_"))
    print("output ->", out)
    n = stage_fiji.split(DS / "denoised_movie_reconstructed.tif", out,
                         "denoised_movie_reconstructed", cfg, timeout_s=3600)
    print("macro wrote", n, "frames")

    with tifffile.TiffFile(str(out / "denoised_movie_reconstructed0000.tif")) as t:
        m = t.imagej_metadata
    if args.expect_range is not None:
        drift = max(abs(m["min"] - args.expect_range[0]), abs(m["max"] - args.expect_range[1]))
        print("display range: (%.8f, %.8f)  drift vs expected: %.3g" % (m["min"], m["max"], drift))
        assert drift < 0.01, "auto_bc no longer replicates the expected Auto B&C range"
    else:
        print("display range: (%.8f, %.8f)" % (m["min"], m["max"]))

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
