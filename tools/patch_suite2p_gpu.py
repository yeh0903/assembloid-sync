"""Patch an installed suite2p so Cellpose detection uses the GPU.

suite2p 0.14.4 constructs CellposeModel without a gpu= argument, and cellpose
defaults it to False - so a CUDA build of torch alone changes nothing. This
rewrites the two constructor call sites in the target environment's
detection/anatomical.py, keeping a .orig backup.

    python tools/patch_suite2p_gpu.py <conda-env-name>
    python tools/patch_suite2p_gpu.py <conda-env-name> --revert
    python tools/patch_suite2p_gpu.py <conda-env-name> --check
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# (old call site, patched call site)
REPLACEMENTS = [
    ("CellposeModel(model_type=pretrained_model)",
     "CellposeModel(model_type=pretrained_model, gpu=True)"),
    ("CellposeModel(pretrained_model=pretrained_model)",
     "CellposeModel(pretrained_model=pretrained_model, gpu=True)"),
]


def _conda_run_python(env, code):
    r = subprocess.run(["conda", "run", "-n", env, "python", "-c", code],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("conda run -n %s python -c ... failed (exit %d):\n%s"
                 % (env, r.returncode, r.stderr.strip()))
    return r.stdout.strip()


def locate_anatomical(env):
    """Ask the target env's own Python where suite2p is installed."""
    out = _conda_run_python(
        env, "import suite2p.detection.anatomical as m; print(m.__file__)")
    lines = [ln for ln in out.splitlines() if ln.strip()]
    if not lines:
        sys.exit("conda run -n %s could not locate suite2p.detection.anatomical "
                 "(is suite2p installed in that env?)" % env)
    path = Path(lines[-1].strip())
    if not path.exists():
        sys.exit("suite2p reported %s but that file does not exist" % path)
    return path


def cuda_available(env):
    out = _conda_run_python(env, "import torch; print(torch.cuda.is_available())")
    lines = [ln for ln in out.splitlines() if ln.strip()]
    return lines[-1].strip() if lines else "<unknown>"


def backup_path(path):
    return Path(str(path) + ".orig")


def is_patched(text):
    return all(new in text for _old, new in REPLACEMENTS)


def cmd_check(env):
    path = locate_anatomical(env)
    text = path.read_text(encoding="utf-8")
    patched = is_patched(text)
    bak = backup_path(path)
    print("target env:  %s" % env)
    print("file (outside this repo, in site-packages): %s" % path)
    print("backup exists: %s%s" % (bak.exists(), (" (%s)" % bak) if bak.exists() else ""))
    print("patched: %s" % patched)
    print("torch.cuda.is_available(): %s" % cuda_available(env))


def cmd_patch(env):
    path = locate_anatomical(env)
    print("target env:  %s" % env)
    print("file to modify (outside this repo, in site-packages): %s" % path)
    text = path.read_text(encoding="utf-8")
    if is_patched(text):
        print("already patched, nothing to do: %s" % path)
        return
    bak = backup_path(path)
    if not bak.exists():
        shutil.copy2(str(path), str(bak))
        print("backed up original -> %s" % bak)
    else:
        print("backup already exists, leaving it alone -> %s" % bak)
    new_text = text
    n = 0
    for old, new in REPLACEMENTS:
        found = new_text.count(old)
        if found:
            new_text = new_text.replace(old, new)
            n += found
    if n == 0:
        sys.exit("no known CellposeModel(...) call sites found in %s - "
                 "suite2p's source may have changed; this patch script needs "
                 "updating for the installed version" % path)
    path.write_text(new_text, encoding="utf-8")
    print("patched %d call site(s) in %s" % (n, path))
    print("verify with:  python tools/patch_suite2p_gpu.py %s --check" % env)


def cmd_revert(env):
    path = locate_anatomical(env)
    bak = backup_path(path)
    print("target env:  %s" % env)
    print("file to restore (outside this repo, in site-packages): %s" % path)
    if not bak.exists():
        sys.exit("no backup found at %s - nothing to revert" % bak)
    shutil.copy2(str(bak), str(path))
    print("restored %s <- %s" % (path, bak))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("env", help="conda environment name, e.g. suite2p_gpu")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--revert", action="store_true",
                      help="restore anatomical.py from its .orig backup")
    mode.add_argument("--check", action="store_true",
                      help="report patch status and torch.cuda.is_available(), change nothing")
    args = ap.parse_args()

    if args.check:
        cmd_check(args.env)
    elif args.revert:
        cmd_revert(args.env)
    else:
        cmd_patch(args.env)


if __name__ == "__main__":
    main()
