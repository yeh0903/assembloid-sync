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

Notable: suite2p is now dominated by tif→binary conversion over the network share
(94 % of its runtime). If that ever matters, `fast_disk` pointing at a local SSD or
feeding suite2p the BigTIFF directly (`tiff_list`) are the levers — deliberately not
taken now, to keep the manual-equivalent data path.

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
