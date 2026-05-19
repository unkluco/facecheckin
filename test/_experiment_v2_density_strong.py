from __future__ import annotations

# Path: xử lý đường dẫn file video / output image.
from pathlib import Path

# Type hints giúp người đọc hiểu input/output của hàm rõ hơn.
from typing import Dict, List, Tuple, Optional, Any

# heapq: priority queue để luôn lấy frame có delete_score cao nhất.
# math: xử lý các giá trị số học nhỏ như NaN FPS.
import heapq
import math

# cv2: đọc/ghi video, resize, grayscale, Laplacian.
import cv2

# numpy: xử lý ảnh dạng array và tính toán vectorized.
import numpy as np

# pandas: tạo bảng log/metric để xem và debug.
import pandas as pd

# matplotlib: trực quan hóa các frame output.
import matplotlib.pyplot as plt

# structural_similarity: metric SSIM giữa hai frame grayscale.
from skimage.metrics import structural_similarity as ssim

# Kích thước figure mặc định cho các biểu đồ/frame grid.
plt.rcParams["figure.figsize"] = (12, 8)


def read_video_frames(
    video_path: str | Path,
    frame_stride: int = 1,
    max_frames: Optional[int] = None,
) -> Tuple[List[np.ndarray], Dict[str, Any]]:
    """
    Đọc video từ ổ đĩa và chuyển thành danh sách frame RGB.

    Ý nghĩa:
        Đây là bước input đầu tiên của pipeline. Ta không xử lý trực tiếp file video
        trong thuật toán greedy, mà đọc video thành list frame để có thể:
        - tính SSIM giữa các frame,
        - tính Variance of Laplacian cho từng frame,
        - xóa/giữ frame bằng index.

    Tham số:
        video_path:
            Đường dẫn tới file video, ví dụ "input.mp4".
        frame_stride:
            Chỉ đọc mỗi `frame_stride` frame.
            Ví dụ:
                frame_stride=1  -> đọc mọi frame.
                frame_stride=5  -> chỉ lấy frame 0, 5, 10, 15, ...
            Tham số này giúp giảm tải trước khi chạy thuật toán chính.
        max_frames:
            Giới hạn số frame tối đa được đọc.
            Hữu ích khi muốn test nhanh trên một đoạn đầu video.

    Output:
        frames_rgb:
            List các frame ở dạng RGB, mỗi frame là numpy array shape (H, W, 3).
        metadata:
            Dictionary chứa thông tin phụ:
            - fps
            - số frame OpenCV báo cáo
            - số frame đã đọc
            - mapping từ internal index sang original frame index
            - timestamp giây tương ứng của mỗi frame
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Không tìm thấy video: {video_path}")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"OpenCV không mở được video: {video_path}")

    # FPS dùng để đổi original frame index sang timestamp giây.
    # Một số video/camera có thể không trả FPS hợp lệ, nên cần fallback 0.0.
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or math.isnan(fps):
        fps = 0.0

    total_reported = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    frames_rgb: List[np.ndarray] = []
    original_frame_indices: List[int] = []
    timestamps_sec: List[Optional[float]] = []

    idx = 0
    while True:
        ok, frame_bgr = cap.read()
        if not ok:
            break

        # frame_stride là bước giảm tải rất đơn giản:
        # thay vì đọc mọi frame, ta chỉ lấy một số frame định kỳ.
        if idx % frame_stride == 0:
            # OpenCV đọc ảnh theo BGR, còn matplotlib hiển thị đúng với RGB.
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

            frames_rgb.append(frame_rgb)
            original_frame_indices.append(idx)
            timestamps_sec.append(idx / fps if fps > 0 else None)

            if max_frames is not None and len(frames_rgb) >= max_frames:
                break

        idx += 1

    cap.release()

    if not frames_rgb:
        raise ValueError("Không đọc được frame nào từ video.")

    metadata = {
        "video_path": str(video_path),
        "fps": fps,
        "total_reported_frames": total_reported,
        "loaded_frames": len(frames_rgb),
        "frame_stride": frame_stride,
        "original_frame_indices": original_frame_indices,
        "timestamps_sec": timestamps_sec,
    }
    return frames_rgb, metadata


def to_gray_resized(frame_rgb: np.ndarray, scale: float = 1.0) -> np.ndarray:
    """
    Chuy?n frame RGB sang grayscale v? resize theo t? l?.

    ? ngh?a:
        SSIM v? Laplacian ??u c? th? t?nh tr?n ?nh grayscale. Resize theo t? l?
        gi?p gi?m chi ph? nh?ng v?n b?m theo ?? ph?n gi?i video g?c.

    Tham s?:
        frame_rgb:
            Frame RGB shape (H, W, 3).
        scale:
            T? l? resize so v?i k?ch th??c g?c.
            scale=1.0 gi? nguy?n k?ch th??c, scale=0.5 gi?m m?i chi?u c?n 50%.

    Output:
        gray:
            ?nh grayscale ?? resize theo scale, shape (height, width), dtype th??ng l? uint8.
    """
    if scale <= 0:
        raise ValueError("scale ph?i > 0")

    gray = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2GRAY)

    if scale == 1.0:
        return gray

    height, width = gray.shape[:2]
    new_width = max(1, int(round(width * scale)))
    new_height = max(1, int(round(height * scale)))

    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
    gray = cv2.resize(gray, (new_width, new_height), interpolation=interpolation)
    return gray


def ssim_score(gray_a: np.ndarray, gray_b: np.ndarray) -> float:
    """
    Tính SSIM giữa hai ảnh grayscale đã cùng kích thước.

    Ý nghĩa:
        SSIM đo mức giống nhau về cấu trúc thị giác giữa hai frame.
        Trong thuật toán này:
            SSIM cao  -> hai frame giống nhau -> có thể dư thừa.
            SSIM thấp -> hai frame khác nhau  -> nên giữ cẩn thận hơn.

    Tham số:
        gray_a, gray_b:
            Hai ảnh grayscale có cùng shape và cùng thang giá trị [0, 255].

    Output:
        score:
            Số thực trong [0, 1].
            1 nghĩa là rất giống, 0 nghĩa là rất khác theo cách clip của notebook.
    """
    score = float(ssim(gray_a, gray_b, data_range=255))

    # skimage có thể trả giá trị âm trong vài trường hợp ảnh rất khác nhau.
    # Để score dễ dùng trong công thức, ta clip về [0, 1].
    return float(np.clip(score, 0.0, 1.0))


def variance_of_laplacian(
    frame_rgb: np.ndarray,
    scale: float = 1.0,
    gaussian_preblur: bool = False,
) -> float:
    """
    Tính độ sắc nét bằng Variance of Laplacian.

    Cơ chế:
        1. Chuyển frame sang grayscale.
        2. Resize về kích thước cố định.
        3. Áp filter Laplacian để làm nổi bật cạnh/chi tiết.
        4. Lấy variance của ảnh Laplacian.

    Ý nghĩa:
        - Ảnh rõ thường có cạnh sắc, Laplacian phản ứng mạnh -> variance cao.
        - Ảnh mờ/nhòe bị mất cạnh sắc -> Laplacian yếu hơn -> variance thấp.

    Tham số:
        frame_rgb:
            Frame RGB gốc.
        size:
            Kích thước dùng để đo sharpness, theo format (width, height).
            Không nên quá nhỏ, vì resize quá nhỏ sẽ làm mất cạnh thật.
        gaussian_preblur:
            Nếu True, blur nhẹ ảnh trước khi đo Laplacian để giảm nhiễu.
            Chỉ nên bật khi video nhiễu/compression artifact nhiều.

    Output:
        score:
            Laplacian variance. Giá trị càng cao thì frame càng sắc nét.
            Giá trị này không nằm trong [0, 1], nên về sau ta chuẩn hóa bằng percentile rank.
    """
    gray = to_gray_resized(frame_rgb, scale=scale)

    # Tùy chọn giảm nhiễu: noise cũng là high-frequency nên có thể làm Laplacian tăng giả.
    if gaussian_preblur:
        gray = cv2.GaussianBlur(gray, (3, 3), 0)

    lap = cv2.Laplacian(gray, cv2.CV_64F)
    return float(lap.var())


def percentile_ranks(values: np.ndarray) -> np.ndarray:
    """
    Chuyển một mảng giá trị bất kỳ thành percentile rank trong [0, 1].

    Ý nghĩa:
        Ta dùng hàm này để chuẩn hóa Variance of Laplacian theo toàn cục video.
        Thay vì hỏi "Laplacian = 500 là cao hay thấp?", ta hỏi:
            "Frame này sắc nét hơn bao nhiêu phần trăm frame khác?"

    Cách hiểu output:
        rank gần 1.0 -> thuộc nhóm giá trị cao trong video.
        rank gần 0.0 -> thuộc nhóm giá trị thấp trong video.

    Tham số:
        values:
            Mảng 1D các giá trị cần xếp hạng.

    Output:
        ranks:
            Mảng cùng chiều với values, mỗi phần tử nằm trong [0, 1].
            Các giá trị bằng nhau được gán average rank để xử lý tie công bằng.
    """
    values = np.asarray(values, dtype=float)
    n = len(values)

    if n == 0:
        return np.array([], dtype=float)
    if n == 1:
        return np.array([1.0], dtype=float)

    # mergesort ổn định, giúp xử lý các phần tử bằng nhau dễ kiểm soát hơn.
    order = np.argsort(values, kind="mergesort")
    sorted_values = values[order]
    ranks = np.empty(n, dtype=float)

    i = 0
    while i < n:
        # Tìm block các giá trị bằng nhau: sorted_values[i:j].
        j = i + 1
        while j < n and sorted_values[j] == sorted_values[i]:
            j += 1

        # Average rank cho tie:
        # ví dụ các vị trí 3,4,5 bằng nhau -> rank trung bình là 4.
        avg_rank = (i + j - 1) / 2.0
        ranks[order[i:j]] = avg_rank / (n - 1)

        i = j

    return ranks


def harmonic_mean(a: float, b: float, eps: float = 1e-12) -> float:
    """
    Tính harmonic mean của hai số không âm.

    Ý nghĩa trong thuật toán:
        Ta dùng harmonic mean để gộp:
            SSIM(frame trái, frame hiện tại)
            SSIM(frame hiện tại, frame phải)

        Harmonic mean cao chỉ khi cả hai SSIM cùng cao.
        Nếu một phía thấp, harmonic mean bị kéo xuống mạnh.

    Vì sao hợp lý:
        Một frame chỉ nên bị xem là dư thừa nếu nó giống cả bên trái lẫn bên phải.
        Nếu nó chỉ giống một bên nhưng khác bên còn lại, có thể đó là frame chuyển tiếp quan trọng.

    Tham số:
        a, b:
            Hai giá trị similarity, thường là SSIM trong [0, 1].
        eps:
            Số rất nhỏ để tránh chia cho 0.

    Output:
        h:
            Harmonic mean trong [0, 1] nếu a,b nằm trong [0, 1].
    """
    a = max(float(a), 0.0)
    b = max(float(b), 0.0)

    if a == 0.0 or b == 0.0:
        return 0.0

    return float((2.0 * a * b) / (a + b + eps))


def compress_video_keyframes(
    video_path: str | Path,
    n: int,
    *,
    frame_stride: int = 1,
    max_frames: Optional[int] = None,
    similarity_scale: float = 1.0,
    sharpness_scale: float = 1.0,
    gaussian_preblur_for_laplacian: bool = False,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Hàm chính: nén video bằng cách loại bỏ frame dư thừa cho đến khi còn n frame.

    Mục tiêu:
        Cho một video có T frame, chọn ra n frame đại diện.
        Thuật toán không dùng face detection/face tracking ở bước này.
        Nó chỉ dựa trên:
            1. Độ dư thừa với hàng xóm bằng SSIM.
            2. Độ mờ/nhòe bằng Variance of Laplacian.

    Công thức chính cho frame nội bộ F_i:
        s_left  = SSIM(F_left, F_i)
        s_right = SSIM(F_i, F_right)

        redundancy_i = harmonic_mean(s_left, s_right)

        sharpness_i = VarianceOfLaplacian(F_i)
        sharpness_rank_i = percentile_rank(sharpness_i)
        blur_badness_i = 1 - sharpness_rank_i

        delete_score_i = redundancy_i * blur_badness_i

    Ý nghĩa:
        - redundancy_i cao:
            Frame F_i giống cả hai frame hàng xóm -> dư thừa.
        - blur_badness_i cao:
            Frame F_i mờ hơn nhiều frame khác trong cùng video.
        - delete_score_i cao:
            Frame vừa dư thừa vừa mờ -> nên xóa trước.

    Tham số:
        video_path:
            Đường dẫn tới file video.
        n:
            Số frame output mong muốn.
        frame_stride:
            Đọc mỗi `frame_stride` frame để giảm tải ban đầu.
        max_frames:
            Giới hạn số frame tối đa được đọc, hữu ích khi thử nghiệm nhanh.
        similarity_scale:
            Tỉ lệ resize dùng để tính SSIM.
            Mặc định 1.0 nghĩa là dùng kích thước gốc.
        sharpness_scale:
            Tỉ lệ resize dùng để tính Variance of Laplacian.
            Mặc định 1.0 nghĩa là dùng kích thước gốc.
        Ghi chú về frame đầu/cuối:
            Hàm này cho phép xóa cả frame đầu và frame cuối.
            Vì vậy không có tham số `protect_endpoints`.
            Với frame đầu/cuối, redundancy được tính bằng SSIM với hàng xóm duy nhất.
        gaussian_preblur_for_laplacian:
            Nếu True, blur nhẹ trước khi tính Laplacian để giảm noise.
        verbose:
            Nếu True, in tóm tắt sau khi chạy.

    Output:
        result:
            Dictionary gồm:
            - selected_indices_internal:
                Index nội bộ của các frame được giữ.
            - selected_original_frame_indices:
                Original frame index trong video gốc.
            - selected_timestamps_sec:
                Timestamp giây của các frame được giữ.
            - selected_frames_rgb:
                List frame RGB được giữ.
            - frame_metrics:
                DataFrame metric của mọi frame đã đọc.
            - deletion_log:
                DataFrame ghi lại thứ tự xóa frame.
            - metadata:
                Thông tin video đọc được.
            - parameters:
                Các tham số đã dùng để chạy thuật toán.
    """
    if n < 1:
        raise ValueError("n phải >= 1")

    # ------------------------------------------------------------------
    # Bước 0: Đọc video thành list frame RGB.
    # ------------------------------------------------------------------
    frames_rgb, metadata = read_video_frames(
        video_path,
        frame_stride=frame_stride,
        max_frames=max_frames,
    )
    T = len(frames_rgb)

    if n >= T:
        # Không cần nén nếu số frame đọc được đã <= n.
        if verbose:
            print(f"Video chỉ có {T} frame đã đọc; n={n}. Trả về toàn bộ frame.")
        return {
            "selected_indices_internal": list(range(T)),
            "selected_original_frame_indices": metadata["original_frame_indices"],
            "selected_timestamps_sec": metadata["timestamps_sec"],
            "selected_frames_rgb": frames_rgb,
            "frame_metrics": pd.DataFrame(),
            "deletion_log": pd.DataFrame(),
            "metadata": metadata,
            "parameters": {
                "n": n,
                "frame_stride": frame_stride,
                "max_frames": max_frames,
                "similarity_scale": similarity_scale,
                "sharpness_scale": sharpness_scale,
                "gaussian_preblur_for_laplacian": gaussian_preblur_for_laplacian,
            },
        }

    # ------------------------------------------------------------------
    # Bước 1: Tạo representation nhỏ để tính SSIM nhanh.
    # ------------------------------------------------------------------
    # sim_repr[i] là frame i đã grayscale + resize nhỏ.
    # Ta không tính SSIM trên frame gốc để tránh tốn chi phí.
    sim_repr = [to_gray_resized(frame, scale=similarity_scale) for frame in frames_rgb]

    # ------------------------------------------------------------------
    # Bước 2: Tính sharpness cho từng frame bằng Variance of Laplacian.
    # ------------------------------------------------------------------
    # sharpness_raw càng cao -> frame càng sắc nét.
    sharpness_raw = np.array([
        variance_of_laplacian(
            frame,
            scale=sharpness_scale,
            gaussian_preblur=gaussian_preblur_for_laplacian,
        )
        for frame in frames_rgb
    ], dtype=float)

    # Percentile rank giúp chuẩn hóa toàn cục trong video:
    #   sharpness_rank gần 1 -> sắc nét hơn phần lớn frame khác.
    #   sharpness_rank gần 0 -> mờ hơn phần lớn frame khác.
    sharpness_rank = percentile_ranks(sharpness_raw)

    # blur_badness là hướng ngược lại:
    #   blur_badness gần 1 -> frame thuộc nhóm mờ.
    #   blur_badness gần 0 -> frame thuộc nhóm sắc nét.
    blur_badness = 1.0 - sharpness_rank

    # ------------------------------------------------------------------
    # Bước 3: Biểu diễn chuỗi frame bằng doubly linked list.
    # ------------------------------------------------------------------
    # Thay vì xóa item khỏi list Python liên tục, ta lưu prev/next index.
    #
    # Ban đầu:
    #   prev_idx[i] = i - 1
    #   next_idx[i] = i + 1
    #
    # Khi xóa i:
    #   l = prev_idx[i]
    #   r = next_idx[i]
    #   next_idx[l] = r
    #   prev_idx[r] = l
    prev_idx: List[Optional[int]] = [None] + list(range(T - 1))
    next_idx: List[Optional[int]] = list(range(1, T)) + [None]

    alive = [True] * T

    # version giúp xử lý lazy update trong heap.
    # Khi score của frame i thay đổi, ta tăng version[i] và push score mới.
    # Các score cũ vẫn nằm trong heap nhưng sẽ bị bỏ qua khi pop.
    version = [0] * T

    alive_count = T

    # ------------------------------------------------------------------
    # Bước 4: SSIM cache theo kiểu lazy computation.
    # ------------------------------------------------------------------
    # SSIM có thể bị gọi nhiều lần cho cùng một cặp frame hàng xóm.
    # Cache giúp tránh tính lại nếu cặp đó đã được tính.
    #
    # Quan trọng:
    #   Ta KHÔNG precompute toàn bộ SSIM ban đầu.
    #   Ta cũng KHÔNG tính trước SSIM cho cạnh mới sau khi xóa frame.
    #   get_pair_ssim() chỉ được gọi khi redundancy()/delete_score() thật sự cần.
    #   Cách này làm code gọn hơn và tránh một số phép tính SSIM thừa.
    sim_cache: Dict[Tuple[int, int], float] = {}

    def pair_key(a: int, b: int) -> Tuple[int, int]:
        """
        Tạo key chuẩn cho một cặp frame.

        Ý nghĩa:
            SSIM(a, b) = SSIM(b, a), nên cache chỉ cần một key duy nhất.
            Ta luôn lưu key dạng (min_index, max_index).

        Tham số:
            a, b:
                Hai internal frame index.

        Output:
            Tuple[int, int] dùng làm key trong sim_cache.
        """
        return (a, b) if a < b else (b, a)

    def get_pair_ssim(a: int, b: int) -> float:
        """
        Lấy SSIM giữa hai frame, có cache.

        Ý nghĩa:
            Nếu cặp (a,b) chưa từng được tính, hàm sẽ tính SSIM và lưu lại.
            Nếu đã có trong cache, hàm trả về ngay để tiết kiệm thời gian.

        Tham số:
            a, b:
                Hai internal frame index.

        Output:
            SSIM score trong [0, 1].
        """
        key = pair_key(a, b)
        if key not in sim_cache:
            sim_cache[key] = ssim_score(sim_repr[a], sim_repr[b])
        return sim_cache[key]

    def redundancy(i: int) -> float:
        """
        Tính độ dư thừa của frame i dựa trên hai hàng xóm hiện tại.

        Ý nghĩa:
            redundancy_i cao khi frame i giống cả bên trái và bên phải.
            Ta dùng harmonic mean để phạt mạnh trường hợp chỉ giống một bên.

        Tham số:
            i:
                Internal frame index cần tính.

        Output:
            redundancy score trong [0, 1], hoặc -inf nếu frame không hợp lệ để xóa.
        """
        if not alive[i]:
            return float("-inf")

        l = prev_idx[i]
        r = next_idx[i]

        # Nếu video chỉ còn một frame hoặc frame cô lập, không tính được redundancy.
        if l is None and r is None:
            return float("-inf")

        # Frame đầu/cuối vẫn được phép xóa.
        # Vì chúng chỉ có một hàng xóm, ta dùng SSIM với hàng xóm duy nhất.
        if l is None:
            return get_pair_ssim(i, r)
        if r is None:
            return get_pair_ssim(l, i)

        s_left = get_pair_ssim(l, i)
        s_right = get_pair_ssim(i, r)

        return harmonic_mean(s_left, s_right)

    def delete_score(i: int) -> float:
        """
        Tính điểm xóa của frame i.

        Công thức:
            delete_score_i = redundancy_i * blur_badness_i

        Ý nghĩa:
            Điểm cao nếu frame:
                - giống cả hai hàng xóm,
                - và mờ hơn tương đối so với toàn video.

        Tham số:
            i:
                Internal frame index.

        Output:
            delete_score, hoặc -inf nếu frame không nên/không thể xóa.
        """
        r = redundancy(i)
        if not np.isfinite(r):
            return float("-inf")

        quality_weight = 0.75 + 0.25 * blur_badness[i]
        l = prev_idx[i]
        rr = next_idx[i]
        left_gap = i - l if l is not None else 1
        right_gap = rr - i if rr is not None else 1
        span = left_gap + right_gap
        target_gap = max(1.0, T / max(n, 1))
        density_weight = 1.0 / (1.0 + (span / target_gap) ** 4)
        return float(r * quality_weight * density_weight)

    # ------------------------------------------------------------------
    # Bước 5: Max-heap chứa các ứng viên xóa.
    # ------------------------------------------------------------------
    # heapq của Python là min-heap, nên ta lưu (-score, frame_id, version).
    # Pop ra phần tử nhỏ nhất theo -score tức là score lớn nhất.
    heap: List[Tuple[float, int, int]] = []

    def push_candidate(i: Optional[int]) -> None:
        """
        Đưa frame i vào heap nếu nó là ứng viên xóa hợp lệ.

        Ý nghĩa:
            Sau mỗi lần xóa một frame, chỉ hai hàng xóm của frame đó thay đổi score.
            Ta chỉ cần push lại hai hàng xóm này, không cần rebuild toàn bộ heap.

        Tham số:
            i:
                Internal frame index, có thể None ở biên video.

        Output:
            Không trả về gì. Hàm cập nhật heap tại chỗ.
        """
        if i is None or not alive[i]:
            return

        score = delete_score(i)
        if np.isfinite(score):
            heapq.heappush(heap, (-score, i, version[i]))

    # Khởi tạo heap với mọi frame hợp lệ.
    for i in range(T):
        push_candidate(i)

    deletion_records: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Bước 6: Greedy loop.
    # ------------------------------------------------------------------
    # Mỗi vòng:
    #   1. Lấy frame có delete_score cao nhất.
    #   2. Xóa frame đó khỏi linked list.
    #   3. Nối lại hai hàng xóm trái/phải.
    #   4. Cập nhật score cho hai hàng xóm bị ảnh hưởng.
    while alive_count > n:
        if not heap:
            raise RuntimeError(
                "Heap rỗng trước khi đạt n frame. "
                "Thử tăng n hoặc kiểm tra lại dữ liệu video."
            )

        neg_score, i, ver = heapq.heappop(heap)

        # Lazy deletion:
        # Nếu frame đã bị xóa hoặc version cũ, bỏ qua item này.
        if not alive[i] or ver != version[i]:
            continue

        # Tính lại score hiện tại sau khi pop từ heap.
        # Vì heap dùng lazy update, score trong heap có thể đã cũ.
        # Ở đây ta tính redundancy một lần rồi dùng lại để tránh gọi get_pair_ssim thừa.
        current_red = redundancy(i)
        if not np.isfinite(current_red):
            continue

        current_score = delete_score(i)

        l = prev_idx[i]
        r = next_idx[i]

        # Ghi log trước khi xóa để debug/visualize sau này.
        deletion_records.append({
            "delete_order": len(deletion_records) + 1,
            "removed_internal_index": i,
            "removed_original_frame": metadata["original_frame_indices"][i],
            "removed_time_sec": metadata["timestamps_sec"][i],
            "left_original_frame": metadata["original_frame_indices"][l] if l is not None else None,
            "right_original_frame": metadata["original_frame_indices"][r] if r is not None else None,
            "delete_score": current_score,
            "redundancy_hmean_ssim": current_red,
            "blur_badness": float(blur_badness[i]),
            "laplacian_variance": float(sharpness_raw[i]),
            "laplacian_percentile_rank": float(sharpness_rank[i]),
        })

        # Xóa frame i khỏi linked list.
        alive[i] = False
        alive_count -= 1

        # Nối frame trái và phải lại với nhau.
        if l is not None:
            next_idx[l] = r
        if r is not None:
            prev_idx[r] = l

        # Không cần gọi get_pair_ssim(l, r) ở đây.
        # Nếu cặp l-r thật sự cần để tính score cho l hoặc r,
        # redundancy()/delete_score() sẽ gọi get_pair_ssim() sau theo kiểu lazy.

        # Chỉ hai hàng xóm l và r bị thay đổi redundancy.
        # Các frame xa hơn vẫn có hàng xóm như cũ, nên score không đổi.
        for j in (l, r):
            if j is not None and alive[j]:
                version[j] += 1
                push_candidate(j)

    # ------------------------------------------------------------------
    # Bước 7: Gom output.
    # ------------------------------------------------------------------
    selected_indices_internal = [i for i in range(T) if alive[i]]
    selected_original_frame_indices = [
        metadata["original_frame_indices"][i]
        for i in selected_indices_internal
    ]
    selected_timestamps_sec = [
        metadata["timestamps_sec"][i]
        for i in selected_indices_internal
    ]
    selected_frames_rgb = [frames_rgb[i] for i in selected_indices_internal]

    # Bảng metric cuối cùng cho mọi frame đã đọc.
    # Bảng này giúp kiểm tra frame nào được giữ, frame nào bị xóa.
    frame_metric_records = []
    for i in range(T):
        frame_metric_records.append({
            "internal_index": i,
            "original_frame": metadata["original_frame_indices"][i],
            "time_sec": metadata["timestamps_sec"][i],
            "kept": alive[i],
            "laplacian_variance": float(sharpness_raw[i]),
            "laplacian_percentile_rank": float(sharpness_rank[i]),
            "blur_badness": float(blur_badness[i]),
        })

    result = {
        "selected_indices_internal": selected_indices_internal,
        "selected_original_frame_indices": selected_original_frame_indices,
        "selected_timestamps_sec": selected_timestamps_sec,
        "selected_frames_rgb": selected_frames_rgb,
        "frame_metrics": pd.DataFrame(frame_metric_records),
        "deletion_log": pd.DataFrame(deletion_records),
        "metadata": metadata,
        "parameters": {
            "n": n,
            "frame_stride": frame_stride,
            "max_frames": max_frames,
            "similarity_scale": similarity_scale,
            "sharpness_scale": sharpness_scale,
            "gaussian_preblur_for_laplacian": gaussian_preblur_for_laplacian,
        },
    }

    if verbose:
        print(f"Loaded frames: {T}")
        print(f"Output frames: {len(selected_indices_internal)}")
        print(f"Removed frames: {T - len(selected_indices_internal)}")
        print("Selected original frame indices:")
        print(selected_original_frame_indices)

    return result


def plot_selected_frames_grid(
    result: Dict[str, Any],
    rows: int = 3,
    cols: int = 4,
    figsize: Tuple[int, int] = (14, 9),
    save_path: Optional[str | Path] = None,
) -> None:
    """
    Hiển thị các frame output theo dạng lưới.

    Ý nghĩa:
        Sau khi thuật toán chọn ra n frame, ta cần nhìn trực quan xem các frame
        được giữ có phân bố hợp lý theo thời gian và nội dung không.
        Với demo n=12, lưới 3x4 là cách xem nhanh nhất.

    Tham số:
        result:
            Dictionary trả về từ compress_video_keyframes().
        rows:
            Số hàng của lưới.
        cols:
            Số cột của lưới.
        figsize:
            Kích thước figure matplotlib.
        save_path:
            Nếu khác None, lưu ảnh lưới ra đường dẫn này.

    Output:
        Không trả về giá trị. Hàm hiển thị figure và tùy chọn lưu file ảnh.
    """
    frames = result["selected_frames_rgb"]
    original_indices = result["selected_original_frame_indices"]
    timestamps = result["selected_timestamps_sec"]

    max_items = rows * cols
    show_count = min(len(frames), max_items)

    fig, axes = plt.subplots(rows, cols, figsize=figsize)
    axes = np.array(axes).reshape(-1)

    for ax_i, ax in enumerate(axes):
        ax.axis("off")

        if ax_i < show_count:
            frame = frames[ax_i]
            ax.imshow(frame)

            # Hiển thị original frame index thay vì internal index,
            # vì original index khớp với vị trí frame trong video gốc.
            t = timestamps[ax_i]
            if t is None:
                title = f"#{ax_i + 1}: frame {original_indices[ax_i]}"
            else:
                title = f"#{ax_i + 1}: frame {original_indices[ax_i]}\n{t:.2f}s"

            ax.set_title(title, fontsize=10)

    fig.suptitle("Selected output frames", fontsize=16)
    plt.tight_layout()

    if save_path is not None:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")

    plt.show()


def summarize_result(result: Dict[str, Any], tail_deletions: int = 8) -> None:
    """
    In tóm tắt kết quả nén video.

    Ý nghĩa:
        Hàm này giúp kiểm tra nhanh:
        - Video nào được xử lý.
        - Số frame đầu vào/đầu ra.
        - Những original frame index nào được giữ.
        - Một số frame cuối cùng bị xóa trong deletion log.

    Tham số:
        result:
            Dictionary trả về từ compress_video_keyframes().
        tail_deletions:
            Số dòng cuối trong deletion_log muốn hiển thị.
            Các dòng cuối thường là những quyết định xóa "khó" nhất vì lúc đó
            video đã bị rút gọn nhiều.

    Output:
        Không trả về giá trị. Hàm in thông tin và hiển thị DataFrame nếu có.
    """
    meta = result["metadata"]

    print("Video:", meta["video_path"])
    print("FPS:", meta["fps"])
    print("Loaded frames:", meta["loaded_frames"])
    print("Output frames:", len(result["selected_indices_internal"]))
    print("Selected original frame indices:")
    print(result["selected_original_frame_indices"])

    deletion_log = result["deletion_log"]
    if len(deletion_log) > 0:
        print(f"\nLast {tail_deletions} deleted frames:")
        display(deletion_log.tail(tail_deletions))


def create_synthetic_demo_video(
    output_path: str | Path = "demo_synthetic_10s.mp4",
    seconds: int = 10,
    fps: int = 20,
    width: int = 320,
    height: int = 180,
) -> Path:
    """
    Tạo một video demo nội bộ để test notebook mà không cần internet.

    Ý nghĩa:
        Trong môi trường notebook, đôi khi không tải được video từ internet.
        Hàm này tạo một video 10 giây có:
        - background có texture,
        - vật thể chuyển động,
        - một số đoạn bị Gaussian blur,
        - text frame number để dễ kiểm tra frame output.

    Tham số:
        output_path:
            Đường dẫn file video sẽ được tạo.
        seconds:
            Thời lượng video tính bằng giây.
        fps:
            Số frame mỗi giây.
        width, height:
            Kích thước video output.

    Output:
        Path tới file video demo đã tạo.
    """
    output_path = Path(output_path)

    # mp4v là codec tương đối phổ biến trong OpenCV cho file .mp4.
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

    if not writer.isOpened():
        raise RuntimeError("Không tạo được VideoWriter. Hãy kiểm tra codec mp4v/OpenCV.")

    total = seconds * fps

    for i in range(total):
        t = i / fps

        # Frame RGB rỗng.
        frame = np.zeros((height, width, 3), dtype=np.uint8)

        # Background gradient + pattern để tạo cạnh/texture.
        # Điều này giúp Laplacian variance có tín hiệu rõ hơn.
        x_grad = np.linspace(40, 120, width, dtype=np.uint8)
        y_grad = np.linspace(20, 80, height, dtype=np.uint8)
        frame[:, :, 0] = x_grad[None, :]
        frame[:, :, 1] = y_grad[:, None]
        frame[:, :, 2] = 90

        # Object chuyển động mượt.
        # Nó hơi giống mặt để output dễ quan sát bằng mắt.
        cx = int(30 + (width - 60) * (0.5 + 0.5 * np.sin(2 * np.pi * t / seconds)))
        cy = int(height / 2 + 40 * np.sin(2 * np.pi * t / 3.0))

        cv2.circle(frame, (cx, cy), 22, (230, 220, 80), -1)
        cv2.circle(frame, (cx - 7, cy - 6), 3, (20, 20, 20), -1)
        cv2.circle(frame, (cx + 7, cy - 6), 3, (20, 20, 20), -1)
        cv2.ellipse(frame, (cx, cy + 6), (8, 4), 0, 0, 180, (20, 20, 20), 2)

        # Một rectangle khác để tạo thay đổi nội dung theo thời gian.
        rx = int((i * 2) % width)
        cv2.rectangle(frame, (rx - 30, 20), (rx + 30, 45), (80, 200, 220), -1)

        # Text frame number để khi hiển thị output, ta biết frame nào được chọn.
        cv2.putText(
            frame,
            f"frame {i}",
            (10, height - 12),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (255, 255, 255),
            1,
        )

        # Cố tình làm mờ một số đoạn để test:
        # thuật toán nên ít giữ các frame này nếu chúng cũng dư thừa với hàng xóm.
        if (45 <= i <= 65) or (120 <= i <= 135) or (i % 37 == 0):
            frame = cv2.GaussianBlur(frame, (13, 13), 0)

        # VideoWriter của OpenCV cần BGR, trong khi frame đang là RGB.
        writer.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))

    writer.release()
    return output_path


# demo_path = create_synthetic_demo_video("demo_synthetic_10s.mp4")
demo_path = "demo_synthetic_10s.mp4"
