"""Configuration: defaults.json merged with config.local.json merged with
<dataset>/assembloid-sync.json. Tier 1: stdlib only."""
import json
import os
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from . import layout

REPO_ROOT = Path(__file__).resolve().parent.parent

ENV_PREFIX = "ASSEMBLOID_SYNC_"
LOCAL_CONFIG_NAME = "config.local.json"

# common Fiji/ImageJ install locations, checked in order
_IMAGEJ_CANDIDATES = [
    r"C:\Program Files\fiji-win64\Fiji.app\ImageJ-win64.exe",
    r"C:\Program Files\Fiji.app\ImageJ-win64.exe",
    r"C:\Fiji.app\ImageJ-win64.exe",
    "/Applications/Fiji.app/Contents/MacOS/ImageJ-macosx",
    "/opt/fiji/ImageJ-linux64",
]


def _merge(base, override):
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError("malformed JSON in %s: %s" % (path, e))


def local_config():
    """Machine-specific settings (paths, env names). Gitignored, optional."""
    p = REPO_ROOT / LOCAL_CONFIG_NAME
    return _load_json(p) if p.exists() else {}


def load_config(dataset):
    defaults_path = REPO_ROOT / "defaults.json"
    cfg = _load_json(defaults_path)
    cfg = _merge(cfg, local_config())
    local = Path(dataset) / layout.DATASET_CONFIG_NAME
    if local.exists():
        cfg = _merge(cfg, _load_json(local))
    return cfg


def resolve_dataset(name_or_path, cfg):
    p = Path(name_or_path)
    if p.is_absolute():
        return p
    return resolve_data_root(cfg) / name_or_path


def resolve_data_root(cfg):
    """env var > config > current directory."""
    v = os.environ.get(ENV_PREFIX + "DATA_ROOT") or cfg.get("data_root")
    return Path(v) if v else Path.cwd()


def resolve_imagej(cfg):
    """env var > config > common install locations > PATH. None if not found."""
    v = os.environ.get(ENV_PREFIX + "IMAGEJ") or cfg.get("fiji", {}).get("imagej_exe")
    if v:
        return Path(v)
    for cand in _IMAGEJ_CANDIDATES:
        if Path(cand).exists():
            return Path(cand)
    for name in ("ImageJ-win64", "fiji", "ImageJ"):
        w = shutil.which(name)
        if w:
            return Path(w)
    return None


def resolve_frame_rate(dataset, cfg):
    """cfg['frame_rate'] if set, else LSM/@frameRate from Experiment.xml. Must be > 0."""
    if cfg.get("frame_rate") is not None:
        fr = float(cfg["frame_rate"])
        if fr <= 0:
            raise ValueError("frame_rate must be > 0, got %r" % (cfg["frame_rate"],))
        return fr
    xml_path = layout.experiment_xml(dataset, cfg)
    if not xml_path.exists():
        raise FileNotFoundError(
            "%s not found - set frame_rate explicitly in config, or "
            "input.metadata_xml if your metadata file has a different name" % xml_path)
    lsm = ET.parse(str(xml_path)).getroot().find("LSM")
    if lsm is None or lsm.get("frameRate") is None:
        raise ValueError("no LSM/@frameRate in %s" % xml_path)
    fr = float(lsm.get("frameRate"))
    if fr <= 0:
        raise ValueError("LSM/@frameRate must be > 0 in %s, got %r" % (xml_path, lsm.get("frameRate")))
    return fr
