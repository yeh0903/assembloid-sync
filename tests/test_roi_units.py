import numpy as np
from assembloid_sync.stage_roi import compute_dfz, cross_corr, select_good, split_organoids


def test_cross_corr_matches_corrcoef_loop():
    rng = np.random.default_rng(1)
    A, B = rng.random((7, 400)), rng.random((5, 400))
    got = cross_corr(A, B)
    want = np.empty((7, 5))
    for i in range(7):
        for j in range(5):
            want[i, j] = np.corrcoef(A[i], B[j])[0, 1]
    np.testing.assert_allclose(got, want, atol=1e-10)


def test_split_organoids_two_blobs():
    rng = np.random.default_rng(0)
    upper = rng.normal([100, 100], 5, (30, 2))   # (x, y): smaller y = upper
    lower = rng.normal([300, 400], 5, (40, 2))
    stat = [{"med": (y, x)} for x, y in np.vstack([upper, lower])]  # med is (row, col)
    idx, xy, labels = split_organoids(stat)
    assert set(idx) == {0, 1}
    assert len(idx[0]) == 30 and len(idx[1]) == 40   # label 0 = upper cluster


def test_compute_dfz_shape_and_zscore():
    rng = np.random.default_rng(2)
    F, Fneu = rng.random((6, 500)) * 100 + 50, rng.random((6, 500)) * 10
    dfz = compute_dfz(F, Fneu, neuropil_r=0.4, baseline_pctl=8)
    assert dfz.shape == (6, 500)
    np.testing.assert_allclose(dfz.mean(axis=1), 0, atol=1e-8)
    np.testing.assert_allclose(dfz.std(axis=1), 1, atol=1e-6)


def test_select_good_orders_by_latency():
    # ROI 0: quiet. ROI 1: bursts late. ROI 2: bursts early.
    dfz = np.zeros((3, 300))
    dfz[1, 200:210] = 10.0
    dfz[2, 50:60] = 10.0
    good, latency, order = select_good(dfz, np.array([0, 1, 2]),
                                       amp_min_z=5.0, burst_z=2.5, min_gap_fr=3)
    assert list(good) == [1, 2]          # ROI 0 fails the amplitude filter
    assert list(order) == [2, 1]         # earliest burst first


def test_sca_reference_importable_and_runs_small():
    from assembloid_sync._sca_reference import calculate_synchronicity_index
    rng = np.random.default_rng(3)
    traces = rng.random((10, 300))
    corr = np.corrcoef(traces)
    res = calculate_synchronicity_index(corr, traces, n_surrogates=3, verbose=False)
    assert "corrSYN" in res


def test_iosi_runs_and_reports_keys():
    from assembloid_sync.sync import calculate_inter_organoid_index
    rng = np.random.default_rng(4)
    res = calculate_inter_organoid_index(rng.random((6, 300)), rng.random((5, 300)),
                                         n_surrogates=3, verbose=False)
    for k in ("IOSI", "IOSI_mean", "z_score", "p_value", "significant"):
        assert k in res
