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


def _load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError("malformed JSON in %s: %s" % (path, e))


def load_config(dataset):
    defaults_path = REPO_ROOT / "defaults.json"
    cfg = _load_json(defaults_path)
    local = Path(dataset) / "orgpipe.json"
    if local.exists():
        cfg = _merge(cfg, _load_json(local))
    return cfg


def resolve_dataset(name_or_path, cfg):
    p = Path(name_or_path)
    if p.is_absolute():
        return p
    return Path(cfg["data_root"]) / name_or_path


def resolve_frame_rate(dataset, cfg):
    """cfg['frame_rate'] if set, else LSM/@frameRate from Experiment.xml. Must be > 0."""
    if cfg.get("frame_rate") is not None:
        fr = float(cfg["frame_rate"])
        if fr <= 0:
            raise ValueError("frame_rate must be > 0, got %r" % (cfg["frame_rate"],))
        return fr
    xml_path = Path(dataset) / "Experiment.xml"
    if not xml_path.exists():
        raise FileNotFoundError(str(xml_path))
    lsm = ET.parse(str(xml_path)).getroot().find("LSM")
    if lsm is None or lsm.get("frameRate") is None:
        raise ValueError("no LSM/@frameRate in %s" % xml_path)
    fr = float(lsm.get("frameRate"))
    if fr <= 0:
        raise ValueError("LSM/@frameRate must be > 0 in %s, got %r" % (xml_path, lsm.get("frameRate")))
    return fr
