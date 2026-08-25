"""Per-dataset stage state in <dataset>/.orgpipe/state.json. Tier 1: stdlib only."""
import datetime
import json

from . import layout


def read_state(ds):
    p = layout.state_path(ds)
    if not p.exists():
        return {"stages": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def write_state(ds, st):
    layout.orgpipe_dir(ds).mkdir(parents=True, exist_ok=True)
    layout.state_path(ds).write_text(json.dumps(st, indent=2), encoding="utf-8")


def mark(ds, stage, status, smoke=False, error=None):
    st = read_state(ds)
    st["stages"][stage] = {
        "status": status,
        "smoke": bool(smoke),
        "at": datetime.datetime.now().isoformat(timespec="seconds"),
        "error": error,
    }
    write_state(ds, st)


def is_done(ds, stage, smoke=False):
    """done, and a real run satisfies a smoke ask but not vice versa."""
    r = read_state(ds)["stages"].get(stage, {})
    if r.get("status") != "done":
        return False
    return (not r.get("smoke", False)) or smoke
