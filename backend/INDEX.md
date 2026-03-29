# FaceCheckin Backend - File Index

Quick reference guide to all backend files.

## Location

```
/sessions/festive-bold-newton/mnt/facecheckin/final/backend/
```

## Files Overview

### Python Source Code (1,544 lines)

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 11 | Package initialization |
| `config.py` | 35 | Configuration & paths |
| `database.py` | 389 | SQLite database operations |
| `face_engine.py` | 218 | Face recognition wrapper |
| `server.py` | 553 | Main HTTP server & REST API |
| `start.py` | 40 | Entry point script |
| `test_backend.py` | 298 | Test suite |

### Documentation

| File | Purpose |
|------|---------|
| `README.md` | Full API & feature documentation |
| `QUICKSTART.md` | Quick start guide with examples |
| `API_REFERENCE.md` | Complete REST API endpoint reference |
| `ARCHITECTURE.md` | System architecture & design |
| `requirements.txt` | Python dependencies |
| `INDEX.md` | This file |

### Supporting Files

| File | Purpose |
|------|---------|
| `static/index.html` | Web dashboard |
| `received/` | Directory for uploaded images |
| `processed/` | Directory for processed results |
| `attendance.db` | SQLite database (auto-created) |

## How to Use Each File

### 1. Getting Started

1. Read: **QUICKSTART.md** - Quick start guide
2. Read: **requirements.txt** - Install dependencies
3. Run: **start.py** - Start the server

### 2. Understanding the System

1. Read: **README.md** - Overview & features
2. Read: **ARCHITECTURE.md** - System design
3. Read: **API_REFERENCE.md** - All endpoints

### 3. Development

1. Edit: **config.py** - Customize settings
2. Modify: **server.py** - Add endpoints
3. Extend: **database.py** - Modify schema
4. Test: **test_backend.py** - Run test suite

## File Dependencies

```
start.py
  └─ server.py
      ├─ config.py
      ├─ database.py
      │   └─ (sqlite3)
      └─ face_engine.py
          ├─ config.py
          └─ model/image_object.py

test_backend.py
  ├─ config.py
  ├─ database.py
  └─ face_engine.py
```

## Database File

**File**: `attendance.db` (SQLite)

Auto-created on first run. Contains:
- `classes` table
- `students` table
- `attendance_records` table

Location: `/sessions/festive-bold-newton/mnt/facecheckin/final/backend/attendance.db`

## Directory Structure

```
/sessions/festive-bold-newton/mnt/facecheckin/final/backend/
├── Python files
│   ├── __init__.py
│   ├── config.py
│   ├── database.py
│   ├── face_engine.py
│   ├── server.py
│   ├── start.py
│   └── test_backend.py
├── Documentation
│   ├── README.md
│   ├── QUICKSTART.md
│   ├── API_REFERENCE.md
│   ├── ARCHITECTURE.md
│   ├── requirements.txt
│   └── INDEX.md (this file)
├── Static files
│   └── static/
│       └── index.html
├── Runtime directories
│   ├── received/        (uploaded images)
│   ├── processed/       (results)
│   └── static/          (assets)
└── Database
    └── attendance.db    (auto-created)
```

## Quick Reference

### Start the Server
```bash
cd /sessions/festive-bold-newton/mnt/facecheckin/final/backend
python3 start.py
```

### Run Tests
```bash
python3 test_backend.py
```

### Test Endpoints
```bash
curl http://localhost:8080/ping
curl http://localhost:8080/api/classes
curl http://localhost:8080
```

### View Documentation
```bash
# Full API reference
cat API_REFERENCE.md

# Quick start
cat QUICKSTART.md

# Architecture
cat ARCHITECTURE.md
```

## Key Concepts

### Classes (database.py)

- **Database**: Thread-safe SQLite wrapper
- **ClassDB**: Class CRUD operations
- **StudentDB**: Student management
- **AttendanceDB**: Attendance tracking
- **DatabaseManager**: Main coordinator

### Endpoints (server.py)

- **REST API**: Classes, students, attendance, stats
- **Image Processing**: Face detection & recognition
- **WebSocket**: Real-time updates
- **Static Files**: Web dashboard

### Face Recognition (face_engine.py)

- **FaceEngine**: Main interface
- **ImageObject**: Face detection/recognition
- **Model**: DeepFace + OpenCV

### Configuration (config.py)

- **Paths**: Database, model, images
- **Settings**: Port, host, thresholds
- **Auto-creation**: Directories

## Common Tasks

### Add New Endpoint
1. Edit `server.py`
2. Add handler method
3. Add route in `_create_app()`
4. Document in `API_REFERENCE.md`

### Modify Database Schema
1. Edit `database.py`
2. Backup `attendance.db`
3. Modify `_init_db()` method
4. Delete `attendance.db` for fresh start

### Change Face Recognition Settings
1. Edit `config.py`
2. Update thresholds/parameters
3. Server picks up changes on restart

### Deploy to Production
1. Read `ARCHITECTURE.md` deployment section
2. Update `config.py` with prod settings
3. Use PostgreSQL instead of SQLite
4. Add authentication
5. Restrict CORS origins
6. Enable HTTPS

## File Sizes

| File | Size |
|------|------|
| API_REFERENCE.md | 11K |
| ARCHITECTURE.md | 18K |
| README.md | 7.7K |
| QUICKSTART.md | 7.7K |
| server.py | 21K |
| database.py | 14K |
| test_backend.py | 8.3K |
| face_engine.py | 6.6K |
| **Total** | **~212K** |

## Important Notes

1. **Database**: SQLite file is not thread-safe for concurrent writes
2. **Face Recognition**: Requires DeepFace & OpenCV (slow on first run)
3. **Session**: Required for auto-attendance logging
4. **Path Handling**: All paths are absolute (no relative path issues)
5. **CORS**: Currently allows all origins (restrict for production)

## Support Resources

| Resource | Location |
|----------|----------|
| Quick Start | QUICKSTART.md |
| API Docs | API_REFERENCE.md |
| Architecture | ARCHITECTURE.md |
| Full Reference | README.md |
| Dependencies | requirements.txt |

## Version Info

- **Backend Version**: 1.0
- **Python**: 3.8+
- **Framework**: aiohttp 3.8+
- **Database**: SQLite 3
- **Created**: 2024-03-27

## Next Steps

1. Read **QUICKSTART.md** for basic setup
2. Run **start.py** to start server
3. Test endpoints with curl
4. Read **API_REFERENCE.md** for detailed usage
5. Check **ARCHITECTURE.md** for system design

---

For detailed information, see individual documentation files.
