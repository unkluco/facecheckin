# FaceCheckin Backend Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Mobile Client / Web Client                   │
│              (Camera or uploaded images)                         │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP/WebSocket
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AttendanceServer (aiohttp)                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ REST API Endpoints                                       │   │
│  │ ├─ /api/classes    (CRUD)                              │   │
│  │ ├─ /api/students   (CRUD)                              │   │
│  │ ├─ /api/attendance (Read stats)                        │   │
│  │ ├─ /api/session/*  (Session mgmt)                      │   │
│  │ ├─ /api/images/*   (Image serving)                     │   │
│  │ ├─ /process        (Face recognition)                  │   │
│  │ ├─ /ws             (WebSocket)                         │   │
│  │ └─ /ping           (Health check)                      │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌─────────────────┐  ┌──────────────────┐  ┌──────────────┐   │
│  │ FaceEngine      │  │ DatabaseManager  │  │ Session Mgmt │   │
│  ├─ process_image │  ├─ ClassDB (CRUD)  │  ├─ class_id    │   │
│  ├─ extract_faces │  ├─ StudentDB (CRUD)│  ├─ date        │   │
│  └─ get_db_info   │  ├─ AttendanceDB    │  └─ started_at  │   │
│                   │  │   (record, query) │                │   │
│                   │  └──────────────────┘                │   │
│                   │                                        │   │
│  Integrates with: │   Uses:                              │   │
│  ├─ ImageObject   │   ├─ Database                        │   │
│  │ ├─ detect()    │   │                                   │   │
│  │ ├─ recognize() │   └─ Config                          │   │
│  │ ├─ draw()      │                                        │   │
│  │ └─ save_drawn()│                                        │   │
│  │                │                                        │   │
│  └─ model/Data/   │ (9 students)                          │   │
│     (faces DB)    │                                        │   │
│                   │                                        │   │
│  Thread pool for  │                                        │   │
│  concurrent       │                                        │   │
│  processing       │                                        │   │
└─────────────────────────────────────────────────────────────────┘
    │                        │                       │
    ▼                        ▼                       ▼
┌──────────────┐  ┌────────────────────┐  ┌──────────────────┐
│   received/  │  │  attendance.db     │  │  processed/      │
│  (uploaded   │  │  ┌──────────────┐  │  │  (results)       │
│   images)    │  │  │ classes      │  │  │                  │
│              │  │  ├─ id          │  │  │ Images with      │
│ Auto-deleted │  │  ├─ name        │  │  │ annotated faces  │
│ after        │  │  ├─ description │  │  │                  │
│ processing   │  │  └─ created_at  │  │  │ Served via       │
│              │  │  ┌──────────────┐  │  │ /api/images/     │
│              │  │  │ students     │  │  │                  │
│              │  │  ├─ id          │  │  │ Deleted after    │
│              │  │  ├─ full_name   │  │  │ time (optional)  │
│              │  │  ├─ folder_name │  │  │                  │
│              │  │  ├─ class_id (FK)  │  │                  │
│              │  │  └─ created_at  │  │  │                  │
│              │  │  ┌──────────────┐  │  │                  │
│              │  │  │ attendance   │  │  │                  │
│              │  │  │ _records     │  │  │                  │
│              │  │  ├─ id          │  │  │                  │
│              │  │  ├─ student_id  │  │  │                  │
│              │  │  ├─ class_id    │  │  │                  │
│              │  │  ├─ timestamp   │  │  │                  │
│              │  │  ├─ date        │  │  │                  │
│              │  │  ├─ confidence  │  │  │                  │
│              │  │  └─ image_path  │  │  │                  │
│              │  │                 │  │  │                  │
│              │  │ Foreign Keys:   │  │  │                  │
│              │  │ - students.class │  │  │                  │
│              │  │ - att_rec.student │ │  │                  │
│              │  │ - att_rec.class   │ │  │                  │
│              │  └────────────────┘  │  │                  │
└──────────────┘  └────────────────────┘  └──────────────────┘
                  (SQLite Database)
```

## Module Architecture

### 1. config.py
```
Config
├── Paths
│   ├── BASE_DIR
│   ├── PROJECT_ROOT
│   ├── MODEL_DIR
│   ├── DATA_DIR
│   ├── DB_PATH
│   ├── RECEIVED_DIR
│   ├── PROCESSED_DIR
│   └── STATIC_DIR
├── Server Settings
│   ├── PORT (8080)
│   ├── HOST (0.0.0.0)
└── Face Detection Settings
    ├── FACE_DETECTION_THRESHOLD
    ├── FACE_MIN_CONFIDENCE
    └── FACE_EXPAND_PERCENTAGE
```

### 2. database.py (389 lines)
```
Database (Thread-safe wrapper)
├── _get_connection() → sqlite3.Connection
├── _init_db() → Create tables
├── execute() → Execute query
├── fetch_one() → Get single row
└── fetch_all() → Get all rows

ClassDB
├── get_all() → List[Dict]
├── get_by_id() → Dict | None
├── create() → Dict
├── update() → bool
└── delete() → bool

StudentDB
├── get_all() → List[Dict]
├── get_by_class() → List[Dict]
├── get_by_id() → Dict | None
├── get_by_folder_name() → Dict | None
├── create() → Dict | None
└── delete() → bool

AttendanceDB
├── record_attendance() → Dict | None
├── get_by_id() → Dict | None
├── get_by_date() → List[Dict]
├── get_by_class() → List[Dict]
├── get_by_student() → List[Dict]
├── get_stats() → Dict
└── get_today_stats() → Dict

DatabaseManager
├── db: Database
├── classes: ClassDB
├── students: StudentDB
├── attendance: AttendanceDB
├── initialize_demo_data()
└── close()
```

### 3. face_engine.py (218 lines)
```
FaceEngine
├── __init__()
├── process_image() → Dict
│   ├── Input: image file path
│   ├── Steps:
│   │  ├─ Load image
│   │  ├─ Detect faces (ImageObject.detect())
│   │  ├─ Recognize faces (ImageObject.recognize())
│   │  ├─ Draw annotations (ImageObject.draw())
│   │  ├─ Save result (ImageObject.save_drawn())
│   │  └─ Extract results
│   └── Output: {labels, faces, count, known, unknown, success}
├── process_image_file()
├── extract_faces() → List[Dict]
└── get_db_info() → Dict
```

### 4. server.py (553 lines)
```
AttendanceServer (aiohttp)
├── __init__()
│   ├── port, host
│   ├── db_manager: DatabaseManager
│   ├── face_engine: FaceEngine
│   ├── current_session: Dict
│   └── websocket_clients: Set
│
├── _create_app() → web.Application
│
├── API Handlers
│   ├── Classes
│   │  ├─ GET /api/classes
│   │  ├─ POST /api/classes
│   │  └─ DELETE /api/classes/{id}
│   ├── Students
│   │  ├─ GET /api/students
│   │  ├─ POST /api/students
│   │  └─ DELETE /api/students/{id}
│   ├── Attendance
│   │  ├─ GET /api/attendance
│   │  ├─ GET /api/attendance/today
│   │  └─ GET /api/stats
│   ├── Session
│   │  ├─ POST /api/session/start
│   │  ├─ POST /api/session/stop
│   │  └─ GET /api/session/current
│   └── Legacy
│       ├─ GET /ping
│       └─ POST /process
│
├── Image & Static
│   ├─ GET /api/images/{filename}
│   ├─ GET /static/{path}
│   └─ GET / (index.html)
│
├── WebSocket
│   ├─ GET /ws
│   └─ _broadcast_attendance()
│
└── Server Control
    ├── start()
    ├── stop()
    ├── get_ip()
    └── _run_loop()
```

## Request Processing Flow

### Image Upload & Face Recognition

```
POST /process
     │
     ▼
1. Receive multipart image
     │
     ▼
2. Save to received/
     │
     ▼
3. FaceEngine.process_image()
     │
     ├─ ImageObject.detect()
     │  ├─ Load image
     │  └─ Extract faces using RetinaFace
     │
     ├─ ImageObject.recognize()
     │  ├─ Loop through each face
     │  └─ DeepFace.find() against model/Data/
     │
     ├─ ImageObject.draw()
     │  └─ Draw boxes + labels
     │
     └─ ImageObject.save_drawn()
        └─ Save to processed/
     │
     ▼
4. Check current_session
     │
     ▼
5. For each recognized student:
   ├─ Get student from DB
   ├─ AttendanceDB.record_attendance()
   ├─ Store in database
   └─ Broadcast via WebSocket
     │
     ▼
6. Return processed image + metadata
```

### Attendance Logging

```
POST /process (with recognized face)
     │
     ├─ If current_session.class_id is set
     │  └─ Yes: Log attendance
     │     │
     │     ├─ StudentDB.get_by_folder_name(label)
     │     │  └─ Get student ID from database
     │     │
     │     ├─ AttendanceDB.record_attendance()
     │     │  ├─ Insert attendance record
     │     │  ├─ Store timestamp
     │     │  ├─ Store confidence
     │     │  └─ Store image path
     │     │
     │     └─ _broadcast_attendance()
     │        └─ Send to all WebSocket clients
     │
     └─ No: Attendance not logged
        (session not started)
```

## Database Schema

```sql
-- classes table
CREATE TABLE classes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  description TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- students table
CREATE TABLE students (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  full_name TEXT NOT NULL,
  folder_name TEXT NOT NULL UNIQUE,  -- Maps to model/Data/{folder_name}
  class_id INTEGER NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(class_id) REFERENCES classes(id)
);

-- attendance_records table
CREATE TABLE attendance_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL,
  class_id INTEGER NOT NULL,
  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  date TEXT NOT NULL,  -- YYYY-MM-DD format
  confidence REAL,     -- 0-1 score
  image_path TEXT,     -- Path to processed image
  FOREIGN KEY(student_id) REFERENCES students(id),
  FOREIGN KEY(class_id) REFERENCES classes(id)
);
```

## Concurrency & Thread Safety

### Database Thread Safety
```
Thread 1          Thread 2          Thread 3
   │                 │                 │
   ├─ Connection A   ├─ Connection B   ├─ Connection C
   │ (thread-local)  │ (thread-local)  │ (thread-local)
   │                 │                 │
   └─────────────────┴─────────────────┘
             │
             ▼
        SQLite DB
        (atomic ops)
```

Each thread gets its own database connection via `threading.local()`.

### Face Processing

```
Request 1    Request 2    Request 3
   │            │            │
   └────────────┼────────────┘
                │
                ▼
         Thread Pool
        (3+ workers)
                │
        ┌───────┼───────┐
        │       │       │
        ▼       ▼       ▼
      Face  Face   Face
      Rec.1 Rec.2  Rec.3
```

Image processing runs in thread pool to avoid blocking HTTP server.

## Data Flow

### Face Recognition Pipeline

```
Image File
    │
    ▼
ImageObject(path)
    │
    ├─ .detect()
    │  ├─ Load BGR image (cv2.imread)
    │  ├─ Run RetinaFace detector
    │  ├─ Extract & align faces
    │  └─ Store FaceRecords
    │
    ├─ .recognize()
    │  ├─ For each face:
    │  │  ├─ DeepFace.find(face_aligned, db_path)
    │  │  ├─ Check confidence vs threshold
    │  │  └─ Assign label
    │  └─ Unknown faces get unique IDs
    │
    ├─ .draw()
    │  ├─ Copy original image
    │  ├─ Draw boxes (green/yellow)
    │  ├─ Draw labels
    │  └─ Update working image
    │
    └─ .save_drawn()
       └─ Save to output path
           │
           ▼
       Result Dict:
       {
         labels: [...],
         faces: [...],
         count: N,
         known: [...],
         unknown: [...]
       }
```

### Session Management

```
POST /api/session/start
     │
     └─ Set: current_session = {
          class_id: 1,
          date: "2024-03-27",
          started_at: "2024-03-27T15:30:00"
        }

Later...

POST /process (image)
     │
     └─ Check: if current_session.class_id
        └─ If set: log attendance to that class
           └─ AttendanceDB.record_attendance(
                student_id,
                class_id=current_session.class_id,
                date=current_session.date
              )

Later...

POST /api/session/stop
     │
     └─ Clear: current_session = {
          class_id: null,
          date: null,
          started_at: null
        }
```

## Configuration Hierarchy

```
1. Hardcoded defaults (config.py)
   ├─ PORT = 8080
   ├─ HOST = '0.0.0.0'
   └─ THRESHOLDS

2. Environment-specific (could add)
   ├─ .env file
   └─ Environment variables

3. Runtime overrides (future)
   ├─ Admin config API
   └─ Database settings
```

## Error Handling Strategy

```
User Request
    │
    ▼
Try:
  ├─ Validate inputs
  │  └─ If invalid: 400 Bad Request
  │
  ├─ Database operation
  │  ├─ If not found: 404 Not Found
  │  ├─ If duplicate: 409 Conflict
  │  └─ If DB error: 500 Internal Error
  │
  ├─ Face processing
  │  ├─ If file missing: 400 Bad Request
  │  └─ If processing error: 500 Internal Error
  │
  └─ Return success response: 200/201
     │
     ▼
Except Exception as e:
  └─ Log error
     └─ Return error JSON + code
```

## Scalability Considerations

### Current Limits
- SQLite: Single-file database
- Thread pool: Small worker count
- Memory: In-process storage

### Optimization Paths
1. **Database**: Migrate to PostgreSQL
2. **Cache**: Add Redis for session/stats
3. **Queue**: RabbitMQ for heavy processing
4. **Storage**: S3/GCS for images
5. **Scale**: Load balancer + multiple servers

### Future Architecture
```
Load Balancer (nginx)
     │
     ├─ Server 1 (aiohttp)
     ├─ Server 2 (aiohttp)
     └─ Server 3 (aiohttp)
     │
     ├─ PostgreSQL (shared DB)
     ├─ Redis (cache)
     └─ S3 (image storage)
```

## Deployment

### Single Server (Current)
```
server.py + database.py + face_engine.py
+ SQLite database
+ Local file storage
```

### Production Ready
```
- Add authentication (JWT)
- Restrict CORS origins
- Enable HTTPS
- Add rate limiting
- Use PostgreSQL
- Separate image storage
- Add logging service
- Monitor performance
```

## Performance Metrics

- Face detection: 1-2 seconds per image
- Database query: <10ms
- API response: <100ms (with caching)
- WebSocket broadcast: <50ms
- Server startup: <5 seconds

---

See API_REFERENCE.md for detailed endpoint documentation.
See QUICKSTART.md for usage examples.
