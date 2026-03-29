# FaceCheckin Backend - Quick Start Guide

## Overview

FaceCheckin backend is a complete face recognition attendance system built with Python, aiohttp, and SQLite.

## What's Included

- **config.py** - Configuration and paths
- **database.py** - SQLite database operations (1,000+ lines)
- **face_engine.py** - Face recognition wrapper
- **server.py** - Main aiohttp server with REST API
- **start.py** - Entry point script
- **test_backend.py** - Comprehensive test suite
- **static/index.html** - Web dashboard

## Installation & Setup

### 1. Install Dependencies

```bash
pip install aiohttp deepface opencv-python numpy
```

### 2. Start the Server

```bash
cd /sessions/festive-bold-newton/mnt/facecheckin/final/backend
python3 start.py
```

You should see:
```
✅ FaceCheckin Server: http://192.168.x.x:8080
📍 Database: /sessions/festive-bold-newton/mnt/facecheckin/final/backend/attendance.db
📁 Data: /sessions/festive-bold-newton/mnt/facecheckin/model/Data
🎯 API: /api/classes, /api/students, /api/attendance
```

### 3. Test the Server

Open browser: `http://localhost:8080`

Or test with curl:

```bash
# Health check
curl http://localhost:8080/ping

# Get all classes
curl http://localhost:8080/api/classes

# Get all students
curl http://localhost:8080/api/students
```

## Core Features

### 1. Face Recognition
- Automatic detection of faces in images
- Recognition against pre-trained database
- Confidence scoring

### 2. Attendance Logging
- Automatic logging when recognized students are detected
- Session-based tracking (start/stop attendance)
- Timestamp and confidence recording

### 3. Database Management
- Classes, Students, Attendance Records
- Full CRUD operations
- Pre-populated with demo data (9 students)

### 4. REST API
Complete REST API for all operations:

```
GET    /api/classes
POST   /api/classes
GET    /api/students
POST   /api/students
GET    /api/attendance
GET    /api/stats
POST   /api/session/start
POST   /api/session/stop
```

### 5. Real-time Updates
WebSocket support for broadcasting attendance events to clients.

## Common Operations

### Start an attendance session

```bash
curl -X POST http://localhost:8080/api/session/start \
  -H "Content-Type: application/json" \
  -d '{"class_id": 1, "date": "2024-03-27"}'
```

### Upload and process image

```bash
curl -X POST http://localhost:8080/process \
  -F "image=@photo.jpg"
```

Returns annotated image with face boxes and labels.

### Get attendance statistics

```bash
curl http://localhost:8080/api/stats?class_id=1&date=2024-03-27
```

Response:
```json
{
  "total_students": 9,
  "present": 7,
  "absent": 2,
  "attendance_rate": 0.7777
}
```

## Database Structure

Three main tables:

### classes
```
id (PRIMARY KEY)
name (UNIQUE)
description
created_at
```

### students
```
id (PRIMARY KEY)
full_name
folder_name (UNIQUE, maps to model/Data/{folder_name})
class_id (FOREIGN KEY)
created_at
```

### attendance_records
```
id (PRIMARY KEY)
student_id (FOREIGN KEY)
class_id (FOREIGN KEY)
timestamp
date (YYYY-MM-DD)
confidence (0-1)
image_path
```

## File Structure

```
/sessions/festive-bold-newton/mnt/facecheckin/
├── final/backend/
│   ├── config.py           # Configuration
│   ├── database.py         # Database operations
│   ├── face_engine.py      # Face recognition engine
│   ├── server.py           # Main server
│   ├── start.py            # Entry point
│   ├── __init__.py         # Package init
│   ├── test_backend.py     # Tests
│   ├── received/           # Uploaded images
│   ├── processed/          # Results
│   ├── static/
│   │   └── index.html      # Web dashboard
│   ├── attendance.db       # SQLite database
│   ├── README.md           # Full documentation
│   └── QUICKSTART.md       # This file
│
├── model/
│   ├── image_object.py     # Face detection/recognition
│   ├── utils.py
│   ├── Data/               # Training data (9 students)
│   │   ├── Dang_The_Vy/
│   │   ├── Nguyen_Anh_Kiet/
│   │   ├── ...
│   │   └── Ta_Nguyen_Phuc/
│   └── ...
└── ...
```

## Pre-populated Demo Data

On first run, the database is auto-initialized with:

**Class:**
- "Lớp Demo" (Demo Class)

**Students (9 total):**
1. Dang_The_Vy
2. Nguyen_Anh_Kiet
3. Nguyen_Ha_Phuc_Nguyen
4. Nguyen_Minh_Dat
5. Nguyen_Viet_Anh
6. Pham_Do_Anh_Quan
7. Pham_Minh_Hung
8. Pham_Quang_Khai
9. Ta_Nguyen_Phuc

## API Response Format

### Success (200)
```json
{
  "id": 1,
  "name": "Lớp Demo",
  "description": "...",
  "created_at": "2024-03-27T12:00:00"
}
```

### Error (400/500)
```json
{
  "error": "Description of error"
}
```

## Running Tests

```bash
python3 test_backend.py
```

Tests:
- ✅ Python syntax validation
- ✅ Module imports
- ✅ File paths
- ✅ Data directory scanning
- ✅ Database operations
- ✅ Face engine initialization

## Configuration

Edit `config.py` to customize:

```python
PORT = 8080                    # Server port
HOST = '0.0.0.0'             # Server host
FACE_DETECTION_THRESHOLD = 0.4  # Recognition threshold
FACE_MIN_CONFIDENCE = 0.85    # Detection confidence
FACE_EXPAND_PERCENTAGE = 15   # Expand bbox by %
```

## Troubleshooting

### "No module named 'deepface'"
Install dependencies:
```bash
pip install deepface opencv-python numpy aiohttp
```

### "Database locked" errors
SQLite doesn't support concurrent writes well. Ensure only one process writes.

### Faces not being detected
- Check image quality (clear, well-lit faces)
- Lower FACE_MIN_CONFIDENCE in config.py
- Ensure model/Data/ folder exists and has images

### ImportError from image_object.py
The code automatically adds the model directory to Python path. If issues persist, ensure:
- `/sessions/festive-bold-newton/mnt/facecheckin/model/image_object.py` exists
- All dependencies are installed

## Performance Notes

- Face recognition is CPU-intensive (processes in thread pool)
- First API call may be slow (model loading)
- SQLite is suitable for small-medium deployments
- Consider PostgreSQL for production

## WebSocket API

Connect client to `ws://localhost:8080/ws`

Server broadcasts attendance events:
```json
{
  "type": "attendance",
  "record": {
    "id": 1,
    "student_id": 3,
    "class_id": 1,
    "timestamp": "2024-03-27T15:30:00",
    "date": "2024-03-27",
    "confidence": 0.95,
    "image_path": "..."
  },
  "timestamp": "2024-03-27T15:30:00"
}
```

## Next Steps

1. ✅ Start server: `python3 start.py`
2. ✅ Create classes/students via API
3. ✅ Start attendance session: `POST /api/session/start`
4. ✅ Upload images: `POST /process`
5. ✅ Check attendance: `GET /api/attendance`
6. ✅ View stats: `GET /api/stats`

## Code Structure

### database.py (389 lines)
- `Database`: Thread-safe SQLite wrapper
- `ClassDB`: Class CRUD operations
- `StudentDB`: Student CRUD operations
- `AttendanceDB`: Attendance CRUD operations
- `DatabaseManager`: Main coordinator

### server.py (553 lines)
- `AttendanceServer`: Main aiohttp application
- REST endpoints for all operations
- WebSocket connection handler
- Image processing pipeline
- Session management

### face_engine.py (218 lines)
- `FaceEngine`: Wrapper around ImageObject
- `process_image()`: Main face recognition function
- `get_db_info()`: Database information

### config.py (35 lines)
- Path configuration
- Server settings
- Face detection parameters
- Automatic directory creation

## Version

FaceCheckin Backend v1.0
- Complete REST API
- SQLite database
- Face recognition
- Real-time WebSocket updates
- 1500+ lines of production code

## Support

For detailed API documentation, see **README.md**.

For implementation details, see inline code comments in:
- `database.py`
- `server.py`
- `face_engine.py`
