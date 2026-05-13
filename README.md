# FaceCheckin — Điểm danh khuôn mặt cho lớp học

FaceCheckin là hệ thống điểm danh bằng nhận diện khuôn mặt chạy trên máy tính giáo viên và cho phép sinh viên điểm danh bằng trình duyệt điện thoại trong cùng mạng LAN. Dự án gồm backend Python, dashboard web, giao diện mobile và cơ sở dữ liệu SQLite cục bộ.

## Tính năng chính

- Quản lý lớp học, sinh viên và ảnh khuôn mặt đăng ký.
- Tạo tiết học, bắt đầu/kết thúc điểm danh và điểm danh thủ công.
- Nhan anh tu dien thoai, nhan dien khuon mat bang SCRFD + ArcFace (InsightFace/OpenCV) va ghi nhan diem danh.
- Dashboard realtime qua WebSocket: thống kê, ảnh đã xử lý, danh sách điểm danh.
- Import danh sách sinh viên từ CSV/XLSX và import kèm thư mục ảnh.
- Export danh sách lớp, ảnh khuôn mặt dạng ZIP, lịch sử điểm danh CSV và điền điểm danh vào file có sẵn.
- Tự tạo token bảo vệ API khi mở server cho LAN nếu chưa cấu hình token thủ công.

## Yêu cầu

- Windows được hỗ trợ sẵn qua `face.bat`.
- Python 3.10 hoac 3.11 64-bit (neu thieu, `face.bat` se tu cai Python 3.11 qua winget).
- Can internet de tai Python/dependencies o lan dau.
- Điện thoại và máy tính phải cùng mạng LAN nếu dùng giao diện mobile.
- Lan chay dau co the tai model InsightFace va cac goi nhu `insightface`, `onnxruntime`, `opencv-python`.

## Khởi động nhanh

### Cách 1: chạy bằng batch trên Windows

Nhấp đúp:

```bat
face.bat
```

Script sẽ:

1. Kiem tra `.venv\Scripts\python.exe` va dung lai neu version hop le (3.10/3.11).
2. Neu may chua co Python 3.10/3.11, tu cai Python 3.11 qua `winget`.
3. Neu `.venv` chua co, tu tao moi bang Python 3.11 (fallback 3.10).
4. Neu `.venv` sai version hoac hong, tu xoa va tao lai.
5. Cai/cap nhat thu vien tu `backend\requirements.txt`.
6. Chay `backend\start.py` va tu mo `http://localhost:8080`.

### Cách 2: chạy thủ công

```powershell
cd backend
python -m pip install -r requirements.txt
python start.py
```

Sau khi server chạy:

- Dashboard: `http://localhost:8080`
- Mobile: `http://<IP_may_tinh>:8080/mobile`
- Health check: `http://localhost:8080/ping`

### Luu y Python cho InsightFace tren Windows

`insightface` khong cai on dinh bang wheel tren Python 3.13+. Neu dung Python 3.13, pip se co build C++ va co the bao loi `Microsoft Visual C++ 14.0 or greater is required`. Du an da pin `insightface==0.2.1` de tang kha nang cai dat 1-click tren Windows (khong can build toolchain C++). `face.bat` se tu cai Python phu hop va tu tao lai `.venv`.

## Cấu trúc thư mục

```text
facecheckin/
├── face.bat                         # Khởi động server trên Windows
├── README.md                        # Tài liệu tổng quan
├── COMPLETION_REPORT.md             # Ghi chú hoàn thiện/tổng kết cũ
└── backend/
    ├── start.py                     # Entry point Python
    ├── server.py                    # aiohttp server, REST API, WebSocket
    ├── database.py                  # SQLite schema, migration và CRUD
    ├── face_engine.py               # Wrapper xử lý nhận diện khuôn mặt
    ├── image_object.py              # Detect, recognize, draw ảnh
    ├── utils.py                     # Helper: file name, token, safe path...
    ├── config.py                    # Cấu hình path, host, port, token, CORS
    ├── requirements.txt             # Dependencies Python
    ├── test_backend.py              # Script kiểm tra backend
    ├── attendance.db                # SQLite runtime, tự tạo khi chạy
    ├── data/                        # Face database theo lớp/sinh viên
    │   └── {class_id}/
    │       └── {mssv_or_folder}/
    │           └── img_0001.jpg
    ├── received/                    # Ảnh upload từ điện thoại
    ├── processed/                   # Ảnh đã vẽ bbox/label
    └── static/
        ├── index.html               # Dashboard web
        └── mobile.html              # Giao diện điện thoại
```

## Luồng hoạt động

1. Giáo viên tạo lớp và thêm/import sinh viên.
2. Upload ảnh khuôn mặt cho từng sinh viên hoặc import kèm thư mục ảnh.
3. Tạo tiết học và bấm bắt đầu điểm danh.
4. Sinh viên mở `/mobile`, chụp ảnh và gửi lên server.
5. Server lưu ảnh vào `backend/received`, nhận diện theo dữ liệu lớp đang điểm danh, lưu ảnh kết quả vào `backend/processed`.
6. Nếu nhận diện được sinh viên hợp lệ, server ghi vào `lesson_attendance` và `attendance_records`, sau đó phát realtime qua WebSocket.

## Cấu hình

Các biến môi trường được đọc trong `backend/config.py`:

| Biến | Mặc định | Ý nghĩa |
|------|----------|--------|
| `FACECHECKIN_PORT` | `8080` | Cổng HTTP server |
| `FACECHECKIN_HOST` | `0.0.0.0` | Host bind server |
| `FACECHECKIN_TOKEN` | rỗng | Token API/mobile nếu muốn đặt thủ công |
| `FACECHECKIN_CORS_ORIGINS` | rỗng | Danh sách origin được phép, phân tách bằng dấu phẩy |

### Xác thực LAN/mobile

- Khi chạy bind ra LAN (`0.0.0.0`) và không đặt `FACECHECKIN_TOKEN`, server tự tạo/lưu token bền vững.
- Các route public gồm `/`, `/mobile`, `/ping`, `/static/...`.
- Các API còn lại cần token qua query `?token=...` hoặc header `Authorization: Bearer ...` khi bật xác thực.
- Dashboard/QR/mobile được thiết kế để truyền token cho các request cần thiết.

## API chính

| Endpoint | Method | Mô tả |
|----------|--------|-------|
| `/` | GET | Dashboard |
| `/mobile` | GET | Giao diện điện thoại |
| `/ping` | GET | Health check |
| `/ws` | GET | WebSocket realtime |
| `/api/server/info` | GET | Thông tin server, IP, token/URL mobile |
| `/api/qr` | GET | QR code truy cập mobile |
| `/api/recognize` | POST | Upload ảnh, nhận diện và ghi điểm danh |
| `/api/classes` | GET/POST | Danh sách/tạo lớp |
| `/api/classes/{id}` | DELETE | Xóa lớp |
| `/api/classes/import` | POST | Import lớp từ CSV/XLSX và ảnh tùy chọn |
| `/api/classes/{id}/export/csv` | GET | Export danh sách sinh viên CSV |
| `/api/classes/{id}/export/faces` | GET | Export ảnh khuôn mặt ZIP |
| `/api/students` | GET/POST | Danh sách/tạo sinh viên |
| `/api/students/{id}` | DELETE | Xóa sinh viên |
| `/api/students/{id}/faces` | GET/POST | Xem/upload ảnh khuôn mặt |
| `/api/students/{id}/faces/{filename}` | DELETE | Xóa một ảnh khuôn mặt |
| `/api/attendance` | GET | Lịch sử điểm danh |
| `/api/attendance/today` | GET | Điểm danh hôm nay |
| `/api/stats` | GET | Thống kê điểm danh |
| `/api/lessons` | GET/POST | Danh sách/tạo tiết học |
| `/api/lessons/{id}` | DELETE | Xóa tiết học |
| `/api/lessons/{id}/start` | POST | Bắt đầu điểm danh tiết học |
| `/api/lessons/{id}/stop` | POST | Kết thúc điểm danh tiết học |
| `/api/lessons/{id}/attendance` | GET | Danh sách điểm danh theo tiết |
| `/api/lessons/{id}/attendance/manual` | POST | Điểm danh thủ công |
| `/api/lessons/{id}/attendance/{student_id}` | DELETE | Xóa điểm danh thủ công/từng sinh viên |
| `/api/lessons/{id}/export/csv` | GET | Export điểm danh tiết học CSV |
| `/api/lessons/{id}/export/fill` | POST | Điền kết quả vào file CSV/XLSX có sẵn |
| `/api/images/{filename}` | GET | Ảnh upload gốc |
| `/api/processed/{filename}` | GET | Ảnh đã xử lý |
| `/api/face-image/{folder}/{filename}` | GET | Ảnh khuôn mặt đăng ký |
| `/api/import/csv` | POST | Import CSV legacy |
| `/api/import/database` | POST | Import database legacy |
| `/api/pick-folder` | GET | Chọn thư mục ảnh trên máy chạy server |

## Database

SQLite được quản lý trong `backend/database.py`, gồm các bảng:

- `classes`: lớp học.
- `students`: sinh viên, gắn với `class_id` và `folder_name`/MSSV.
- `attendance_records`: lịch sử điểm danh tổng quát theo ngày.
- `lessons`: tiết học và trạng thái điểm danh.
- `lesson_attendance`: kết quả điểm danh theo tiết.

Khi schema cũ không còn phù hợp, code có cơ chế backup/migrate database trước khi cập nhật bảng.

## Kiểm tra nhanh

```powershell
cd backend
python test_backend.py
```

Script test kiểm tra import, đường dẫn runtime, database CRUD/cascade, cú pháp Python và khởi tạo FaceEngine nếu dependencies đã sẵn sàng.

## Ghi chú vận hành

- Không nên commit `attendance.db`, ảnh trong `received/`, `processed/` hoặc dữ liệu khuôn mặt thật nếu chứa thông tin cá nhân.
- Nếu điện thoại không truy cập được mobile URL, kiểm tra cùng Wi-Fi, Windows Firewall và IP hiển thị trên dashboard/QR.
- N?u nh?n di?n ch?m ? l?n ??u, ?? th??ng l? l?c InsightFace/ONNX t?i model ho?c build embedding cache.
- Mỗi lớp nên có thư mục ảnh riêng trong `backend/data/{class_id}/...` để tránh nhận nhầm giữa các lớp.
