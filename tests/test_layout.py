import os
import time
from pathlib import Path
from assembloid_sync import layout


def test_paths(tmp_path):
    ds = tmp_path / "250528_B2_003"
    assert layout.raw_tif(ds).name == "Image_scan_1_region_0_0.tif"
    assert layout.denoised_tif(ds).name == "denoised_movie_reconstructed.tif"
    assert layout.caiman_dir(ds) == ds / "caiman"
    assert layout.plane0(ds) == ds / "caiman" / "suite2p" / "plane0"
    assert layout.state_path(ds) == ds / ".assembloid-sync" / "state.json"
    assert layout.caiman_temp(ds) == ds / ".assembloid-sync" / "caiman_temp"
    assert layout.logs_dir(ds) == ds / ".assembloid-sync" / "logs"


def test_is_b3():
    assert layout.is_b3(Path(r"Z:\Joseph\250605_B3_000"))
    assert not layout.is_b3(Path(r"Z:\Joseph\250528_B2_003"))
    assert not layout.is_b3(Path(r"Z:\Joseph\241029_ILDT8_00"))
    assert layout.is_b3(Path(r"Z:\Joseph\250605_b3_000"))


def test_is_curated(tmp_path):
    ds = tmp_path / "d"
    p0 = layout.plane0(ds)
    p0.mkdir(parents=True)
    f, ic = p0 / "F.npy", p0 / "iscell.npy"
    f.write_bytes(b"x")
    ic.write_bytes(b"x")
    now = time.time()
    os.utime(f, (now, now))
    os.utime(ic, (now, now))            # same second -> not curated
    assert not layout.is_curated(ds)
    os.utime(ic, (now + 60, now + 60))  # rewritten later -> curated
    assert layout.is_curated(ds)


def test_is_curated_missing(tmp_path):
    assert not layout.is_curated(tmp_path / "nonexistent")
