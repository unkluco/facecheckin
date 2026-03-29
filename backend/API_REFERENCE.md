# FaceCheckin REST API Reference

Complete API documentation for FaceCheckin backend server.

## Base URL

```
http://localhost:8080
```

## Content Type

All requests and responses use `application/json` unless otherwise noted.

## Authentication

Currently no authentication. For production, add API keys or JWT tokens.

---

## Classes API

### Get All Classes

**Request**
```
GET /api/classes
```

**Response** (200 OK)
```json
[
  {
    "id": 1,
    "name": "Lớp Demo",
    "description": "Lớp mặc định cho demo",
    "created_at": "2024-03-27T12:00:00"
  }
]
```

---

### Create Class

**Request**
```
POST /api/classes
Content-Type: application/json

{
  "name": "Class A",
  "description": "First class"
}
```

**Response** (201 Created)
```json
{
  "id": 2,
  "name": "Class A",
  "description": "First class",
  "created_at": "2024-03-27T15:30:00"
}
```

**Errors**
- 400: Missing `name` field
- 409: Class name already exists

---

### Delete Class

**Request**
```
DELETE /api/classes/1
```

**Response** (200 OK)
```json
{
  "deleted": true
}
```

**Errors**
- 404: Class not found

**Note:** Deletes class and all related students and attendance records.

---

## Students API

### Get All Students

**Request**
```
GET /api/students
```

**Response** (200 OK)
```json
[
  {
    "id": 1,
    "full_name": "Dang The Vy",
    "folder_name": "Dang_The_Vy",
    "class_id": 1,
    "created_at": "2024-03-27T12:00:00"
  },
  {
    "id": 2,
    "full_name": "Nguyen Anh Kiet",
    "folder_name": "Nguyen_Anh_Kiet",
    "class_id": 1,
    "created_at": "2024-03-27T12:00:00"
  }
]
```

---

### Get Students by Class

**Request**
```
GET /api/students?class_id=1
```

**Query Parameters**
- `class_id` (int): Filter students by class ID

**Response** (200 OK)
```json
[
  {
    "id": 1,
    "full_name": "Dang The Vy",
    "folder_name": "Dang_The_Vy",
    "class_id": 1,
    "created_at": "2024-03-27T12:00:00"
  }
]
```

**Errors**
- 400: Missing `class_id` parameter

---

### Create Student

**Request**
```
POST /api/students
Content-Type: application/json

{
  "full_name": "John Doe",
  "folder_name": "John_Doe",
  "class_id": 1
}
```

**Response** (201 Created)
```json
{
  "id": 10,
  "full_name": "John Doe",
  "folder_name": "John_Doe",
  "class_id": 1,
  "created_at": "2024-03-27T15:30:00"
}
```

**Errors**
- 400: Missing required fields
- 404: Class not found
- 409: `folder_name` already exists

**Note:** `folder_name` must correspond to a folder in `model/Data/` for face recognition to work.

---

### Delete Student

**Request**
```
DELETE /api/students/1
```

**Response** (200 OK)
```json
{
  "deleted": true
}
```

**Errors**
- 404: Student not found

**Note:** Deletes student and all their attendance records.

---

## Attendance API

### Get Attendance Records

**Request**
```
GET /api/attendance?class_id=1&date=2024-03-27
```

**Query Parameters**
- `class_id` (int, required): Filter by class
- `date` (string, optional): Filter by date (YYYY-MM-DD)

**Response** (200 OK)
```json
[
  {
    "id": 1,
    "student_id": 1,
    "class_id": 1,
    "timestamp": "2024-03-27T15:30:00",
    "date": "2024-03-27",
    "confidence": 0.95,
    "image_path": "/processed/image.jpg"
  },
  {
    "id": 2,
    "student_id": 2,
    "class_id": 1,
    "timestamp": "2024-03-27T15:32:00",
    "date": "2024-03-27",
    "confidence": 0.92,
    "image_path": "/processed/image2.jpg"
  }
]
```

**Errors**
- 400: Missing `class_id` parameter

---

### Get Today's Attendance

**Request**
```
GET /api/attendance/today?class_id=1
```

**Query Parameters**
- `class_id` (int, required): Filter by class

**Response** (200 OK)
```json
[
  {
    "id": 1,
    "student_id": 1,
    "class_id": 1,
    "timestamp": "2024-03-27T15:30:00",
    "date": "2024-03-27",
    "confidence": 0.95,
    "image_path": "/processed/image.jpg"
  }
]
```

---

## Statistics API

### Get Attendance Statistics

**Request**
```
GET /api/stats?class_id=1&date=2024-03-27
```

**Query Parameters**
- `class_id` (int, required): Filter by class
- `date` (string, optional): Filter by date (YYYY-MM-DD)

**Response** (200 OK)
```json
{
  "total_students": 9,
  "present": 7,
  "absent": 2,
  "attendance_rate": 0.7777,
  "records": [
    {
      "id": 1,
      "student_id": 1,
      "class_id": 1,
      "timestamp": "2024-03-27T15:30:00",
      "date": "2024-03-27",
      "confidence": 0.95,
      "image_path": "/processed/image.jpg"
    }
  ]
}
```

**Fields**
- `total_students`: Total students in the class
- `present`: Number of present students
- `absent`: Number of absent students
- `attendance_rate`: Percentage of attendance (0-1)
- `records`: List of attendance records

**Errors**
- 400: Missing `class_id` parameter

---

## Session Management API

### Start Attendance Session

**Request**
```
POST /api/session/start
Content-Type: application/json

{
  "class_id": 1,
  "date": "2024-03-27"
}
```

**Response** (200 OK)
```json
{
  "class_id": 1,
  "date": "2024-03-27",
  "started_at": "2024-03-27T15:30:00"
}
```

**Note:** The session determines which class and date new attendance records are logged to.

**Errors**
- 400: Missing `class_id`
- 404: Class not found

---

### Stop Attendance Session

**Request**
```
POST /api/session/stop
```

**Response** (200 OK)
```json
{
  "stopped": true
}
```

---

### Get Current Session

**Request**
```
GET /api/session/current
```

**Response** (200 OK)
```json
{
  "class_id": 1,
  "date": "2024-03-27",
  "started_at": "2024-03-27T15:30:00"
}
```

If no active session:
```json
{
  "class_id": null,
  "date": null,
  "started_at": null
}
```

---

## Image Processing API

### Process Image (Face Recognition)

**Request**
```
POST /process
Content-Type: multipart/form-data

file: <image.jpg>
```

**Response** (200 OK with image file)

Headers:
```
Content-Type: image/jpeg
X-Face-Labels: ["Dang_The_Vy", "Nguyen_Anh_Kiet"]
X-Recognition-Result: {"count": 2, "known": ["Dang_The_Vy", "Nguyen_Anh_Kiet"], "success": true}
```

Body: Annotated image (JPEG) with face boxes and labels

**Features**
- Detects all faces in image
- Recognizes known faces from database
- Draws boxes around faces (green for known, yellow for unknown)
- Automatically logs attendance for known faces
- Returns annotated image

**Errors**
- 400: No image data provided
- 500: Processing error (check logs)

**Note:** Requires active session for attendance logging.

---

### Get Image

**Request**
```
GET /api/images/photo.jpg
```

**Response** (200 OK with image file)

**Behavior**
- First checks `processed/` directory
- Falls back to `received/` directory
- Returns file if found, 404 if not found

**Errors**
- 400: Invalid filename (security check)
- 404: Image not found

---

## Health Check API

### Ping

**Request**
```
GET /ping
```

**Response** (200 OK)
```
OK
```

---

## WebSocket API

### Connect

**Request**
```
GET /ws
```

Upgrade to WebSocket connection.

### Messages

Server broadcasts attendance events in real-time:

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

**Usage Example (JavaScript)**
```javascript
const ws = new WebSocket('ws://localhost:8080/ws');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'attendance') {
    console.log('New attendance:', data.record);
  }
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};
```

---

## Static Files

### Index Page

**Request**
```
GET /
```

**Response** (200 OK with HTML)

Returns dashboard at `static/index.html`.

### Static Assets

**Request**
```
GET /static/{path}
```

Serves static files (CSS, JS, images, etc.)

---

## Error Responses

All errors return JSON with appropriate HTTP status codes:

### 400 Bad Request
```json
{
  "error": "Description of what's wrong"
}
```

Examples:
- Missing required parameters
- Invalid data types
- Invalid file paths

### 404 Not Found
```json
{
  "error": "Resource not found"
}
```

Examples:
- Class/student/image doesn't exist
- Invalid ID

### 409 Conflict
```json
{
  "error": "Resource already exists"
}
```

Examples:
- Duplicate class name
- Duplicate folder_name

### 500 Internal Server Error
```json
{
  "error": "Internal server error description"
}
```

Examples:
- Database errors
- Face recognition processing errors

---

## Request/Response Examples

### Example 1: Create class and students

```bash
# Create class
curl -X POST http://localhost:8080/api/classes \
  -H "Content-Type: application/json" \
  -d '{"name":"Math Class","description":"Mathematics"}'

# Get class ID from response (e.g., 2)

# Create student
curl -X POST http://localhost:8080/api/students \
  -H "Content-Type: application/json" \
  -d '{
    "full_name":"New Student",
    "folder_name":"New_Student",
    "class_id":2
  }'
```

### Example 2: Start session and process image

```bash
# Start session
curl -X POST http://localhost:8080/api/session/start \
  -H "Content-Type: application/json" \
  -d '{"class_id":1}'

# Process image
curl -X POST http://localhost:8080/process \
  -F "image=@photo.jpg" \
  > result.jpg

# Check attendance
curl 'http://localhost:8080/api/attendance?class_id=1&date=2024-03-27'
```

### Example 3: Get statistics

```bash
curl 'http://localhost:8080/api/stats?class_id=1&date=2024-03-27' | python -m json.tool
```

---

## Rate Limiting

Currently no rate limiting. For production, implement rate limiting on:
- `/process` endpoint (heavy processing)
- WebSocket connections (broadcast overhead)

---

## CORS

Server allows all origins for development:
```
Access-Control-Allow-Origin: *
```

For production, restrict to trusted domains in `server.py`.

---

## Authentication

Currently unauthenticated. For production, add:
1. API keys
2. JWT tokens
3. User roles (admin, teacher, student)
4. Session tokens

---

## Performance Notes

- Face recognition is CPU-intensive (1-5 seconds per image)
- First `/process` call slower (model loading)
- WebSocket broadcasts are non-blocking
- SQLite concurrent writes limited (single writer)

---

## Versioning

API version: 1.0

Future versions may add:
- Pagination for large result sets
- Advanced filtering
- Batch operations
- File exports (CSV, PDF)

---

## Support

For issues:
1. Check server logs: `python3 start.py`
2. Verify database: `sqlite3 attendance.db ".tables"`
3. Test endpoints: `curl http://localhost:8080/ping`
4. Check file permissions: `ls -la /path/to/backend/`
