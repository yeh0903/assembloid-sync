# Measured timings — first automated full run

Dataset: `250528_B2_003` (5400 frames, 512×512), 2026-08-25. Manual baseline:
`250514_B2_000` file-timestamp reconstruction (same dims/frame count). The manual
detect+extract figure includes any idle time between the user's steps; the automated
figures are wall clock from logs/state timestamps.

| stage | manual baseline | automated | notes |
|---|---|---|---|
| CNMF-E denoise | "hours" (unmeasured) | **3.5 min** (fit 155 s + write 45 s) | 31-worker cluster, chunked float32 writer |
| Fiji split (auto-B&C + sequence) | 4 min | **4 m 34 s** | GUI-mode macro, sentinel completion |
| suite2p binary conversion | 18 min | **12 m 18 s** (737.5 s) | I/O-bound: 5400 × 1 MB tifs read over Z: |
| suite2p detection (Cellpose) | — | **30 s** total; mask finding **4.4 s** | GPU (RTX A4000), 186-frame binned movie, 359 ROIs |
| suite2p extraction | — | **16 s** | 359 ROIs × 5400 frames |
| suite2p detect+extract combined | **~4 h 40 m** | **~47 s** | the campaign's headline number |
| ROI analysis (corrSYN + IOSI) | 25 min | ~1–2 min (on a 300-frame test dataset) | vectorized IOSI; full-length run pending curation |

**End-to-end `assembloid-sync run`: ~21 minutes** (denoise 3.5 m + fiji 4.5 m + suite2p 13 m),
vs ~5.5 h manual. Curation remains human; `assembloid-sync analyze` adds minutes.

Notable: suite2p is dominated by tif→binary conversion (94 % of its runtime).

**Correction (2026-08-27):** an earlier version of this note called `Z:` a network
share. It is not — `Z:` is a *local* 29 TB NTFS volume (`DriveType 3`) on a 3-disk
RAID5 array of ST16000DM001 HDDs. The cost is disk seek, not network latency.

GPU evidence per run: `[suite2p] torch 2.6.0+cu124 cuda_available=True` in
`<ds>/.assembloid-sync/logs/suite2p.log`; detection block shows Cellpose mask timing.

## Denoise fidelity vs the original notebook

Measured directly (2026-08-26), running this pipeline's denoise on a copy of
`250514_B2_000`'s raw input and comparing against the movie that dataset's own
`denoise.ipynb` produced. Sampled every 20th frame; M = notebook output,
B = this pipeline with the notebook's parameters, A = this pipeline's defaults.

| check | result |
|---|---|
| B vs M, per-frame Pearson r | 0.99999990 / 0.99999998 / 0.99999998 (min/median/max) |
| B vs M, pixels within 0.1% relative | 99.81 % |
| A vs M, mean abs difference | 0.0071 (M dynamic range 12,588) |
| variance explained vs raw — M / B / A | 0.385285 / 0.385285 / 0.385285 |
| residual spatial autocorrelation — M / B / A | 0.010806 / 0.010806 / 0.010806 |
| per-pixel temporal-σ image, A vs M | 0.99999994 |

Conclusion: this pipeline reproduces the notebook's denoise. Residual differences
are floating-point reduction-order noise, not algorithmic divergence — CNMF-E is
deterministic in practice but not bit-exact. Information content relative to the
raw movie is identical to four significant figures, and the temporal-σ image
(the closest proxy for what Cellpose detection consumes) matches to seven nines.

Note: `write_denoised` reconstructs from **all** fitted components (`A@C + b@f`)
and `fit()` never calls `evaluate_components()`, so `decay_time` reaches the
output only through AR(2) deconvolution — which is why the parameter change is
barely visible above. The same is true of the original notebook, whose cells this
mirrors; `min_SNR`, `rval_thr`, `use_cnn`, `cnn_thr` and `min_fitness_raw` are
passed to CNMF-E but unused on this code path in both.

## Batch throughput and free-space fragmentation (2026-08-27 campaign)

Eleven B2/C3 datasets, 5400 frames each, run back-to-back on one machine.
Per-stage minutes, in execution order:

| # | dataset | denoise | fiji | suite2p | total |
|---|---|---|---|---|---|
| 1 | 250521_B2_001 | 10.0 | 6.2 | 8.3 | 24.5 |
| 2 | 250605_B2_001 | 9.0 | 6.2 | 8.6 | 23.8 |
| 3 | 250611_B2_001 | 9.0 | 6.4 | 6.4 | 21.8 |
| 4 | 250618_B2_003 | 8.9 | 6.4 | 6.3 | 21.6 |
| 5 | 250703_B2_007 | 7.1 | 6.7 | 11.2 | 24.9 |
| 6 | 250521_C3_002 | 6.5 | 6.7 | 13.1 | 26.2 |
| 7 | 250528_C3_003 | 6.3 | 6.6 | 18.7 | 31.7 |

**suite2p degrades monotonically across a batch; Fiji does not.** The cost is
entirely in tif→binary conversion — 335 s on dataset 4 versus 1031 s on dataset 7
for byte-identical work (5400 frames), a 3.1x slowdown. Detection and extraction
scale the same way (2.84 → 6.36 s, 8.70 → 23.25 s), so it is the volume, not a
code path.

Diagnosis: Fiji *writes* those 5400 files and its time never moves (6.2 → 6.6 min),
because write-behind caching hides seek cost and writes go to whatever free space
exists. suite2p *reads* them back. As each dataset adds ~14 GB (5400 × 1 MB frames,
a 5.3 GB BigTIFF, a 2.8 GB binary), Z:'s free space fragments, newly written frames
land scattered, and reading them becomes seek-bound on RAID5. Every dataset makes
the next one worse.

Ruled out by measurement, not assumption: CPU (5 % during denoise), RAM (154 GB
free throughout, flat across dataset boundaries), other users on this shared
machine (all sessions idle 15 h+), and disk health (all disks `Healthy`, no
rebuild in progress, 16.8 TB free).

### Levers, untested

Listed in expected-value order. None has been measured — do that before trusting
the estimates.

1. **Put `<ds>/caiman` on flash** (directory junction, or a layout change). Targets
   the actual bottleneck: the 5400-file write-then-read cycle. Caveat: the suite2p
   output the human curates would then live off the data volume, which matters if
   that volume is what gets backed up.
2. **suite2p `fast_disk`** on flash. Moves only the 2.8 GB binary write. Cheaper to
   adopt (`suite2p.ops_overrides` already exists), smaller win, and the GUI then
   depends on the recorded `reg_file` path.
3. **`denoise.scratch_dir`** on flash — implemented, see config.local.json.example.
   Moves CNMF-E's ~5.7 GB memmap off the data volume. Tried mid-campaign at
   dataset 6; denoise was already trending down for unrelated reasons, so the
   change is **not credited with a measured gain**. Sound in principle, unproven
   in practice.
4. **Defragment the data volume** between campaigns.

Running datasets concurrently is *not* on this list: the bottleneck volume is
already saturated, so it would divide the same bandwidth. It would also need
`-port0` on the Fiji invocation, since ImageJ's single-instance listener otherwise
forwards a second instance's macro to the first.
