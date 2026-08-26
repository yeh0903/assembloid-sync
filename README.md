# assembloid-sync

Automated two-photon calcium-imaging pipeline for **paired neural organoids
(assembloids)** — from raw ThorLabs movies to inter-organoid synchronization indices.

Two commands, one human step in between:

```bash
assembloid-sync run 250528_B2_003        # denoise -> contrast -> cell detection   (~30 min)
#   ... curate cells in the suite2p GUI, save, close ...
assembloid-sync analyze 250528_B2_003    # correlation + synchronization metrics   (~1-2 min)
```

Setting up from scratch? See [docs/SETUP.md](docs/SETUP.md).

Built for **jGCaMP8s** two-photon recordings of fused cortical organoids at ~30 Hz,
512×512, acquired on ThorImage. Replaces a manual workflow that took ~5.5 hours per
dataset across three separate applications and three human touchpoints.

---

## What it measures

Two organoids are fused and imaged together. The scientific question is whether their
neural activity is *coupled* — do they burst independently, or has a functional
connection formed across the junction?

The pipeline answers that with two numbers per recording:

- **corrSYN** — network synchronization *within* the imaged population, from the
  eigenvalue structure of the ROI-ROI correlation matrix.
- **IOSI** — Inter-Organoid Synchronization Index, which measures coupling *between*
  the two organoids specifically, excluding within-organoid correlation entirely.

Both are tested against phase-randomized surrogate data, so a reported value means
"more synchronized than chance", not just "correlated".

---

## The pipeline, stage by stage

### 1. Denoise — CNMF-E (CaImAn), `caiman_env`

Constrained Non-negative Matrix Factorization for microendoscopic data factors the
movie `Y` (pixels × time) into

```
Y  ≈  A·C  +  b·f  +  noise
```

- `A` — spatial footprints (pixels × components): *where* each source is
- `C` — temporal traces (components × time): *what it does*, modeled as an
  autoregressive process of order `p=2`
- `b`, `f` — background spatial/temporal components, using the ring model
  (`ring_size_factor=1.4`) that separates diffuse background from somatic signal

Fitting runs in overlapping patches (`rf=20` half-size, `stride=6` overlap, `K=5`
initial components per patch, `greedy_roi` initialization), merging components whose
traces correlate above `merge_thr=0.80`.

The stage then writes the **reconstruction** `A·C + b·f` — the movie with the noise
term dropped — as a float32 BigTIFF, streamed in 200-frame chunks so memory stays flat
(~200 MB) instead of materializing all 5400 frames at once (~25 GB).

*Why reconstruct a movie instead of using `C` directly?* The downstream segmentation is
morphological (Cellpose on image data), matching the established manual workflow. CNMF-E
here is used as a denoiser, not as the ROI detector.

### 2. Contrast normalization and frame export — Fiji/ImageJ, any env

Reproduces ImageJ's Brightness/Contrast **Auto** button exactly
(`ContrastAdjuster.autoAdjust`): a 256-bin histogram of the first slice, ignoring bins
holding more than `npixels/10`, scanning inward from both ends for the first bin above
`npixels/5000`. That display range is applied to the whole stack, and every frame is
saved as an individual TIFF into `<dataset>/caiman/`.

**This changes display metadata only — pixel values are untouched** (verified
byte-identical against hand-made output across all 5400 frames). suite2p reads raw
pixels and never consults the display range. The step is retained because the per-frame
sequence is suite2p's input directory and because it preserves the original workflow.

### 3. Cell detection and fluorescence extraction — suite2p + Cellpose, `suite2p_gpu`

1. **Binary conversion** — the TIFF sequence becomes an int16 `data.bin`.
2. **Registration** — disabled (`do_registration=0`); these recordings are stable and
   the CNMF-E reconstruction is already motion-consistent.
3. **Detection** (`anatomical_only=4`) — the movie is binned in blocks of
   `round(tau × fs)` frames (29 frames ≈ 1 s here), temporally high-pass filtered,
   PCA-denoised, and reduced to a **maximum-intensity projection**. Cellpose (`cyto3`,
   `diameter≈9 px`) segments that projection into ROI masks. Binning matters: one bin
   should span roughly one calcium transient, so the projection shows active cells
   brightly without smearing separate events together.
4. **Extraction** — per-ROI fluorescence `F`, plus a surrounding neuropil annulus
   `Fneu` (`inner_neuropil_radius=2`, `min_neuropil_pixels=350`).
5. **Classification** — suite2p's built-in classifier scores each ROI on skew,
   normalized pixel count and compactness, producing `iscell` probabilities.
6. **Deconvolution** — OASIS produces `spks`. Computed but *not used* downstream; the
   analysis works on ΔF/F, not inferred spikes.

Cellpose runs on GPU (CUDA). On an RTX A4000 this step takes ~4 seconds; on CPU it was
the multi-hour bottleneck of the original workflow.

### 4. Curation — human, suite2p GUI

You accept or reject cells. This is the one irreducibly manual step, and the pipeline is
built around it rather than pretending it away.

Curation is recorded explicitly: `assembloid-sync run`/`curate` writes a marker
(`.assembloid-sync/curated.json`) once the suite2p GUI is closed. As a fallback for
curating outside this tool, the pipeline also detects curation by comparing
modification times: suite2p writes `iscell.npy` in the same second as `F.npy`, while
curation rewrites it later. `analyze` refuses to run until one of those signals appears
(override with `--assume-curated`). A suite2p rerun clears the marker, since detection
is being redone and any prior curation decision no longer applies.

### 5. Analysis — `code` env

**Organoid assignment.** A 2-component Gaussian Mixture (full covariance, 10
initializations, fixed seed) clusters ROI centroids into two spatial blobs. Because GMM
assignment is probabilistic and can misplace ROIs near the boundary, each ROI is then
reassigned to whichever component it is closer to by **Mahalanobis distance**. Label 0
is forced to be the upper organoid (smaller mean y).

**ΔF/F and normalization.**

```
Fcorr = F − 0.4·Fneu           neuropil subtraction
F0    = 8th percentile of Fcorr per ROI      baseline
ΔF/F  = (Fcorr − F0) / F0
dFz   = z-score of ΔF/F per ROI             makes ROIs comparable
```

**Activity filter.** Robust amplitude per ROI is `P98 − P02` of `dFz`; ROIs below
`amp_min_z` (default 3.75) are dropped as inactive. Surviving ROIs are ordered by
*first-burst latency* — the first frame where `dFz` exceeds `burst_z` (default 2.5) —
which is what makes propagation visible in the trace plots.

**Correlation.** Pearson correlation across all surviving ROIs (`corr_full.npy`), plus a
**balanced subsample** — `min(n_A, n_B)` ROIs drawn from each organoid with a fixed seed
— used for the heatmap and for corrSYN, so that the larger organoid cannot dominate the
statistic.

**corrSYN — network synchronization**, follows the Synchronization Cluster Analysis
method of Patel et al. (2015) (after FluoroSNNAP). Eigendecompose the correlation
matrix. Under the null hypothesis of no synchrony, its eigenvalue spectrum still has
structure from finite data, so the null is built empirically: **AAFT surrogates**
(Amplitude-Adjusted Fourier Transform — randomize Fourier phases while preserving both
the power spectrum and the amplitude distribution) produce surrogate correlation
matrices and their eigenvalue spectra. Then

```
SI_i = (λ_i − λ̄_sur,i) / (M − λ̄_sur,i)     if λ_i > λ̄_sur,i + 2·SD_sur,i,  else 0
corrSYN = SI_0
```

i.e. how far the leading eigenvalue exceeds chance, normalized so that 1.0 is perfect
synchrony (all M neurons in one mode). Synchronization *clusters* are eigenvectors with
`SI ≥ 0.01`; each neuron is assigned to the cluster maximizing its participation index
`PI_k = λ_k · v_k²`, and clusters smaller than `sca_min_cluster_size` are discarded.

**IOSI — inter-organoid synchronization.** IOSI as implemented here builds the
cross-correlation matrix **between** organoids only (`M_A × M_B`), so within-organoid
synchrony cannot inflate the result. Its coupling strength is the dominant singular
value from an SVD, normalized by `√(M_A·M_B)`. The null distribution comes from AAFT
surrogates of organoid B alone — destroying A↔B timing while preserving each trace's
own spectrum. Then

```
IOSI = (observed − surrogate_mean) / (1 − surrogate_mean)   if observed > mean + 2·SD, else 0
```

reported with a z-score and p-value. A z-score above 2 means the two organoids are
coupled beyond chance.

---

## Outputs

Written into the dataset folder:

| file | contents |
|---|---|
| `roi_results.json` | corrSYN, IOSI, z-scores, p-value, significance, ROI counts, SCA cluster sizes |
| `corr_full.npy` | correlation matrix over all surviving ROIs |
| `corr_sampled.npy` | balanced-subsample correlation matrix (the one corrSYN uses) |
| `correlation.tif` | correlation heatmap, organoid boundary marked |
| `assembloid_demo.jpg` | ROI centroids colored by organoid assignment |
| `denoised_movie_reconstructed.tif` | CNMF-E reconstruction (float32 BigTIFF) |
| `caiman/` | per-frame TIFF sequence + `suite2p/plane0/` outputs |
| `.assembloid-sync/` | pipeline state, per-stage logs |

---

## Configuration

Defaults live in `defaults.json`, merged with the gitignored `config.local.json`
(machine-specific paths and env names - see "Installation / running elsewhere"
below). Per-dataset overrides go in `<dataset>/assembloid-sync.json` and only need
the keys that differ:

```json
{ "roi": { "amp_min_z": 3.2 } }
```

### Indicator kinetics

**ThorImage's `Experiment.xml` does not record which calcium indicator was used**, so it
is declared in `defaults.json` (`"indicator": "jGCaMP8s"`). Two parameters follow from
it:

| parameter | consumer | role |
|---|---|---|
| `denoise.decay_time` | CaImAn | expected length of one transient, used for SNR-based component evaluation |
| `suite2p.tau` | suite2p | sensor timescale; sets the detection bin `round(tau × fs)` and the OASIS deconvolution kernel |

Both default to **1.0 s for jGCaMP8s**. That is measured, not assumed: exponential fits
to 1,555 isolated transient decays across three datasets give a median τ of **0.49–0.57 s**,
consistent with published jGCaMP8s kinetics for multi-spike bursts. A detection bin of
≈2×τ captures a transient without merging neighbours.

If you use a different indicator, change both numbers. Note that jGCaMP8 sensors are
*much faster* than the GCaMP6 series — a common source of error is carrying over
GCaMP6s-era values (τ ≈ 1.25–2.0 s), which doubles the detection bin and changes which
ROIs Cellpose finds.

### Frame rate

Read automatically from `Experiment.xml` (`LSM/@frameRate`, ≈29.16 Hz). Frame averaging
is checked (`averageMode`) so a stale `averageNum` cannot mislead. Override with
`"frame_rate": <hz>` if needed. One resolved value feeds both CaImAn's `fr` and
suite2p's `fs`, so they cannot drift apart.

### Analysis thresholds

`neuropil_r` 0.4 · `baseline_pctl` 8 · `amp_min_z` 3.75 · `burst_z` 2.5 ·
`n_surrogates` 200 · `seed` 0. Tune `amp_min_z`/`burst_z` against the amplitude
histograms in `notebooks/ROI_analysis.ipynb`, then pin the chosen values in that
dataset's `assembloid-sync.json`.

---

## Commands

| command | what it does |
|---|---|
| `assembloid-sync run <ds>` | denoise → contrast/export → detection, then opens the curation GUI |
| `assembloid-sync analyze <ds>` | correlation + synchronization metrics (requires curation) |
| `assembloid-sync curate <ds>` | reopen the suite2p GUI on a dataset |
| `assembloid-sync status` | table of every dataset × stage |

| flag | effect |
|---|---|
| `--force` | redo stages already marked done |
| `--recurate` | permit rerunning a dataset whose cells were already curated |
| `--no-gui` | do not open the curation GUI at the end of `run` |
| `--all` | every eligible dataset under `data_root` |
| `--keep-going` | continue to the next dataset after a failure |
| `--assume-curated` | bypass the curation check |

### Trying it on a small dataset

`tools/make_test_dataset.py` truncates a real dataset's raw movie into a small,
ordinary dataset folder. It runs through the normal pipeline with no special flags, and
because it is its own folder with its own filenames, it can never collide with or
overwrite a real run's output:

```bash
python tools/make_test_dataset.py <source-dataset> <destination> --frames 300
assembloid-sync run <destination>
```

### Safety rails

- **`--recurate` and `--force` destroy manual curation.** Rerunning suite2p deletes
  `iscell.npy`; hours of human labor, not recomputable. The pipeline refuses by default.
- **`--all` skips datasets processed before this pipeline existed** (suite2p output but
  no pipeline state) and datasets that are already curated. Historical results cannot be
  clobbered by a batch command.
- **Every stage invalidates downstream state when it runs**, so a rerun can never leave
  stale results from an earlier configuration sitting on disk as the apparent answer.
- Running a single stage directly (`bin/run_<stage>.py`) bypasses the orchestrator's
  guards — it still clears downstream state, but use it deliberately.
- No concurrency lock: do not run two jobs against the same dataset at once.

---

## Architecture

Three conda environments that **cannot import each other** — CaImAn (3.10), suite2p
(3.9), analysis (3.13) — so the package is organized around a three-tier import rule:

```
assembloid_sync/
├── config.py  state.py  layout.py  preflight.py  entry.py   TIER 1: stdlib only, py3.9
│                                                            syntax, imports everywhere
├── stage_denoise.py    TIER 2: imports caiman   (function-local)
├── stage_fiji.py               subprocess only
├── stage_suite2p.py            imports suite2p  (function-local)
├── stage_roi.py  sync.py  plots.py   imports sklearn/scipy/seaborn
└── _sca_reference.py   GENERATED verbatim from the original analysis notebook
bin/         entry script per stage + the orchestrator
macros/      the ImageJ macro
notebooks/   interactive figure workflow (one copy, dataset as a variable)
tools/       reference extractor, notebook generator, Fiji equivalence check
```

Every heavy dependency is imported *inside a function*, so any module can be imported
anywhere; the orchestrator shells out with `conda run -n <env>` and never imports a
scientific package itself. `bin/` entry scripts all carry an `if __name__ == "__main__"`
guard — Windows spawn-based multiprocessing re-executes them in every worker.

State per dataset lives in `<dataset>/.assembloid-sync/state.json`; stages are idempotent
and skip when already done, so an interrupted run resumes by reissuing the same command.

---

## Requirements

- Python ≥3.9 on `PATH` for the orchestrator itself (any interpreter — it imports only
  the standard library; the scientific work happens inside the conda environments)
- Windows (the Fiji automation and process handling are Windows-specific)
- conda environments: CaImAn, suite2p (+ a CUDA-torch clone for GPU Cellpose), and an
  analysis env with numpy/scipy/scikit-learn/seaborn/tifffile
- Fiji/ImageJ
- NVIDIA GPU for Cellpose (optional — CPU works, far slower)

GPU support needs **two** changes, not one: a CUDA build of torch *and* a patch making
suite2p pass `gpu=True` to `CellposeModel` (0.14.4 hardcodes the CPU default). Installing
CUDA torch alone changes nothing.

## Installation / running elsewhere

The repo carries no machine-specific paths — `data_root`, conda env names and the
ImageJ/Fiji path all resolve at runtime instead of being hardcoded:

1. Clone the repo anywhere.
2. Copy `config.local.json.example` to `config.local.json` (gitignored) and fill in
   this machine's values: `data_root`, `envs` (the three conda env names), and
   optionally `fiji.imagej_exe` — if omitted, it's auto-discovered from common Fiji
   install locations and then `PATH`.
3. Run `./assembloid-sync status` (or `assembloid-sync.bat status` on Windows) to
   confirm it finds your datasets.

The wrappers call bare `python`, so it must be on `PATH` — on Windows, an Anaconda/
Miniconda Prompt (or any activated conda environment) is the easiest way to guarantee
that.

Two environment variables override the config file, useful for one-off runs or CI:
`ASSEMBLOID_SYNC_DATA_ROOT` and `ASSEMBLOID_SYNC_IMAGEJ`.

## Performance

~30 minutes end-to-end for 5400 frames at 512×512, versus ~5.5 hours manually. Per-stage
measurements in [`docs/timings.md`](docs/timings.md). suite2p is now dominated by TIFF→binary
conversion over network storage (~94% of its runtime), not by computation.

## Fidelity

This pipeline reproduces an existing manual workflow, and that claim is tested rather
than asserted:

- Fiji output is **pixel-identical** to hand-made output across all 5400 frames, with the
  auto-contrast display range matching to 7 significant figures
- the chunked writer is byte-equal to the original full-array reconstruction
- suite2p receives an ops dict differing from the archived settings in exactly
  `{fs, tau, data_path, save_path0}`, enforced by a test
- the synchronization analysis is extracted from the original notebook by AST and
  verified identical node-for-node; the vectorized cross-correlation is pinned against
  the original loop to 1e-10
- ROI counts reproduce the reference dataset's curated cell count exactly

Design rationale and decision history: [`docs/superpowers/specs/`](docs/superpowers/specs/)
and [`docs/superpowers/plans/`](docs/superpowers/plans/).

---

## References

**Tools this pipeline runs**

- CaImAn — Giovannucci A, et al. CaImAn: an open source tool for scalable calcium
  imaging data analysis. *eLife* 2019;8:e38173.
- CNMF-E — Zhou P, et al. Efficient and accurate extraction of in vivo calcium signals
  from microendoscopic video data. *eLife* 2018;7:e28728.
- suite2p — Pachitariu M, et al. Suite2p: beyond 10,000 neurons with standard
  two-photon microscopy. *bioRxiv* 2017:061507.
- Cellpose — Stringer C, Wang T, Michaelos M, Pachitariu M. Cellpose: a generalist
  algorithm for cellular segmentation. *Nature Methods* 2021;18:100–106.
- Cellpose3 (the `cyto3` model used here) — Stringer C, Pachitariu M. Cellpose3:
  one-click image restoration for improved cellular segmentation. *Nature Methods* 2025.
- Fiji — Schindelin J, et al. Fiji: an open-source platform for biological-image
  analysis. *Nature Methods* 2012;9:676–682.
- OASIS deconvolution — Friedrich J, Zhou P, Paninski L. Fast online deconvolution of
  calcium imaging data. *PLoS Computational Biology* 2017;13:e1005423.

**Methods implemented in the analysis**

- Synchronization Cluster Analysis / corrSYN — Patel TP, Man K, Firestein BL, Meaney DF.
  Automated quantification of neuronal networks and single-cell calcium dynamics using
  calcium imaging. *Journal of Neuroscience Methods* 2015;243:26–38.
- AAFT surrogate data — Theiler J, Eubank S, Longtin A, Galdrikian B, Farmer JD. Testing
  for nonlinearity in time series: the method of surrogate data. *Physica D*
  1992;58:77–94.
- jGCaMP8 indicator kinetics — Zhang Y, et al. Fast and sensitive GCaMP calcium
  indicators for imaging neural populations. *Nature* 2023;615:884–891.

A machine-readable version of the top citation is in [`CITATION.cff`](CITATION.cff).

---

## License

GPL-3.0 — see [LICENSE](LICENSE). This project imports CaImAn (GPL-2.0-or-later)
and suite2p (GPL-3.0); GPL-3.0 is the compatible license for the combined work.
Cellpose (BSD-3) and the remaining dependencies are permissively licensed.
