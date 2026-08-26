import numpy as np
from assembloid_sync import config
from assembloid_sync.stage_suite2p import build_ops


def _cfg():
    return {
        "suite2p": {"ops_file": "settings/suite2p_ops.npy", "tau": 1.0, "ops_overrides": {}},
    }


def test_build_ops_only_permitted_diffs(tmp_path):
    ops, db, diffs = build_ops(tmp_path, _cfg(), fs=29.16)
    baseline = np.load(str(config.REPO_ROOT / "settings" / "suite2p_ops.npy"),
                       allow_pickle=True).item()
    changed = {k for k in ops if not np.array_equal(ops[k], baseline.get(k))}
    assert changed == {"fs", "tau"}
    assert ops["fs"] == 29.16 and ops["tau"] == 1.0
    assert db["data_path"] == [str(tmp_path / "caiman")]
    assert db["save_path0"] == str(tmp_path / "caiman")
    assert set(diffs) == {"fs", "tau", "data_path", "save_path0"}


def test_explicit_override_flows_through(tmp_path):
    cfg = _cfg()
    cfg["suite2p"]["ops_overrides"] = {"diameter": 12}
    ops, db, diffs = build_ops(tmp_path, cfg, fs=29.16)
    assert ops["diameter"] == 12
    assert "diameter" in diffs
