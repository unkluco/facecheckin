# FaceCheckin Backend

Complete backend system for face recognition attendance application.

## Features

- **Face Detection & Recognition**: Real-time face detection using DeepFace
- **Attendance Management**: Automatic attendance logging via face recognition
- **REST API**: Complete REST API for classes, students, and attendance
- **Database**: SQLite database with CRUD operations
- **WebSocket Support**: Real-time updates via WebSocket
- **Thread-safe**: Concurrent request handling
- **Logging**: Comprehensive error handling and logging

## Project Structure

```
backend/
├── config.py              # Configuration (paths, settings)
├── database.py            # SQLite database operations
├── face_engine.py         # Face recognition engine wrapper
├── server.py              # Main aiohttp server & REST API
├── start.py               # Entry point
├── __init__.py            # Package init
├── static/
│   └── index.html         # Web dashboard
└── README.md              # This file
```

## Installation

### Requirements

- Python 3.8+
- aiohttp
- deepface
- opencv-python
- numpy

### Setup

```bash
# Navigate to backend directory
cd /sessions/festive-bold-newton/mnt/facecheckin/final/backend

# Install dependencies (if not already installed)
pip install aiohttp deepface opencv-python numpy

# Verify syntax
python3 -m py_compile *.py
```

## Running the Server

### Method 1: Using start.py (Recommended)

```bash
cd /sessions/festive-bold-newton/mnt/facecheckin/final/backend
python3 start.py
```

### Method 2: Direct execution

```bash
cd /sessions/festive-bold-newton/mnt/facecheckin/final/backend
python3 -c "from server import AttendanceServer; s = AttendanceServer(); s.start(); input()"
```

## Configuration

Edit `config.py` to customize:

- `PORT` (default: 8080)
- `HOST` (default: 0.0.0.0)
- `FACE_DETECTION_THRESHOLD` (default: 0.4)
- `FACE_MIN_CONFIDENCE` (default: 0.85)
- `FACE_EXPAND_PERCENTAGE` (default: 15)

## Database

SQLite database with three main tables:

### classes
- `id` (INTEGER PRIMARY KEY)
- `name` (TEXT UNIQUE)
- `description` (TEXT)
- `created_at` (TIMESTAMP)

### students
- `id` (INTEGER PRIMARY KEY)
- `full_name` (TEXT)
- `folder_name` (TEXT UNIQUE) - Maps to model/Data/{folder_name}
- `class_id` (FOREIGN KEY)
- `created_at` (TIMESTAMP)

### attendance_records
- `id` (INTEGER PRIMARY KEY)
- `student_id` (FOREIGN KEY)
- `class_id` (FOREIGN KEY)
- `timestamp` (TIMESTAMP)
- `date` (TEXT YYYY-MM-DD)
- `confidence` (REAL)
- `image_path` (TEXT)

### Pre-population

On first run, the database is automatically populated with:
- 1 default class: "Lớp Demo"
- 9 students from model/Data/ folders:
  - Dang_The_Vy
  - Nguyen_Anh_Kiet
  - Nguyen_Ha_Phuc_Nguyen
  - Nguyen_Minh_Dat
  - Nguyen_Viet_Anh
  - Pham_Do_Anh_Quan
  - Pham_Minh_Hung
  - Pham_Quang_Khai
  - Ta_Nguyen_Phuc

## REST API Endpoints

### Classes

```
GET    /api/classes           - Get all classes
POST   /api/classes           - Create new class
DELETE /api/classes/{id}      - Delete class
```

### Students

```
GET    /api/students?class_id=X    - Get students (filter by class)
POST   /api/students               - Create new student
DELETE /api/students/{id}          - Delete student
```

### Attendance

```
GET    /api/attendance?class_id=X&date=YYYY-MM-DD  - Get records
GET    /api/attendance/today?class_id=X            - Get today's records
GET    /api/stats?class_id=X&date=YYYY-MM-DD      - Get statistics
```

### Session Management

```
POST /api/session/start              - Start attendance session
POST /api/session/stop               - Stop attendance session
GET  /api/session/current            - Get current session
```

### Image Processing

```
GET    /api/images/{filename}   - Serve processed images
POST   /process                 - Process image (legacy endpoint)
```

### Utilities

```
GET  /ping                      - Health check
GET  /ws                        - WebSocket connection
GET  /static/{path}             - Static files
```

## WebSocket API

Connect to `ws://host:8080/ws` to receive real-time updates:

```json
{
  "type": "attendance",
  "record": {
    "id": 1,
    "student_id": 1,
    "class_id": 1,
    "timestamp": "2024-03-27T15:30:00",
    "date": "2024-03-27",
    "confidence": 0.95,
    "image_path": "/processed/image.jpg"
  },
  "timestamp": "2024-03-27T15:30:00"
}
```

## Example Usage

### Create a class

```bash
curl -X POST http://localhost:8080/api/classes \
  -H "Content-Type: application/json" \
  -d '{"name": "Class A", "description": "First class"}'
```

### Get all students in a class

```bash
curl http://localhost:8080/api/students?class_id=1
```

### Start attendance session

```bash
curl -X POST http://localhost:8080/api/session/start \
  -H "Content-Type: application/json" \
  -d '{"class_id": 1, "date": "2024-03-27"}'
```

### Process image (face recognition)

```bash
curl -X POST http://localhost:8080/process \
  -F "image=@/path/to/image.jpg"
```

### Get attendance statistics

```bash
curl http://localhost:8080/api/stats?class_id=1&date=2024-03-27
```

## Logging

All operations are logged to console with timestamps and severity levels:

- `INFO`: Normal operations
- `WARNING`: Non-critical issues
- `ERROR`: Critical errors

## Error Handling

All endpoints return JSON with proper HTTP status codes:

- `200 OK`: Successful GET/POST
- `201 Created`: Resource created
- `400 Bad Request`: Missing/invalid parameters
- `404 Not Found`: Resource not found
- `409 Conflict`: Duplicate resource
- `500 Internal Server Error`: Server error

Example error response:

```json
{
  "error": "Class not found"
}
```

## File Directories

- `received/`: Original images from mobile
- `processed/`: Processed images with face annotations
- `static/`: Static files (HTML, CSS, JS)
- `attendance.db`: SQLite database file

## Thread Safety

- Database connections use thread-local storage
- All database operations are atomic
- Concurrent requests are handled safely

## Performance Considerations

- Face recognition is CPU-intensive (runs in thread pool)
- Images are processed asynchronously
- Database operations use connection pooling
- WebSocket broadcasts are non-blocking

## Troubleshooting

### ImportError: No module named 'image_object'

Ensure the model directory is in the Python path. The code automatically adds it, but if issues persist:

```python
import sys
sys.path.insert(0, '/sessions/festive-bold-newton/mnt/facecheckin/model')
```

### Database locked errors

SQLite has limited concurrent writes. If you encounter locking:
- Ensure only one process writes at a time
- Increase timeout in database.py
- Consider switching to PostgreSQL for production

### Face detection not working

- Ensure model/Data/ folder exists with student images
- Check FACE_MIN_CONFIDENCE threshold (too high = no detections)
- Verify image quality (clear, well-lit faces)

## Integration with Mobile

Mobile app sends images to `POST /process`:

1. App captures photo
2. Sends to `/process` endpoint
3. Server processes with face recognition
4. Server logs attendance automatically
5. Server returns annotated image

## Future Enhancements

- [ ] Database migration support
- [ ] Batch processing
- [ ] Advanced analytics dashboard
- [ ] Export attendance reports
- [ ] Face verification API
- [ ] Multi-camera support
- [ ] Admin authentication
- [ ] Role-based access control

## Version

**FaceCheckin Backend v1.0**

- Face detection & recognition
- SQLite database
- REST API
- WebSocket real-time updates
- Comprehensive logging

## License

MIT License - See LICENSE file

## Support

For issues or questions, check:
1. Server logs for error messages
2. Database integrity
3. Face recognition accuracy with test images
