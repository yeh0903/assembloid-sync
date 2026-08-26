"""Fiji stage: split denoised BigTIFF into an auto-B&C'd image sequence.

Runs ImageJ in GUI mode (-macro without --headless): headless cannot open
float64/BigTIFF (Bio-Formats VerifyError). A window flashes; no interaction
is needed; success is verified by counting output files, not parsing stdout.
"""
import subprocess
import time
from pathlib import Path

from . import config, layout


def _fwd(p):
    return str(Path(p)).replace("\\", "/")


def split(src, outdir, prefix, cfg, timeout_s=None, poll_s=2.0):
    """Core splitter, targetable at any output dir (used by tools/verify_fiji.py).

    ImageJ's exit path is unreliable after a Bio-Formats import (the JVM can
    outlive System.exit), so completion is signalled by a sentinel file the
    macro writes after the save loop, and the process tree is then killed.
    """
    import tifffile
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    sentinel = outdir / "DONE_SENTINEL.txt"
    if sentinel.exists():
        sentinel.unlink()
    for stale in outdir.glob(prefix + "*.tif"):
        stale.unlink()
    with tifffile.TiffFile(str(src)) as t:
        n_src = len(t.pages)
    if timeout_s is None:
        timeout_s = 60 + 0.5 * n_src
    macro = config.REPO_ROOT / "macros" / "split_sequence.ijm"
    arg = "|".join([_fwd(src), _fwd(outdir), prefix,
                    cfg["fiji"]["mode"], str(cfg["fiji"]["saturated"])])
    imagej_exe = config.resolve_imagej(cfg)
    if imagej_exe is None:
        raise RuntimeError("ImageJ/Fiji not found - set fiji.imagej_exe in "
                           "config.local.json or the ASSEMBLOID_SYNC_IMAGEJ env var")
    proc = subprocess.Popen([str(imagej_exe), "-macro", str(macro), arg])
    try:
        deadline = time.monotonic() + timeout_s
        while not sentinel.exists():
            if proc.poll() is not None:
                break  # exited on its own; sentinel checked below
            if time.monotonic() >= deadline:
                raise RuntimeError("Fiji timed out after %ds (%s)" % (timeout_s, src))
            time.sleep(poll_s)
    finally:
        if proc.poll() is None:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           capture_output=True)
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                pass
    if not sentinel.exists():
        raise RuntimeError("Fiji ended without writing the completion sentinel (%s)" % src)
    sentinel.unlink()
    n_out = len(list(outdir.glob(prefix + "*.tif")))
    if n_out != n_src:
        raise RuntimeError("Fiji wrote %d frames, source has %d" % (n_out, n_src))
    return n_out


def run(ds, cfg):
    n = split(layout.denoised_tif(ds), layout.caiman_dir(ds), layout.SEQ_PREFIX, cfg)
    print("[fiji] %d frames -> %s" % (n, layout.caiman_dir(ds)))
