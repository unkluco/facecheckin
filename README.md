# FaceCheckin — Hệ thống điểm danh khuôn mặt

Hệ thống điểm danh bằng nhận diện khuôn mặt, gồm **server Python** chạy trên máy tính và **giao diện web** dành cho điện thoại — không cần cài app.

---

## Khởi động nhanh

**Bước 1 — Chạy server:**

Nhấp đúp vào `face.bat` (Windows).

Script sẽ tự động tìm Python (ưu tiên `.venv` nội bộ nếu có, nếu không dùng Python hệ thống), kiểm tra thư viện và cài đặt nếu thiếu.

**Bước 2 — Mở Dashboard:**

Trình duyệt tự động mở `http://localhost:8080` sau vài giây. Nếu không, mở thủ công.

**Bước 3 — Điểm danh bằng điện thoại:**

- Điện thoại kết nối cùng mạng LAN với máy tính
- Mở QR code trên Dashboard (góc dưới trái) → quét bằng điện thoại
- Hoặc truy cập thẳng: `http://<IP_máy_tính>:8080/mobile`

> **Yêu cầu:** Python 3.9+ (có trong PATH). Lần chạy đầu sẽ tải thư viện `deepface` (~vài trăm MB).

---

## Cấu trúc thư mục

```
final/
├── face.bat                  # ← CHẠY FILE NÀY để khởi động
├── README.md
└── backend/
    ├── start.py              # Entry point Python
    ├── server.py             # HTTP Server + REST API + WebSocket
    ├── database.py           # SQLite (lớp, sinh viên, điểm danh, tiết học)
    ├── face_engine.py        # Wrapper nhận diện khuôn mặt (DeepFace)
    ├── image_object.py       # Pipeline xử lý ảnh
    ├── utils.py              # Tiện ích
    ├── config.py             # Cấu hình đường dẫn (tất cả tương đối)
    ├── requirements.txt      # Danh sách thư viện Python
    ├── attendance.db         # SQLite database (tự tạo khi chạy lần đầu)
    ├── static/
    │   ├── index.html        # Web Dashboard (SPA)
    │   └── mobile.html       # Giao diện điện thoại (web, không cần app)
    ├── data/                 # Cơ sở dữ liệu khuôn mặt
    │   └── {class_id}/
    │       └── {mssv}/
    │           └── img_0001.jpg   # Ảnh đăng ký của sinh viên
    ├── received/             # Ảnh chụp nhận từ điện thoại (runtime)
    └── processed/            # Ảnh đã annotate sau nhận diện (runtime)
```

---

## Tính năng

### Web Dashboard (`http://localhost:8080`)

| Tab | Chức năng |
|-----|-----------|
| **Tổng quan** | Thống kê real-time: số SV điểm danh, tỉ lệ %, feed ảnh nhận diện |
| **Lớp học** | Tạo/xóa lớp, import danh sách từ CSV/XLSX, export danh sách + ảnh |
| **Sinh viên** | Thêm/xóa sinh viên, upload ảnh khuôn mặt (nhiều ảnh/SV) |
| **Tiết học** | Tạo tiết, bắt đầu/kết thúc điểm danh, điểm danh thủ công |
| **Lịch sử** | Xem lịch sử điểm danh, xuất CSV, điền vào file có sẵn (XLSX/CSV) |
| **Cài đặt** | QR code cho điện thoại, thông tin server |

### Giao diện điện thoại (`/mobile`)

- Chụp ảnh bằng camera điện thoại → gửi lên server → nhận diện
- Chọn lớp học trước khi điểm danh
- Hiển thị kết quả nhận diện ngay trên màn hình
- Không cần cài app — chỉ cần trình duyệt

### Xuất điểm danh

- **Tạo file mới:** xuất CSV có cột MSSV + tick điểm danh
- **Điền file có sẵn:** chọn file XLSX/CSV → chọn cột MSSV, cột điểm danh → tải về file đã điền

---

## API Endpoints

| Endpoint | Method | Mô tả |
|----------|--------|-------|
| `/ping` | GET | Health check |
| `/mobile` | GET | Giao diện web điện thoại |
| `/api/recognize` | POST | Nhận ảnh → nhận diện → ghi điểm danh |
| `/api/classes` | GET / POST | Danh sách / tạo lớp |
| `/api/classes/{id}` | DELETE | Xóa lớp |
| `/api/classes/import` | POST | Import lớp từ CSV + thư mục ảnh |
| `/api/classes/{id}/export/csv` | GET | Xuất danh sách SV |
| `/api/classes/{id}/export/faces` | GET | Xuất ảnh khuôn mặt (ZIP) |
| `/api/students` | GET / POST | Danh sách / thêm sinh viên |
| `/api/students/{id}` | DELETE | Xóa sinh viên |
| `/api/students/{id}/faces` | GET / POST | Xem / upload ảnh khuôn mặt |
| `/api/students/{id}/faces/{file}` | DELETE | Xóa một ảnh |
| `/api/lessons` | GET / POST | Danh sách / tạo tiết học |
| `/api/lessons/{id}` | DELETE | Xóa tiết |
| `/api/lessons/{id}/start` | POST | Bắt đầu điểm danh |
| `/api/lessons/{id}/stop` | POST | Kết thúc điểm danh |
| `/api/lessons/{id}/attendance` | GET | Điểm danh của tiết |
| `/api/lessons/{id}/attendance/manual` | POST | Điểm danh thủ công |
| `/api/lessons/{id}/attendance/{sid}` | DELETE | Xóa một bản ghi |
| `/api/lessons/{id}/export/csv` | GET | Xuất CSV tiết học |
| `/api/lessons/{id}/export/fill` | POST | Điền vào file CSV/XLSX có sẵn |
| `/api/attendance` | GET | Toàn bộ lịch sử |
| `/api/attendance/today` | GET | Điểm danh hôm nay |
| `/api/stats` | GET | Thống kê tổng hợp |
| `/api/server/info` | GET | IP + port (dùng cho QR code) |
| `/ws` | WebSocket | Cập nhật real-time |

---

## Yêu cầu

**Python:** 3.9 trở lên (khuyến nghị 3.11+)

**Thư viện** (tự động cài qua `face.bat`):
```
aiohttp >= 3.8
aiofiles >= 23.0
deepface >= 0.0.75
opencv-python >= 4.5
numpy >= 1.20
```

**Mạng:** Điện thoại và máy tính phải cùng một mạng LAN (WiFi hoặc cáp).

---

## Cấu hình khuôn mặt

Ảnh khuôn mặt lưu theo cấu trúc:
```
backend/data/{class_id}/{mssv}/img_0001.jpg
                               img_0002.jpg
                               ...
```

Thêm ảnh qua Dashboard (tab Sinh viên → chọn SV → Upload ảnh). Hệ thống tự crop và căn chỉnh khuôn mặt khi upload.

Mô hình nhận diện: **FaceNet512** (DeepFace), ngưỡng mặc định **0.4**.

---

## Ghi chú

- `attendance.db` tự tạo khi chạy lần đầu — không cần cấu hình thêm
- `received/` và `processed/` là thư mục runtime — không cần commit
- Folder có thể đặt ở bất kỳ đâu trên máy, không phụ thuộc đường dẫn tuyệt đối
