
from __future__ import annotations

import heapq
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import pandas as pd

from _experiment_base import (
    harmonic_mean,
    percentile_ranks,
    read_video_frames,
    ssim_score,
    to_gray_resized,
    variance_of_laplacian,
    compress_video_keyframes,
)


def compress_video_keyframes_temporal(
    video_path: str | Path,
    n: int,
    *,
    frame_stride: int = 1,
    max_frames: Optional[int] = None,
    similarity_scale: float = 0.5,
    sharpness_scale: float = 0.5,
    gaussian_preblur_for_laplacian: bool = False,
    temporal_tau_ratio: float = 0.55,
    coverage_tau_ratio: float = 0.35,
    endpoint_delete_multiplier: float = 0.15,
    min_blur_badness_floor: float = 0.08,
    verbose: bool = True,
) -> Dict[str, Any]:
    if n < 1:
        raise ValueError("n must be >= 1")

    frames_rgb, metadata = read_video_frames(video_path, frame_stride=frame_stride, max_frames=max_frames)
    T = len(frames_rgb)
    if n >= T:
        return compress_video_keyframes(video_path, n, frame_stride=frame_stride, max_frames=max_frames,
                                        similarity_scale=similarity_scale, sharpness_scale=sharpness_scale,
                                        gaussian_preblur_for_laplacian=gaussian_preblur_for_laplacian, verbose=verbose)

    sim_repr = [to_gray_resized(frame, scale=similarity_scale) for frame in frames_rgb]
    sharpness_raw = np.array([
        variance_of_laplacian(frame, scale=sharpness_scale, gaussian_preblur=gaussian_preblur_for_laplacian)
        for frame in frames_rgb
    ], dtype=float)
    sharpness_rank = percentile_ranks(sharpness_raw)
    blur_badness = 1.0 - sharpness_rank
    quality_delete = min_blur_badness_floor + (1.0 - min_blur_badness_floor) * blur_badness

    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    face_scores = []
    for frame in frames_rgb:
        gray_face = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        faces = cascade.detectMultiScale(gray_face, scaleFactor=1.08, minNeighbors=4, minSize=(40, 40))
        if len(faces) == 0:
            face_scores.append(0.0)
        else:
            h, w = gray_face.shape[:2]
            max_area = max(float(fw * fh) for (_, _, fw, fh) in faces)
            face_scores.append(min(1.0, max_area / float(h * w) / 0.03))
    face_scores = np.array(face_scores, dtype=float)

    original = metadata["original_frame_indices"]
    full_span = max(1, original[-1] - original[0])
    target_gap = max(1.0, full_span / max(1, n - 1))
    temporal_tau = max(1.0, temporal_tau_ratio * target_gap)
    coverage_tau = max(1.0, coverage_tau_ratio * target_gap)

    prev_idx: List[Optional[int]] = [None] + list(range(T - 1))
    next_idx: List[Optional[int]] = list(range(1, T)) + [None]
    alive = [True] * T
    version = [0] * T
    alive_count = T
    sim_cache: Dict[Tuple[int, int], float] = {}

    def pair_key(a: int, b: int) -> Tuple[int, int]:
        return (a, b) if a < b else (b, a)

    def get_pair_ssim(a: int, b: int) -> float:
        key = pair_key(a, b)
        if key not in sim_cache:
            sim_cache[key] = ssim_score(sim_repr[a], sim_repr[b])
        return sim_cache[key]

    def redundancy(i: int) -> float:
        if not alive[i]:
            return float("-inf")
        l, r = prev_idx[i], next_idx[i]
        if l is None and r is None:
            return float("-inf")
        if l is None:
            return get_pair_ssim(i, r)
        if r is None:
            return get_pair_ssim(l, i)
        return harmonic_mean(get_pair_ssim(l, i), get_pair_ssim(i, r))

    def temporal_terms(i: int) -> Tuple[float, float, float]:
        l, r = prev_idx[i], next_idx[i]
        if l is None and r is None:
            return 0.0, 0.0, 0.0
        if l is None or r is None:
            neighbor = r if l is None else l
            nearest_gap = abs(original[i] - original[neighbor])
            crowding = math.exp(-nearest_gap / temporal_tau)
            coverage_safe = endpoint_delete_multiplier
            created_gap_ratio = 0.0
        else:
            gap_left = original[i] - original[l]
            gap_right = original[r] - original[i]
            nearest_gap = min(gap_left, gap_right)
            gap_after_delete = original[r] - original[l]
            crowding = math.exp(-nearest_gap / temporal_tau)
            overflow = max(0.0, gap_after_delete - target_gap)
            coverage_safe = math.exp(-overflow / coverage_tau)
            created_gap_ratio = gap_after_delete / target_gap
        return float(crowding), float(coverage_safe), float(created_gap_ratio)

    def delete_score(i: int) -> float:
        red = redundancy(i)
        if not np.isfinite(red):
            return float("-inf")
        crowding, coverage_safe, _ = temporal_terms(i)
        face_protect = 1.0 - 0.85 * face_scores[i]
        return float(red * quality_delete[i] * crowding * coverage_safe * face_protect)

    heap: List[Tuple[float, int, int]] = []

    def push_candidate(i: Optional[int]) -> None:
        if i is None or not alive[i]:
            return
        score = delete_score(i)
        if np.isfinite(score):
            heapq.heappush(heap, (-score, i, version[i]))

    for i in range(T):
        push_candidate(i)

    deletion_records = []
    while alive_count > n:
        if not heap:
            raise RuntimeError("Heap empty")
        _, i, ver = heapq.heappop(heap)
        if not alive[i] or ver != version[i]:
            continue
        red = redundancy(i)
        if not np.isfinite(red):
            continue
        crowding, coverage_safe, created_gap_ratio = temporal_terms(i)
        face_protect = 1.0 - 0.85 * face_scores[i]
        score = float(red * quality_delete[i] * crowding * coverage_safe * face_protect)
        l, r = prev_idx[i], next_idx[i]
        deletion_records.append({
            "delete_order": len(deletion_records) + 1,
            "removed_internal_index": i,
            "removed_original_frame": original[i],
            "delete_score_temporal": score,
            "redundancy_hmean_ssim": red,
            "blur_badness": float(blur_badness[i]),
            "quality_delete": float(quality_delete[i]),
            "temporal_crowding": crowding,
            "coverage_safe": coverage_safe,
            "created_gap_ratio": created_gap_ratio,
        })
        alive[i] = False
        alive_count -= 1
        if l is not None:
            next_idx[l] = r
        if r is not None:
            prev_idx[r] = l
        for j in (l, r):
            if j is not None and alive[j]:
                version[j] += 1
                push_candidate(j)

    selected_indices_internal = [i for i in range(T) if alive[i]]
    result = {
        "selected_indices_internal": selected_indices_internal,
        "selected_original_frame_indices": [original[i] for i in selected_indices_internal],
        "selected_timestamps_sec": [metadata["timestamps_sec"][i] for i in selected_indices_internal],
        "selected_frames_rgb": [frames_rgb[i] for i in selected_indices_internal],
        "frame_metrics": pd.DataFrame({
            "internal_index": list(range(T)),
            "original_frame": original,
            "time_sec": metadata["timestamps_sec"],
            "kept": alive,
            "laplacian_variance": sharpness_raw,
            "laplacian_percentile_rank": sharpness_rank,
            "blur_badness": blur_badness,
            "face_score": face_scores,
        }),
        "deletion_log": pd.DataFrame(deletion_records),
        "metadata": metadata,
        "parameters": {
            "n": n,
            "frame_stride": frame_stride,
            "max_frames": max_frames,
            "similarity_scale": similarity_scale,
            "sharpness_scale": sharpness_scale,
            "temporal_tau_ratio": temporal_tau_ratio,
            "coverage_tau_ratio": coverage_tau_ratio,
            "endpoint_delete_multiplier": endpoint_delete_multiplier,
            "min_blur_badness_floor": min_blur_badness_floor,
            "target_gap_original_frames": target_gap,
        },
    }
    if verbose:
        print("Selected original frame indices:", result["selected_original_frame_indices"])
        print("Selected timestamps:", result["selected_timestamps_sec"])
    return result


def main() -> None:
    video = Path("demo_synthetic_10s.mp4")
    baseline = compress_video_keyframes(video, n=3, similarity_scale=0.5, sharpness_scale=0.5, verbose=False)
    temporal = compress_video_keyframes_temporal(video, n=3, verbose=False)
    print("baseline", baseline["selected_original_frame_indices"], baseline["selected_timestamps_sec"])
    print("temporal", temporal["selected_original_frame_indices"], temporal["selected_timestamps_sec"])
    print("params", temporal["parameters"])
    selected = temporal["frame_metrics"][temporal["frame_metrics"]["kept"]]
    print(selected[["internal_index", "original_frame", "time_sec", "laplacian_variance", "laplacian_percentile_rank", "blur_badness"]].to_string(index=False))
    temporal["deletion_log"].tail(10).to_csv("temporal_diversity_deletion_tail.csv", index=False)


if __name__ == "__main__":
    main()
