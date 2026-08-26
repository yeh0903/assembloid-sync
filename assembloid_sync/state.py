"""Per-dataset stage state in <dataset>/.assembloid-sync/state.json. Tier 1: stdlib only."""
import datetime
import json
import os

from . import layout


def read_state(ds):
    p = layout.state_path(ds)
    if not p.exists():
        return {"stages": {}}
    try:
        st = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print("WARNING: could not read state file %s (%s) - starting fresh" % (p, e))
        return {"stages": {}}
    st.setdefault("stages", {})
    return st


def write_state(ds, st):
    layout.state_dir(ds).mkdir(parents=True, exist_ok=True)
    p = layout.state_path(ds)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(st, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(p))


def mark(ds, stage, status, error=None):
    st = read_state(ds)
    st["stages"][stage] = {
        "status": status,
        "at": datetime.datetime.now().isoformat(timespec="seconds"),
        "error": error,
    }
    write_state(ds, st)


def is_done(ds, stage):
    """True if the stage's last recorded run finished successfully."""
    return read_state(ds)["stages"].get(stage, {}).get("status") == "done"


DOWNSTREAM = {
    "denoise": ["fiji", "suite2p", "roi"],
    "fiji": ["suite2p", "roi"],
    "suite2p": ["roi"],
    "roi": [],
}


def clear_downstream(ds, stage):
    """A stage that actually executes invalidates everything after it."""
    st = read_state(ds)
    removed = [k for k in DOWNSTREAM.get(stage, []) if st["stages"].pop(k, None) is not None]
    if removed:
        write_state(ds, st)
    return removed
