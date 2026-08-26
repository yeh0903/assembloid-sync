"""Checks run before committing to multi-hour stages. Tier 1: stdlib only."""
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from . import config, layout

MIN_FREE_BYTES = 20 * 1024 ** 3  # memmap 5.7 + denoised 5.7 + sequence 5.4 + bin 2.8 GB


def check(ds, cfg, needs_space=True):
    if not Path(ds).is_dir():
        return ["dataset folder does not exist: %s" % ds]
    errs = []
    if not layout.raw_tif(ds, cfg).exists():
        errs.append("missing raw tif: %s" % layout.raw_tif(ds, cfg))
    try:
        ET.parse(str(layout.experiment_xml(ds, cfg)))
    except Exception as e:
        errs.append("Experiment.xml unreadable: %s" % e)
    imagej_exe = config.resolve_imagej(cfg)
    if imagej_exe is None:
        errs.append("ImageJ/Fiji not found - set fiji.imagej_exe in "
                    "config.local.json or the ASSEMBLOID_SYNC_IMAGEJ env var")
    elif not imagej_exe.exists():
        errs.append("ImageJ not found: %s" % imagej_exe)
    if not (config.REPO_ROOT / cfg["suite2p"]["ops_file"]).exists():
        errs.append("ops file missing: %s" % cfg["suite2p"]["ops_file"])
    if needs_space:
        free = shutil.disk_usage(str(ds)).free
        if free < MIN_FREE_BYTES:
            errs.append("only %.1f GB free on dataset drive; need 20" % (free / 1024 ** 3))
    return errs


def check_env(env_name):
    """One conda-run round trip; returns error string or None."""
    r = subprocess.run(["conda", "run", "-n", env_name, "python", "-c", "pass"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return "conda env %r not runnable: %s" % (env_name, r.stderr.strip()[-200:])
    return None
