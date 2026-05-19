# Final n=3 keyframe experiment

Scope: all files are inside `C:\Users\ADMIN\Desktop\ff\final\facecheckin\test`. The original notebook `keyframe_pruning_ssim_laplacian_demo.ipynb` was not modified during this pass.

## Baseline issue

- Original formula `DeleteScore = redundancy * blur_badness` collapses to adjacent frames for `n=3`.
- Cross-check baseline: `[239, 240, 295]`, gaps `[1, 55]`.

## Formula direction tested

Temporal diversity delete score:

```text
quality_delete_i = floor + (1 - floor) * blur_badness_i
crowding_i = exp(-nearest_temporal_gap_i / temporal_tau)
coverage_safe_i = exp(-max(0, gap_after_delete_i - target_gap) / coverage_tau)
DeleteScore_i = redundancy_i * quality_delete_i * crowding_i * coverage_safe_i
```

This fixed temporal spread in the automatic pruning result, but direct visual inspection showed that some spread-out frames did not clearly contain the face.

## Final face-verified output

Final selected original frame indices:

```text
[22, 229, 538]
```

Timestamps:

```text
[0.736s, 7.661s, 17.999s]
```

Gaps:

```text
[207, 309]
```

Visual check: all three frames contain the user's face. The second and third frames are clear; the first frame is slightly blurred but face is still visible.

## Artifacts

- Notebook copy: `keyframe_pruning_ssim_laplacian_temporal_face_n3.ipynb`
- Final image: `selected_frames_grid_n3_face_verified.png`
- Metrics: `temporal_n3_final_metrics.json`
- Supporting image: `face_22_229_538.png`
