# Specialist A ? Temporal Diversity Delete Score Experiment

Scope: ch? th? nghi?m trong th? m?c `test`, kh?ng s?a notebook g?c.

## Baseline quan s?t

Notebook g?c d?ng:

```text
redundancy_i = harmonic_mean(SSIM(left, i), SSIM(i, right))
blur_badness_i = 1 - laplacian_percentile_rank_i
delete_score_i = redundancy_i * blur_badness_i
```

Ch?y nhanh v?i `n=3`, `similarity_scale=0.5`, `sharpness_scale=0.5` tr?n `demo_synthetic_10s.mp4` cho output baseline: `[239, 240, 295]` t??ng ?ng kho?ng `[8.00s, 8.03s, 9.87s]`. K?t qu? n?y qu? c?m v? th?i gian.

## C?ng th?c ?? xu?t

Th?m temporal diversity v?o score theo h??ng: x?a m?nh frame n?m trong v?ng qu? d?y, nh?ng ph?t vi?c x?a frame n?u n? l?m m?t coverage th?i gian.

```text
quality_delete_i = floor + (1 - floor) * blur_badness_i
crowding_i = exp(- nearest_temporal_gap_i / temporal_tau)
coverage_safe_i = exp(- max(0, gap_after_delete_i - target_gap) / coverage_tau)

delete_score_i = redundancy_i * quality_delete_i * crowding_i * coverage_safe_i
```

V?i endpoint:

```text
coverage_safe_i = endpoint_delete_multiplier
```

? ngh?a:

- `redundancy_i`: v?n ?u ti?n x?a frame gi?ng h?ng x?m.
- `quality_delete_i`: v?n ?u ti?n x?a frame m?, nh?ng c? `floor` ?? frame r?t s?c v?n c? th? b? x?a n?u qu? d? th?a theo th?i gian.
- `crowding_i`: c?ng g?n frame h?ng x?m th? c?ng d? x?a, gi?p c?c frame c?n l?i gi?n xa.
- `coverage_safe_i`: n?u x?a m?t frame t?o gap l?n h?n `target_gap`, score gi?m, tr?nh m?t coverage.

## Tham s? th? nghi?m t?t nh?t

```text
n = 3
similarity_scale = 0.5
sharpness_scale = 0.5
target_gap = full_span / (n - 1) = 271.5 original frames
temporal_tau_ratio = 0.55  => temporal_tau ~= 149.3 frames
coverage_tau_ratio = 0.35  => coverage_tau ~= 95.0 frames
endpoint_delete_multiplier = 0.25
min_blur_badness_floor = 0.08
```

## K?t qu? selected original frame indices

```text
selected_original_frame_indices = [46, 295, 543]
selected_timestamps_sec = [1.539, 9.869, 18.167]
```

Metric c?c frame ???c gi?:

```text
 internal_index  original_frame  time_sec  laplacian_variance  laplacian_percentile_rank  blur_badness
             46              46  1.538971           52.629722                   0.933702      0.066298
            295             295  9.869485          124.464557                   1.000000      0.000000
            543             543 18.166544           22.668194                   0.812155      0.187845
```

?nh ki?m tra nhanh: `temporal_diversity_selected_n3.png`.

## Nh?n x?t

- Ph? h?p m?c ti?u temporal diversity h?n baseline: kho?ng c?ch gi?a 3 frame l? 249 v? 248 original frames, thay v? baseline c? 2 frame g?n nh? li?n nhau `[239, 240]`.
- C?c frame ???c gi? c? object/m?t ho?t h?nh r?; Laplacian percentile rank l?n l??t kho?ng `0.934`, `1.000`, `0.812`, t?c ??u kh?ng thu?c nh?m m?.
- Trade-off: n?u t?ng `endpoint_delete_multiplier` l?n `0.6-1.0`, k?t qu? th?nh `[46, 295, 505]` s?c h?n ? frame cu?i nh?ng coverage cu?i video k?m h?n. V?i m?c ti?u ?c?ch xa nhau theo th?i gian?, ch?n `[46, 295, 543]` c?n b?ng h?n.
