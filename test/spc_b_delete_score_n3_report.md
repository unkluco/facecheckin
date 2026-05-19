# Specialist B - n=3 delete_score proposal

## Proposed formula

For candidate frame `i` with current linked-list neighbors `l` and `r`:

```text
R_i = harmonic_mean(SSIM(F_l,F_i), SSIM(F_i,F_r))
B_i = 1 - PercentileRank(VarianceOfLaplacian(F_i))
S_i = 0.30 + 0.70 * B_i
D_i = 1.10                         if i is endpoint
D_i = 1 + 1.8 * (1 - min(1, (orig_r - orig_l) / video_span)) otherwise
DeleteScore_i = (R_i ^ 0.75) * S_i * D_i
```

Rationale: redundancy remains primary, sharpness becomes a soft preference instead of a hard veto, and `D_i` deletes frames from dense local clusters. Endpoints receive no density boost, but can still be deleted if blurry/redundant. This directly targets the failure mode where adjacent sharp frames survive as a small cluster.

## Results on demo_synthetic_10s.mp4

| Formula | Selected original frame indices | Gaps | Min gap | Output image |
|---|---:|---:|---:|---|
| Original `R * B` | [239, 240, 295] | [1, 55] | 1 | `spc_b_original_formula_n3.png` |
| Proposed balanced-density | [65, 295, 543] | [230, 248] | 230 | `spc_b_balanced_density_n3.png` |

## Visual clarity assessment

Original formula:
[
  {
    "original_frame": 239,
    "laplacian_variance": 114.1,
    "sharpness_rank": 0.996,
    "clarity": "clear object/face"
  },
  {
    "original_frame": 240,
    "laplacian_variance": 116.79,
    "sharpness_rank": 0.998,
    "clarity": "clear object/face"
  },
  {
    "original_frame": 295,
    "laplacian_variance": 124.46,
    "sharpness_rank": 1.0,
    "clarity": "clear object/face"
  }
]

Proposed balanced-density formula:
[
  {
    "original_frame": 65,
    "laplacian_variance": 36.43,
    "sharpness_rank": 0.902,
    "clarity": "clear object/face"
  },
  {
    "original_frame": 295,
    "laplacian_variance": 124.46,
    "sharpness_rank": 1.0,
    "clarity": "clear object/face"
  },
  {
    "original_frame": 543,
    "laplacian_variance": 22.67,
    "sharpness_rank": 0.812,
    "clarity": "clear object/face"
  }
]

Assessment: the proposed output keeps three temporally separated frames with no consecutive/local cluster. The synthetic face-like object is visible and clear in all selected frames; object/face features remain recognizable in the saved grid.

Artifacts are all written inside `test` only.
