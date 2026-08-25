"""Configuration: defaults.json merged with <dataset>/orgpipe.json. Tier 1: stdlib only."""
import json
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _merge(base, override):
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(dataset):
    cfg = json.loads((REPO_ROOT / "defaults.json").read_text(encoding="utf-8"))
    local = Path(dataset) / "orgpipe.json"
    if local.exists():
        cfg = _merge(cfg, json.loads(local.read_text(encoding="utf-8")))
    return cfg


def resolve_dataset(name_or_path, cfg):
    p = Path(name_or_path)
    if p.is_absolute():
        return p
    return Path(cfg["data_root"]) / name_or_path


def resolve_frame_rate(dataset, cfg):
    """cfg['frame_rate'] if set, else LSM/@frameRate from Experiment.xml."""
    if cfg.get("frame_rate"):
        return float(cfg["frame_rate"])
    xml_path = Path(dataset) / "Experiment.xml"
    if not xml_path.exists():
        raise FileNotFoundError(str(xml_path))
    lsm = ET.parse(str(xml_path)).getroot().find("LSM")
    if lsm is None or lsm.get("frameRate") is None:
        raise ValueError("no LSM/@frameRate in %s" % xml_path)
    return float(lsm.get("frameRate"))
