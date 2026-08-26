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


def curated_marker(ds):
    return state_dir(ds) / "curated.json"


def is_curated(ds, min_gap_s=2.0):
    """True when a human has curated this dataset's cells.

    Detected either by the marker written when the curation GUI closes, or by
    iscell.npy having been rewritten well after suite2p wrote F.npy (which also
    covers curating outside this tool). The marker matters because suite2p's GUI
    only rewrites iscell.npy when a cell is actually flipped - reviewing the cells
    and agreeing with the classifier leaves no trace otherwise.
    """
    if curated_marker(ds).exists():
        return True
    f = plane0(ds) / "F.npy"
    ic = plane0(ds) / "iscell.npy"
    if not f.exists() or not ic.exists():
        return False
    return ic.stat().st_mtime >= f.stat().st_mtime + min_gap_s
