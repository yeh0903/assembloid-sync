# Setup — from scratch

A from-scratch guide for a machine that has none of this installed yet. Follow the
sections in order; each one assumes the previous ones are done.

---

## 1. What you need

- **Windows.** The Fiji automation (driving ImageJ's macro recorder output and
  waiting on its process) and the process-handling in `bin/pipeline.py` are
  Windows-specific. This is a real platform constraint, not just an untested path.
- **An NVIDIA GPU** — optional but strongly recommended. Cell detection (Cellpose)
  is the one stage where CPU vs GPU makes an order-of-magnitude difference; see
  [§5](#5-gpu-optional).
- **~25 GB free** on the drive holding each dataset while it's being processed
  (denoise memmap + reconstructed movie + per-frame sequence + suite2p binary, all
  coexisting temporarily; `preflight` checks for at least 20 GB and refuses to start
  a run without it).

---

## 2. Miniconda

Install Miniconda from <https://docs.conda.io/en/latest/miniconda.html> (the full
Anaconda distribution also works; Miniconda is smaller). Every command below assumes
it's run from an **Anaconda Prompt / Miniconda Prompt** (or any shell where `conda`
and `python` are on `PATH`) — the wrapper scripts call bare `python`, so a plain
`cmd.exe`/PowerShell window that hasn't had conda's hooks initialized won't find it.

---

## 3. The three environments

This pipeline shells out across three conda environments with mutually incompatible
Python versions and dependency sets — they cannot be merged into one. From the repo
root:

```bash
conda env create -f envs/caiman.yml     # -> "caiman_env"   Python 3.10, CaImAn/CNMF-E
conda env create -f envs/suite2p.yml    # -> "suite2p_gpu"  Python 3.9,  suite2p + Cellpose
conda env create -f envs/analysis.yml   # -> "code"         Python 3.13, the ROI/sync analysis
```

**CaImAn is the slowest to install** — its conda-forge package pulls in a large
scientific stack (Jupyter, TensorFlow, PyQt5, ...), so budget a solid chunk of time
for `envs/caiman.yml` alone; the other two pull comparatively few conda packages and
resolve most of their dependencies through pip, so they're faster once conda's
solver finishes — except that `envs/suite2p.yml` also pip-installs `torch`, which is
a multi-hundred-MB-to-multi-GB download depending on whether you take the CPU or
CUDA build (see [§5](#5-gpu-optional)). None of these times were stopwatched on the
reference machine (the environments already existed there); treat them as rough,
connection-speed-dependent expectations, not measurements.

These three names — `caiman_env`, `suite2p_gpu`, `code` — are what [§6](#6-configure)
tells the pipeline to use. Rename them if you like, as long as `config.local.json`
matches.

---

## 4. Fiji

Download and install Fiji from <https://fiji.sc>. No configuration is needed if you
install to one of the locations the pipeline already checks:

```
C:\Program Files\fiji-win64\Fiji.app\ImageJ-win64.exe
C:\Program Files\Fiji.app\ImageJ-win64.exe
C:\Fiji.app\ImageJ-win64.exe
```

Installed somewhere else? Set `fiji.imagej_exe` in `config.local.json` ([§6](#6-configure))
or the `ASSEMBLOID_SYNC_IMAGEJ` environment variable to the full path of
`ImageJ-win64.exe`. If neither is set and none of the default locations exist, the
pipeline also falls back to searching `PATH`.

---

## 5. GPU (optional)

The pipeline runs without a GPU — Cellpose just falls back to CPU, correctly, only
much slower. On the reference machine, GPU cell detection (Cellpose, RTX A4000) took
roughly **4 seconds**; the same step on CPU was the multi-hour bottleneck of the
original manual workflow. If you have an NVIDIA GPU, it's worth the two extra steps
below.

GPU support needs **two separate changes** — installing a CUDA build of torch alone
is not enough, because suite2p 0.14.4 constructs Cellpose's model without asking for
the GPU, so it silently stays on CPU even when CUDA torch is present.

**1. Install CUDA torch into the suite2p environment**, replacing whatever `torch`
`envs/suite2p.yml` installed by default:

```bash
conda activate suite2p_gpu
pip install torch==2.6.0+cu124 --index-url https://download.pytorch.org/whl/cu124
```

Use whichever CUDA version matches your driver — see the version selector at
<https://pytorch.org/get-started/locally/> if `cu124` isn't right for your GPU.

**2. Patch suite2p to actually pass `gpu=True` to Cellpose:**

```bash
python tools/patch_suite2p_gpu.py suite2p_gpu
python tools/patch_suite2p_gpu.py suite2p_gpu --check
```

The patch rewrites the two `CellposeModel(...)` construction sites in **the
installed suite2p package itself** — `detection/anatomical.py` inside
`suite2p_gpu`'s `site-packages`, not anything in this repo — adding `gpu=True` to
each. It keeps a `.orig` backup the first time it patches, and `--revert` restores
from that backup:

```bash
python tools/patch_suite2p_gpu.py suite2p_gpu --revert
```

Running the patch again when it's already patched is a no-op (it says so and exits).
`--check` never modifies anything; it just reports whether the file is patched and
prints `torch.cuda.is_available()` from that environment, which is the fastest way
to confirm both halves (CUDA torch + the patch) are actually in place.

---

## 6. Configure

Copy the example config and fill in this machine's values:

```bash
copy config.local.json.example config.local.json
```

```json
{
  "data_root": "D:\\path\\to\\your\\datasets",
  "envs": { "caiman": "caiman_env", "suite2p": "suite2p_gpu", "code": "code" },
  "fiji": { "imagej_exe": "C:\\Program Files\\Fiji.app\\ImageJ-win64.exe" }
}
```

`data_root` is the folder containing your dataset subfolders. The three `envs`
values must match whatever you named the environments in [§3](#3-the-three-environments)
(shown here matching the defaults used throughout this guide). `fiji.imagej_exe` can
be omitted if Fiji is in one of the auto-discovered locations from [§4](#4-fiji).

`config.local.json` is gitignored on purpose — it's machine-specific and never
committed. Two environment variables cover the same two most-common overrides
without a config file at all: `ASSEMBLOID_SYNC_DATA_ROOT` and
`ASSEMBLOID_SYNC_IMAGEJ`.

---

## 7. Verify

```bash
assembloid-sync.bat status
```

This should print a table — one row per dataset folder under `data_root`, or just
the header row if `data_root` is empty. Either is fine; it means the pipeline can
see your data root and its config resolves correctly.

Then run the test suite (no conda environment or dataset needed — it's pure
standard-library-and-stdlib-adjacent logic):

```bash
python -m pytest -q
```

---

## 8. First run on a small dataset

`tools/make_test_dataset.py` truncates a real dataset's raw movie into a small,
disposable dataset folder that runs through the pipeline exactly like a real one
(same filenames, same code path — no special "test mode"), so it can never collide
with or overwrite real output. It needs `numpy` and `tifffile`, both already present
in `caiman_env`:

```bash
conda activate caiman_env
python tools/make_test_dataset.py <a-real-dataset> <somewhere-local> --frames 300
conda deactivate
```

Then run the pipeline on it exactly as you would on real data:

```bash
assembloid-sync.bat run <somewhere-local>
```

Expect, in order: CNMF-E denoise (`caiman_env`) — brief on 300 frames — then Fiji
contrast/export, then suite2p binary conversion and Cellpose detection
(`suite2p_gpu`). All three stages log to `<somewhere-local>/.assembloid-sync/logs/`.
`run` then opens the suite2p curation GUI; accept or reject the detected cells, save,
and close it. Finally:

```bash
assembloid-sync.bat analyze <somewhere-local>
```

computes corrSYN/IOSI and writes `roi_results.json` plus the correlation and ROI
figures into `<somewhere-local>`.

---

## 9. Using data from other acquisition software

Everything above assumes ThorImage's file layout: a raw TIFF named
`Image_scan_1_region_0_0.tif` and metadata in `Experiment.xml` (which is also where
the frame rate is read from). None of that is hardcoded — three config keys cover a
different acquisition system:

```json
{
  "input": { "raw_tif": "my_movie.tif", "metadata_xml": null },
  "frame_rate": 30.0
}
```

Set these in `config.local.json` if every dataset on your machine uses the same
non-ThorImage naming, or in a specific dataset's own `assembloid-sync.json` for a
one-off. `input.raw_tif` is the raw movie filename to look for inside each dataset
folder; `input.metadata_xml` is the metadata filename. Leave either `null` to keep
the ThorImage default for that one.

If your acquisition software doesn't produce a ThorImage-style XML at all, set
`input.metadata_xml` to `null` (or leave it) and **set `frame_rate` explicitly** —
without a metadata file to read `LSM/@frameRate` from, the pipeline has no other way
to know your sampling rate, and `resolve_frame_rate` will raise a clear error naming
exactly which file it looked for and didn't find.

One assumption is baked further into the analysis than a config key: it expects
**two spatially separable organoids in one field of view** (the ROI-to-organoid
assignment is a 2-component Gaussian mixture over centroid position). A single-
organoid or single-region recording will still run through denoise/detection/
extraction, but the organoid-pair-specific parts of the analysis — the IOSI
cross-organoid coupling metric in particular — assume that layout and won't be
meaningful without it.

---

## 10. Troubleshooting

**`'python' is not recognized...` / `'conda' is not recognized...`**
You're not in an Anaconda/Miniconda Prompt, or conda's shell hooks were never
initialized for this shell. Open "Anaconda Prompt" from the Start menu, or run
`conda init` once and restart your shell.

**`conda env 'X' not runnable: ...`**
`preflight` checks each configured environment with a one-line `conda run` before
committing to a multi-hour stage, and names the broken one directly in this message.
Confirm the name matches an environment `conda env list` actually shows, and that it
matches what's in `config.local.json`'s `envs` block.

**`ImageJ/Fiji not found - set fiji.imagej_exe in config.local.json or the ASSEMBLOID_SYNC_IMAGEJ env var`**
None of the auto-discovered locations ([§4](#4-fiji)) exist and Fiji isn't on `PATH`
either. Set one of the two options the message names.

**`cuda_available=False` in `<dataset>/.assembloid-sync/logs/suite2p.log`**
GPU Cellpose isn't active. The suite2p stage logs a line like
`[suite2p] torch 2.6.0+cu124 cuda_available=True` when everything's working; `False`
means either the CUDA build of torch isn't installed in `suite2p_gpu`, or the GPU
patch hasn't been applied — redo both steps in [§5](#5-gpu-optional), then confirm
with `python tools/patch_suite2p_gpu.py suite2p_gpu --check` (it prints
`torch.cuda.is_available()` directly, which is faster to check than digging through
a log). Note that CPU-mode Cellpose is *correct*, just slow — this isn't a failure,
just a missed optimization.

**`Data root does not exist: <path> / Set data_root in config.local.json or the ASSEMBLOID_SYNC_DATA_ROOT environment variable.`**
`data_root` in `config.local.json` (or `ASSEMBLOID_SYNC_DATA_ROOT`) points somewhere
that doesn't exist on this machine — typically a stale path copied from another
machine, or a network drive that isn't currently mapped. Fix the path or map the
drive.
