"""orgpipe CLI.

  orgpipe run <ds> [--smoke] [--force] [--no-gui] [--all] [--keep-going]
  orgpipe analyze <ds> [--assume-curated] [--force] [--all] [--keep-going]
  orgpipe curate <ds>
  orgpipe status
"""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from orgpipe import config, layout, preflight, state

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

BIN = Path(__file__).resolve().parent


def _tee(cmd, log_path):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(log_path), "a", encoding="utf-8", errors="replace") as log:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True,
                                errors="replace", bufsize=1)
        for line in proc.stdout:
            print(line, end="")
            log.write(line)
        return proc.wait()


def _stage(ds, cfg, stage, script, env, extra):
    if env == "base":
        cmd = [sys.executable, "-u", str(BIN / script), str(ds)] + extra
    else:
        cmd = ["conda", "run", "--no-capture-output", "-n", env,
               "python", "-u", str(BIN / script), str(ds)] + extra
    print("\n=== [%s] %s (%s) ===" % (stage, ds.name, env))
    rc = _tee(cmd, layout.logs_dir(ds) / (stage + ".log"))
    if rc != 0:
        raise RuntimeError("stage %s failed (exit %d) - see %s"
                           % (stage, rc, layout.logs_dir(ds) / (stage + ".log")))


def _targets(args, cfg0):
    if args.all:
        root = Path(cfg0["data_root"])
        return [p for p in sorted(root.iterdir())
                if p.is_dir()
                and p.name[:2].isdigit()
                and not layout.is_b3(p)
                and layout.raw_tif(p).exists()]
    return [config.resolve_dataset(args.dataset, cfg0)]


def cmd_run(args, cfg0):
    failures = []
    for ds in _targets(args, cfg0):
        cfg = config.load_config(ds)
        if layout.is_b3(ds):
            print("SKIP (B3):", ds.name)
            continue
        if args.all and (layout.plane0(ds) / "F.npy").exists() and not layout.state_path(ds).exists():
            print("SKIP (historical dataset, no orgpipe state):", ds.name)
            continue
        if layout.is_curated(ds) and not args.recurate:
            print("SKIP (curated; rerunning would DESTROY manual curation - pass --recurate to redo):", ds.name)
            if not args.all:
                sys.exit(1)
            continue
        errs = preflight.check(ds, cfg, needs_space=args.force or not state.is_done(ds, "suite2p", args.smoke))
        for env in {cfg["envs"]["caiman"], cfg["envs"]["suite2p"]}:
            e = preflight.check_env(env)
            if e:
                errs.append(e)
        if errs:
            print("PREFLIGHT FAILED for %s:\n  %s" % (ds.name, "\n  ".join(errs)))
            failures.append(ds.name)
            if args.keep_going:
                continue
            sys.exit(1)
        extra = (["--smoke"] if args.smoke else []) + (["--force"] if args.force else [])
        try:
            _stage(ds, cfg, "denoise", "run_denoise.py", cfg["envs"]["caiman"], extra)
            _stage(ds, cfg, "fiji", "run_fiji.py", "base", extra)
            _stage(ds, cfg, "suite2p", "run_suite2p.py", cfg["envs"]["suite2p"], extra)
        except RuntimeError as e:
            print(e)
            failures.append(ds.name)
            if args.keep_going:
                continue
            sys.exit(1)
        if not args.no_gui and not args.all and not args.smoke:
            print("\nOpening suite2p GUI - curate cells, save, close. Then: orgpipe analyze %s" % ds.name)
            rc = subprocess.run(["conda", "run", "--no-capture-output", "-n",
                                 cfg["envs"]["suite2p"], "python",
                                 str(BIN / "run_suite2p.py"), "--gui", str(ds)]).returncode
            if rc != 0:
                print("suite2p GUI failed to launch (exit %d) - check the suite2p env" % rc)
    if failures:
        print("\nFAILED datasets:", ", ".join(failures))
        sys.exit(1)


def cmd_analyze(args, cfg0):
    e = preflight.check_env(config.load_config(Path("."))["envs"]["code"])
    if e:
        print("PREFLIGHT FAILED:", e)
        sys.exit(1)
    failures = []
    for ds in _targets(args, cfg0):
        cfg = config.load_config(ds)
        if layout.is_b3(ds):
            print("SKIP (B3):", ds.name)
            continue
        if args.all and (layout.plane0(ds) / "F.npy").exists() and not layout.state_path(ds).exists():
            print("SKIP (historical dataset, no orgpipe state):", ds.name)
            continue
        if not state.is_done(ds, "suite2p", smoke=True) and not (layout.plane0(ds) / "F.npy").exists():
            print("SKIP (no suite2p output):", ds.name)
            continue
        if not layout.is_curated(ds) and not args.assume_curated:
            print("REFUSING %s: not curated yet (mtime gate). Curate in the GUI "
                  "(orgpipe curate %s) or pass --assume-curated." % (ds.name, ds.name))
            failures.append(ds.name)
            continue
        s2p_smoke = state.read_state(ds)["stages"].get("suite2p", {}).get("smoke", False)
        extra = (["--smoke"] if s2p_smoke else []) + (["--force"] if args.force else [])
        try:
            _stage(ds, cfg, "roi", "run_roi.py", cfg["envs"]["code"], extra)
        except RuntimeError as e:
            print(e)
            failures.append(ds.name)
            if not args.keep_going:
                sys.exit(1)
    if failures:
        sys.exit(1)


def cmd_curate(args, cfg0):
    ds = config.resolve_dataset(args.dataset, cfg0)
    cfg = config.load_config(ds)
    if layout.is_b3(ds):
        print("REFUSING: %s is a B3 dataset (out of scope)" % ds)
        sys.exit(2)
    stat_file = layout.plane0(ds) / "stat.npy"
    if not stat_file.exists():
        print("No suite2p output at %s - run `orgpipe run %s` first." % (stat_file, ds.name))
        sys.exit(1)
    rc = subprocess.run(["conda", "run", "--no-capture-output", "-n",
                         cfg["envs"]["suite2p"], "python",
                         str(BIN / "run_suite2p.py"), "--gui", str(ds)]).returncode
    if rc != 0:
        print("suite2p GUI failed to launch (exit %d) - check the suite2p env" % rc)


def cmd_status(args, cfg0):
    root = Path(cfg0["data_root"])
    print("%-46s %-8s %-6s %-8s %-8s %-5s" % ("dataset", "denoise", "fiji", "suite2p", "curated", "roi"))
    for p in sorted(root.iterdir()):
        if not p.is_dir() or not layout.raw_tif(p).exists():
            continue
        if layout.is_b3(p):
            continue
        def s(stage):
            r = state.read_state(p)["stages"].get(stage, {})
            v = r.get("status", "-")
            return v + ("*" if r.get("smoke") else "")
        print("%-46s %-8s %-6s %-8s %-8s %-5s"
              % (p.name[:45], s("denoise"), s("fiji"), s("suite2p"),
                 "yes" if layout.is_curated(p) else "-", s("roi")))
    print("(* = smoke run)")


def main():
    ap = argparse.ArgumentParser(prog="orgpipe")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "analyze"):
        p = sub.add_parser(name)
        p.add_argument("dataset", nargs="?")
        p.add_argument("--all", action="store_true")
        p.add_argument("--force", action="store_true")
        p.add_argument("--keep-going", action="store_true")
        if name == "run":
            p.add_argument("--smoke", action="store_true")
            p.add_argument("--no-gui", action="store_true")
            p.add_argument("--recurate", action="store_true")
        else:
            p.add_argument("--assume-curated", action="store_true")
    sub.add_parser("curate").add_argument("dataset")
    sub.add_parser("status")
    args = ap.parse_args()
    if args.cmd in ("run", "analyze") and not args.all and not args.dataset:
        ap.error("dataset required (or --all)")

    cfg0 = config.load_config(Path("."))  # defaults only; per-dataset reload happens later
    {"run": cmd_run, "analyze": cmd_analyze,
     "curate": cmd_curate, "status": cmd_status}[args.cmd](args, cfg0)


if __name__ == "__main__":
    main()
