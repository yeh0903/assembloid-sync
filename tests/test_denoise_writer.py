import numpy as np
import pytest
import scipy.sparse as sp
import tifffile
from orgpipe.stage_denoise import write_denoised


class FakeEstimates:
    pass


class FakeCnm:
    pass


def _fake_cnm(T=17, H=8, W=9, K=4, nb=2, seed=0):
    rng = np.random.default_rng(seed)
    est = FakeEstimates()
    est.A = sp.csc_matrix(rng.random((H * W, K)).astype(np.float32))
    est.C = rng.random((K, T)).astype(np.float32)
    est.b = rng.random((H * W, nb)).astype(np.float32)
    est.f = rng.random((nb, T)).astype(np.float32)
    est.dims = (H, W)
    cnm = FakeCnm()
    cnm.estimates = est
    return cnm


@pytest.mark.parametrize("chunk", [5, 17, 20, 200])
def test_chunked_writer_matches_full_reconstruction(tmp_path, chunk):
    cnm = _fake_cnm()
    out = tmp_path / "den.tif"
    write_denoised(cnm, out, chunk=chunk)
    est = cnm.estimates
    T = est.C.shape[1]
    full = np.asarray(est.A @ est.C + est.b @ est.f)
    full = full.reshape(est.dims + (T,), order="F").transpose(2, 0, 1).astype(np.float32)
    written = tifffile.imread(str(out))
    assert written.dtype == np.float32
    assert written.shape == (T,) + est.dims
    np.testing.assert_array_equal(written, full)


def test_writer_float64_C_promotes_then_casts_once(tmp_path):
    cnm = _fake_cnm()
    cnm.estimates.C = cnm.estimates.C.astype(np.float64)
    out = tmp_path / "den64.tif"
    write_denoised(cnm, out, chunk=5)
    est = cnm.estimates
    T = est.C.shape[1]
    full = np.asarray(est.A @ est.C + est.b @ est.f)  # float64 compute
    full = full.reshape(est.dims + (T,), order="F").transpose(2, 0, 1).astype(np.float32)
    written = tifffile.imread(str(out))
    assert written.dtype == np.float32
    np.testing.assert_array_equal(written, full)
