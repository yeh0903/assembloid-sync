# orgpipe

Pipeline for organoid calcium-imaging data: denoise (CaImAn) -> fiji (contrast
sequence) -> suite2p (ROI extraction) -> curate (manual, GUI) -> analyze
(SCA/IOSI).

## Commands

Git Bash: `bin/orgpipe <command> ...`
cmd.exe:  `orgpipe.bat <command> ...`

```
orgpipe run <dataset> [--smoke] [--force] [--recurate] [--no-gui] [--all] [--keep-going]
orgpipe analyze <dataset> [--assume-curated] [--force] [--all] [--keep-going]
orgpipe curate <dataset>
orgpipe status
```

## Flow

1. `orgpipe run <dataset>` - denoise, fiji, suite2p, then opens the suite2p GUI.
2. In the GUI: curate cells (mark real vs not), save, close.
3. `orgpipe analyze <dataset>` - refuses until curation is detected (iscell.npy
   rewritten after F.npy); pass `--assume-curated` to skip the check.

`orgpipe status` lists every non-B3 dataset with per-stage state (`*` = smoke run).

## Flags

| Flag | Commands | Meaning |
|---|---|---|
| `--smoke` | run | 300-frame test run, tags state `smoke: true` |
| `--force` | run, analyze | redo a stage even if already marked done |
| `--recurate` | run | allow rerunning a curated dataset (see WARNINGS) |
| `--no-gui` | run | skip opening the suite2p GUI after suite2p finishes |
| `--all` | run, analyze | apply to every eligible dataset under `data_root` |
| `--keep-going` | run, analyze | don't stop the `--all` batch on one dataset's failure |
| `--assume-curated` | analyze | skip the curation mtime-gate check |

## WARNINGS

- **`--recurate` (via `orgpipe run`), or `--force` on a direct `bin/run_*.py`
  call, on a curated dataset destroys manual curation irreversibly.** Only
  `orgpipe run` itself checks curation before rerunning suite2p; calling
  `bin/run_suite2p.py <dataset> --force` directly skips that guard - it only
  prints a warning - then deletes `caiman/suite2p/`. There is no undo.
- Running a single stage directly with `--force` clears the recorded state of
  every downstream stage automatically (their inputs just changed). Rerun
  `orgpipe run` (or the later stages) to rebuild them.
- `--all` silently skips two categories by design: historical datasets that
  have suite2p output but no `.orgpipe/state.json` (pre-orgpipe runs), and
  already-curated datasets (unless `--recurate`). Run those single-dataset if
  you mean to touch them.

## More

- Design + rationale: `docs/superpowers/specs/2026-08-24-orgpipe-design.md`
- Implementation plan: `docs/superpowers/plans/2026-08-24-orgpipe.md`
- Stage timings: `docs/timings.md`
