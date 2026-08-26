"""Path conventions for a dataset folder. Tier 1: stdlib only."""
from pathlib import Path

RAW_TIF_NAME = "Image_scan_1_region_0_0.tif"
SEQ_PREFIX = "denoised_movie_reconstructed"
DATASET_CONFIG_NAME = "assembloid-sync.json"


def raw_tif(ds):
    return Path(ds) / RAW_TIF_NAME


def experiment_xml(ds):
    return Path(ds) / "Experiment.xml"


def denoised_tif(ds):
    return Path(ds) / "denoised_movie_reconstructed.tif"


def caiman_dir(ds):
    return Path(ds) / "caiman"


def plane0(ds):
    return caiman_dir(ds) / "suite2p" / "plane0"


def state_dir(ds):
    return Path(ds) / ".assembloid-sync"


def state_path(ds):
    return state_dir(ds) / "state.json"


def caiman_temp(ds):
    return state_dir(ds) / "caiman_temp"


def logs_dir(ds):
    return state_dir(ds) / "logs"


def is_b3(ds):
    return "_b3_" in Path(ds).name.lower()


def is_curated(ds, min_gap_s=2.0):
    """True when iscell.npy was rewritten after suite2p finished.

    run_s2p writes iscell.npy in the same second as F.npy; human curation in
    the GUI rewrites it later. mtime(iscell) >= mtime(F) + min_gap_s therefore
    means a person has been there.
    """
    f = plane0(ds) / "F.npy"
    ic = plane0(ds) / "iscell.npy"
    if not f.exists() or not ic.exists():
        return False
    return ic.stat().st_mtime >= f.stat().st_mtime + min_gap_s
