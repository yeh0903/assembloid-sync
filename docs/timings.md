# Measured timings — first automated full run

Dataset: `250528_B2_003` (5400 frames, 512×512), 2026-08-25. Manual baseline:
`250514_B2_000` file-timestamp reconstruction (same dims/frame count). The manual
detect+extract figure includes any idle time between the user's steps; the automated
figures are wall clock from logs/state timestamps.

| stage | manual baseline | automated | notes |
|---|---|---|---|
| CNMF-E denoise | "hours" (unmeasured) | **~13 min** | 30-worker cluster, chunked float32 writer |
| Fiji split (auto-B&C + sequence) | 4 min | **4 m 34 s** | GUI-mode macro, sentinel completion |
| suite2p binary conversion | 18 min | **12 m 18 s** (737.5 s) | I/O-bound: 5400 × 1 MB tifs read over Z: |
| suite2p detection (Cellpose) | — | **30 s** total; mask finding **4.4 s** | GPU (RTX A4000), 186-frame binned movie, 359 ROIs |
| suite2p extraction | — | **16 s** | 359 ROIs × 5400 frames |
| suite2p detect+extract combined | **~4 h 40 m** | **~47 s** | the campaign's headline number |
| ROI analysis (corrSYN + IOSI) | 25 min | ~1–2 min (measured at smoke scale) | vectorized IOSI; real-scale run pending curation |

**End-to-end `assembloid-sync run`: ~30 minutes** (denoise 13 m + fiji 4.5 m + suite2p 13 m),
vs ~5.5 h manual. Curation remains human; `assembloid-sync analyze` adds minutes.

Notable: suite2p is now dominated by tif→binary conversion over the network share
(94 % of its runtime). If that ever matters, `fast_disk` pointing at a local SSD or
feeding suite2p the BigTIFF directly (`tiff_list`) are the levers — deliberately not
taken now, to keep the manual-equivalent data path.

GPU evidence per run: `[suite2p] torch 2.6.0+cu124 cuda_available=True` in
`<ds>/.assembloid-sync/logs/suite2p.log`; detection block shows Cellpose mask timing.
