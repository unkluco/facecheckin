"""
InsightFace SCRFD + ArcFace recognition engine.

Keeps the old FaceEngine.process_image() contract used by server.py, but
replaces DeepFace with image -> SCRFD -> ArcFace embedding -> cosine matching
against a per-class cache built from backend/data/{class_id}/{student}/ images.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import threading
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import numpy as np
from config import CACHE_DIR as CONFIG_CACHE_DIR
from config import INSIGHTFACE_ROOT, RECOGNITION_SETTINGS_PATH

try:
    from insightface.app import FaceAnalysis
except ImportError:
    FaceAnalysis = None

logger = logging.getLogger(__name__)
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}
SETTINGS_FILE = Path(os.environ.get('FACECHECKIN_RECOGNITION_SETTINGS', RECOGNITION_SETTINGS_PATH))
CACHE_DIR = Path(os.environ.get('FACECHECKIN_CACHE_DIR', CONFIG_CACHE_DIR)) / 'embeddings'
DEFAULT_INSIGHTFACE_ROOT = Path(os.path.expanduser(os.environ.get('FACECHECKIN_INSIGHTFACE_ROOT', INSIGHTFACE_ROOT)))

# For legacy insightface wheels (e.g. 0.2.1), FaceAnalysis does not auto-download
# model packs and cannot parse every ONNX in buffalo_l. We keep only the required
# detection + recognition files in the model folder.
LEGACY_MODEL_PACK_URLS = {
    'buffalo_l': 'https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip',
}
LEGACY_REQUIRED_ONNX = {
    'buffalo_l': ('det_10g.onnx', 'w600k_r50.onnx'),
}

DEFAULT_SETTINGS = {
    'engine': 'insightface',
    'model_pack': os.environ.get('FACECHECKIN_FACE_MODEL', 'buffalo_l'),
    'threshold': float(os.environ.get('FACECHECKIN_FACE_THRESHOLD', '0.35')),
    'det_size': int(os.environ.get('FACECHECKIN_FACE_DET_SIZE', '640')),
    'ctx_id': int(os.environ.get('FACECHECKIN_FACE_CTX_ID', '-1')),
    'multi_face': os.environ.get('FACECHECKIN_MULTI_FACE', '1').strip().lower() not in {'0', 'false', 'no'},
    'det_score_threshold': float(os.environ.get('FACECHECKIN_DET_SCORE_THRESHOLD', '0.5')),
    'registration_crop': True,
    'draw_box_thickness_ratio': float(os.environ.get('FACECHECKIN_DRAW_BOX_THICKNESS_RATIO', '0.004')),
    'draw_font_scale_ratio': float(os.environ.get('FACECHECKIN_DRAW_FONT_SCALE_RATIO', '0.0018')),
    'draw_text_thickness_ratio': float(os.environ.get('FACECHECKIN_DRAW_TEXT_THICKNESS_RATIO', '0.0032')),
    'draw_text_padding_ratio': float(os.environ.get('FACECHECKIN_DRAW_TEXT_PADDING_RATIO', '0.006')),
}


def l2_normalize(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float32)
    norm = np.linalg.norm(vector)
    return vector if norm <= 1e-12 else vector / norm


def read_image(path: str) -> Optional[np.ndarray]:
    data = np.fromfile(path, dtype=np.uint8)
    return None if data.size == 0 else cv2.imdecode(data, cv2.IMREAD_COLOR)


def write_image(path: str, image: np.ndarray, quality: int = 92) -> bool:
    ext = Path(path).suffix.lower() or '.jpg'
    params = [cv2.IMWRITE_JPEG_QUALITY, quality] if ext in {'.jpg', '.jpeg'} else []
    ok, buf = cv2.imencode(ext, image, params)
    if ok:
        np.asarray(buf).tofile(path)
    return bool(ok)


def iter_images(folder: Path):
    if not folder.exists():
        return []
    return [p for p in sorted(folder.iterdir()) if p.is_file() and p.suffix.lower() in IMAGE_EXTS]


@dataclass
class CacheData:
    labels: List[str]
    embeddings: np.ndarray
    image_counts: List[int]
    errors: List[dict]
    built_at: float
    signature: str


class FaceEngine:
    """SCRFD detector + ArcFace matcher with per-class embedding cache."""
    _legacy_prepare_lock = threading.Lock()

    def __init__(self, db_path: str, threshold: float = None):
        self.db_path = str(db_path)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.insightface_root = DEFAULT_INSIGHTFACE_ROOT
        self.settings = self.load_settings()
        if threshold is not None and not SETTINGS_FILE.exists():
            self.settings['threshold'] = float(threshold)
        self._apps: Dict[int, object] = {}
        logger.info('FaceEngine initialized: %s', self.settings)

    @staticmethod
    def load_settings() -> Dict:
        settings = dict(DEFAULT_SETTINGS)
        if SETTINGS_FILE.exists():
            try:
                saved = json.loads(SETTINGS_FILE.read_text(encoding='utf-8'))
                settings.update({k: saved[k] for k in settings.keys() & saved.keys()})
            except Exception as exc:
                logger.warning('Could not load recognition settings: %s', exc)
        return settings

    def get_settings(self) -> Dict:
        return dict(self.settings)

    def save_settings(self, updates: Dict) -> Dict:
        def clamp(value: float, low: float, high: float) -> float:
            return max(low, min(high, float(value)))

        allowed = set(DEFAULT_SETTINGS.keys()) - {'engine'}
        next_settings = dict(self.settings)
        for key, value in (updates or {}).items():
            if key not in allowed:
                continue
            if key in {'threshold', 'det_score_threshold'}:
                next_settings[key] = clamp(value, 0.0, 1.0)
            elif key in {'det_size', 'ctx_id'}:
                next_settings[key] = int(value)
            elif key in {'multi_face', 'registration_crop'}:
                next_settings[key] = bool(value)
            elif key == 'model_pack':
                next_settings[key] = str(value).strip() or DEFAULT_SETTINGS[key]
            elif key == 'draw_box_thickness_ratio':
                next_settings[key] = clamp(value, 0.0005, 0.03)
            elif key == 'draw_font_scale_ratio':
                next_settings[key] = clamp(value, 0.0005, 0.03)
            elif key == 'draw_text_thickness_ratio':
                next_settings[key] = clamp(value, 0.0005, 0.03)
            elif key == 'draw_text_padding_ratio':
                next_settings[key] = clamp(value, 0.0005, 0.05)
        reload_model = any(
            next_settings.get(k) != self.settings.get(k)
            for k in ('model_pack', 'ctx_id', 'det_size', 'det_score_threshold')
        )
        self.settings = next_settings
        SETTINGS_FILE.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2), encoding='utf-8')
        if reload_model:
            self._apps = {}
            self.invalidate_cache()
        return self.get_settings()

    def _legacy_model_dir(self, model_name: str) -> Path:
        return self.insightface_root / model_name

    def _legacy_required_files(self, model_name: str) -> tuple[str, ...]:
        return LEGACY_REQUIRED_ONNX.get(model_name, ())

    def _legacy_pack_ready(self, model_name: str) -> bool:
        required = self._legacy_required_files(model_name)
        if not required:
            return False
        model_dir = self._legacy_model_dir(model_name)
        return all((model_dir / name).exists() for name in required)

    def _download_legacy_pack(self, model_name: str):
        pack_url = LEGACY_MODEL_PACK_URLS.get(model_name)
        if not pack_url:
            raise RuntimeError(
                f'Legacy insightface model "{model_name}" is not configured. '
                f'Configured packs: {sorted(LEGACY_MODEL_PACK_URLS.keys())}'
            )

        required = self._legacy_required_files(model_name)
        if not required:
            raise RuntimeError(
                f'Legacy required ONNX list is missing for model pack "{model_name}".'
            )

        self.insightface_root.mkdir(parents=True, exist_ok=True)
        model_dir = self._legacy_model_dir(model_name)
        model_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            'Downloading legacy insightface model pack: %s -> %s',
            model_name,
            pack_url,
        )

        tmp_zip = None
        extract_dir = None
        try:
            with tempfile.NamedTemporaryFile(
                suffix=f'_{model_name}.zip',
                dir=self.insightface_root,
                delete=False,
            ) as tmp_file:
                tmp_zip = Path(tmp_file.name)

            urllib.request.urlretrieve(pack_url, tmp_zip)

            extract_dir = Path(
                tempfile.mkdtemp(prefix=f'{model_name}_extract_', dir=self.insightface_root)
            )
            with zipfile.ZipFile(tmp_zip) as zf:
                zf.extractall(extract_dir)

            found = {}
            for onnx_path in extract_dir.rglob('*.onnx'):
                name = onnx_path.name.lower()
                if name not in found:
                    found[name] = onnx_path

            missing = [name for name in required if name.lower() not in found]
            if missing:
                raise RuntimeError(
                    f'Legacy model pack "{model_name}" missing files: {missing}'
                )

            # Clean old ONNX files to avoid legacy model router crashes on unsupported files.
            for old in model_dir.glob('*.onnx'):
                old.unlink(missing_ok=True)

            for name in required:
                src = found[name.lower()]
                dst = model_dir / name
                shutil.copyfile(src, dst)

            logger.info(
                'Prepared legacy insightface model pack "%s" with files: %s',
                model_name,
                ', '.join(required),
            )
        finally:
            if tmp_zip and tmp_zip.exists():
                try:
                    tmp_zip.unlink()
                except OSError:
                    pass
            if extract_dir and extract_dir.exists():
                shutil.rmtree(extract_dir, ignore_errors=True)

    def _ensure_legacy_models_ready(self, model_name: str):
        if self._legacy_pack_ready(model_name):
            return

        with self._legacy_prepare_lock:
            if self._legacy_pack_ready(model_name):
                return
            self._download_legacy_pack(model_name)
            if not self._legacy_pack_ready(model_name):
                raise RuntimeError(
                    f'Legacy insightface pack "{model_name}" is not ready after download.'
                )

    def _ensure_app(self, det_size: Optional[int] = None):
        if FaceAnalysis is None:
            raise RuntimeError('insightface is not installed. Run: pip install insightface onnxruntime')
        size = max(160, int(det_size if det_size is not None else self.settings.get('det_size', 640)))
        app = self._apps.get(size)
        if app is None:
            model_name = self.settings.get('model_pack', 'buffalo_l')
            providers = ['CPUExecutionProvider']
            if int(self.settings.get('ctx_id', -1)) >= 0:
                providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']

            # Newer insightface supports allowed_modules/providers; older wheels do not.
            try:
                app = FaceAnalysis(
                    name=model_name,
                    root=str(self.insightface_root),
                    allowed_modules=['detection', 'recognition'],
                    providers=providers,
                )
            except TypeError:
                logger.warning(
                    'Legacy insightface detected, fallback constructor without '
                    'allowed_modules/providers.'
                )
                self._ensure_legacy_models_ready(model_name)
                app = FaceAnalysis(name=model_name, root=str(self.insightface_root))

            try:
                app.prepare(
                    ctx_id=int(self.settings.get('ctx_id', -1)),
                    det_thresh=float(self.settings.get('det_score_threshold', 0.5)),
                    det_size=(size, size),
                )
            except TypeError:
                app.prepare(
                    ctx_id=int(self.settings.get('ctx_id', -1)),
                    det_size=(size, size),
                )
            self._apps[size] = app
        return app

    def _detect(self, image: np.ndarray):
        min_score = float(self.settings.get('det_score_threshold', 0.5))
        base_size = max(160, int(self.settings.get('det_size', 640)))
        fallback_sizes = [base_size]
        for candidate in (480, 320):
            if candidate not in fallback_sizes and candidate < base_size:
                fallback_sizes.append(candidate)

        faces = []
        detected_with = base_size
        last_exc = None
        had_successful_call = False
        for size in fallback_sizes:
            try:
                raw_faces = self._ensure_app(size).get(image)
                had_successful_call = True
            except Exception as exc:
                last_exc = exc
                logger.warning('Face detect failed at det_size=%s: %s', size, exc)
                continue

            scored_faces = [
                face for face in raw_faces
                if float(getattr(face, 'det_score', 0.0)) >= min_score
            ]
            if scored_faces:
                faces = scored_faces
                detected_with = size
                break

        if not had_successful_call and last_exc is not None:
            raise last_exc
        if not faces:
            return []
        if detected_with != base_size:
            logger.info(
                'Face detect fallback succeeded at det_size=%s (base=%s)',
                detected_with,
                base_size,
            )
        faces.sort(key=lambda face: (face.bbox[2] - face.bbox[0]) * (face.bbox[3] - face.bbox[1]), reverse=True)
        return faces if self.settings.get('multi_face', True) else faces[:1]

    def _cache_path(self, class_db_path: str) -> Path:
        class_name = Path(class_db_path).name or 'root'
        model = self.settings.get('model_pack', 'buffalo_l')
        return CACHE_DIR / f'class_{class_name}_{model}.npz'

    def _signature(self, class_db_path: str) -> str:
        root = Path(class_db_path)
        parts = []
        if root.exists():
            for image in sorted(root.glob('*/*')):
                if image.is_file() and image.suffix.lower() in IMAGE_EXTS:
                    stat = image.stat()
                    parts.append(f'{image.relative_to(root).as_posix()}:{stat.st_size}:{int(stat.st_mtime)}')
        return '|'.join(parts)

    def invalidate_cache(self, class_db_path: str = None):
        paths = [self._cache_path(class_db_path)] if class_db_path else list(CACHE_DIR.glob('class_*.npz'))
        for path in paths:
            try:
                path.unlink(missing_ok=True)
            except Exception as exc:
                logger.warning('Could not remove cache %s: %s', path, exc)

    def build_cache(self, class_db_path: str, progress_callback=None) -> CacheData:
        root = Path(class_db_path)
        root.mkdir(parents=True, exist_ok=True)
        labels, means, counts, errors = [], [], [], []
        image_paths = [
            image_path
            for student_dir in sorted([p for p in root.iterdir() if p.is_dir()])
            for image_path in iter_images(student_dir)
        ]
        total_images = len(image_paths)
        indexed_images = 0
        processed_images = 0
        if progress_callback:
            progress_callback(0, total_images)
        for student_dir in sorted([p for p in root.iterdir() if p.is_dir()]):
            embeddings = []
            for image_path in iter_images(student_dir):
                try:
                    image = read_image(str(image_path))
                    if image is None:
                        errors.append({'label': student_dir.name, 'image': image_path.name, 'reason': 'read_failed'})
                        continue
                    try:
                        faces = self._detect(image)
                    except Exception as exc:
                        errors.append({'label': student_dir.name, 'image': image_path.name, 'reason': str(exc)})
                        continue
                    if not faces:
                        errors.append({'label': student_dir.name, 'image': image_path.name, 'reason': 'no_face'})
                        continue
                    embeddings.append(l2_normalize(np.asarray(faces[0].embedding, dtype=np.float32)))
                    indexed_images += 1
                finally:
                    processed_images += 1
                    if progress_callback:
                        progress_callback(indexed_images, total_images)
            if embeddings:
                labels.append(student_dir.name)
                means.append(l2_normalize(np.mean(np.stack(embeddings), axis=0)))
                counts.append(len(embeddings))
        matrix = np.stack(means).astype(np.float32) if means else np.empty((0, 512), dtype=np.float32)
        cache = CacheData(labels, matrix, counts, errors, time.time(), self._signature(class_db_path))
        np.savez_compressed(
            self._cache_path(class_db_path),
            labels=np.array(labels, dtype=object),
            embeddings=matrix,
            image_counts=np.array(counts, dtype=np.int32),
            errors=np.array([json.dumps(e, ensure_ascii=False) for e in errors], dtype=object),
            built_at=np.array([cache.built_at], dtype=np.float64),
            signature=np.array([cache.signature], dtype=object),
        )
        return cache

    def load_cache(self, class_db_path: str, rebuild: bool = False, progress_callback=None) -> CacheData:
        path = self._cache_path(class_db_path)
        signature = self._signature(class_db_path)
        if not rebuild and path.exists():
            try:
                data = np.load(path, allow_pickle=True)
                cached_sig = str(data['signature'][0]) if 'signature' in data else ''
                if cached_sig == signature:
                    return CacheData(
                        labels=[str(x) for x in data['labels'].tolist()],
                        embeddings=np.asarray(data['embeddings'], dtype=np.float32),
                        image_counts=[int(x) for x in data['image_counts'].tolist()],
                        errors=[json.loads(str(x)) for x in data['errors'].tolist()] if 'errors' in data else [],
                        built_at=float(data['built_at'][0]) if 'built_at' in data else 0.0,
                        signature=cached_sig,
                    )
            except Exception as exc:
                logger.warning('Could not load cache %s: %s', path, exc)
        return self.build_cache(class_db_path, progress_callback)

    def cache_status(self, class_db_path: str = None, rebuild: bool = False, progress_callback=None) -> Dict:
        class_db_path = class_db_path or self.db_path
        path = self._cache_path(class_db_path)
        signature = self._signature(class_db_path)
        total_images = sum(1 for student_dir in Path(class_db_path).glob('*') if student_dir.is_dir() for _ in iter_images(student_dir))
        exists = path.exists()
        dirty, labels, counts, errors, built_at = True, [], [], [], None
        if rebuild:
            cache = self.build_cache(class_db_path, progress_callback)
            labels, counts, errors, built_at = cache.labels, cache.image_counts, cache.errors, cache.built_at
            exists, dirty = True, False
        elif exists:
            try:
                data = np.load(path, allow_pickle=True)
                dirty = str(data['signature'][0]) != signature
                labels = [str(x) for x in data['labels'].tolist()]
                counts = [int(x) for x in data['image_counts'].tolist()]
                errors = [json.loads(str(x)) for x in data['errors'].tolist()] if 'errors' in data else []
                built_at = float(data['built_at'][0]) if 'built_at' in data else None
            except Exception:
                dirty = True
        return {
            'engine': 'insightface',
            'settings': self.get_settings(),
            'cache_file': str(path),
            'ready': exists and not dirty,
            'dirty': dirty,
            'students_with_embeddings': len(labels),
            'images_indexed': int(sum(counts)),
            'total_images': int(total_images),
            'errors': errors[:50],
            'error_count': len(errors),
            'built_at': built_at,
        }

    def process_image(self, input_path: str, output_path: str, db_path: Optional[str] = None) -> Dict:
        try:
            if not os.path.exists(input_path):
                return self._error(f'Input image not found: {input_path}')
            db_path = str(db_path or self.db_path)
            image = read_image(input_path)
            if image is None:
                return self._error('Could not read input image')
            faces = self._detect(image)
            cache = self.load_cache(db_path)
            labels, face_rows, known, unknown = [], [], [], []
            for idx, face in enumerate(faces, start=1):
                bbox = [int(v) for v in face.bbox.tolist()]
                emb = l2_normalize(np.asarray(face.embedding, dtype=np.float32))
                label, confidence, is_known = f'unknown${idx}', 0.0, False
                if cache.embeddings.size and cache.labels:
                    scores = cache.embeddings @ emb
                    best_idx = int(np.argmax(scores))
                    confidence = float(scores[best_idx])
                    if confidence >= float(self.settings.get('threshold', 0.35)):
                        label, is_known = cache.labels[best_idx], True
                labels.append(label)
                (known if is_known else unknown).append(label)
                face_rows.append({
                    'label': label,
                    'confidence': confidence,
                    'similarity': confidence,
                    'is_known': is_known,
                    'box': self._xyxy_to_xywh(bbox),
                    'box_expanded': self._xyxy_to_xywh(bbox),
                    'det_score': float(getattr(face, 'det_score', 0.0)),
                })
            annotated = image.copy()
            self._draw(annotated, face_rows)
            write_image(output_path, annotated)
            return {
                'engine': 'insightface',
                'model': self.settings.get('model_pack'),
                'threshold': self.settings.get('threshold'),
                'labels': labels,
                'faces': face_rows,
                'count': len(labels),
                'known': known,
                'unknown': unknown,
                'success': True,
                'error': None,
            }
        except Exception as exc:
            logger.error('Error processing image: %s', exc, exc_info=True)
            return self._error(str(exc))

    def preprocess_registration_image(self, file_path: str, expand_percentage: int = 15) -> bool:
        image = read_image(file_path)
        if image is None:
            return False
        faces = self._detect(image)
        if not faces:
            return False
        x1, y1, x2, y2 = [int(v) for v in faces[0].bbox.tolist()]
        pad_x = int((x2 - x1) * expand_percentage / 100)
        pad_y = int((y2 - y1) * expand_percentage / 100)
        h_img, w_img = image.shape[:2]
        x1, y1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
        x2, y2 = min(w_img, x2 + pad_x), min(h_img, y2 + pad_y)
        crop = image[y1:y2, x1:x2]
        return crop.size > 0 and write_image(file_path, crop, quality=95)

    def process_image_file(self, input_path: str, output_dir: str = None) -> Dict:
        output_path = os.path.join(output_dir, Path(input_path).name) if output_dir else f'{Path(input_path).with_suffix("")}_result{Path(input_path).suffix or ".jpg"}'
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        return self.process_image(input_path, output_path)

    def extract_faces(self, input_path: str) -> List[Dict]:
        image = read_image(input_path)
        if image is None:
            return []
        return [{'box': self._xyxy_to_xywh([int(v) for v in f.bbox.tolist()]), 'confidence': float(getattr(f, 'det_score', 0.0))} for f in self._detect(image)]

    def get_db_info(self) -> Dict:
        root = Path(self.db_path)
        people = [d for d in root.iterdir() if d.is_dir()] if root.exists() else []
        return {'engine': 'insightface', 'db_path': self.db_path, 'num_people': len(people), 'people': [{'name': p.name, 'num_images': len(iter_images(p))} for p in sorted(people)]}

    @staticmethod
    def _xyxy_to_xywh(bbox: List[int]) -> List[int]:
        x1, y1, x2, y2 = bbox
        return [x1, y1, max(0, x2 - x1), max(0, y2 - y1)]

    def _draw(self, image: np.ndarray, faces: List[Dict]):
        img_h, img_w = image.shape[:2]
        # Scale all drawing primitives from image height for consistent appearance.
        box_ratio = float(self.settings.get('draw_box_thickness_ratio', DEFAULT_SETTINGS['draw_box_thickness_ratio']))
        font_ratio = float(self.settings.get('draw_font_scale_ratio', DEFAULT_SETTINGS['draw_font_scale_ratio']))
        text_ratio = float(self.settings.get('draw_text_thickness_ratio', DEFAULT_SETTINGS['draw_text_thickness_ratio']))
        pad_ratio = float(self.settings.get('draw_text_padding_ratio', DEFAULT_SETTINGS['draw_text_padding_ratio']))

        box_thickness = max(1, int(round(img_h * box_ratio)))
        font_scale = max(0.40, img_h * font_ratio)
        text_thickness = max(1, int(round(img_h * text_ratio)))
        text_padding = max(2, int(round(img_h * pad_ratio)))

        for face in faces:
            x, y, w, h = face['box']
            color = (0, 200, 0) if face.get('is_known') else (0, 210, 255)
            cv2.rectangle(image, (x, y), (x + w, y + h), color, box_thickness)

            confidence_pct = float(face.get('confidence', 0.0)) * 100.0
            text = f"{face.get('label')} {confidence_pct:.0f}%"

            (tw, th), baseline = cv2.getTextSize(
                text,
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                text_thickness,
            )

            # Prefer label above bbox; fallback inside if there is not enough room.
            text_x = max(0, min(x, img_w - tw - (text_padding * 2)))
            above_y = y - text_padding
            if above_y - th - baseline >= 0:
                text_y = above_y
            else:
                text_y = min(img_h - baseline - text_padding, y + th + text_padding)

            bg_tl = (text_x, max(0, text_y - th - baseline - text_padding))
            bg_br = (
                min(img_w - 1, text_x + tw + (text_padding * 2)),
                min(img_h - 1, text_y + text_padding),
            )
            cv2.rectangle(image, bg_tl, bg_br, color, -1)

            cv2.putText(
                image,
                text,
                (text_x + text_padding, text_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                (10, 10, 10),
                text_thickness,
                cv2.LINE_AA,
            )

    @staticmethod
    def _error(message: str) -> Dict:
        return {'labels': [], 'faces': [], 'count': 0, 'known': [], 'unknown': [], 'success': False, 'error': message}
