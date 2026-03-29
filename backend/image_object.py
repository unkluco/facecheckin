"""
image_object.py — Lớp ImageObject: giao diện pipeline nhận diện khuôn mặt.

Thiết kế pipeline (method chaining):

    result = (
        ImageObject("photo.jpg")
            .detect(expand_percentage=15)
            .recognize(db_path="./my_db")
            .draw()
            .save_drawn("output/result.jpg")
            .save_faces("output/faces/")
            .show()
    )

    print(result.get_labels())
    face_data = result.get_face_data()
"""

import cv2
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from deepface import DeepFace
import itertools

from utils import extract_faces


# ─────────────────────────────────────────
# COUNTER NHÃN UNKNOWN
# ─────────────────────────────────────────

_unknown_counter = itertools.count(1)


def _next_unknown_label():
    """Tạo nhãn unknown duy nhất, ví dụ: unknown$1, unknown$2, ..."""
    return f"unknown${next(_unknown_counter)}"


def reset_unknown_counter(start=1):
    """Reset bộ đếm nhãn unknown (hữu ích khi khởi động lại session)."""
    global _unknown_counter
    _unknown_counter = itertools.count(start)


# ─────────────────────────────────────────
# FACE RECORD
# ─────────────────────────────────────────

class FaceRecord:
    """
    Lưu thông tin của một khuôn mặt được phát hiện trong ảnh.

    Attributes:
        face_img     (np.ndarray): Ảnh crop mở rộng từ ảnh gốc (BGR).
        face_aligned (np.ndarray): Ảnh khuôn mặt đã align (BGR).
        box          (tuple)     : (x, y, w, h) bounding box gốc.
        box_expanded (tuple)     : (x, y, w, h) bounding box đã mở rộng.
        confidence   (float)     : Điểm tin cậy phát hiện [0, 1].
        label        (str | None): Nhãn sau khi nhận diện.
            - Tên người: đã nhận diện.
            - 'unknown$N': không nhận diện được.
            - None: chưa gọi recognize().
    """

    def __init__(self, face_img, face_aligned, box, box_expanded, confidence, label=None):
        self.face_img     = face_img
        self.face_aligned = face_aligned
        self.box          = box
        self.box_expanded = box_expanded
        self.confidence   = confidence
        self.label        = label

    @property
    def is_known(self):
        """True nếu đã được nhận diện (không phải unknown$N hay None)."""
        return (
            self.label is not None
            and not self.label.startswith('unknown$')
        )

    def __repr__(self):
        return f"FaceRecord(label={self.label!r}, confidence={self.confidence:.2f})"


# ─────────────────────────────────────────
# IMAGE OBJECT
# ─────────────────────────────────────────

class ImageObject:
    """
    Đối tượng ảnh hỗ trợ pipeline phát hiện và nhận diện khuôn mặt.

    Ví dụ cơ bản:

        img = ImageObject("group_photo.jpg")
        result = img.detect().recognize("./db").draw().show()
        print(result.get_labels())

    Ví dụ đầy đủ:

        result = (
            ImageObject("photo.jpg", model_name='Facenet512')
                .detect(expand_percentage=15, min_confidence=0.9)
                .recognize(db_path="./my_db", threshold=0.4)
                .draw(known_color=(0,255,0), unknown_color=(0,255,255))
                .save_drawn("output/annotated.jpg")
                .save_faces("output/faces/")
                .show()
        )

        labels   = result.get_labels()           # ['Alice', 'unknown$1']
        data     = result.get_face_data()        # list[dict]
        known    = result.get_known_faces()      # list[FaceRecord]
        total, k, u = result.count_faces()       # (2, 1, 1)
    """

    # ─── Khởi tạo ───────────────────────────────────────────────────

    def __init__(
        self,
        img,
        model_name:      str = 'Facenet512',
        model_detection: str = 'retinaface',
    ):
        """
        Args:
            img (str | np.ndarray):
                Đường dẫn ảnh hoặc numpy array BGR.
            model_name (str):
                Model nhận diện khuôn mặt. Mặc định: 'Facenet512'.
            model_detection (str):
                Model phát hiện khuôn mặt. Mặc định: 'retinaface'.
        """
        if isinstance(img, str):
            arr = cv2.imread(img)
            if arr is None:
                raise ValueError(f"Không thể đọc ảnh: {img}")
            self._img_original = arr
        else:
            self._img_original = img.copy()

        self.img             = self._img_original.copy()  # ảnh làm việc
        self.model_name      = model_name
        self.model_detection = model_detection
        self.faces: list     = []   # list[FaceRecord]

    # ─── DETECTION ──────────────────────────────────────────────────

    def detect(
        self,
        expand_percentage: int   = 10,
        min_confidence:    float = 0.85,
        align:             bool  = True,
    ) -> 'ImageObject':
        """
        Phát hiện tất cả khuôn mặt trong ảnh.

        Hỗ trợ ảnh thô: nhiều người, khuôn mặt nhỏ/xa, nhiều góc.

        Args:
            expand_percentage (int):
                % mở rộng bounding box về 4 phía. Mặc định: 10.
            min_confidence (float):
                Ngưỡng confidence tối thiểu. Mặc định: 0.85.
            align (bool):
                Căn chỉnh khuôn mặt theo mắt. Mặc định: True.

        Returns:
            self — để chain phương thức.
        """
        raw_faces = extract_faces(
            self._img_original,
            model_detection  = self.model_detection,
            expand_percentage= expand_percentage,
            min_confidence   = min_confidence,
            align            = align,
        )

        self.faces = [
            FaceRecord(
                face_img     = f['face'],
                face_aligned = f['face_aligned'],
                box          = f['box'],
                box_expanded = f['box_expanded'],
                confidence   = f['confidence'],
                label        = None,
            )
            for f in raw_faces
        ]

        self.img = self._img_original.copy()  # reset ảnh (xóa bbox cũ nếu có)
        return self

    # ─── RECOGNITION ────────────────────────────────────────────────

    def recognize(
        self,
        db_path,
        threshold:            float = 0.4,
        silent:               bool  = True,
        unknown_label_prefix: str   = 'unknown$',
    ) -> 'ImageObject':
        """
        Nhận diện từng khuôn mặt đã phát hiện dựa trên DeepFace database.

        Cần gọi detect() trước.

        Cơ chế:
          - Mỗi face_aligned được truyền vào DeepFace.find() với
            detector_backend='skip' (không detect lại, ảnh đã là khuôn mặt).
          - Nếu tìm được match dưới ngưỡng threshold → gán nhãn = tên folder.
          - Nếu không → gán nhãn unique 'unknown$N'.

        Args:
            db_path (str | Path):
                Đường dẫn thư mục database theo cấu trúc DeepFace:
                    db/person_name/img.jpg
            threshold (float):
                Ngưỡng cosine distance tối đa để chấp nhận match.
                Mặc định: 0.4 (tương đương ~60% similarity).
            silent (bool):
                Ẩn output của DeepFace. Mặc định: True.
            unknown_label_prefix (str):
                Prefix cho nhãn khi không nhận diện được. Mặc định: 'unknown$'.

        Returns:
            self — để chain phương thức.
        """
        if not self.faces:
            return self

        db_path = str(db_path)

        for face in self.faces:
            try:
                dfs = DeepFace.find(
                    img_path         = face.face_aligned,
                    db_path          = db_path,
                    model_name       = self.model_name,
                    detector_backend = 'skip',   # ảnh đã là khuôn mặt
                    distance_metric  = 'cosine',
                    enforce_detection= False,
                    silent           = silent,
                    threshold        = threshold,
                )

                if dfs and len(dfs[0]) > 0:
                    df      = dfs[0]
                    # Tìm cột distance (tên thay đổi theo version DeepFace)
                    dist_cols = [
                        c for c in df.columns
                        if 'distance' in c.lower() or 'cosine' in c.lower()
                    ]
                    if dist_cols:
                        df = df.sort_values(dist_cols[0])
                    best = df.iloc[0]
                    face.label = Path(str(best['identity'])).parent.name
                else:
                    face.label = _next_unknown_label()

            except Exception:
                face.label = _next_unknown_label()

        return self

    # ─── VISUALIZATION ──────────────────────────────────────────────

    def draw(
        self,
        thickness:      int   = 2,
        font_scale:     float = 0.6,
        known_color:    tuple = (0, 255, 0),    # Xanh lá (BGR)
        unknown_color:  tuple = (0, 255, 255),  # Vàng (BGR)
        show_confidence:bool  = False,
    ) -> 'ImageObject':
        """
        Vẽ bounding box và nhãn lên ảnh làm việc.

        Quy tắc màu:
          - Xanh lá : khuôn mặt đã nhận diện được.
          - Vàng    : khuôn mặt chưa nhận diện (unknown$N).

        Args:
            thickness (int)       : Độ dày đường viền. Mặc định: 2.
            font_scale (float)    : Kích thước chữ. Mặc định: 0.6.
            known_color (tuple)   : Màu BGR cho nhãn đã biết.
            unknown_color (tuple) : Màu BGR cho nhãn unknown.
            show_confidence (bool): Hiển thị thêm confidence score.

        Returns:
            self — để chain phương thức.
        """
        self.img = self._img_original.copy()

        # Auto-scale thickness & font relative to image size.
        # Baseline reference: 640 px on the long edge.
        img_h, img_w = self.img.shape[:2]
        scale = max(img_h, img_w) / 640.0
        eff_thickness  = max(1, round(thickness  * scale))
        eff_font_scale = font_scale * scale

        for face in self.faces:
            x, y, w, h = face.box_expanded
            color       = known_color if face.is_known else unknown_color
            label_text  = face.label if face.label else '?'

            if show_confidence:
                label_text += f" ({face.confidence:.2f})"

            # Vẽ bounding box
            cv2.rectangle(self.img, (x, y), (x + w, y + h), color, eff_thickness)

            # Vẽ nền nhãn
            (tw, th), baseline = cv2.getTextSize(
                label_text, cv2.FONT_HERSHEY_SIMPLEX, eff_font_scale, eff_thickness
            )
            pad = max(4, round(4 * scale))
            cv2.rectangle(
                self.img,
                (x, y - th - 2 * pad),
                (x + tw + 2 * pad, y),
                color, -1,
            )

            # Vẽ chữ nhãn (màu đen trên nền màu)
            cv2.putText(
                self.img, label_text,
                (x + pad, y - pad),
                cv2.FONT_HERSHEY_SIMPLEX, eff_font_scale,
                (0, 0, 0), eff_thickness,
            )

        return self

    def show(
        self,
        figsize: tuple = (12, 8),
        title:   str   = None,
    ) -> 'ImageObject':
        """
        Hiển thị ảnh làm việc hiện tại bằng matplotlib.

        Returns:
            self — để chain phương thức.
        """
        img_rgb = cv2.cvtColor(self.img, cv2.COLOR_BGR2RGB)
        plt.figure(figsize=figsize)
        if title:
            plt.title(title, fontsize=13)
        plt.imshow(img_rgb)
        plt.axis('off')
        plt.tight_layout()
        plt.show()
        return self

    def show_faces(
        self,
        cols:      int   = 4,
        face_size: tuple = (150, 150),
        figsize:   tuple = None,
        use_aligned: bool = True,
    ) -> 'ImageObject':
        """
        Hiển thị từng khuôn mặt đã phát hiện trong dạng lưới ảnh.

        Args:
            cols (int)        : Số cột. Mặc định: 4.
            face_size (tuple) : Kích thước thumbnail (w, h). Mặc định: (150, 150).
            figsize (tuple)   : Kích thước figure matplotlib.
            use_aligned (bool): Dùng ảnh aligned thay vì crop gốc.

        Returns:
            self — để chain phương thức.
        """
        if not self.faces:
            print("Không có khuôn mặt nào được phát hiện.")
            return self

        n    = len(self.faces)
        rows = (n + cols - 1) // cols
        if figsize is None:
            figsize = (cols * 3, rows * 3.2)

        fig, axes = plt.subplots(rows, cols, figsize=figsize)
        axes_flat = np.array(axes).flatten()

        for i, face in enumerate(self.faces):
            img_src = face.face_aligned if use_aligned else face.face_img
            thumb   = cv2.resize(img_src, face_size)
            img_rgb = cv2.cvtColor(thumb, cv2.COLOR_BGR2RGB)

            axes_flat[i].imshow(img_rgb)
            title = face.label or '(chưa nhận diện)'
            color = 'green' if face.is_known else 'goldenrod'
            axes_flat[i].set_title(title, fontsize=9, color=color)
            axes_flat[i].axis('off')

        for i in range(n, len(axes_flat)):
            axes_flat[i].axis('off')

        plt.suptitle(f'Khuôn mặt phát hiện được: {n}', fontsize=13, y=1.01)
        plt.tight_layout()
        plt.show()
        return self

    # ─── SAVE / EXPORT ──────────────────────────────────────────────

    def save_drawn(self, path) -> 'ImageObject':
        """
        Lưu ảnh làm việc (đã vẽ bbox) vào file.

        Args:
            path (str | Path): Đường dẫn file output (tự tạo thư mục cha).

        Returns:
            self — để chain phương thức.
        """
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out), self.img)
        return self

    def save_faces(
        self,
        output_dir,
        use_aligned: bool = True,
        prefix:      str  = '',
    ) -> 'ImageObject':
        """
        Lưu từng khuôn mặt đã crop thành file riêng.

        Tên file theo quy tắc: {prefix}{label}_{index}.jpg
        Ký tự '$' trong nhãn unknown được thay bằng '_'.

        Args:
            output_dir (str | Path): Thư mục lưu ảnh.
            use_aligned (bool)     : Dùng ảnh aligned. Mặc định: True.
            prefix (str)           : Tiền tố tên file. Mặc định: ''.

        Returns:
            self — để chain phương thức.
        """
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        for i, face in enumerate(self.faces):
            label      = face.label or f'unknown_{i}'
            safe_label = label.replace('$', '_').replace('/', '_')
            filename   = f"{prefix}{safe_label}_{i:03d}.jpg"
            img_src    = face.face_aligned if use_aligned else face.face_img
            cv2.imwrite(str(out_dir / filename), img_src)

        return self

    def save_faces_to_db(
        self,
        db_path,
        only_known: bool = False,
    ) -> 'ImageObject':
        """
        Lưu khuôn mặt trực tiếp vào cấu trúc thư mục DeepFace database.

        Cấu trúc output:
            db_path/
                ├── person_name/
                │   └── img_0001.jpg
                └── unknown$1/
                    └── img_0001.jpg

        Mỗi lần gọi tự động đặt tên file không trùng.

        Args:
            db_path (str | Path): Đường dẫn database.
            only_known (bool)   : Chỉ lưu khuôn mặt đã nhận diện.

        Returns:
            self — để chain phương thức.
        """
        db = Path(db_path)

        for i, face in enumerate(self.faces):
            if face.label is None:
                continue
            if only_known and not face.is_known:
                continue

            person_dir = db / face.label
            person_dir.mkdir(parents=True, exist_ok=True)

            idx      = len(list(person_dir.glob('*.jpg')))
            out_path = person_dir / f"img_{idx:04d}.jpg"
            cv2.imwrite(str(out_path), face.face_aligned)

        return self

    # ─── GETTERS ────────────────────────────────────────────────────

    def get_labels(self) -> list:
        """
        Trả về danh sách nhãn của tất cả khuôn mặt.

        Returns:
            list[str | None]
        """
        return [f.label for f in self.faces]

    def get_face_data(self) -> list:
        """
        Trả về thông tin đầy đủ về mỗi khuôn mặt.

        Returns:
            list[dict]: Mỗi dict gồm:
                - label        : str | None
                - face_img     : np.ndarray BGR (crop mở rộng)
                - face_aligned : np.ndarray BGR (aligned)
                - box          : (x, y, w, h)
                - box_expanded : (x, y, w, h)
                - confidence   : float
                - is_known     : bool
        """
        return [
            {
                'label':        f.label,
                'face_img':     f.face_img,
                'face_aligned': f.face_aligned,
                'box':          f.box,
                'box_expanded': f.box_expanded,
                'confidence':   f.confidence,
                'is_known':     f.is_known,
            }
            for f in self.faces
        ]

    def get_known_faces(self) -> list:
        """Trả về list[FaceRecord] các khuôn mặt đã nhận diện."""
        return [f for f in self.faces if f.is_known]

    def get_unknown_faces(self) -> list:
        """Trả về list[FaceRecord] các khuôn mặt chưa nhận diện."""
        return [f for f in self.faces if not f.is_known]

    def count_faces(self) -> tuple:
        """
        Trả về (tổng, đã nhận diện, chưa nhận diện).

        Returns:
            tuple[int, int, int]
        """
        known = sum(1 for f in self.faces if f.is_known)
        return len(self.faces), known, len(self.faces) - known

    def get_image(self, copy: bool = True) -> np.ndarray:
        """
        Trả về ảnh làm việc hiện tại.

        Args:
            copy (bool): Trả về bản sao (tránh ngoài ý muốn sửa). Mặc định: True.
        """
        return self.img.copy() if copy else self.img

    def get_original(self, copy: bool = True) -> np.ndarray:
        """Trả về ảnh gốc (chưa vẽ gì lên)."""
        return self._img_original.copy() if copy else self._img_original

    # ─── MISC ───────────────────────────────────────────────────────

    def reset_image(self) -> 'ImageObject':
        """Reset ảnh làm việc về ảnh gốc (xóa bbox đã vẽ)."""
        self.img = self._img_original.copy()
        return self

    def copy(self) -> 'ImageObject':
        """Trả về bản sao độc lập của ImageObject."""
        new       = ImageObject(self._img_original.copy(), self.model_name, self.model_detection)
        new.img   = self.img.copy()
        new.faces = [
            FaceRecord(
                f.face_img.copy(), f.face_aligned.copy(),
                f.box, f.box_expanded, f.confidence, f.label,
            )
            for f in self.faces
        ]
        return new

    def __len__(self) -> int:
        return len(self.faces)

    def __repr__(self) -> str:
        total, known, unknown = self.count_faces()
        return (
            f"ImageObject(total_faces={total}, known={known}, unknown={unknown}, "
            f"model='{self.model_name}', detector='{self.model_detection}')"
        )
