import json
from pathlib import Path
import pytest
from assembloid_sync import config


def test_load_defaults_only(tmp_path):
    cfg = config.load_config(tmp_path)  # no assembloid-sync.json in tmp_path
    assert cfg["roi"]["neuropil_r"] == 0.4
    assert cfg["suite2p"]["tau"] == 1.0
    assert cfg["denoise"]["decay_time"] == 1.0
    assert cfg["frame_rate"] is None


def test_dataset_override_deep_merge(tmp_path):
    (tmp_path / "assembloid-sync.json").write_text(
        json.dumps({"roi": {"amp_min_z": 3.5}, "frame_rate": 15.0}), encoding="utf-8")
    cfg = config.load_config(tmp_path)
    assert cfg["roi"]["amp_min_z"] == 3.5          # overridden
    assert cfg["roi"]["neuropil_r"] == 0.4          # untouched sibling survives
    assert cfg["frame_rate"] == 15.0


def test_resolve_dataset_bare_name_and_absolute():
    cfg = {"data_root": r"Z:\Joseph"}
    assert config.resolve_dataset("250528_B2_003", cfg) == Path(r"Z:\Joseph\250528_B2_003")
    assert config.resolve_dataset(r"D:\elsewhere\x", cfg) == Path(r"D:\elsewhere\x")


def test_frame_rate_from_xml(tmp_path):
    (tmp_path / "Experiment.xml").write_text(
        '<?xml version="1.0"?><ThorImageExperiment>'
        '<LSM name="ResonanceGalvo" frameRate="29.160" averageMode="0" averageNum="5" />'
        '</ThorImageExperiment>', encoding="utf-8")
    assert config.resolve_frame_rate(tmp_path, {"frame_rate": None}) == pytest.approx(29.160)


def test_frame_rate_config_wins(tmp_path):
    assert config.resolve_frame_rate(tmp_path, {"frame_rate": 15.0}) == 15.0


def test_frame_rate_missing_xml_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        config.resolve_frame_rate(tmp_path, {"frame_rate": None})


def test_frame_rate_zero_raises(tmp_path):
    with pytest.raises(ValueError):
        config.resolve_frame_rate(tmp_path, {"frame_rate": 0})


def test_frame_rate_zero_xml_raises(tmp_path):
    (tmp_path / "Experiment.xml").write_text(
        '<?xml version="1.0"?><ThorImageExperiment>'
        '<LSM frameRate="0" /></ThorImageExperiment>', encoding="utf-8")
    with pytest.raises(ValueError):
        config.resolve_frame_rate(tmp_path, {"frame_rate": None})


def test_malformed_dataset_json_names_file(tmp_path):
    (tmp_path / "assembloid-sync.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError, match="assembloid-sync.json"):
        config.load_config(tmp_path)


def test_resolve_data_root_env_var_wins(tmp_path, monkeypatch):
    monkeypatch.setenv(config.ENV_PREFIX + "DATA_ROOT", str(tmp_path))
    assert config.resolve_data_root({"data_root": r"Z:\other"}) == tmp_path


def test_resolve_data_root_falls_back_to_cwd(monkeypatch, tmp_path):
    monkeypatch.delenv(config.ENV_PREFIX + "DATA_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    assert config.resolve_data_root({}) == Path.cwd()


def test_resolve_imagej_env_var_wins(tmp_path, monkeypatch):
    monkeypatch.setenv(config.ENV_PREFIX + "IMAGEJ", str(tmp_path / "ij.exe"))
    assert config.resolve_imagej({}) == tmp_path / "ij.exe"


def test_local_config_isolated_in_tests(tmp_path):
    assert config.load_config(tmp_path)["data_root"] is None
