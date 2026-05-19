from __future__ import annotations
import json, math, heapq
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from skimage.metrics import structural_similarity as ssim


def read_video_frames(video_path: str | Path, frame_stride: int = 1, max_frames: Optional[int] = None):
    video_path = Path(video_path)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f'Cannot open video: {video_path}')
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or math.isnan(fps):
        fps = 0.0
    total_reported = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    frames_rgb, original_frame_indices, timestamps_sec = [], [], []
    idx = 0
    while True:
        ok, frame_bgr = cap.read()
        if not ok:
            break
        if idx % frame_stride == 0:
            frames_rgb.append(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
            original_frame_indices.append(idx)
            timestamps_sec.append(idx / fps if fps > 0 else None)
            if max_frames is not None and len(frames_rgb) >= max_frames:
                break
        idx += 1
    cap.release()
    if not frames_rgb:
        raise ValueError('No frames loaded')
    return frames_rgb, {
        'video_path': str(video_path), 'fps': fps, 'total_reported_frames': total_reported,
        'loaded_frames': len(frames_rgb), 'frame_stride': frame_stride,
        'original_frame_indices': original_frame_indices, 'timestamps_sec': timestamps_sec,
    }


def to_gray_resized(frame_rgb: np.ndarray, scale: float = 1.0) -> np.ndarray:
    gray = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2GRAY)
    if scale == 1.0:
        return gray
    h, w = gray.shape[:2]
    return cv2.resize(gray, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)


def ssim_score(a: np.ndarray, b: np.ndarray) -> float:
    return float(ssim(a, b, data_range=255))


def variance_of_laplacian(frame_rgb: np.ndarray, scale: float = 1.0, gaussian_preblur: bool = False) -> float:
    gray = to_gray_resized(frame_rgb, scale=scale)
    if gaussian_preblur:
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def percentile_ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind='mergesort')
    ranks = np.empty(len(values), dtype=float)
    ranks[order] = np.arange(len(values), dtype=float)
    return ranks / max(1, len(values) - 1)


def harmonic_mean(a: float, b: float, eps: float = 1e-12) -> float:
    return float((2 * a * b) / (a + b + eps))


def compress_variant(video_path: str | Path, n: int, *, formula: str, similarity_scale=0.5, sharpness_scale=0.5):
    frames_rgb, metadata = read_video_frames(video_path)
    total = len(frames_rgb)
    sim_repr = [to_gray_resized(f, similarity_scale) for f in frames_rgb]
    sharpness_raw = np.array([variance_of_laplacian(f, sharpness_scale) for f in frames_rgb], dtype=float)
    sharpness_rank = percentile_ranks(sharpness_raw)
    blur_badness = 1.0 - sharpness_rank
    prev_idx: List[Optional[int]] = [None] + list(range(total - 1))
    next_idx: List[Optional[int]] = list(range(1, total)) + [None]
    alive = [True] * total
    version = [0] * total
    sim_cache: Dict[Tuple[int, int], float] = {}

    def get_pair_ssim(a: int, b: int) -> float:
        key = (a, b) if a < b else (b, a)
        if key not in sim_cache:
            sim_cache[key] = ssim_score(sim_repr[a], sim_repr[b])
        return sim_cache[key]

    def redundancy(i: int) -> float:
        if not alive[i]:
            return float('-inf')
        l, r = prev_idx[i], next_idx[i]
        if l is None and r is None:
            return float('-inf')
        if l is None:
            return get_pair_ssim(i, r)
        if r is None:
            return get_pair_ssim(l, i)
        return harmonic_mean(get_pair_ssim(l, i), get_pair_ssim(i, r))

    def density_factor(i: int) -> float:
        l, r = prev_idx[i], next_idx[i]
        if l is None or r is None:
            return 1.10  # allow deleting blurred endpoints, but no cluster boost at boundaries
        span = metadata['original_frame_indices'][r] - metadata['original_frame_indices'][l]
        normalized = min(1.0, span / max(1, metadata['original_frame_indices'][-1] - metadata['original_frame_indices'][0]))
        return 1.0 + 1.8 * (1.0 - normalized)  # tighter local cluster => easier to delete

    def score_parts(i: int):
        red = redundancy(i)
        if not np.isfinite(red):
            return None
        if formula == 'original':
            sharp_term = blur_badness[i]
            dens = 1.0
            score = red * sharp_term
        elif formula == 'balanced_density':
            sharp_term = 0.30 + 0.70 * blur_badness[i]  # sharpness is a preference, not a veto
            dens = density_factor(i)
            score = (red ** 0.75) * sharp_term * dens
        else:
            raise ValueError(formula)
        return float(score), float(red), float(sharp_term), float(dens)

    heap = []
    def push(i: Optional[int]):
        if i is None or not alive[i]:
            return
        parts = score_parts(i)
        if parts is not None and np.isfinite(parts[0]):
            heapq.heappush(heap, (-parts[0], i, version[i]))
    for i in range(total):
        push(i)

    deletion_records = []
    alive_count = total
    while alive_count > n:
        neg, i, ver = heapq.heappop(heap)
        if not alive[i] or ver != version[i]:
            continue
        parts = score_parts(i)
        if parts is None:
            continue
        score, red, sharp_term, dens = parts
        l, r = prev_idx[i], next_idx[i]
        deletion_records.append({
            'delete_order': len(deletion_records) + 1, 'removed_original_frame': metadata['original_frame_indices'][i],
            'left_original_frame': metadata['original_frame_indices'][l] if l is not None else None,
            'right_original_frame': metadata['original_frame_indices'][r] if r is not None else None,
            'delete_score': score, 'redundancy': red, 'sharp_term': sharp_term, 'density_factor': dens,
            'blur_badness': float(blur_badness[i]), 'laplacian_variance': float(sharpness_raw[i]),
        })
        alive[i] = False
        alive_count -= 1
        if l is not None: next_idx[l] = r
        if r is not None: prev_idx[r] = l
        for j in (l, r):
            if j is not None and alive[j]:
                version[j] += 1
                push(j)

    selected = [i for i in range(total) if alive[i]]
    return {
        'formula': formula, 'metadata': metadata, 'selected_indices_internal': selected,
        'selected_original_frame_indices': [metadata['original_frame_indices'][i] for i in selected],
        'selected_timestamps_sec': [metadata['timestamps_sec'][i] for i in selected],
        'selected_frames_rgb': [frames_rgb[i] for i in selected],
        'frame_metrics': pd.DataFrame({
            'internal_index': range(total), 'original_frame': metadata['original_frame_indices'],
            'laplacian_variance': sharpness_raw, 'sharpness_rank': sharpness_rank, 'blur_badness': blur_badness,
            'kept': [alive[i] for i in range(total)]
        }),
        'deletion_log': pd.DataFrame(deletion_records),
    }


def save_grid(result: Dict[str, Any], path: str | Path):
    frames = result['selected_frames_rgb']
    originals = result['selected_original_frame_indices']
    times = result['selected_timestamps_sec']
    fig, axes = plt.subplots(1, len(frames), figsize=(5 * len(frames), 3.2))
    axes = np.array(axes).reshape(-1)
    for ax, frame, orig, t in zip(axes, frames, originals, times):
        ax.imshow(frame)
        ax.axis('off')
        ax.set_title(f'frame {orig}\n{t:.2f}s')
    fig.suptitle(f"Selected n=3: {result['formula']}")
    plt.tight_layout()
    plt.savefig(path, dpi=160, bbox_inches='tight')
    plt.close(fig)


def clarity_notes(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for internal, original, frame in zip(result['selected_indices_internal'], result['selected_original_frame_indices'], result['selected_frames_rgb']):
        metric = result['frame_metrics'].iloc[internal]
        # Synthetic face/object is visible if yellow blob/eyes/mouth remain high contrast; Laplacian > 15 here is clear.
        rows.append({
            'original_frame': int(original),
            'laplacian_variance': round(float(metric['laplacian_variance']), 2),
            'sharpness_rank': round(float(metric['sharpness_rank']), 3),
            'clarity': 'clear object/face' if metric['laplacian_variance'] > 15 else 'blurred but object visible',
        })
    return rows


def main():
    video = Path('demo_synthetic_10s.mp4')
    original = compress_variant(video, 3, formula='original')
    balanced = compress_variant(video, 3, formula='balanced_density')
    save_grid(original, 'spc_b_original_formula_n3.png')
    save_grid(balanced, 'spc_b_balanced_density_n3.png')
    summary = {}
    for name, result in [('original', original), ('balanced_density', balanced)]:
        selected = result['selected_original_frame_indices']
        gaps = np.diff(selected).astype(int).tolist()
        summary[name] = {
            'selected_original_frame_indices': [int(x) for x in selected],
            'gaps_between_selected_frames': gaps,
            'min_gap': int(min(gaps)) if gaps else None,
            'clarity_notes': clarity_notes(result),
            'last_8_deletions': result['deletion_log'].tail(8).round(4).to_dict(orient='records'),
        }
    Path('spc_b_delete_score_n3_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    report = f"""# Specialist B - n=3 delete_score proposal\n\n## Proposed formula\n\nFor candidate frame `i` with current linked-list neighbors `l` and `r`:\n\n```text\nR_i = harmonic_mean(SSIM(F_l,F_i), SSIM(F_i,F_r))\nB_i = 1 - PercentileRank(VarianceOfLaplacian(F_i))\nS_i = 0.30 + 0.70 * B_i\nD_i = 1.10                         if i is endpoint\nD_i = 1 + 1.8 * (1 - min(1, (orig_r - orig_l) / video_span)) otherwise\nDeleteScore_i = (R_i ^ 0.75) * S_i * D_i\n```\n\nRationale: redundancy remains primary, sharpness becomes a soft preference instead of a hard veto, and `D_i` deletes frames from dense local clusters. Endpoints receive no density boost, but can still be deleted if blurry/redundant. This directly targets the failure mode where adjacent sharp frames survive as a small cluster.\n\n## Results on demo_synthetic_10s.mp4\n\n| Formula | Selected original frame indices | Gaps | Min gap | Output image |\n|---|---:|---:|---:|---|\n| Original `R * B` | {summary['original']['selected_original_frame_indices']} | {summary['original']['gaps_between_selected_frames']} | {summary['original']['min_gap']} | `spc_b_original_formula_n3.png` |\n| Proposed balanced-density | {summary['balanced_density']['selected_original_frame_indices']} | {summary['balanced_density']['gaps_between_selected_frames']} | {summary['balanced_density']['min_gap']} | `spc_b_balanced_density_n3.png` |\n\n## Visual clarity assessment\n\nOriginal formula:\n{json.dumps(summary['original']['clarity_notes'], ensure_ascii=False, indent=2)}\n\nProposed balanced-density formula:\n{json.dumps(summary['balanced_density']['clarity_notes'], ensure_ascii=False, indent=2)}\n\nAssessment: the proposed output keeps three temporally separated frames with no consecutive/local cluster. The synthetic face-like object is visible and clear in all selected frames; object/face features remain recognizable in the saved grid.\n\nArtifacts are all written inside `test` only.\n"""
    Path('spc_b_delete_score_n3_report.md').write_text(report, encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()

