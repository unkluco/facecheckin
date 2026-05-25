# FaceCheckin

FaceCheckin là ứng dụng điểm danh lớp học bằng nhận diện khuôn mặt, chạy cục bộ trên máy giáo viên và có giao diện web cho laptop + giao diện phụ cho điện thoại trong cùng mạng LAN. Dữ liệu lớp, sinh viên, ảnh khuôn mặt và lịch sử điểm danh được lưu bằng SQLite và thư mục ảnh local.

Dự án hiện hỗ trợ nhận diện ảnh, video điểm danh, quản lý lớp/sinh viên, đăng ký khuôn mặt bằng ảnh/camera/video, xuất báo cáo và đóng gói Windows MSI.

## Tính năng chính

### Điểm danh

- Tạo tiết học theo lớp, bắt đầu/dừng phiên điểm danh.
- Điểm danh bằng camera laptop, upload ảnh, hoặc upload video.
- Video điểm danh dùng thuật toán chọn keyframe 2 pha:
  - Pha 1: ghép các cặp frame liền kề có độ tương đồng cao để giảm số nhóm.
  - Pha 2: giữ các frame tốt theo điểm `sqrt(sharpness_norm * face_norm)`.
  - Số keyframe video điểm danh có thể chỉnh, tối đa `50` frame.
- Hiển thị realtime qua WebSocket: ảnh xử lý, khuôn mặt nhận diện, trạng thái có mặt/vắng.
- Hỗ trợ điểm danh thủ công và xóa điểm danh trong từng tiết học.

### Quản lý lớp và sinh viên

- Tạo/xóa lớp, xem chi tiết danh sách sinh viên trong lớp.
- Thêm/sửa/xóa sinh viên theo bản nháp rồi lưu một lần.
- MSSV/folder ảnh chỉ cần duy nhất trong từng lớp, không bắt buộc duy nhất toàn hệ thống.
- Thêm sinh viên từ lớp khác và copy ảnh khuôn mặt.
- Import lớp mới từ CSV/XLSX, có thể import kèm thư mục ảnh khuôn mặt.
- Export danh sách lớp ra CSV và export ảnh khuôn mặt dạng ZIP.

### Đăng ký khuôn mặt

- Đăng ký ảnh cho từng sinh viên bằng camera laptop hoặc upload ảnh.
- Ảnh đăng ký được preprocess: detect mặt, crop/align, bỏ ảnh không phát hiện mặt.
- Đăng ký lớp bằng video:
  - Upload video vào lớp hiện tại.
  - Trích keyframe và gom các khuôn mặt khác nhau.
  - Hiển thị các ứng viên để sửa MSSV/tên tại chỗ.
  - MSSV mặc định là số tăng dần; tên mặc định là `Người 1`, `Người 2`, ...
  - Chỉ thêm vào bản nháp, chưa ghi thật cho đến khi bấm lưu lớp.

### Giao diện điện thoại

- Mở bằng QR hoặc URL LAN: `http://<IP_MAY_TINH>:8080/mobile`.
- Dùng chủ yếu cho điểm danh nhanh:
  - Chụp ảnh.
  - Upload ảnh.
  - Upload video.
  - Chỉnh số frame tối đa khi upload video, tối đa `50`.
- Điện thoại và laptop phải cùng mạng LAN.

### Cài đặt và nhận diện

- Engine nhận diện: InsightFace/SCRFD + ArcFace chạy qua ONNXRuntime CPU.
- Cache embedding theo từng lớp để tăng tốc nhận diện.
- Cache được tự invalidate khi thêm/xóa/sửa ảnh khuôn mặt.
- Có trang settings để chỉnh threshold, det size, multi-face, crop ảnh đăng ký, bbox/label và giới hạn upload video.

### Đóng gói Windows

- Có PyInstaller `onedir` + WiX MSI.
- Entry point bản đóng gói là `backend/tray_launcher.py`:
  - Ẩn console.
  - Tự mở browser tới `http://localhost:8080`.
  - Có System Tray menu để mở dashboard hoặc tắt server.
- Bundle model offline `buffalo_l/det_10g.onnx` và `buffalo_l/w600k_r50.onnx`.
- Bản release không nên bundle dữ liệu runtime của developer.

## Yêu cầu hệ thống

### Chạy từ source

- Windows 10/11 khuyến nghị.
- Python `3.10` hoặc `3.11` 64-bit.
- Không khuyến nghị Python `3.13+` cho source vì hệ sinh thái InsightFace/ONNXRuntime có thể thiếu wheel hoặc kéo build C++.
- Internet ở lần cài đầu để tải dependency/model nếu máy chưa có.
- Camera/browser permission nếu dùng camera.

### Chạy bản MSI

- Windows 10/11.
- Không cần cài Python hay dependency thủ công.
- Có thể bị Windows Defender/SmartScreen cảnh báo vì binary chưa ký số.
- Server dùng port `8080`; nếu port này bị chiếm, app có thể không mở được.

## Khởi động nhanh từ source

### Cách 1: dùng batch Windows

Ở thư mục gốc dự án, chạy:

```bat
face.bat
```

Script sẽ:

1. Kiểm tra hoặc tạo `.venv` bằng Python 3.10/3.11.
2. Cài dependencies từ `backend\requirements.txt`.
3. Chạy `backend\start.py`.
4. Tự mở `http://localhost:8080`.

Khi dùng cách này, hãy giữ cửa sổ terminal mở trong lúc điểm danh. Muốn tắt server thì đóng cửa sổ hoặc dùng `Ctrl+C`.

### Cách 2: chạy thủ công

```powershell
cd C:\Users\ADMIN\Desktop\ff\final\facecheckin
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd backend
..\.venv\Scripts\python.exe start.py
```

Sau khi chạy:

- Dashboard laptop: `http://localhost:8080`
- Mobile LAN: `http://<IP_MAY_TINH>:8080/mobile`
- Health check: `http://localhost:8080/ping`

## Cách dùng cơ bản

### 1. Tạo hoặc import lớp

- Vào màn hình `Lớp học`.
- Chọn `+ Tạo lớp trống` để tạo lớp mới.
- Hoặc chọn `Import lớp mới` để import CSV/XLSX và thư mục ảnh khuôn mặt.

CSV thường dùng dạng:

```csv
MSSV,Họ tên
001,Người 1
002,Người 2
```

### 2. Thêm ảnh khuôn mặt

- Mở chi tiết lớp.
- Chọn sinh viên và mở phần ảnh khuôn mặt.
- Thêm ảnh bằng upload hoặc camera.
- Bấm lưu thay đổi lớp để ghi thật.

### 3. Tạo tiết học và điểm danh

- Vào màn hình `Tiết học`.
- Tạo tiết học cho lớp cần điểm danh.
- Bấm bắt đầu tiết học.
- Chọn một trong các cách:
  - Camera laptop.
  - Upload ảnh.
  - Upload video.
  - Điện thoại qua QR/mobile URL.

### 4. Xuất kết quả

- Xuất CSV điểm danh của tiết học.
- Điền điểm danh vào file có sẵn bằng API/export UI.
- Export danh sách lớp hoặc ảnh khuôn mặt nếu cần backup/chuyển máy.

## Cấu trúc dự án

```text
facecheckin/
├── README.md
├── AGENTS.md
├── face.bat                       # Chạy source trên Windows
├── stop_facecheckin.bat           # Dừng tiến trình liên quan nếu cần
├── assists/
│   └── logo.png
├── backend/
│   ├── start.py                   # Entry chạy server khi dùng source
│   ├── tray_launcher.py           # Entry cho bản đóng gói desktop/tray
│   ├── server.py                  # aiohttp server, REST API, WebSocket
│   ├── database.py                # SQLite schema, migration, CRUD
│   ├── face_engine.py             # InsightFace/SCRFD/ArcFace wrapper + cache
│   ├── config.py                  # Path/runtime config, port, token, CORS
│   ├── requirements.txt
│   ├── recognition_settings.json  # Cấu hình nhận diện mặc định/runtime
│   ├── attendance.db              # Runtime DB khi chạy source
│   ├── data/                      # Ảnh đăng ký theo class/student
│   ├── cache/                     # Embedding cache
│   ├── received/                  # Ảnh/video upload tạm
│   ├── processed/                 # Ảnh đã xử lý/crop/output
│   └── static/
│       ├── index.html             # Dashboard laptop
│       ├── mobile.html            # UI điện thoại
│       ├── js/app.js
│       └── css/app.css
├── deploy/
│   ├── FaceCheckin.spec           # PyInstaller spec
│   ├── build_msi.ps1              # WiX MSI builder
│   ├── assets/FaceCheckin.ico
│   ├── dist/FaceCheckin/          # Output PyInstaller
│   └── installer/                 # Output MSI
└── test/                          # Notebook/script thử nghiệm local
```

## Runtime data và đường dẫn

### Source mode

Khi chạy từ source, runtime data nằm trong `backend/`:

```text
backend/attendance.db
backend/data/
backend/cache/
backend/received/
backend/processed/
```

### Frozen/MSI mode

Khi chạy từ EXE/MSI:

- Static UI và code được đọc từ bundle `_internal`.
- Runtime data được tạo cạnh `FaceCheckin.exe`:

```text
FaceCheckin/
├── FaceCheckin.exe
├── _internal/
├── attendance.db
├── data/
├── cache/
├── received/
└── processed/
```

Điều này giúp app chạy offline và không phụ thuộc dữ liệu developer. Tuy nhiên nếu uninstall xóa thư mục cài đặt thì có thể mất dữ liệu runtime, nên cần backup trước khi gỡ/cài lại nếu dữ liệu quan trọng.

## API chính

Một số endpoint quan trọng:

| Nhóm | Endpoint |
|---|---|
| Health/UI | `GET /`, `GET /ping`, `GET /mobile`, `GET /ws` |
| Nhận diện | `POST /api/recognize` |
| Video điểm danh | `POST /api/video/keyframes` |
| Video đăng ký lớp | `POST /api/classes/{id}/video-faces/extract` |
| Lớp | `GET/POST /api/classes`, `DELETE /api/classes/{id}` |
| Sinh viên | `GET/POST /api/students`, `PUT/DELETE /api/students/{id}` |
| Ảnh khuôn mặt | `GET/POST /api/students/{id}/faces`, `DELETE /api/students/{id}/faces/{filename}` |
| Tiết học | `GET/POST /api/lessons`, `POST /api/lessons/{id}/start`, `POST /api/lessons/{id}/stop` |
| Điểm danh tiết | `GET /api/lessons/{id}/attendance`, `POST /api/lessons/{id}/attendance/manual` |
| Export | `GET /api/classes/{id}/export/csv`, `GET /api/classes/{id}/export/faces`, `GET /api/lessons/{id}/export/csv` |
| Nhận diện settings/cache | `GET/PUT /api/recognition/settings`, `GET /api/recognition/cache/status`, `POST /api/recognition/cache/rebuild` |

## Thuật toán video keyframe

Video upload được giảm về tối đa `m` keyframe trước khi nhận diện.

1. Đọc frame và tính metric:
   - `sim_gray`: ảnh xám resize để tính tương đồng frame liền kề.
   - `sharpness`: phương sai Laplacian.
   - `face_score`: điểm mặt nhẹ bằng Haar Cascade, chuẩn hóa về `[0, 1]`.
2. Chuẩn hóa độ nét:
   - `sharpness_norm` dùng min-max robust theo percentile `p05 -> p95`, clamp `[0, 1]`.
3. Điểm chọn frame:
   - `selection_score = sqrt(sharpness_norm * face_norm)`.
   - Không dùng trọng số, không thêm sàn.
4. Lặp 2 pha:
   - Ghép các cặp frame liền kề có độ tương đồng cao.
   - Trong mỗi nhóm giữ khoảng 50% frame tốt nhất theo `selection_score`.
5. Lặp đến khi còn `m` frame hoặc ít hơn.

Giới hạn hiện tại:

- Video điểm danh laptop/mobile: `m <= 50`.
- Video đăng ký lớp: `m <= 40`.
- Số frame đọc từ video có guard `max_frames` để tránh xử lý quá tải.

## Đóng gói MSI

### Yêu cầu build

- Windows.
- Python 3.10 khuyến nghị.
- WiX Toolset v3 (`candle.exe`, `light.exe`).
- Dependencies đã cài theo `backend\requirements.txt`.
- Model InsightFace tồn tại ở `%USERPROFILE%\.insightface\models\buffalo_l` trước khi build nếu muốn bundle offline.

### Build PyInstaller

Chạy từ thư mục gốc:

```powershell
Push-Location deploy
py -3.10 -m PyInstaller --clean --noconfirm FaceCheckin.spec
Pop-Location
```

Kiểm tra các file quan trọng:

```text
deploy/dist/FaceCheckin/FaceCheckin.exe
deploy/dist/FaceCheckin/_internal/models/insightface/buffalo_l/det_10g.onnx
deploy/dist/FaceCheckin/_internal/models/insightface/buffalo_l/w600k_r50.onnx
```

### Dọn runtime trước khi build MSI

Không đóng gói DB/cache/dữ liệu runtime của developer:

```powershell
$dist = "deploy\dist\FaceCheckin"
"attendance.db","attendance.db-wal","attendance.db-shm","data","cache","received","processed","models" |
  ForEach-Object {
    $p = Join-Path $dist $_
    if (Test-Path $p) { Remove-Item $p -Recurse -Force }
  }
```

### Build MSI

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\build_msi.ps1 -Version 0.1.0
```

Output:

```text
deploy/installer/FaceCheckin-0.1.0.msi
```

## Kiểm tra nhanh khi phát triển

```powershell
python -m py_compile backend/config.py backend/face_engine.py backend/tray_launcher.py backend/server.py
node --check backend/static/js/app.js
```

Kiểm tra script trong `mobile.html` nếu có sửa mobile:

```powershell
$script = (Get-Content backend/static/mobile.html -Raw) -replace '(?s)^.*?<script>','' -replace '(?s)</script>.*$',''
Set-Content test\_mobile_check.js $script
node --check test\_mobile_check.js
Remove-Item test\_mobile_check.js
```

## Cấu hình và biến môi trường

| Biến | Mặc định | Ý nghĩa |
|---|---:|---|
| `FACECHECKIN_PORT` | `8080` | Port server |
| `FACECHECKIN_HOST` | `0.0.0.0` | Host bind để mobile LAN truy cập |
| `FACECHECKIN_TOKEN` | rỗng | Token API thủ công |
| `FACECHECKIN_CORS_ORIGINS` | rỗng | CORS allowlist bổ sung |
| `FACECHECKIN_FACE_MODEL` | `buffalo_l` | Model pack InsightFace |
| `FACECHECKIN_FACE_THRESHOLD` | `0.35` | Ngưỡng nhận diện |
| `FACECHECKIN_FACE_DET_SIZE` | `640` | Kích thước detect mặc định |
| `FACECHECKIN_FACE_CTX_ID` | `-1` | `-1` CPU, `>=0` GPU nếu môi trường hỗ trợ |
| `FACECHECKIN_DET_SCORE_THRESHOLD` | `0.5` | Ngưỡng detect face |

Nếu server mở ra LAN và không có `FACECHECKIN_TOKEN`, app có thể tạo token local trong `.facecheckin_token` để bảo vệ API/mobile URL.

## Lưu ý bảo mật và dữ liệu

- Ảnh khuôn mặt và dữ liệu điểm danh là dữ liệu nhạy cảm; chỉ chạy trong mạng tin cậy.
- Không public port `8080` ra Internet.
- Backup `attendance.db` và `data/` trước khi gỡ/cài lại bản MSI hoặc chuyển máy.
- Binary chưa ký số có thể bị Windows Defender/SmartScreen cảnh báo.
- Khi upload video lớn hoặc chọn nhiều keyframe, CPU/RAM sẽ tăng; nên dùng video vừa đủ và frame limit hợp lý.

## Troubleshooting

### Không mở được dashboard

- Kiểm tra server có chạy không: `http://localhost:8080/ping`.
- Kiểm tra port `8080` có bị app khác chiếm không.
- Nếu dùng source, xem log trong terminal hoặc `facecheckin_setup.log`.

### Điện thoại không vào được mobile

- Đảm bảo điện thoại và laptop cùng Wi-Fi/LAN.
- Dùng URL IP thật của laptop: `http://<IP_MAY_TINH>:8080/mobile`.
- Kiểm tra firewall Windows có chặn Python/FaceCheckin không.

### Nhận diện lần đầu chậm

- Lần đầu theo lớp có thể phải build embedding cache.
- Sau khi thêm/xóa/sửa ảnh khuôn mặt, cache lớp sẽ bị rebuild.
- Bản MSI chưa ký có thể bị Defender scan kỹ ở lần chạy đầu.

### Không nhận diện đúng

- Kiểm tra ảnh đăng ký có rõ mặt, đủ sáng, không quá mờ.
- Rebuild cache trong Settings.
- Chỉnh threshold/det size trong Settings nếu cần.
- Với video, giảm rung/mờ hoặc tăng số frame trích xuất.

### Build MSI lỗi thiếu WiX

Cài WiX Toolset v3 rồi chạy lại:

```powershell
winget install WiXToolset.WiXToolset
```

## Ghi chú cho contributor/agent

- Không commit dữ liệu runtime cá nhân như `backend/attendance.db`, `backend/data/`, `backend/cache/`, `backend/received/`, `backend/processed/` nếu không có chủ đích.
- Khi sửa đóng gói, tuân thủ `AGENTS.md` và skill installer packaging của repo.
- Với thử nghiệm notebook/video tạm, giữ trong `test/` để tránh làm bẩn source/runtime.
