# Cross-check keyframe pruning n=3

## Phạm vi

- Chỉ kiểm thử trong thư mục `test`.
- Không sửa notebook gốc `keyframe_pruning_ssim_laplacian_demo.ipynb`.
- Video demo: `demo_synthetic_10s.mp4`.
- Mục tiêu: kiểm tra với `n=3` liệu output có 3 frame cách xa nhau, phủ được video, và có object/face không.

## Kết quả chạy lại pipeline hiện tại

Thông số video đọc bằng OpenCV:

- Tổng frame: `544`
- FPS: `29.89`
- Thời lượng suy ra: `18.20s`

Frame được giữ bởi `compress_video_keyframes(..., n=3, similarity_scale=0.5, sharpness_scale=0.5)`:

| Rank | Frame | Time (s) | Laplacian variance |
|---:|---:|---:|---:|
| 1 | 239 | 7.996 | 114.10 |
| 2 | 240 | 8.029 | 116.79 |
| 3 | 295 | 9.869 | 124.46 |

Các metric phân bố thời gian:

| Metric | Giá trị | Nhận xét |
|---|---:|---|
| Gap frame | `[1, 55]` | Có 2 frame gần như trùng thời điểm |
| Gap giây | `[0.033s, 1.840s]` | Không đạt yêu cầu “cách xa nhau” |
| `min_gap_ratio` | `0.002` | Quá thấp cho `n=3` |
| `max_gap_ratio` | `0.101` | Cả 3 frame chỉ nằm trong vùng hẹp |
| `coverage_ratio = (last-first)/(T-1)` | `0.103` | Chỉ phủ khoảng 10.3% chiều dài video |
| `left_margin_ratio` | `0.440` | Bỏ gần nửa đầu video |
| `right_margin_ratio` | `0.457` | Bỏ gần nửa cuối video |

Kết luận định lượng: thuật toán hiện tại không có ràng buộc phân tán thời gian nên với `n=3` bị collapse vào cụm frame quanh giây `8-10`.

## Kiểm tra object/face

Đã kiểm tra 2 hướng:

1. Haar face detector của OpenCV.
2. Objectness proxy bằng vùng foreground/contour lớn so với nền.

Kết quả:

| Frame | Haar face | Object/foreground lớn | Nhận xét |
|---:|---:|---:|---|
| 239 | Không | Có contour lớn | Có object, chưa xác nhận face |
| 240 | Không | Có contour lớn | Gần trùng frame 239 |
| 295 | Có 3 bbox Haar | Có contour lớn | Có tín hiệu face/object rõ hơn |

Kết luận object/face: bộ 3 frame hiện tại có object, nhưng chỉ frame `295` có tín hiệu face rõ bằng Haar; `239` và `240` không nên cùng tồn tại vì gần trùng thời gian và thông tin.

## Tiêu chí định lượng nên dùng để phát hiện lỗi n=3

Với `T` là tổng số frame, `selected = [f1, f2, f3]` đã sort tăng dần:

### 1. Gap tối thiểu

```text
gaps = diff(selected)
min_gap_ratio = min(gaps) / (T - 1)
```

Khuyến nghị pass/fail:

- Hard fail nếu `min_gap_ratio < 0.20` với `n=3`.
- Tốt hơn nếu `min_gap_ratio >= 0.25`.

Trường hợp hiện tại: `0.002` → fail rõ ràng.

### 2. Coverage toàn video

```text
coverage_ratio = (max(selected) - min(selected)) / (T - 1)
```

Khuyến nghị pass/fail:

- Hard fail nếu `coverage_ratio < 0.60`.
- Tốt hơn nếu `coverage_ratio >= 0.70`.

Trường hợp hiện tại: `0.103` → fail rõ ràng.

### 3. Biên trái/phải không bị bỏ trống quá nhiều

```text
left_margin_ratio = min(selected) / (T - 1)
right_margin_ratio = (T - 1 - max(selected)) / (T - 1)
```

Khuyến nghị:

- Với `n=3`, mỗi margin nên `<= 0.25`, trừ khi cố ý không giữ đầu/cuối.

Trường hợp hiện tại: `0.440` và `0.457` → fail.

### 4. Object/face presence

Nên tính `object_score` hoặc `face_score` cho từng candidate:

```text
object_pass = object_area_ratio >= 0.002
face_pass = detector_confidence >= threshold hoặc haar_bbox_count > 0
```

Khuyến nghị:

- Nếu use case là check-in/face, ít nhất `2/3` frame nên có face pass.
- Nếu detector face không ổn định, dùng fallback objectness/foreground nhưng phải phạt frame không có face.

Trường hợp hiện tại: object có, nhưng face rõ chỉ `1/3` theo Haar.

## Đề xuất scoring/post-processing

Không nên chỉ greedy xóa theo redundancy/blur khi `n` nhỏ. Cần thêm bước chọn lại hoặc ràng buộc sau pruning.

### Phương án khuyến nghị: Temporal-diverse rerank

1. Chạy pipeline hiện tại để lấy nhiều candidate hơn, ví dụ `m = max(5*n, 12)`.
2. Tính score giữ frame:

```text
keep_score = quality_score
           + λ_object * object_or_face_score
           + λ_diverse * min_temporal_distance_to_selected
```

3. Chọn lần lượt bằng Maximal Marginal Relevance:

```text
score(candidate) = base_score(candidate)
                 + λ * normalized_distance_to_nearest_selected
                 - μ * similarity_to_nearest_selected
```

4. Enforce hard constraints:

```text
min_gap_ratio >= 0.20
coverage_ratio >= 0.60
left_margin_ratio <= 0.25
right_margin_ratio <= 0.25
```

### Phương án đơn giản cho n=3

Chia video thành 3 segment theo thời gian:

```text
[0, T/3), [T/3, 2T/3), [2T/3, T)
```

Trong mỗi segment chọn frame có:

```text
segment_score = sharpness_percentile
              + object_or_face_score
              - blur_badness
```

Ưu điểm: đảm bảo coverage và gap ngay lập tức. Nhược điểm: có thể bỏ qua đoạn có sự kiện quan trọng nếu sự kiện tập trung một vùng.

## Khuyến nghị cuối cùng

Với demo hiện tại, `n=3` của notebook không đạt tiêu chí keyframe đại diện vì chọn `[239, 240, 295]`, trong đó 2 frame gần như liền nhau và coverage chỉ `10.3%`. Nên thêm post-processing temporal diversity bắt buộc. Nếu cần sửa nhanh cho demo/check-in, dùng chia 3 segment và chọn frame tốt nhất có face/object trong mỗi segment; nếu cần tổng quát hơn, dùng rerank kiểu MMR với hard constraints `min_gap_ratio`, `coverage_ratio`, và `face/object_pass`.

