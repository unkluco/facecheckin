"""
FaceCheckin backend server.
Extended aiohttp server with face recognition and attendance management.
"""

import asyncio
import csv
import io
import os
import socket
import threading
import shutil
import json
import logging
import re
import secrets
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List
from urllib.parse import urlparse

import aiohttp
import qrcode
from aiohttp import web

from config import (
    BASE_DIR, MODEL_DIR, DATA_DIR, DB_PATH, RECEIVED_DIR, PROCESSED_DIR,
    STATIC_DIR, PORT, HOST, AUTH_TOKEN, CORS_ORIGINS,
    FACE_DETECTION_THRESHOLD, FACE_MIN_CONFIDENCE, FACE_EXPAND_PERCENTAGE
)
from database import DatabaseManager
from face_engine import FaceEngine

# Setup logging
class _RedErrorFormatter(logging.Formatter):
    RED   = '\033[91m'
    RESET = '\033[0m'
    def format(self, record):
        msg = super().format(record)
        if record.levelno >= logging.ERROR:
            return f'{self.RED}{msg}{self.RESET}'
        return msg

_handler = logging.StreamHandler()
_handler.setFormatter(_RedErrorFormatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))
logging.basicConfig(level=logging.INFO, handlers=[_handler])
logger = logging.getLogger(__name__)

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}
SAFE_SEGMENT_RE = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
PUBLIC_PATHS = {'/', '/mobile', '/ping', '/api/server/info', '/api/qr'}


def _is_local_host(host: str) -> bool:
    host = (host or '').strip().lower()
    if host.startswith('['):
        host = host.split(']', 1)[0][1:]
    elif host.count(':') <= 1:
        host = host.split(':', 1)[0]
    return host in {'127.0.0.1', 'localhost', '::1'}


def _resolved(path: str) -> str:
    return os.path.normcase(os.path.realpath(path))


def safe_join(base: str, *parts: str) -> str:
    base_real = _resolved(base)
    candidate = _resolved(os.path.join(base, *[str(p) for p in parts]))
    if os.path.commonpath([base_real, candidate]) != base_real:
        raise ValueError('Unsafe path')
    return candidate


def sanitize_path_segment(value, label: str = 'path segment') -> str:
    value = str(value or '').strip()
    if not SAFE_SEGMENT_RE.fullmatch(value):
        raise ValueError(f'Invalid {label}')
    return value


def sanitize_image_filename(value, label: str = 'filename') -> str:
    value = str(value or '').strip()
    if not value or any(ch in value for ch in ('/', '\\', '\x00')) or ':' in value:
        raise ValueError(f'Invalid {label}')
    if os.path.basename(value) != value or value in {'.', '..'}:
        raise ValueError(f'Invalid {label}')
    stem, ext = os.path.splitext(value)
    if not SAFE_SEGMENT_RE.fullmatch(stem) or ext.lower() not in IMAGE_EXTS:
        raise ValueError(f'Invalid {label}')
    return f'{stem}{ext.lower()}'


def make_capture_filename(original_name: str = '') -> str:
    ext = os.path.splitext(str(original_name or ''))[1].lower()
    if ext not in IMAGE_EXTS:
        ext = '.jpg'
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    return f'capture_{stamp}_{secrets.token_hex(4)}{ext}'


def safe_download_name(value: str, fallback: str = 'download') -> str:
    safe = re.sub(r'[^A-Za-z0-9_-]+', '_', str(value or '')).strip('_')
    return safe[:80] or fallback


def safe_zip_arcname(*segments: str) -> str:
    return '/'.join(sanitize_path_segment(s, 'zip path') for s in segments)


def is_image_name(name: str) -> bool:
    return os.path.splitext(name)[1].lower() in IMAGE_EXTS


def get_or_create_persistent_token() -> str:
    token_path = os.path.join(BASE_DIR, '.facecheckin_token')
    try:
        if os.path.exists(token_path):
            token = open(token_path, 'r', encoding='utf-8').read().strip()
            if token:
                return token
        token = secrets.token_urlsafe(32)
        with open(token_path, 'w', encoding='utf-8') as f:
            f.write(token)
        return token
    except Exception:
        logger.warning("Could not persist API token; using temporary token")
        return secrets.token_urlsafe(32)


def _origin_allowed(request: web.Request) -> Optional[str]:
    origin = request.headers.get('Origin')
    if not origin:
        return None
    parsed = urlparse(origin)
    origin_host = parsed.hostname or ''
    request_host = request.host.split(':', 1)[0]
    if origin_host == request_host or _is_local_host(origin_host) or origin in CORS_ORIGINS:
        return origin
    return None


# ─── CORS Middleware (module-level, required by aiohttp 3.10+) ────────────────
@web.middleware
async def cors_middleware(request: web.Request, handler) -> web.Response:
    """Add restricted CORS headers. Must be module-level for aiohttp 3.10+."""
    allowed_origin = _origin_allowed(request)
    cors_headers = {
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    }
    if allowed_origin:
        cors_headers['Access-Control-Allow-Origin'] = allowed_origin
        cors_headers['Vary'] = 'Origin'

    if request.method == 'OPTIONS':
        return web.Response(status=204 if allowed_origin or not request.headers.get('Origin') else 403, headers=cors_headers)
    try:
        response = await handler(request)
    except web.HTTPException as ex:
        ex.headers.update(cors_headers)
        raise
    response.headers.update(cors_headers)
    return response


class AttendanceServer:
    """Main attendance server with face recognition and REST API."""

    def __init__(self, port: int = PORT, host: str = HOST):
        """Initialize server."""
        self.port = port
        self.host = host

        # Initialize components
        self.db_manager = DatabaseManager(DB_PATH)
        self.face_engine = FaceEngine(DATA_DIR, threshold=FACE_DETECTION_THRESHOLD)

        # Current session
        self.current_session = {
            'class_id': None,
            'date': None,
            'started_at': None
        }

        # Active lesson ID (set when a lesson is started)
        self.active_lesson_id = None
        self.lesson_state_lock = asyncio.Lock()
        self.recognition_semaphore = asyncio.Semaphore(1)
        self.auth_token = AUTH_TOKEN.strip()
        self.require_auth = bool(self.auth_token) or not _is_local_host(self.host)
        if self.require_auth and not self.auth_token:
            self.auth_token = get_or_create_persistent_token()
            logger.info("Using persistent API token for mobile/LAN access")
        if self.auth_token:
            logger.info("API token is enabled for mobile/LAN access")

        # WebSocket connections for broadcasting
        self.websocket_clients = set()

        # Create directories
        for dir_path in [RECEIVED_DIR, PROCESSED_DIR, STATIC_DIR]:
            os.makedirs(dir_path, exist_ok=True)

        # Create aiohttp app
        self._app = self._create_app()
        self._loop = None
        self._stop_event = None  # Set when start() is called

        logger.info("AttendanceServer initialized")

    def _auth_ok(self, request: web.Request) -> bool:
        if not self.require_auth:
            return True
        token = request.query.get('token', '')
        auth = request.headers.get('Authorization', '')
        if auth.lower().startswith('bearer '):
            token = auth[7:].strip()
        return bool(token) and secrets.compare_digest(token, self.auth_token)

    @web.middleware
    async def _auth_middleware(self, request: web.Request, handler) -> web.Response:
        path = request.path
        public = path in PUBLIC_PATHS or path.startswith('/static/')
        if request.method == 'OPTIONS' or public:
            return await handler(request)
        if not self._auth_ok(request):
            return web.json_response({'error': 'Unauthorized'}, status=401)
        return await handler(request)

    def _create_app(self) -> web.Application:
        """Create and configure aiohttp application."""
        # Use module-level cors_middleware (required by aiohttp 3.10+)
        app = web.Application(
            client_max_size=100 * 1024 * 1024,
            middlewares=[cors_middleware, self._auth_middleware]
        )

        # Static files route
        app.router.add_static('/static', STATIC_DIR)
        app.router.add_get('/', self._handle_index)

        app.router.add_get('/ping', self._handle_ping)
        app.router.add_post('/api/recognize', self._handle_process)

        # Class API endpoints
        app.router.add_get('/api/classes', self._handle_get_classes)
        app.router.add_post('/api/classes', self._handle_create_class)
        app.router.add_delete('/api/classes/{id}', self._handle_delete_class)

        # Student API endpoints
        app.router.add_get('/api/students', self._handle_get_students)
        app.router.add_post('/api/students', self._handle_create_student)
        app.router.add_delete('/api/students/{id}', self._handle_delete_student)

        # Attendance API endpoints
        app.router.add_get('/api/attendance', self._handle_get_attendance)
        app.router.add_get('/api/attendance/today', self._handle_get_today_attendance)
        app.router.add_get('/api/stats', self._handle_get_stats)

        # Image serving
        app.router.add_get('/api/images/{filename}', self._handle_get_image)
        app.router.add_get('/api/processed/{filename}', self._handle_get_processed_image)
        # Face image serving: /api/face-image/{folder}/{filename}
        app.router.add_get('/api/face-image/{folder}/{filename}', self._handle_get_face_image)

        # Server info
        app.router.add_get('/api/server/info', self._handle_server_info)
        app.router.add_get('/api/qr', self._handle_qr)
        app.router.add_get('/api/recognition/settings', self._handle_get_recognition_settings)
        app.router.add_put('/api/recognition/settings', self._handle_update_recognition_settings)
        app.router.add_get('/api/recognition/cache/status', self._handle_recognition_cache_status)
        app.router.add_post('/api/recognition/cache/rebuild', self._handle_recognition_cache_rebuild)

        # WebSocket
        app.router.add_get('/ws', self._handle_websocket)

        # Mobile web interface
        app.router.add_get('/mobile', self._handle_mobile)

        # Face registration
        app.router.add_get('/api/students/{id}/faces', self._handle_get_faces)
        app.router.add_post('/api/students/{id}/faces', self._handle_upload_faces)
        app.router.add_delete('/api/students/{id}/faces/{filename}', self._handle_delete_face)

        # Import endpoints
        app.router.add_post('/api/import/csv', self._handle_import_csv)
        app.router.add_post('/api/import/database', self._handle_import_database)
        # Import class (2-step: CSV required + optional face folder)
        app.router.add_post('/api/classes/import', self._handle_import_class)

        # Export endpoints
        app.router.add_get('/api/classes/{id}/export/csv', self._handle_export_class_csv)
        app.router.add_get('/api/classes/{id}/export/faces', self._handle_export_class_faces)

        # Lesson (tiết học) endpoints
        app.router.add_get('/api/lessons', self._handle_get_lessons)
        app.router.add_post('/api/lessons', self._handle_create_lesson)
        app.router.add_delete('/api/lessons/{id}', self._handle_delete_lesson)
        app.router.add_post('/api/lessons/{id}/start', self._handle_start_lesson)
        app.router.add_post('/api/lessons/{id}/stop', self._handle_stop_lesson)
        app.router.add_get('/api/lessons/{id}/attendance', self._handle_get_lesson_attendance)
        app.router.add_post('/api/lessons/{id}/attendance/manual', self._handle_manual_attendance)
        app.router.add_delete('/api/lessons/{id}/attendance/{student_id}', self._handle_delete_lesson_attendance)
        app.router.add_get('/api/lessons/{id}/export/csv', self._handle_export_lesson_csv)
        app.router.add_post('/api/lessons/{id}/export/fill', self._handle_export_lesson_fill)
        app.router.add_get('/api/pick-folder', self._handle_pick_folder)

        return app

    # ─── Request Handlers ───────────────────────────────────────────

    async def _handle_index(self, request) -> web.Response:
        """Serve index.html with no-cache headers."""
        index_path = os.path.join(STATIC_DIR, 'index.html')
        if os.path.exists(index_path):
            with open(index_path, 'rb') as f:
                content = f.read()
            return web.Response(
                body=content,
                content_type='text/html',
                headers={
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Pragma': 'no-cache',
                    'Expires': '0',
                }
            )
        return web.Response(text="FaceCheckin Server Running", status=200)

    async def _handle_mobile(self, request) -> web.Response:
        """Serve mobile.html — optimised capture interface for phones."""
        mobile_path = os.path.join(STATIC_DIR, 'mobile.html')
        if os.path.exists(mobile_path):
            with open(mobile_path, 'rb') as f:
                content = f.read()
            return web.Response(
                body=content,
                content_type='text/html',
                headers={
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Pragma': 'no-cache',
                    'Expires': '0',
                }
            )
        return web.Response(text="Mobile interface not found", status=404)

    async def _handle_ping(self, request) -> web.Response:
        """Health check endpoint."""
        return web.Response(text="OK", status=200)

    async def _handle_process(self, request) -> web.Response:
        """
        Process image from mobile.
        Receives image, runs face recognition, logs attendance.
        """
        try:
            reader = await request.multipart()
            filename = None
            input_path = None
            output_path = None
            requested_lesson_id = None

            while True:
                field = await reader.next()
                if field is None:
                    break
                if field.name == 'image':
                    filename = make_capture_filename(field.filename)
                    input_path = safe_join(RECEIVED_DIR, filename)
                    output_path = safe_join(PROCESSED_DIR, filename)
                    with open(input_path, 'wb') as f:
                        while chunk := await field.read_chunk():
                            f.write(chunk)
                elif field.name == 'lesson_id':
                    raw_lesson_id = (await field.text()).strip()
                    if raw_lesson_id:
                        requested_lesson_id = int(raw_lesson_id)

            if not input_path or not output_path or not filename:
                return web.json_response({'error': 'No image data'}, status=400)

            logger.info(f"Received image: {filename}")

            if requested_lesson_id is not None:
                lesson = self.db_manager.lessons.get_by_id(requested_lesson_id)
                if not lesson:
                    return web.json_response({'error': 'Lesson not found'}, status=404)
                lesson_id = requested_lesson_id
                class_id = lesson['class_id']
                session_date = lesson.get('date') or datetime.now().strftime('%Y-%m-%d')
                db_path = self._class_db_path(class_id)
            else:
                async with self.lesson_state_lock:
                    lesson_id = self.active_lesson_id
                    class_id = self.current_session.get('class_id')
                    session_date = self.current_session.get('date') or datetime.now().strftime('%Y-%m-%d')
                    db_path = self._class_db_path(class_id) if class_id else self.face_engine.db_path

            # Process with face engine
            async with self.recognition_semaphore:
                result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    self.face_engine.process_image,
                    input_path,
                    output_path,
                    db_path
                )

            attendance_records = []
            batch_faces = []

            # Record attendance if there are known faces
            if result.get('success') and result.get('known'):

                # face_engine.db_path is already scoped to the active class's directory
                # (set in _handle_start_lesson), so result['known'] only contains
                # students from the current class. No extra filtering needed.
                for label in result['known']:
                    student = self.db_manager.students.get_by_folder_name(label, class_id) if class_id else self.db_manager.students.get_by_folder_name(label)
                    if not student:
                        continue
                    confidence = next(
                        (f['confidence'] for f in result['faces'] if f['label'] == label), None
                    )
                    if class_id and student.get('class_id') != class_id:
                        continue
                    # Record to active lesson (if any)
                    lesson_rec = None
                    if lesson_id:
                        lesson_rec = self.db_manager.lesson_attendance.record(
                            lesson_id=lesson_id,
                            student_id=student['id'],
                            image_path=output_path
                        )
                    # Also record to legacy attendance table
                    if class_id:
                        record = self.db_manager.attendance.record_attendance(
                            student_id=student['id'],
                            class_id=class_id,
                            date=session_date,
                            confidence=confidence,
                            image_path=output_path
                        )
                        if record:
                            attendance_records.append(record)

                    batch_faces.append({
                        'student_id': student['id'],
                        'name': student['full_name'],
                        'mssv': student['folder_name'],
                        'confidence': confidence,
                        'lesson_recorded': lesson_rec is not None,
                    })

                result['attendance_logged'] = attendance_records
                logger.info(f"Recorded {len(attendance_records)} attendance entries")
            else:
                result['attendance_logged'] = []

            known_labels = {face['mssv'] for face in batch_faces}
            for face in result.get('faces', []):
                label = face.get('label', '')
                if face.get('is_known') or label in known_labels:
                    continue
                batch_faces.append({
                    'student_id': None,
                    'name': 'Không nhận ra',
                    'mssv': label or 'unknown',
                    'confidence': face.get('confidence'),
                    'lesson_recorded': False,
                    'recognized': False,
                })

            # If output image not created (e.g. no faces detected), use original
            if not os.path.exists(output_path):
                shutil.copy(input_path, output_path)

            fname = os.path.basename(output_path) if output_path else None
            await self._broadcast({
                'type': 'attendance_batch',
                'faces': batch_faces,
                'image_url': f'/api/processed/{fname}' if fname else None,
                'lesson_id': lesson_id,
                'timestamp': datetime.now().isoformat(),
            })

            # Return image and results
            response = web.FileResponse(output_path)
            # Encode headers safely (avoid special chars in JSON)
            labels_json = json.dumps(result.get('labels', []), ensure_ascii=True)
            recog_json = json.dumps({
                'count':   result.get('count', 0),
                'known':   result.get('known', []),
                'success': result.get('success', False),
                'error':   result.get('error'),
                # Per-face details (confidence) for mobile UI
                'faces': [
                    {
                        'label':      f.get('label', ''),
                        'confidence': f.get('confidence'),
                        'is_known':   f.get('is_known', False),
                    }
                    for f in result.get('faces', [])
                ],
            }, ensure_ascii=True)
            response.headers['X-Face-Labels'] = labels_json
            response.headers['X-Recognition-Result'] = recog_json

            return response

        except Exception as e:
            logger.error(f"Error processing image: {e}", exc_info=True)
            return web.json_response({'error': str(e)}, status=500)

    # ─── Class API ───────────────────────────────────────────────────

    async def _handle_get_classes(self, request) -> web.Response:
        """Get all classes."""
        try:
            classes = self.db_manager.classes.get_all()
            return web.json_response(classes)
        except Exception as e:
            logger.error(f"Error getting classes: {e}")
            return web.json_response({'error': str(e)}, status=500)

    async def _handle_create_class(self, request) -> web.Response:
        """Create new class."""
        try:
            data = await request.json()
            name = data.get('name')
            description = data.get('description', '')

            if not name:
                return web.json_response({'error': 'Name required'}, status=400)

            result = self.db_manager.classes.create(name, description)
            if result:
                return web.json_response(result, status=201)
            else:
                return web.json_response({'error': 'Class already exists'}, status=409)

        except Exception as e:
            logger.error(f"Error creating class: {e}")
            return web.json_response({'error': str(e)}, status=500)

    async def _handle_delete_class(self, request) -> web.Response:
        """Delete class, all its students, and their face image folders."""
        try:
            class_id = int(request.match_info['id'])
            # Collect folder_names BEFORE deleting from DB
            students = self.db_manager.students.get_by_class(class_id)
            folder_names = [s['folder_name'] for s in students if s.get('folder_name')]

            success = self.db_manager.classes.delete(class_id)
            if not success:
                return web.json_response({'error': 'Class not found'}, status=404)

            # Delete the entire class face-db directory (new per-class layout)
            deleted_dirs = 0
            class_dir = self._class_db_path(class_id, create=False)
            if os.path.isdir(class_dir):
                shutil.rmtree(class_dir)
                deleted_dirs += 1
                logger.info(f"Deleted class face directory: {class_dir}")
            # Fallback: also remove legacy root-level student folders
            for folder_name in folder_names:
                try:
                    legacy_dir = safe_join(DATA_DIR, sanitize_path_segment(folder_name, 'folder_name'))
                except ValueError:
                    logger.warning(f"Skipping unsafe legacy folder during class delete: {folder_name}")
                    continue
                if os.path.isdir(legacy_dir):
                    shutil.rmtree(legacy_dir)
                    deleted_dirs += 1

            if deleted_dirs:
                self._invalidate_face_cache(class_id)

            return web.json_response({'deleted': True, 'deleted_face_dirs': deleted_dirs})
        except Exception as e:
            logger.error(f"Error deleting class: {e}")
            return web.json_response({'error': str(e)}, status=500)

    # ─── Student API ───────────────────────────────────────────────────

    async def _handle_get_students(self, request) -> web.Response:
        """Get students (optionally filtered by class)."""
        try:
            class_id = request.rel_url.query.get('class_id')

            if class_id:
                students = self.db_manager.students.get_by_class(int(class_id))
            else:
                students = self.db_manager.students.get_all()

            # Add name alias for full_name
            for s in students:
                s['name'] = s.get('full_name', '')

            return web.json_response(students)
        except Exception as e:
            logger.error(f"Error getting students: {e}")
            return web.json_response({'error': str(e)}, status=500)

    async def _handle_create_student(self, request) -> web.Response:
        """Create new student. Accepts full_name or name, auto-generates folder_name."""
        try:
            data = await request.json()
            # Accept both 'full_name' and 'name' for compatibility with dashboard
            full_name = data.get('full_name') or data.get('name')
            class_id = data.get('class_id')
            folder_name = data.get('folder_name')

            if not full_name or not class_id:
                return web.json_response(
                    {'error': 'full_name (or name) and class_id are required'},
                    status=400
                )

            # Auto-generate folder_name from full_name if not provided
            if not folder_name:
                folder_name = re.sub(r'[^a-zA-Z0-9_]', '_',
                    full_name.strip().replace(' ', '_'))
                folder_name = re.sub(r'_+', '_', folder_name).strip('_')
            try:
                folder_name = sanitize_path_segment(folder_name, 'folder_name')
            except ValueError as e:
                return web.json_response({'error': str(e)}, status=400)

            result = self.db_manager.students.create(
                str(full_name), folder_name, int(class_id)
            )
            if result:
                return web.json_response(result, status=201)
            else:
                return web.json_response(
                    {'error': f'Folder name "{folder_name}" already exists'},
                    status=409
                )

        except Exception as e:
            logger.error(f"Error creating student: {e}")
            return web.json_response({'error': str(e)}, status=500)

    async def _handle_delete_student(self, request) -> web.Response:
        """Delete student and their face image folder."""
        try:
            student_id = int(request.match_info['id'])
            # Get folder_name BEFORE deleting from DB
            student = self.db_manager.students.get_by_id(student_id)
            if not student:
                return web.json_response({'error': 'Student not found'}, status=404)
            folder_name = student.get('folder_name')

            success = self.db_manager.students.delete(student_id)
            if not success:
                return web.json_response({'error': 'Student not found'}, status=404)

            # Delete face image folder from disk (new per-class layout)
            if folder_name:
                class_id = student.get('class_id')
                try:
                    face_dir = self._student_face_path(student) if class_id else safe_join(DATA_DIR, sanitize_path_segment(folder_name, 'folder_name'))
                except ValueError:
                    logger.warning(f"Skipping unsafe face folder during student delete: {folder_name}")
                    face_dir = None
                if face_dir and os.path.isdir(face_dir):
                    shutil.rmtree(face_dir)
                    logger.info(f"Deleted face folder: {face_dir}")
                # Also rebuild face cache for this student's class
                await self._rebuild_face_cache(class_id)

            return web.json_response({'deleted': True})
        except Exception as e:
            logger.error(f"Error deleting student: {e}")
            return web.json_response({'error': str(e)}, status=500)

    # ─── Attendance API ─────────────────────────────────────────────────

    def _enrich_records(self, records: list) -> list:
        """Add student name and class name to attendance records."""
        enriched = []
        for r in records:
            rec = dict(r)
            student = self.db_manager.students.get_by_id(rec.get('student_id'))
            cls = self.db_manager.classes.get_by_id(rec.get('class_id'))
            rec['name'] = student['full_name'] if student else 'Unknown'
            rec['class_name'] = cls['name'] if cls else 'Unknown'
            rec['image'] = os.path.basename(rec.get('image_path') or '')
            enriched.append(rec)
        return enriched

    async def _handle_get_attendance(self, request) -> web.Response:
        """Get attendance records (filtered by date and/or class)."""
        try:
            date = request.rel_url.query.get('date')
            class_id = request.rel_url.query.get('class_id')

            if class_id:
                records = self.db_manager.attendance.get_by_class(int(class_id), date)
            elif date:
                records = self.db_manager.attendance.get_by_date(date)
            else:
                # Return all recent records (last 100)
                records = self.db_manager.attendance.get_by_class(
                    self.current_session.get('class_id') or 1
                )

            return web.json_response(self._enrich_records(records))

        except Exception as e:
            logger.error(f"Error getting attendance: {e}")
            return web.json_response({'error': str(e)}, status=500)

    async def _handle_get_today_attendance(self, request) -> web.Response:
        """Get today's attendance for a class."""
        try:
            class_id = request.rel_url.query.get('class_id')
            today = datetime.now().strftime('%Y-%m-%d')

            if class_id:
                records = self.db_manager.attendance.get_by_class(int(class_id), today)
            else:
                records = self.db_manager.attendance.get_by_date(today)

            return web.json_response(self._enrich_records(records))

        except Exception as e:
            logger.error(f"Error getting today's attendance: {e}")
            return web.json_response({'error': str(e)}, status=500)

    # ─── Stats API ──────────────────────────────────────────────────────

    async def _handle_get_stats(self, request) -> web.Response:
        """Get attendance statistics."""
        try:
            class_id = request.rel_url.query.get('class_id')
            date = request.rel_url.query.get('date', datetime.now().strftime('%Y-%m-%d'))

            if not class_id:
                # Return basic stats without class filter
                return web.json_response({
                    'total_students': 0, 'present': 0, 'absent': 0,
                    'attendance_rate': 0, 'today': 0, 'total': 0,
                    'percentage': 0, 'detections': 0, 'records': []
                })

            class_id = int(class_id)
            stats = self.db_manager.attendance.get_stats(class_id, date)
            # Add aliases for dashboard compatibility
            stats['today'] = stats['present']
            stats['total'] = stats['total_students']
            stats['percentage'] = round(stats['attendance_rate'] * 100, 1)
            stats['detections'] = len(stats.get('records', []))
            return web.json_response(stats)

        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return web.json_response({'error': str(e)}, status=500)

    # ─── Image API ──────────────────────────────────────────────────────

    async def _handle_get_image(self, request) -> web.Response:
        """Serve processed/received images."""
        try:
            filename = sanitize_image_filename(request.match_info['filename'])

            # Try processed directory first, then received
            for dir_path in [PROCESSED_DIR, RECEIVED_DIR]:
                full_path = safe_join(dir_path, filename)
                if os.path.isfile(full_path):
                    return web.FileResponse(full_path)

            return web.json_response({'error': 'Image not found'}, status=404)

        except ValueError as e:
            return web.json_response({'error': str(e)}, status=400)
        except Exception as e:
            logger.error(f"Error getting image: {e}")
            return web.json_response({'error': str(e)}, status=500)

    async def _handle_get_processed_image(self, request) -> web.Response:
        """Serve processed (annotated) images."""
        try:
            filename = sanitize_image_filename(request.match_info['filename'])
            filepath = safe_join(PROCESSED_DIR, filename)
            if os.path.isfile(filepath):
                return web.FileResponse(filepath)
            return web.Response(status=404)
        except ValueError:
            return web.Response(status=400)

    async def _handle_get_face_image(self, request) -> web.Response:
        """Serve a registered face image.
        URL: /api/faces/{folder}/{filename}  (folder = student folder_name / MSSV)
        Special filename '_first' returns the first image found in the folder.
        Looks up the student's class_id to resolve the per-class path."""
        try:
            folder = sanitize_path_segment(request.match_info['folder'], 'folder')
            filename = request.match_info['filename']

            # Resolve actual path: per-class layout DATA_DIR/{class_id}/{folder}/.
            # Fall back to legacy root layout if student not found in DB.
            student = self.db_manager.students.get_by_folder_name(folder)
            if student and student.get('class_id'):
                folder_path = self._student_face_path(student)
            else:
                folder_path = safe_join(DATA_DIR, folder)

            if filename == '_first':
                if os.path.isdir(folder_path):
                    files = sorted([
                        f for f in os.listdir(folder_path)
                        if is_image_name(f) and os.path.isfile(safe_join(folder_path, f))
                    ])
                    if files:
                        return web.FileResponse(safe_join(folder_path, files[0]))
                return web.Response(status=404)

            filename = sanitize_image_filename(filename)
            filepath = safe_join(folder_path, filename)
            if os.path.isfile(filepath):
                return web.FileResponse(filepath)
            return web.Response(status=404)
        except ValueError:
            return web.Response(status=400)

    async def _handle_server_info(self, request) -> web.Response:
        """Return reachable URLs for dashboard/mobile QR."""
        ips = self.get_lan_ips()
        urls = [f'http://{ip}:{self.port}' for ip in ips]
        request_host = request.host.split(':', 1)[0]
        if request_host and not _is_local_host(request_host):
            request_url = f'{request.scheme}://{request.host}'
            urls = [request_url] + [u for u in urls if u != request_url]
        if _is_local_host(request.host):
            urls.append(f'http://localhost:{self.port}')
        return web.json_response({
            'ips': ips,
            'port': self.port,
            'urls': urls,
            'bind_host': self.host,
            'requires_auth': self.require_auth,
            'token': self.auth_token if self.require_auth else ''
        })

    async def _handle_qr(self, request) -> web.Response:
        data = request.rel_url.query.get('data', '')
        if not data:
            return web.json_response({'error': 'data required'}, status=400)
        if len(data) > 2048:
            return web.json_response({'error': 'data too long'}, status=400)
        img = qrcode.make(data)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return web.Response(body=buf.getvalue(), content_type='image/png')

    # ─── WebSocket ──────────────────────────────────────────────────────

    async def _handle_get_recognition_settings(self, request) -> web.Response:
        class_id = request.query.get('class_id')
        db_path = self._class_db_path(class_id, create=False) if class_id else self.face_engine.db_path
        return web.json_response({
            'settings': self.face_engine.get_settings(),
            'status': self.face_engine.cache_status(db_path),
        })

    async def _handle_update_recognition_settings(self, request) -> web.Response:
        try:
            data = await request.json()
            settings = self.face_engine.save_settings(data)
            return web.json_response({'settings': settings})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=400)

    async def _handle_recognition_cache_status(self, request) -> web.Response:
        try:
            class_id = request.query.get('class_id')
            db_path = self._class_db_path(class_id, create=False) if class_id else self.face_engine.db_path
            return web.json_response(self.face_engine.cache_status(db_path))
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def _handle_recognition_cache_rebuild(self, request) -> web.Response:
        try:
            data = await request.json() if request.can_read_body else {}
            class_id = data.get('class_id') or request.query.get('class_id')
            db_path = self._class_db_path(class_id, create=False) if class_id else self.face_engine.db_path
            async with self.recognition_semaphore:
                status = await asyncio.get_event_loop().run_in_executor(
                    None, self.face_engine.cache_status, db_path, True
                )
            return web.json_response(status)
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def _handle_websocket(self, request) -> web.WebSocketResponse:
        """WebSocket connection for real-time updates."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self.websocket_clients.add(ws)
        logger.info(f"WebSocket client connected. Total: {len(self.websocket_clients)}")

        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {ws.exception()}")
        finally:
            self.websocket_clients.discard(ws)
            logger.info(f"WebSocket client disconnected. Total: {len(self.websocket_clients)}")

        return ws

    async def _broadcast_attendance(self, student: Dict, confidence: float, image_path: str, lesson_recorded: bool):
        """Broadcast attendance event to all WebSocket clients."""
        fname = os.path.basename(image_path) if image_path else None
        message = json.dumps({
            'type': 'attendance',
            'student_id': student['id'],
            'name': student['full_name'],
            'mssv': student['folder_name'],
            'confidence': confidence,
            'image_url': f'/api/processed/{fname}' if fname else None,
            'lesson_id': self.active_lesson_id,
            'recognized': True,
            'lesson_recorded': lesson_recorded,
            'timestamp': datetime.now().isoformat()
        })

        dead = set()
        for ws in self.websocket_clients:
            try:
                await ws.send_str(message)
            except Exception as e:
                logger.error(f"Error broadcasting to WebSocket: {e}")
                dead.add(ws)
        self.websocket_clients -= dead

    # ─── Face Registration API ──────────────────────────────────────────

    async def _handle_get_faces(self, request) -> web.Response:
        """Get list of registered face images for a student."""
        try:
            student_id = int(request.match_info['id'])
            student = self.db_manager.students.get_by_id(student_id)

            if not student:
                return web.json_response({'error': 'Student not found'}, status=404)

            folder_name = student['folder_name']
            folder_path = self._student_face_path(student)

            faces = []
            if os.path.isdir(folder_path):
                for filename in sorted(os.listdir(folder_path)):
                    try:
                        safe_filename = sanitize_image_filename(filename)
                        file_path = safe_join(folder_path, safe_filename)
                    except ValueError:
                        continue
                    if os.path.isfile(file_path):
                        faces.append({
                            'filename': safe_filename,
                            'path': file_path,
                            'url': f'/api/face-image/{folder_name}/{safe_filename}'
                        })

            return web.json_response({
                'student': student,
                'faces': faces,
                'count': len(faces)
            })

        except ValueError:
            return web.json_response({'error': 'Invalid student ID'}, status=400)
        except Exception as e:
            logger.error(f"Error getting faces: {e}")
            return web.json_response({'error': str(e)}, status=500)

    async def _handle_upload_faces(self, request) -> web.Response:
        """Upload face images for a student."""
        try:
            student_id = int(request.match_info['id'])
            student = self.db_manager.students.get_by_id(student_id)

            if not student:
                return web.json_response({'error': 'Student not found'}, status=404)

            folder_name = student['folder_name']
            folder_path = self._student_face_path(student)

            # Create folder if it doesn't exist
            os.makedirs(folder_path, exist_ok=True)

            # Read multipart form
            reader = await request.multipart()
            saved_files = []
            invalid_no_face = []
            total_faces = 0

            # Count existing images
            existing_images = [f for f in os.listdir(folder_path)
                              if is_image_name(f) and os.path.isfile(safe_join(folder_path, f))]

            # Find next available number by scanning existing img_XXXX filenames
            # (using len() would overwrite files if any were deleted or renamed)
            existing_nums = []
            for f in existing_images:
                m = re.match(r'img_(\d+)\.', f, re.IGNORECASE)
                if m:
                    existing_nums.append(int(m.group(1)))
            next_num = (max(existing_nums) + 1) if existing_nums else 1

            # Process uploaded files
            while True:
                field = await reader.next()
                if not field:
                    break

                if field.name != 'files':
                    continue

                filename = field.filename
                if not filename or os.path.splitext(filename)[1].lower() not in IMAGE_EXTS:
                    logger.warning(f"Skipping invalid file: {filename}")
                    continue

                # Save with standardized name
                output_filename = f'img_{next_num:04d}.jpg'
                output_path = safe_join(folder_path, output_filename)

                with open(output_path, 'wb') as f:
                    while chunk := await field.read_chunk():
                        f.write(chunk)

                # ── Preprocess: detect face, crop with padding, align ──
                ok = await self._preprocess_and_save_face(output_path)
                if not ok:
                    # Keep registration data clean: if no face can be extracted,
                    # remove this file so it cannot poison recognition cache.
                    try:
                        os.remove(output_path)
                    except Exception:
                        pass
                    invalid_no_face.append(output_filename)
                    logger.info(f"No face detected in upload — removed unusable file: {output_filename}")
                    next_num += 1
                    continue

                saved_files.append(output_filename)
                logger.info(f"Saved face image: {output_filename} for student {folder_name}")
                next_num += 1

            # Mark this class cache dirty only when at least one valid face image was added.
            # The face registration modal rebuilds once when the user clicks Done.
            if saved_files:
                self._invalidate_face_cache(student.get('class_id'))

            total_faces = len([f for f in os.listdir(folder_path)
                              if is_image_name(f) and os.path.isfile(safe_join(folder_path, f))])

            return web.json_response({
                'saved': saved_files,
                'invalid_no_face': invalid_no_face,
                'total_faces': total_faces
            }, status=201)

        except ValueError:
            return web.json_response({'error': 'Invalid student ID'}, status=400)
        except Exception as e:
            logger.error(f"Error uploading faces: {e}")
            return web.json_response({'error': str(e)}, status=500)

    async def _handle_delete_face(self, request) -> web.Response:
        """Delete a face image for a student."""
        try:
            student_id = int(request.match_info['id'])
            filename = sanitize_image_filename(request.match_info['filename'])

            student = self.db_manager.students.get_by_id(student_id)
            if not student:
                return web.json_response({'error': 'Student not found'}, status=404)

            folder_name = student['folder_name']
            folder_path = self._student_face_path(student)
            file_path = safe_join(folder_path, filename)

            if not os.path.isfile(file_path):
                return web.json_response({'error': 'File not found'}, status=404)

            os.remove(file_path)
            logger.info(f"Deleted face image: {filename} for student {folder_name}")

            # Mark face cache dirty for this student's class only.
            # The face registration modal rebuilds once when the user clicks Done.
            self._invalidate_face_cache(student.get('class_id'))

            return web.json_response({'deleted': True})

        except ValueError:
            return web.json_response({'error': 'Invalid student ID'}, status=400)
        except Exception as e:
            logger.error(f"Error deleting face: {e}")
            return web.json_response({'error': str(e)}, status=500)

    # ─── Import API ─────────────────────────────────────────────────────

    async def _handle_import_csv(self, request) -> web.Response:
        """Import students from CSV file."""
        try:
            reader = await request.multipart()
            filename = ''
            content = b''
            class_id = None

            while True:
                field = await reader.next()
                if field is None:
                    break
                if field.name == 'file':
                    filename = field.filename or ''
                    while chunk := await field.read_chunk():
                        content += chunk
                elif field.name == 'class_id':
                    raw = (await field.text()).strip()
                    class_id = int(raw) if raw else None

            if not content:
                return web.json_response({'error': 'No CSV file provided'}, status=400)

            if not filename.lower().endswith('.csv'):
                return web.json_response({'error': 'File must be CSV'}, status=400)

            for encoding in ('utf-8-sig', 'utf-8', 'cp1258'):
                try:
                    csv_text = content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    csv_text = None
            if csv_text is None:
                return web.json_response({'error': 'Could not decode CSV file'}, status=400)

            rows = [
                [str(cell).strip() for cell in row]
                for row in csv.reader(io.StringIO(csv_text))
                if any(str(cell).strip() for cell in row)
            ]

            imported = 0
            skipped = 0
            errors = []
            classes_created = []

            if not rows:
                return web.json_response({'imported': 0, 'skipped': 0, 'errors': [], 'classes_created': []})

            header_tokens = {cell.lower() for cell in rows[0]}
            has_header = bool(header_tokens & {'name', 'full_name', 'họ tên', 'ten', 'tên', 'class', 'class_name', 'lớp', 'folder_name', 'mssv'})
            data_rows = rows[1:] if has_header else rows
            row_start = 2 if has_header else 1

            fixed_class = None
            if class_id is not None:
                fixed_class = self.db_manager.classes.get_by_id(class_id)
                if not fixed_class:
                    return web.json_response({'error': 'Class not found'}, status=404)

            classes_by_name = {c['name']: c for c in self.db_manager.classes.get_all()}

            for row_num, parts in enumerate(data_rows, start=row_start):
                try:
                    if fixed_class:
                        if len(parts) < 2:
                            skipped += 1
                            continue
                        first, second = parts[0], parts[1]
                        if re.fullmatch(r'[A-Za-z0-9_-]{1,64}', first or ''):
                            folder_name, full_name = first, second
                        else:
                            full_name, folder_name = first, second
                        class_record = fixed_class
                    else:
                        if len(parts) < 2:
                            skipped += 1
                            continue
                        full_name = parts[0]
                        if len(parts) == 2:
                            folder_name = None
                            class_name = parts[1]
                        else:
                            folder_name = parts[1] or None
                            class_name = parts[2]

                        if not class_name:
                            skipped += 1
                            continue
                        class_record = classes_by_name.get(class_name)
                        if not class_record:
                            class_record = self.db_manager.classes.create(class_name, '')
                            if class_record:
                                classes_by_name[class_name] = class_record
                                classes_created.append(class_name)
                            else:
                                errors.append(f"Row {row_num}: Failed to create class '{class_name}'")
                                skipped += 1
                                continue

                    if not full_name:
                        skipped += 1
                        continue

                    if not folder_name:
                        folder_name = re.sub(r'[^a-zA-Z0-9_]', '_', full_name.strip().replace(' ', '_'))
                        folder_name = re.sub(r'_+', '_', folder_name).strip('_')
                    folder_name = sanitize_path_segment(folder_name, 'folder_name')

                    student = self.db_manager.students.create(full_name, folder_name, class_record['id'])
                    if student:
                        imported += 1
                        logger.info(f"Imported student: {full_name} ({folder_name})")
                    else:
                        errors.append(f"Row {row_num}: Student '{folder_name}' already exists in class '{class_record['name']}'")
                        skipped += 1

                except Exception as e:
                    errors.append(f"Row {row_num}: {str(e)}")
                    skipped += 1

            return web.json_response({
                'imported': imported,
                'skipped': skipped,
                'errors': errors,
                'classes_created': classes_created,
                'class_id': class_id
            })

        except ValueError:
            return web.json_response({'error': 'Invalid class_id'}, status=400)
        except Exception as e:
            logger.error(f"Error importing CSV: {e}", exc_info=True)
            return web.json_response({'error': 'Import failed'}, status=500)

    async def _handle_import_database(self, request) -> web.Response:
        """Import students from face-image folder structure."""
        try:
            data = await request.json()
            source_path = data.get('source_path')

            if not source_path:
                return web.json_response({'error': 'source_path required'}, status=400)

            source_path = os.path.abspath(source_path)

            # Security: validate path exists and is accessible
            if not os.path.exists(source_path) or not os.path.isdir(source_path):
                return web.json_response({'error': 'Source path does not exist'}, status=400)

            # Get or create default class
            class_record = next(
                (c for c in self.db_manager.classes.get_all() if c['name'] == 'Lớp Import'),
                None
            )
            if not class_record:
                class_record = self.db_manager.classes.create('Lớp Import', 'Lớp mặc định cho import')

            class_id = class_record['id']

            imported = 0
            skipped = 0
            students_list = []

            # Scan source directory
            for item in os.listdir(source_path):
                item_path = os.path.join(source_path, item)

                if not os.path.isdir(item_path) or item.startswith('.'):
                    continue

                try:
                    folder_name = sanitize_path_segment(item, 'folder_name')
                except ValueError:
                    skipped += 1
                    logger.warning(f"Skipping unsafe import folder: {item}")
                    continue
                full_name = folder_name.replace('_', ' ')

                # Check if student already exists
                existing = self.db_manager.students.get_by_folder_name(folder_name, class_id)
                if existing:
                    skipped += 1
                    continue

                # Create student
                student = self.db_manager.students.create(full_name, folder_name, class_id)
                if not student:
                    skipped += 1
                    continue

                # Copy images into per-class sub-directory
                dest_folder = safe_join(self._class_db_path(class_id), folder_name)
                src_real  = os.path.normcase(os.path.realpath(item_path))
                dest_real = os.path.normcase(os.path.realpath(dest_folder))
                if src_real != dest_real:
                    os.makedirs(dest_folder, exist_ok=True)
                    # De-dup by FILENAME (not size — size changes after preprocessing)
                    existing_db_names = {
                        f.lower() for f in os.listdir(dest_folder)
                        if is_image_name(f)
                    }
                    for filename in sorted(os.listdir(item_path)):
                        src_file = os.path.join(item_path, filename)
                        try:
                            safe_filename = sanitize_image_filename(filename)
                        except ValueError:
                            continue
                        if not os.path.isfile(src_file) or os.path.islink(src_file):
                            continue
                        if safe_filename.lower() in existing_db_names:
                            continue  # de-dup by original filename
                        dst_file = safe_join(dest_folder, safe_filename)
                        if not os.path.exists(dst_file):
                            shutil.copy2(src_file, dst_file)
                            existing_db_names.add(safe_filename.lower())

                # Preprocess ALL images in dest (including previously imported ones
                # that may have been saved with wrong colours by an older code version)
                all_dest_imgs = [
                    safe_join(dest_folder, f)
                    for f in os.listdir(dest_folder)
                    if is_image_name(f)
                ]
                if all_dest_imgs and self.face_engine.get_settings().get('registration_crop', True):
                    _loop = asyncio.get_running_loop()
                    preprocess_tasks = [
                        _loop.run_in_executor(None, self._preprocess_face_sync, p)
                        for p in all_dest_imgs
                    ]
                    await asyncio.gather(*preprocess_tasks)

                imported += 1
                students_list.append({
                    'id': student['id'],
                    'full_name': student['full_name'],
                    'folder_name': student['folder_name']
                })
                logger.info(f"Imported student from database: {full_name}")

            # Invalidate face cache
            self._invalidate_face_cache()

            return web.json_response({
                'imported': imported,
                'skipped': skipped,
                'students': students_list
            })

        except Exception as e:
            logger.error(f"Error importing database: {e}")
            return web.json_response({'error': str(e)}, status=500)

    # ─── Import Class (2-step: CSV required + optional face folder) ─────

    async def _handle_import_class(self, request) -> web.Response:
        """
        Import a new class from JSON body (frontend parses CSV/XLSX via SheetJS):
          {
            class_name: str (required),
            students: [{mssv: str, full_name: str}, ...] (required, already filtered by browser),
            face_folder: str (optional),
            skipped_client: int (informational)
          }
        """
        try:
            data = await request.json()
            class_name = data.get('class_name', '').strip()
            students_input = data.get('students', [])
            face_folder = (data.get('face_folder') or '').strip()
            skipped_client = int(data.get('skipped_client', 0))

            if not class_name:
                return web.json_response({'error': 'class_name is required'}, status=400)
            if not students_input:
                return web.json_response({'error': 'students list is empty'}, status=400)

            # Create class
            cls = self.db_manager.classes.create(class_name)
            if not cls:
                all_cls = self.db_manager.classes.get_all()
                cls = next((c for c in all_cls if c['name'] == class_name), None)
            if not cls:
                return web.json_response({'error': f'Could not create class "{class_name}"'}, status=500)
            class_id = cls['id']

            imported_students = 0
            imported_faces = 0
            skipped = skipped_client  # include client-side skipped rows
            students_created = []

            for entry in students_input:
                mssv = str(entry.get('mssv', '')).strip()
                full_name = str(entry.get('full_name', '')).strip()
                if not mssv:   # extra safety — skip if MSSV empty
                    skipped += 1
                    continue
                if not full_name:
                    skipped += 1
                    continue
                try:
                    mssv = sanitize_path_segment(mssv, 'mssv')
                except ValueError:
                    skipped += 1
                    continue

                student = self.db_manager.students.create(full_name, mssv, class_id)
                if student:
                    imported_students += 1
                    students_created.append({'mssv': mssv, 'full_name': full_name, 'id': student['id']})
                else:
                    skipped += 1

            # Optional: import face photos from folder
            all_dest_imgs: List[str] = []
            if face_folder and os.path.isdir(face_folder):
                mssv_set = {s['mssv'] for s in students_created}
                for subfolder in os.listdir(face_folder):
                    subfolder_path = os.path.join(face_folder, subfolder)
                    if not os.path.isdir(subfolder_path):
                        continue
                    try:
                        mssv = sanitize_path_segment(subfolder.strip(), 'mssv')
                    except ValueError:
                        continue
                    if mssv not in mssv_set:
                        continue
                    dest = safe_join(self._class_db_path(class_id), mssv)
                    # Robust same-path check (realpath resolves symlinks + normalises separators)
                    src_real  = os.path.normcase(os.path.realpath(subfolder_path))
                    dest_real = os.path.normcase(os.path.realpath(dest))
                    if src_real == dest_real:
                        imported_faces += len([
                            f for f in os.listdir(dest)
                            if f.lower().endswith(('.jpg', '.jpeg', '.png'))
                        ])
                        continue
                    os.makedirs(dest, exist_ok=True)
                    # De-dup by FILENAME (not size — size changes after preprocessing)
                    existing_names = {
                        f.lower() for f in os.listdir(dest)
                        if is_image_name(f)
                    }
                    count = 0
                    for img_file in sorted(os.listdir(subfolder_path)):
                        try:
                            safe_img_file = sanitize_image_filename(img_file)
                        except ValueError:
                            continue
                        src = os.path.join(subfolder_path, img_file)
                        if not os.path.isfile(src) or os.path.islink(src):
                            continue
                        # Skip if dest already has a file with this exact name
                        if safe_img_file.lower() in existing_names:
                            continue
                        dst_path = safe_join(dest, safe_img_file)
                        if not os.path.exists(dst_path):
                            shutil.copy2(src, dst_path)
                            existing_names.add(safe_img_file.lower())
                            count += 1
                    imported_faces += count
                    # Collect ALL images in dest for preprocessing (including previously
                    # imported ones that may have been saved with wrong colours)
                    all_dest_imgs.extend([
                        safe_join(dest, f)
                        for f in os.listdir(dest)
                        if is_image_name(f)
                    ])

            # Preprocess ALL dest face images (detect, crop, align)
            if all_dest_imgs and self.face_engine.get_settings().get('registration_crop', True):
                logger.info(f"[PREPROCESS] Launching {len(all_dest_imgs)} tasks in parallel...")
                loop = asyncio.get_running_loop()
                preprocess_tasks = [
                    loop.run_in_executor(None, self._preprocess_face_sync, p)
                    for p in all_dest_imgs
                ]
                await asyncio.gather(*preprocess_tasks)

            if imported_faces > 0 or all_dest_imgs:
                await self._rebuild_face_cache(class_id)
            else:
                self._invalidate_face_cache(class_id)

            return web.json_response({
                'class_id': class_id,
                'class_name': class_name,
                'imported_students': imported_students,
                'imported_faces': imported_faces,
                'skipped': skipped
            })

        except Exception as e:
            logger.error(f"Error importing class: {e}", exc_info=True)
            return web.json_response({'error': str(e)}, status=500)

    # ─── Export Endpoints ────────────────────────────────────────────────

    async def _handle_export_class_csv(self, request) -> web.Response:
        """Export class student list as CSV: MSSV,Họ tên,Số ảnh đã đăng ký"""
        try:
            class_id = int(request.match_info['id'])
            cls = self.db_manager.classes.get_by_id(class_id)
            if not cls:
                return web.json_response({'error': 'Class not found'}, status=404)

            students = self.db_manager.students.get_by_class(class_id)
            import csv as csv_mod, io
            output = io.StringIO()
            writer = csv_mod.writer(output)
            writer.writerow(['MSSV', 'Họ tên', 'Số ảnh đã đăng ký'])
            for s in students:
                mssv = s.get('folder_name', '')
                name = s.get('full_name', s.get('name', ''))
                # Count photos in per-class directory
                try:
                    photo_dir = self._student_face_path(s)
                except ValueError:
                    photo_dir = None
                photo_count = len([f for f in os.listdir(photo_dir)
                                   if is_image_name(f)]) if photo_dir and os.path.isdir(photo_dir) else 0
                writer.writerow([mssv, name, photo_count])

            csv_bytes = output.getvalue().encode('utf-8-sig')
            safe_name = safe_download_name(cls['name'], 'class')
            return web.Response(
                body=csv_bytes,
                content_type='text/csv',
                headers={'Content-Disposition': f'attachment; filename="{safe_name}.csv"'}
            )
        except Exception as e:
            logger.error(f"Error exporting CSV: {e}")
            return web.json_response({'error': str(e)}, status=500)

    async def _handle_export_class_faces(self, request) -> web.Response:
        """Export face photos as zip with face database structure: MSSV/img_XXXX.jpg"""
        try:
            import zipfile, io as _io
            class_id = int(request.match_info['id'])
            cls = self.db_manager.classes.get_by_id(class_id)
            if not cls:
                return web.json_response({'error': 'Class not found'}, status=404)

            students = self.db_manager.students.get_by_class(class_id)
            buf = _io.BytesIO()
            with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
                for s in students:
                    try:
                        mssv = sanitize_path_segment(s.get('folder_name', ''), 'folder_name')
                        photo_dir = self._student_face_path(s)
                    except ValueError:
                        continue
                    if not os.path.isdir(photo_dir):
                        continue
                    for img_file in sorted(os.listdir(photo_dir)):
                        try:
                            safe_img_file = sanitize_image_filename(img_file)
                        except ValueError:
                            continue
                        src = safe_join(photo_dir, safe_img_file)
                        if os.path.isfile(src):
                            zf.write(src, safe_zip_arcname(mssv, safe_img_file))

            zip_bytes = buf.getvalue()
            safe_name = safe_download_name(cls['name'], 'class')
            return web.Response(
                body=zip_bytes,
                content_type='application/zip',
                headers={'Content-Disposition': f'attachment; filename="{safe_name}_faces.zip"'}
            )
        except Exception as e:
            logger.error(f"Error exporting faces: {e}")
            return web.json_response({'error': str(e)}, status=500)

    # ─── Lesson (Tiết học) Handlers ──────────────────────────────────────

    async def _handle_get_lessons(self, request) -> web.Response:
        """Get all lessons with attendance counts."""
        lessons = self.db_manager.lessons.get_all()
        result = []
        for l in lessons:
            cnt = self.db_manager.lesson_attendance.get_count(l['id'])
            total = len(self.db_manager.students.get_by_class(l['class_id']))
            result.append({**l, 'attended': cnt, 'total_students': total,
                           'is_active': l['id'] == self.active_lesson_id})
        return web.json_response(result)

    async def _handle_create_lesson(self, request) -> web.Response:
        try:
            data = await request.json()
            class_id = int(data.get('class_id', 0))
            name = data.get('name', '').strip()
            date = data.get('date', datetime.now().strftime('%Y-%m-%d'))
            if not class_id or not name:
                return web.json_response({'error': 'class_id and name required'}, status=400)
            lesson = self.db_manager.lessons.create(class_id, name, date)
            if not lesson:
                return web.json_response({'error': 'Failed to create lesson'}, status=500)
            return web.json_response(lesson, status=201)
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def _handle_delete_lesson(self, request) -> web.Response:
        try:
            lesson_id = int(request.match_info['id'])
            if lesson_id == self.active_lesson_id:
                self.active_lesson_id = None
            ok = self.db_manager.lessons.delete(lesson_id)
            return web.json_response({'ok': ok})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def _handle_start_lesson(self, request) -> web.Response:
        try:
            lesson_id = int(request.match_info['id'])
            lesson = self.db_manager.lessons.get_by_id(lesson_id)
            if not lesson:
                return web.json_response({'error': 'Lesson not found'}, status=404)
            async with self.lesson_state_lock:
                # Stop any currently active lesson
                if self.active_lesson_id and self.active_lesson_id != lesson_id:
                    self.db_manager.lessons.set_status(self.active_lesson_id, 'ended')
                self.active_lesson_id = lesson_id
                self.db_manager.lessons.set_status(lesson_id, 'active')
                # Sync current_session with lesson's class
                self.current_session['class_id'] = lesson['class_id']
                self.current_session['date'] = lesson['date']
                self.current_session['started_at'] = datetime.now().isoformat()
                # ── Point face engine at this class's isolated face DB ──────────
                class_db = self._class_db_path(lesson['class_id'])
                self.face_engine.db_path = class_db
            logger.info(f"Face engine switched to class DB: {class_db}")
            await self._broadcast({'type': 'lesson_started', 'lesson': self.db_manager.lessons.get_by_id(lesson_id)})
            return web.json_response({'ok': True, 'lesson_id': lesson_id})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def _handle_stop_lesson(self, request) -> web.Response:
        try:
            lesson_id = int(request.match_info['id'])
            async with self.lesson_state_lock:
                self.db_manager.lessons.set_status(lesson_id, 'ended')
                if self.active_lesson_id == lesson_id:
                    self.active_lesson_id = None
                    self.current_session['class_id'] = None
                    self.current_session['date'] = None
                    self.current_session['started_at'] = None
                    self.face_engine.db_path = DATA_DIR   # reset to root
            await self._broadcast({'type': 'lesson_stopped', 'lesson_id': lesson_id})
            return web.json_response({'ok': True})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def _handle_get_lesson_attendance(self, request) -> web.Response:
        try:
            lesson_id = int(request.match_info['id'])
            records = self.db_manager.lesson_attendance.get_by_lesson(lesson_id)
            return web.json_response(records)
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def _handle_manual_attendance(self, request) -> web.Response:
        """Manually mark a student as attended (tick). Idempotent."""
        try:
            lesson_id = int(request.match_info['id'])
            data = await request.json()
            student_id = int(data['student_id'])
            lesson = self.db_manager.lessons.get_by_id(lesson_id)
            student = self.db_manager.students.get_by_id(student_id)
            if not lesson or not student:
                return web.json_response({'error': 'Lesson or student not found'}, status=404)
            if student.get('class_id') != lesson.get('class_id'):
                return web.json_response({'error': 'Student does not belong to lesson class'}, status=409)
            rec = self.db_manager.lesson_attendance.record(lesson_id, student_id, image_path=None)
            # rec is None if already recorded — still counts as success
            existing = self.db_manager.lesson_attendance.get_by_ids(lesson_id, student_id)
            return web.json_response({'ok': True, 'record': existing}, status=200)
        except (KeyError, ValueError) as e:
            return web.json_response({'error': f'Invalid data: {e}'}, status=400)
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def _handle_delete_lesson_attendance(self, request) -> web.Response:
        """Manually un-tick a student's attendance."""
        try:
            lesson_id = int(request.match_info['id'])
            student_id = int(request.match_info['student_id'])
            lesson = self.db_manager.lessons.get_by_id(lesson_id)
            student = self.db_manager.students.get_by_id(student_id)
            if not lesson or not student:
                return web.json_response({'error': 'Lesson or student not found'}, status=404)
            if student.get('class_id') != lesson.get('class_id'):
                return web.json_response({'error': 'Student does not belong to lesson class'}, status=409)
            deleted = self.db_manager.lesson_attendance.delete(lesson_id, student_id)
            return web.json_response({'ok': True, 'deleted': deleted})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def _handle_export_lesson_csv(self, request) -> web.Response:
        """Export lesson attendance as CSV: MSSV, Họ tên, Thời gian điểm danh"""
        try:
            lesson_id = int(request.match_info['id'])
            lesson = self.db_manager.lessons.get_by_id(lesson_id)
            if not lesson:
                return web.json_response({'error': 'Lesson not found'}, status=404)
            records = self.db_manager.lesson_attendance.get_by_lesson(lesson_id)
            attended_set = {r['student_id']: r for r in records}
            students = self.db_manager.students.get_by_class(lesson['class_id'])
            import csv as csv_mod, io
            output = io.StringIO()
            writer = csv_mod.writer(output)
            # Dùng ngày tiết học làm tên cột điểm danh, chỉ đánh tick
            lesson_date = lesson.get('date', 'Điểm danh') or 'Điểm danh'
            writer.writerow(['MSSV', 'Họ tên', lesson_date])
            for s in students:
                rec = attended_set.get(s['id'])
                writer.writerow([s['folder_name'], s['full_name'], '✓' if rec else ''])
            csv_bytes = output.getvalue().encode('utf-8-sig')
            safe = lesson['name'].replace(' ', '_').replace('/', '-')
            return web.Response(
                body=csv_bytes,
                content_type='text/csv',
                headers={'Content-Disposition': f'attachment; filename="{safe}.csv"'}
            )
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def _handle_export_lesson_fill(self, request) -> web.Response:
        """Fill existing CSV/XLSX data: match MSSV, mark attendance column.
        Body: {rows: [[...]], mssv_col: N, att_col: N or -1 (after last), has_header: bool,
               skip_rows: N (bỏ qua N hàng đầu không chạm vào),
               prepend_rows: N (thêm N hàng trống vào ĐẦU file trước mọi xử lý),
               tick_symbol: str (ký hiệu điểm danh, mặc định '✓')}
        Returns: {rows: [[...]] with attendance column filled, matched: count}
        """
        try:
            lesson_id = int(request.match_info['id'])
            data = await request.json()
            rows = data.get('rows', [])
            mssv_col = int(data.get('mssv_col', 0))
            att_col_raw = data.get('att_col', -1)
            # -1 means "append new column after last"
            att_col = -1 if str(att_col_raw) in ('-1', 'after_last') else int(att_col_raw)
            has_header = bool(data.get('has_header', True))
            skip_rows = max(0, int(data.get('skip_rows', 0)))
            prepend_rows = max(0, int(data.get('prepend_rows', 0)))
            tick_symbol = str(data.get('tick_symbol', '✓')) or '✓'

            # Lấy thông tin tiết học để ghi ngày vào header
            lesson = self.db_manager.lessons.get_by_id(lesson_id)
            lesson_date = lesson['date'] if lesson else ''

            records = self.db_manager.lesson_attendance.get_by_lesson(lesson_id)
            attended_mssv = {r['folder_name'] for r in records}

            # Thêm hàng trống ở đầu — sau đó coi toàn bộ file mới là file làm việc.
            # skip_rows và has_header đều tính từ đầu file MỚI (kể cả hàng trống vừa thêm).
            # Ví dụ: prepend=1, skip=0, has_header=True
            #   → hàng 0 (hàng trống mới) = header → ghi ngày tiết vào đó
            #   → hàng 1 trở đi = dữ liệu sinh viên
            blank_rows = [[''] * (max((len(r) for r in rows), default=1)) for _ in range(prepend_rows)]
            rows_to_process = blank_rows + [list(r) for r in rows]

            out = []
            matched = 0
            for i, row in enumerate(rows_to_process):
                row = list(row)

                # Hàng bị bỏ qua (skip_rows tính từ đầu file mới) — giữ nguyên
                if i < skip_rows:
                    out.append(row)
                    continue

                # Hàng header (ngay tại vị trí skip_rows, nếu has_header)
                if has_header and i == skip_rows:
                    if att_col == -1:
                        row.append(lesson_date)
                    else:
                        while len(row) <= att_col:
                            row.append('')
                        row[att_col] = lesson_date
                    out.append(row)
                    continue

                # Hàng dữ liệu — điền tick nếu sinh viên có điểm danh
                mssv = str(row[mssv_col]).strip() if mssv_col < len(row) else ''
                is_attended = mssv in attended_mssv
                if att_col == -1:
                    row.append(tick_symbol if is_attended else '')
                else:
                    while len(row) <= att_col:
                        row.append('')
                    if is_attended:
                        row[att_col] = tick_symbol
                if is_attended:
                    matched += 1
                out.append(row)

            return web.json_response({'rows': out, 'matched': matched})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def _broadcast(self, data: dict):
        """Broadcast arbitrary JSON to all WebSocket clients."""
        message = json.dumps(data)
        dead = set()
        for ws in self.websocket_clients:
            try:
                await ws.send_str(message)
            except Exception:
                dead.add(ws)
        self.websocket_clients -= dead

    # ─── Utility Methods ────────────────────────────────────────────────

    def _preprocess_face_sync(self, file_path: str) -> bool:
        """Detect the largest face with SCRFD and overwrite the registration image with a crop."""
        tid = threading.get_ident()
        fname = os.path.basename(file_path)
        logger.info(f"[PREPROCESS][thread={tid}] START {fname}")
        try:
            ok = self.face_engine.preprocess_registration_image(
                file_path,
                expand_percentage=FACE_EXPAND_PERCENTAGE
            )
            logger.info(f"[PREPROCESS][thread={tid}] {'OK' if ok else 'SKIPPED'} {fname}")
            return ok
        except Exception as e:
            logger.error(f"[PREPROCESS][thread={tid}] EXCEPTION {fname}: {type(e).__name__}: {e}")
            return False

    async def _preprocess_and_save_face(self, file_path: str) -> bool:
        """Async wrapper — runs face preprocessing in a thread executor."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._preprocess_face_sync, file_path)

    async def _handle_pick_folder(self, request) -> web.Response:
        """Open a native folder picker dialog on the server machine and return the selected path."""
        def _pick():
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.wm_attributes('-topmost', True)
            folder = filedialog.askdirectory(title='Chọn thư mục ảnh khuôn mặt')
            root.destroy()
            return folder
        loop = asyncio.get_running_loop()
        folder = await loop.run_in_executor(None, _pick)
        if folder:
            return web.json_response({'path': folder})
        return web.json_response({'path': None})

    # ─── Per-class Face DB ──────────────────────────────────────────────

    def _class_db_path(self, class_id, create: bool = True) -> str:
        """Return the face-image directory for a specific class."""
        class_segment = sanitize_path_segment(str(int(class_id)), 'class_id')
        path = safe_join(DATA_DIR, class_segment)
        if create:
            os.makedirs(path, exist_ok=True)
        return path

    def _student_face_path(self, student: dict) -> str:
        """Absolute path to a student's face-image folder (new per-class layout)."""
        folder_name = sanitize_path_segment(student['folder_name'], 'folder_name')
        return safe_join(self._class_db_path(student['class_id']), folder_name)

    def _migrate_legacy_face_data(self):
        """One-time migration: move DATA_DIR/{folder_name}/ → DATA_DIR/{class_id}/{folder_name}/.

        Called at startup. Safe to run multiple times — already-migrated folders are skipped.
        """
        try:
            all_students = self.db_manager.students.get_all()

            migrated = 0
            for student in all_students:
                folder_name = student.get('folder_name')
                class_id    = student.get('class_id')
                if not folder_name or not class_id:
                    continue
                try:
                    safe_folder = sanitize_path_segment(folder_name, 'folder_name')
                    legacy_path = safe_join(DATA_DIR, safe_folder)
                    new_path = safe_join(self._class_db_path(class_id), safe_folder)
                except ValueError:
                    logger.warning(f"Skipping unsafe legacy folder during migration: {folder_name}")
                    continue
                if os.path.isdir(legacy_path) and not os.path.exists(new_path):
                    os.makedirs(os.path.dirname(new_path), exist_ok=True)
                    shutil.move(legacy_path, new_path)
                    migrated += 1
                    logger.info(f"Migrated face folder: {legacy_path} → {new_path}")
            if migrated:
                logger.info(f"Face data migration complete: {migrated} folder(s) moved.")
                self._invalidate_face_cache()
        except Exception as e:
            logger.warning(f"Face data migration error (non-fatal): {e}")

    def _invalidate_face_cache(self, class_id=None):
        """Invalidate InsightFace embedding cache for one class or all classes."""
        try:
            if class_id is not None:
                self.face_engine.invalidate_cache(self._class_db_path(class_id, create=False))
            else:
                self.face_engine.invalidate_cache()
        except Exception as e:
            logger.warning(f"Could not invalidate face cache: {e}")

    async def _rebuild_face_cache(self, class_id=None):
        """Invalidate and rebuild InsightFace embedding cache for one class or all classes."""
        try:
            db_path = self._class_db_path(class_id, create=False) if class_id is not None else self.face_engine.db_path
            self.face_engine.invalidate_cache(db_path)
            async with self.recognition_semaphore:
                return await asyncio.get_event_loop().run_in_executor(
                    None,
                    self.face_engine.cache_status,
                    db_path,
                    True
                )
        except Exception as e:
            logger.warning(f"Could not rebuild face cache: {e}")
            return None

    # ─── Server Control ────────────────────────────────────────────────

    def start(self):
        """Start the server (compatible with aiohttp 3.10+)."""
        import time
        try:
            # Migrate legacy face data to per-class directory structure
            self._migrate_legacy_face_data()

            # No demo data auto-import — data/ folder is clean and managed through the app

            # Create event loop and start in background thread
            self._loop = asyncio.new_event_loop()
            self._stop_event = asyncio.Event()
            self._server_thread = threading.Thread(target=self._run_loop, daemon=True)
            self._server_thread.start()

            # Wait for server to be ready
            time.sleep(2)

            print(f"\n✅ FaceCheckin Server: http://{self.get_ip()}:{self.port}")
            print(f"📍 Database: {DB_PATH}")
            print(f"📁 Data: {DATA_DIR}")
            print(f"🌐 Dashboard: http://localhost:{self.port}")
            print(f"🎯 API: /api/classes, /api/students, /api/attendance")

        except Exception as e:
            logger.error(f"Error starting server: {e}", exc_info=True)
            raise

    def stop(self):
        """Stop the server."""
        try:
            if self._loop and not self._loop.is_closed():
                if hasattr(self, '_stop_event'):
                    self._loop.call_soon_threadsafe(self._stop_event.set)
                if hasattr(self, '_server_thread') and self._server_thread.is_alive():
                    self._server_thread.join(timeout=5)
            self.db_manager.close()
            print("\n✅ Server stopped")
        except Exception as e:
            logger.error(f"Error stopping server: {e}")

    def _run_loop(self):
        """Run aiohttp server using AppRunner (aiohttp 3.10+ compatible)."""
        asyncio.set_event_loop(self._loop)

        # Suppress harmless "connection forcibly closed" errors from iOS/mobile clients
        # on Windows (WinError 10054 / ConnectionResetError).
        def _loop_exception_handler(loop, context):
            exc = context.get('exception')
            if isinstance(exc, (ConnectionResetError, BrokenPipeError)):
                return  # ignore — remote host closed the socket early
            loop.default_exception_handler(context)

        self._loop.set_exception_handler(_loop_exception_handler)

        async def _serve():
            runner = web.AppRunner(self._app, handle_signals=False)
            await runner.setup()
            site = web.TCPSite(runner, self.host, self.port)
            await site.start()
            logger.info(f"Server listening on {self.host}:{self.port}")
            # Keep running until stop event
            await self._stop_event.wait()
            await runner.cleanup()

        try:
            self._loop.run_until_complete(_serve())
        except Exception as e:
            logger.error(f"Error in server loop: {e}", exc_info=True)
        finally:
            self._loop.close()

    @staticmethod
    def get_lan_ips() -> List[str]:
        ips = []
        try:
            hostname = socket.gethostname()
            for info in socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_DGRAM):
                ip = info[4][0]
                if ip.startswith('127.') or ip.startswith('169.254.'):
                    continue
                if ip not in ips:
                    ips.append(ip)
        except Exception:
            pass
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            if not ip.startswith('127.') and ip not in ips:
                ips.insert(0, ip)
        except Exception:
            pass
        return ips or ["127.0.0.1"]

    @staticmethod
    def get_ip() -> str:
        """Get local IP address."""
        return AttendanceServer.get_lan_ips()[0]


if __name__ == '__main__':
    server = AttendanceServer()
    server.start()

    try:
        input("Press Enter to stop server...\n")
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
