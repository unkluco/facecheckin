"""
utils.py — Tiện ích nền tảng cho thư viện facecheckin.

Nội dung:
  - extract_faces(): phát hiện + crop khuôn mặt từ ảnh
  - cosine_similarity / cosine_distance / l2norm
  - get_images_in_dir(), is_image_file()
"""

import numpy as np
import cv2
from deepface import DeepFace
from pathlib import Path


# ─────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────

SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}


# ─────────────────────────────────────────
# FILE HELPERS
# ─────────────────────────────────────────

def is_image_file(path):
    """Kiểm tra file có phải ảnh không (theo đuôi file)."""
    return Path(path).suffix.lower() in SUPPORTED_EXTENSIONS


def get_images_in_dir(folder):
    """
    Trả về danh sách Path của tất cả file ảnh trong thư mục (không đệ quy).

    Returns:
        list[Path]
    """
    return sorted(
        p for p in Path(folder).iterdir()
        if p.is_file() and is_image_file(p)
    )


# ─────────────────────────────────────────
# FACE EXTRACTION
# ─────────────────────────────────────────

def extract_faces(
    img,
    model_detection='retinaface',
    expand_percentage=10,
    min_confidence=0.85,
    align=True,
):
    """
    Trích xuất tất cả khuôn mặt từ ảnh đầu vào.

    Hỗ trợ ảnh thô (nhiều người, mặt xa, nhiều angle).
    Tự động lọc theo ngưỡng confidence và mở rộng bounding box.

    Args:
        img (str | np.ndarray):
            Đường dẫn ảnh (str) hoặc numpy array BGR.
        model_detection (str):
            Backend phát hiện khuôn mặt. Mặc định: 'retinaface'.
        expand_percentage (int):
            % mở rộng bounding box về 4 phía. Mặc định: 10.
        min_confidence (float):
            Ngưỡng confidence tối thiểu [0, 1]. Mặc định: 0.85.
        align (bool):
            Căn chỉnh khuôn mặt theo landmark mắt. Mặc định: True.

    Returns:
        list[dict]: Mỗi dict chứa:
            - 'face'         : np.ndarray BGR — vùng crop mở rộng từ ảnh gốc
            - 'face_aligned' : np.ndarray BGR — khuôn mặt đã align từ DeepFace
            - 'box'          : (x, y, w, h)  — bounding box gốc
            - 'box_expanded' : (x, y, w, h)  — bounding box đã mở rộng
            - 'confidence'   : float
    """
    # Đọc ảnh nếu là đường dẫn
    if isinstance(img, str):
        img_array = cv2.imread(img)
        if img_array is None:
            raise ValueError(f"Không thể đọc ảnh: {img}")
    else:
        img_array = img.copy()

    h_img, w_img = img_array.shape[:2]

    # Phát hiện bằng DeepFace (không expand, lấy box gốc)
    try:
        faces_raw = DeepFace.extract_faces(
            img_path=img_array,
            detector_backend=model_detection,
            enforce_detection=False,
            align=align,
            expand_percentage=0,
        )
    except Exception:
        return []

    results = []
    for face_data in faces_raw:
        confidence = face_data.get('confidence', 0)
        if confidence < min_confidence:
            continue

        region = face_data['facial_area']
        x, y, w, h = region['x'], region['y'], region['w'], region['h']
        box = (x, y, w, h)

        # Tính box mở rộng (clamped theo kích thước ảnh)
        pad_w = int(w * expand_percentage / 100)
        pad_h = int(h * expand_percentage / 100)
        x_exp  = max(0, x - pad_w)
        y_exp  = max(0, y - pad_h)
        x2_exp = min(w_img, x + w + pad_w)
        y2_exp = min(h_img, y + h + pad_h)
        box_expanded = (x_exp, y_exp, x2_exp - x_exp, y2_exp - y_exp)

        # Crop vùng mở rộng từ ảnh gốc (BGR)
        cropped = img_array[y_exp:y2_exp, x_exp:x2_exp].copy()

        # Face aligned từ DeepFace (float RGB 0-1 → uint8 BGR)
        face_rgb_float = face_data['face']   # (H, W, 3) float [0, 1] RGB
        face_aligned_bgr = cv2.cvtColor(
            (face_rgb_float * 255).astype(np.uint8),
            cv2.COLOR_RGB2BGR,
        )

        results.append({
            'face':          cropped,
            'face_aligned':  face_aligned_bgr,
            'box':           box,
            'box_expanded':  box_expanded,
            'confidence':    float(confidence),
        })

    return results


# ─────────────────────────────────────────
# VECTOR MATH
# ─────────────────────────────────────────

def l2norm(v):
    """L2-normalize một vector numpy."""
    v = np.asarray(v, dtype=np.float32)
    norm = np.linalg.norm(v)
    return v / (norm + 1e-12)


def cosine_similarity(v1, v2):
    """
    Tính cosine similarity giữa 2 vector (cao = giống nhau hơn).

    Returns:
        float trong khoảng [-1, 1] (thực tế embedding ≥ 0)
    """
    v1 = np.asarray(v1, dtype=np.float32)
    v2 = np.asarray(v2, dtype=np.float32)
    n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if n1 < 1e-12 or n2 < 1e-12:
        return 0.0
    return float(np.dot(v1, v2) / (n1 * n2))


def cosine_distance(v1, v2):
    """
    Tính cosine distance giữa 2 vector (thấp = giống nhau hơn).

    Returns:
        float trong khoảng [0, 2]
    """
    return 1.0 - cosine_similarity(v1, v2)
