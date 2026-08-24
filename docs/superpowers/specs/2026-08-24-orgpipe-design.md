# orgpipe — design

**Date:** 2026-08-24
**Status:** awaiting review

## Problem

The calcium-imaging analysis pipeline runs across three conda environments that cannot
import each other, and takes ~5.5 hours per dataset with a human present at three
separate points. Measured on `250514_B2_000` (5400 frames, 512×512) from file timestamps:

| Stage | Env | Wall clock | Output |
|---|---|---|---|
| CNMF-E denoise | caiman_env | → 02:12 | `denoised_movie_reconstructed.tif` 11.3 GB |
| Fiji auto-B&C + image sequence | Fiji GUI | 02:19 → 02:23 (4 min) | `caiman/` 5400 × 1 MB |
| suite2p binary conversion | suite2p | → 02:41 (18 min) | `data.bin` 2.8 GB |
| suite2p detect + extract | suite2p | → 07:22 (**4 h 40 m**) | `F/Fneu/stat/spks/ops.npy` |
| cell curation | suite2p GUI | → 07:28 | `iscell.npy` |
| ROI analysis | code | → 07:54 (25 min) | `correlation.tif`, IOSI |

Notebooks are copied into each dataset folder to make relative paths work. Across 39
copies of `denoise.ipynb` every parameter is constant except `fr`; across 27 copies of
`ROI_analysis.ipynb` the analysis is near-identical but the notebooks exist in five
different vintages (12 to 20 cells) that have silently drifted apart.

## Goal

Two commands. The first runs unattended through suite2p and hands back the suite2p GUI
with the dataset loaded. The human curates. The second returns correlation and
synchronicity data.

```
orgpipe run 250528_B2_003        # denoise → fiji → suite2p → GUI opens
                                 # (curate cells, save, close)
orgpipe analyze 250528_B2_003    # → correlation + synchronicity
```

A bare name resolves against `data_root` in `defaults.json` (`Z:\Joseph`), so
`250528_B2_003` means `Z:\Joseph\250528_B2_003`. An absolute path is accepted as-is and
used verbatim. `data_root` is configuration rather than a constant because the drive
letter has moved before — existing scripts in `Z:\Joseph` still reference `F:` and `G:`.

## Scope

**In:** the four datasets with no prior run — `241029_ILDT8_00`, `250521_B2_001`,
`250528_B2_003`, `250605_B2_001`. `250528_B2_003` is the development target: raw TIFF
and `Experiment.xml` only, nothing else to collide with.

**Out:** all `*_B3_*` datasets, excluded by default in the runner, not merely by
convention. Backfilling the 14 datasets that have suite2p output but no ROI analysis —
this project builds the system, it does not reprocess history.

## Architecture

The environment split is the dominant constraint, so the package is organized around a
**three-tier import rule** rather than around subject matter.

```
Z:\Joseph\orgpipe\                 (git repo)
├── orgpipe/
│   ├── __init__.py                EMPTY — nothing eager
│   ├── config.py   ┐
│   ├── state.py    ├─ TIER 1: stdlib only, 3.9 syntax → imports in ALL three envs
│   ├── layout.py   ┘
│   ├── stage_denoise.py           TIER 2: caiman_env only  (imports caiman)
│   ├── stage_fiji.py                      any env          (subprocess only)
│   ├── stage_suite2p.py                   suite2p env only (imports suite2p)
│   ├── stage_roi.py                       code env only    (imports sklearn/seaborn)
│   └── plots.py                           code env         (figure fns for the notebook)
├── macros/split_sequence.ijm
├── bin/{run_denoise,run_fiji,run_suite2p,run_roi,pipeline}.py
├── orgpipe.bat / orgpipe            one-line wrappers
├── settings/suite2p_ops.npy         copy of settings_ver1.0.npy
├── defaults.json                    repo-level parameter defaults
└── notebooks/{denoise,ROI_analysis}.ipynb
```

Tier 1 is stdlib-only and written in 3.9 syntax so suite2p's Python 3.9.21 can import it.
Tier 2 modules each pull in exactly one heavy dependency and are only ever imported by
their own environment's entry script. `__init__.py` stays empty so that
`import orgpipe.config` under suite2p never transitively touches caiman.

Config is JSON, not TOML: `tomllib` does not exist in 3.9.

### Cross-environment invocation

The orchestrator never imports caiman or suite2p. It shells out:

```python
subprocess.run(["conda", "run", "--no-capture-output", "-n", env,
                "python", entry_script, dataset_path])
```

Verified working for all three: `caiman_env` 3.10.8, `suite2p` 3.9.21, `code` 3.13.2.
`--no-capture-output` is required — without it a five-hour stage produces no output until
it finishes.

Subprocess isolation also fixes the memory problem: process exit returns everything to
the OS, so nothing accumulates the way it does in a long-lived Jupyter kernel.

## Data flow

```
Image_scan_1_region_0_0.tif  +  Experiment.xml
   └─ config.resolve() ──► frame_rate = 29.16   (LSM/@frameRate)

[caiman_env]  stage_denoise
   CAIMAN_TEMP=<ds>/.orgpipe/caiman_temp        (isolated; makedirs first — see note)
   chunked TiffWriter(bigtiff=True), float32, 200-frame chunks
   finally: cm.stop_server(dview=dview)
   ▼  denoised_movie_reconstructed.tif           5.7 GB

[any env]     stage_fiji → ImageJ-win64.exe -macro   (GUI mode — see note)
   ▼  caiman/denoised_movie_reconstructed####.tif × N

[suite2p]     stage_suite2p    ops = settings/suite2p_ops.npy + overrides
   ▼  caiman/suite2p/plane0/{F,Fneu,stat,spks,iscell,ops}.npy
   ▼  launches: gui2p.run(<ds>/caiman/suite2p/plane0/stat.npy)

  ═══ CURATION GATE — human, in the suite2p GUI ═══

[code]        stage_roi
   ▼  correlation.tif, assembloid_demo.jpg, roi_results.json
```

### Note: CAIMAN_TEMP

Every dataset's raw file is named `Image_scan_1_region_0_0.tif`, so every caiman run
writes the same memmap filename into `C:\Users\Joseph\caiman_data\temp`. Concurrent runs
would clobber each other. `caiman/paths.py:39` honours `CAIMAN_TEMP`, but **silently
ignores it and falls back to the shared directory if the path does not already exist** —
so the runner must `os.makedirs` before setting it.

That directory currently holds 42 GB of stale intermediates including a 22 GB orphan
TIFF; Phase 0 cleans it.

### Note: Fiji runs in GUI mode, not headless

Tested against real data from `250514_B2_000`:

| input | mode | result |
|---|---|---|
| float32 plain TIFF | `--headless` | works |
| float64 | `--headless` | `VerifyError` in `loci/plugins/in/MainDialog` |
| float32 BigTIFF | `--headless` | `VerifyError` in `loci/plugins/in/MainDialog` |
| float64 | GUI (`-macro`, no `--headless`) | works |

ImageJ's native TIFF reader handles neither float64 nor BigTIFF, so `open()` delegates to
Bio-Formats, whose importer dialog cannot construct without a display. The denoised movie
at float32 × 5400 frames is 5.66 GB — above the 4 GB plain-TIFF ceiling — so it must be
BigTIFF, so headless cannot open it.

Downcasting to uint16 to fit under 4 GB is **ruled out**: `suite2p/io/tiff.py:131` does
`im = (im // 2).astype(np.int16)` for uint16 input while passing float32 through unscaled
at line 136. That is a silent 2× intensity change for no benefit.

GUI mode runs the macro unattended, needs no interaction, and exits cleanly with no
orphaned Java processes (verified). Its one cost: ImageJ `print()` goes to the Log window
rather than stdout, so the runner confirms success by counting output files, not by
parsing console text.

The recorder-syntax `run("Image Sequence... ")` writer throws `IndexOutOfBoundsException`
under automation regardless of mode. The macro uses a per-slice loop instead:

```javascript
run("Enhance Contrast", "saturated=" + saturated);
getMinAndMax(dmin, dmax);
for (i = 1; i <= nSlices; i++) {
    setSlice(i); run("Duplicate...", "title=__frm"); setMinAndMax(dmin, dmax);
    saveAs("Tiff", outdir + "/" + prefix + IJ.pad(i-1, 4) + ".tif"); close();
}
```

Auto B&C sets one display range for the whole stack — verified identical across frames
0, 1, 50, 2700 and 5399 of the existing manual output.

## Stage contract

Every stage takes a dataset folder, and:

1. loads `defaults.json` merged with optional `<dataset>/orgpipe.json`
2. reads `<dataset>/.orgpipe/state.json`; if the stage is `done` and inputs are unchanged,
   returns immediately unless `--force`
3. runs, writes outputs, updates state
4. exits 0, or writes `failed` with a traceback and exits nonzero

Stages are idempotent. Re-running a completed stage is a no-op.

### stage_denoise (caiman_env)

Same CNMF-E computation as `denoise.ipynb` cells 0–2 — same imports, same `CNMFParams`,
same `cnm.fit_file()`. Only `fr` changes source, from hardcoded to `Experiment.xml`.

Cell 3 (`plot_contours` / `view_components`) is **dropped** from the batch path;
`view_components` blocks on a GUI event loop. Verified safe: both functions touch
estimates only via `self.A = scipy.sparse.csc_matrix(self.A)`, a storage-format
conversion, and neither calls `select_components`. Cell 4's inputs are unaffected. That
block moves to the notebook.

Cell 4 is **replaced by cell 5**, the chunked writer currently commented out at the bottom
of the notebook. `save_dtype` is pinned to `np.float32`.

Pinning float32 is lossless, structurally and not just empirically: `A`, `C`, `b` and `f`
are all float32, so `A @ C + b @ f` produces a float32 result and the current upcast to
float64 adds no information. It only doubles the file — 11.3 GB → 5.7 GB for identical
numbers. (Confirmed empirically: ImageJ's float32 downcast of the existing float64 file
is bit-identical, max abs diff 0.0.)

Memory: cell 4 materializes the whole movie at once and peaks at 25–30 GB. Cell 5's
200-frame chunks peak at ~210 MB. `cm.stop_server(dview=dview)` is added in a `finally` —
the notebook currently has no shutdown at all; its only `stop_server` call is the
defensive one at the top of cell 2 that kills a *previous* run's cluster.

### stage_fiji (any env)

Generates the macro, invokes `ImageJ-win64.exe -macro`, verifies the output frame count
matches the source stack depth. `saturated` defaults to `0.35`.

### stage_suite2p (suite2p env)

Loads `settings/suite2p_ops.npy`, applies `data_path`, `save_path0` and any configured
overrides, calls `run_s2p`. Prints every key it changes relative to the stored ops so no
parameter moves silently. On success, launches:

```python
from suite2p.gui import gui2p
gui2p.run(r"<ds>\caiman\suite2p\plane0\stat.npy")
```

`gui2p.run(statfile)` → `MainWindow(statfile=...)` sets `self.fname` and calls
`io.load_proc`, so the GUI opens with the dataset already loaded.

### stage_roi (code env)

Loads `F/Fneu/iscell/stat`, GMM + Mahalanobis organoid split, ΔF/F z-scoring, amplitude
and latency filtering, correlation heatmap, and the inter-organoid synchronization index.

`sample_size` is derived as `min(len(good_idx[0]), len(good_idx[1]))` rather than being a
hand-set constant.

`calculate_inter_organoid_index` currently computes cross-correlation with a Python double
loop — `M_A × M_B` calls to `np.corrcoef`, repeated for every surrogate. At
`n_surrogates=200` that is millions of calls and dominates the 25-minute stage. Since
z-scored rows make Pearson r a normalized dot product, it becomes `A_z @ B_z.T / T` —
identical result, minutes to well under a second.

The propagation/raster cells (15–18 in the 20-cell notebook vintage) are not carried over;
they are not part of the correlation/synchronicity output.

## Configuration

`defaults.json` in the repo holds every parameter. `<dataset>/orgpipe.json` holds only the
deltas for that dataset. Missing file means all defaults.

```json
{
  "frame_rate": null,
  "denoise": { "decay_time": 2.0, "gSig": [5, 5], "rf": 20, "stride": 6, "K": 5,
               "p": 2, "nb": 2, "merge_thr": 0.80, "min_SNR": 2.0, "rval_thr": 0.80,
               "chunk_size": 200 },
  "fiji":    { "saturated": 0.35 },
  "suite2p": { "ops_file": "settings/suite2p_ops.npy" },
  "roi":     { "neuropil_r": 0.7, "baseline_pctl": 8, "amp_min_z": 3.5,
               "burst_z": 3.5, "min_gap_fr": 3, "n_surrogates": 200 }
}
```

`frame_rate: null` means "read `LSM/@frameRate` from `Experiment.xml`". A number overrides
it. The resolved value feeds both caiman `fr` and suite2p `fs`, so the two cannot drift
apart the way they have historically.

## State and the curation gate

`<dataset>/.orgpipe/state.json`, advancing:

```
pending → denoised → split → extracted → awaiting_curation → curated → analyzed
```

or `failed:<stage>` with a traceback.

**The gate detects itself.** suite2p writes `iscell.npy` in the same second as `F.npy`;
human curation rewrites it later. So `mtime(iscell) > mtime(F)` means a person has been
there. On the existing `250514_B2_000` run that reads 07:28:02 vs 07:22:16 — unambiguous.
`--assume-curated` overrides when the check is not wanted.

`orgpipe analyze` refuses to run on a dataset still in `awaiting_curation` unless
overridden, so uncurated output cannot silently become a result.

## Fidelity

The automated pipeline must produce the same result as the manual one. That is enforced by
four equivalence tests, not by assertion.

1. **Fiji split.** Automated output vs the existing hand-made `250514_B2_000/caiman/*.tif`,
   byte-compared. Already passing on a 20-frame slice of the real data in both GUI and
   headless modes: `pixels_identical_to_manual=True`, dtype float32. Phase 0 runs it over
   the full 5400.

2. **Denoise save path.** Chunked float32 writer vs the existing float64 file, compared
   frame by frame. Establishes that chunking and the dtype pin change nothing.

3. **suite2p ops.** The dict the runner builds, diffed key-by-key against
   `settings_ver1.0.npy`. The only permitted differences are `data_path`, `save_path0`,
   and anything explicitly configured. Printed at run time. This is the right test because
   the automation does not change *how* suite2p runs — both paths call `run_s2p` — only
   which dict reaches it. Comparing dicts is exact and costs seconds; re-running suite2p
   to compare `F.npy` costs 4.7 hours and proves less.

4. **Vectorized IOSI.** `A_z @ B_z.T / T` vs the original double loop, on real `F.npy`,
   to float tolerance.

A `--smoke` mode truncates to the first 300 frames so the whole chain runs in minutes
instead of hours. Without it, development is limited to roughly one attempt per workday.

## The one deliberate divergence — needs sign-off

`settings_ver1.0.npy` has `fs = 15.0`. The true acquisition rate is ~29–30 Hz for every
dataset: `Experiment.xml` reports `frameRate="29.160"` with `averageMode="0"`, meaning
frame averaging is **off** and `averageNum="5"` is a dead setting. The notebooks disagree
with themselves — 21 use `fr=15`, 18 use `fr=30`, and folders with identical acquisition
settings pick different values (`250605_B3_000`→15, `250618_B3_005`→30, both 29.160 Hz).

Setting `frame_rate` to the true rate is correct but **is not** result-preserving:

```
detection/detect.py:21
bin_size = int(max(1, ops["nframes"] // ops["nbinned"], np.round(ops["tau"] * ops["fs"])))
```

With `tau=2.0`, `nframes=5400`, `nbinned=5000`: `fs=15` → bin_size **30**; `fs=29.16` →
bin_size **58**. Because `anatomical_only=4` segments the max projection of that binned
movie with Cellpose, doubling the bin halves the temporal resolution going in (180 binned
frames → 93) and Cellpose returns a different ROI set. On the caiman side `fr` scales
`decay_time` into frames for the CNMF-E temporal model, so the denoised movie changes too.

Worth noting the accident: `fs=15` yields a ~1-second detection bin at the true 30 Hz
rate, which is plausibly *better* for burst detection than the ~2-second bin the corrected
value produces. There is no ops knob to push `bin_size` below `tau * fs`, so keeping the
finer bin alongside a correct `fs` requires lowering `tau` to 1.0 — which decouples "what
rate was this recorded at" from "how finely do I bin for segmentation" instead of having
one constant quietly serve both.

The four in-scope datasets have no prior manual run, so there is no prior result to
diverge *from*. This matters only for comparability against the nine already-complete
non-B3 datasets. **Recorded as an open decision below.**

## Error handling

Preflight before committing to any multi-hour stage: raw TIFF readable, `Experiment.xml`
parses, ≥14 GB free (5.7 denoised + 5.4 sequence + 2.8 binary), ops file present, Fiji
binary present, target conda env resolves.

Each stage catches, records `failed` plus traceback to state, exits nonzero. The
orchestrator advances to the next dataset under `--keep-going`, otherwise stops. Because
state is per-dataset and stages are idempotent, a failed run is resumed by re-issuing the
same command.

## Plan

**Phase 0 — the fixes, validated on `250528_B2_003` in `--smoke` mode.** GPU-enable
Cellpose; measure the detect/extract split so the 4h40m finally has a real breakdown;
chunked float32 denoise with `stop_server`; the Fiji macro; `CAIMAN_TEMP` isolation; the
vectorized IOSI. Each is independently useful and none depends on the orchestration.

GPU carries a risk worth isolating: the suite2p env has `torch 2.6.0+cpu` while two RTX
A4000s sit idle, and `detection/anatomical.py:105` calls `CellposeModel(model_type=...)`
with no `gpu=` argument, which cellpose defaults to `False`. **Both** must change — a CUDA
install alone does nothing. Installing CUDA torch could break a working environment, so
Phase 0 clones it first (`conda create -n suite2p_gpu --clone suite2p`) and points the
runner at the clone. The existing env stays as a fallback and the change is revertible by
editing one string.

**Phase 1 — the package**: tier 1 modules, the four stages, the orchestrator, the two
wrappers, the two notebooks, the four equivalence tests.

No speedup figure is promised. The 4h40m is dominated by Cellpose on CPU, but the
detect-versus-extract split has not been measured, and Phase 0's first task is to measure
it.

## Open decisions

1. **Frame rate.** Adopt the true rate (~29.16 Hz) for both `fr` and `fs`, accepting a
   different ROI set than the nine completed non-B3 datasets? Or keep `fs = 15.0` verbatim
   for comparability? A third option sets `fs` correctly and `tau = 1.0` to preserve the
   ~1-second detection bin.

2. **Notebook location.** The two notebooks take `DATASET = r"Z:\Joseph\250528_B2_003"` in
   the first cell and live once in the repo rather than being copied into each folder.
   This is what stops the five-vintage drift from recurring, but it does change how they
   are opened.
