"""
Database module for FaceCheckin.
Manages SQLite database with classes, students, and attendance records.
"""

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class Database:
    """Thread-safe SQLite database wrapper using WAL mode + single connection + lock."""

    def __init__(self, db_path: str):
        """Initialize database connection."""
        self.db_path = db_path
        self._lock = threading.Lock()
        # Single shared connection with WAL mode for concurrency
        self._conn = sqlite3.connect(
            db_path,
            check_same_thread=False,
            timeout=30,          # wait up to 30s if locked
        )
        self._conn.row_factory = sqlite3.Row
        # WAL mode allows concurrent reads + one writer without locking
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=10000")
        self._conn.commit()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Return the shared connection (thread-safe via _lock)."""
        return self._conn

    def _init_db(self):
        """Create tables if they don't exist."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

        # Classes table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS classes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Students table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                folder_name TEXT NOT NULL UNIQUE,
                class_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(class_id) REFERENCES classes(id)
            )
        ''')

        # Attendance records table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS attendance_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                class_id INTEGER NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                date TEXT NOT NULL,
                confidence REAL,
                image_path TEXT,
                FOREIGN KEY(student_id) REFERENCES students(id),
                FOREIGN KEY(class_id) REFERENCES classes(id)
            )
        ''')

        # Lessons (tiết học) table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                class_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                date TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(class_id) REFERENCES classes(id)
            )
        ''')

        # Lesson attendance table (one record per student per lesson)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS lesson_attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lesson_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                image_path TEXT,
                FOREIGN KEY(lesson_id) REFERENCES lessons(id),
                FOREIGN KEY(student_id) REFERENCES students(id),
                UNIQUE(lesson_id, student_id)
            )
        ''')

        conn.commit()
        logger.info("Database tables initialized")

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a write query with lock to prevent concurrent write conflicts."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(query, params)
            self._conn.commit()
            return cursor

    def fetch_one(self, query: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """Fetch a single row (reads don't need the write lock in WAL mode)."""
        cursor = self._conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchone()

    def fetch_all(self, query: str, params: tuple = ()) -> List[sqlite3.Row]:
        """Fetch all rows (reads don't need the write lock in WAL mode)."""
        cursor = self._conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchall()

    def close(self):
        """Close database connection."""
        try:
            self._conn.close()
        except Exception:
            pass


class ClassDB:
    """Database operations for classes."""

    def __init__(self, db: Database):
        self.db = db

    def get_all(self) -> List[Dict]:
        """Get all classes."""
        rows = self.db.fetch_all('SELECT * FROM classes ORDER BY created_at')
        return [dict(row) for row in rows]

    def get_by_id(self, class_id: int) -> Optional[Dict]:
        """Get class by ID."""
        row = self.db.fetch_one('SELECT * FROM classes WHERE id = ?', (class_id,))
        return dict(row) if row else None

    def create(self, name: str, description: str = '') -> Dict:
        """Create a new class."""
        try:
            cursor = self.db.execute(
                'INSERT INTO classes (name, description) VALUES (?, ?)',
                (name, description)
            )
            class_id = cursor.lastrowid
            logger.info(f"Created class: {name} (id={class_id})")
            return self.get_by_id(class_id)
        except sqlite3.IntegrityError:
            logger.warning(f"Class '{name}' already exists")
            return None

    def update(self, class_id: int, name: str = None, description: str = None) -> bool:
        """Update a class."""
        updates = []
        params = []

        if name is not None:
            updates.append('name = ?')
            params.append(name)
        if description is not None:
            updates.append('description = ?')
            params.append(description)

        if not updates:
            return False

        params.append(class_id)
        query = f'UPDATE classes SET {", ".join(updates)} WHERE id = ?'

        try:
            cursor = self.db.execute(query, tuple(params))
            if cursor.rowcount > 0:
                logger.info(f"Updated class id={class_id}")
                return True
            return False
        except sqlite3.IntegrityError:
            logger.warning(f"Failed to update class id={class_id}")
            return False

    def delete(self, class_id: int) -> bool:
        """Delete a class and its associated records."""
        try:
            # Delete attendance records for this class
            self.db.execute('DELETE FROM attendance_records WHERE class_id = ?', (class_id,))

            # Delete students in this class
            self.db.execute('DELETE FROM students WHERE class_id = ?', (class_id,))

            # Delete the class
            cursor = self.db.execute('DELETE FROM classes WHERE id = ?', (class_id,))

            if cursor.rowcount > 0:
                logger.info(f"Deleted class id={class_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting class: {e}")
            return False


class StudentDB:
    """Database operations for students."""

    def __init__(self, db: Database):
        self.db = db

    def get_all(self) -> List[Dict]:
        """Get all students."""
        rows = self.db.fetch_all('SELECT * FROM students ORDER BY full_name')
        return [dict(row) for row in rows]

    def get_by_class(self, class_id: int) -> List[Dict]:
        """Get students in a class."""
        rows = self.db.fetch_all(
            'SELECT * FROM students WHERE class_id = ? ORDER BY full_name',
            (class_id,)
        )
        return [dict(row) for row in rows]

    def get_by_id(self, student_id: int) -> Optional[Dict]:
        """Get student by ID."""
        row = self.db.fetch_one('SELECT * FROM students WHERE id = ?', (student_id,))
        return dict(row) if row else None

    def get_by_folder_name(self, folder_name: str) -> Optional[Dict]:
        """Get student by folder name."""
        row = self.db.fetch_one(
            'SELECT * FROM students WHERE folder_name = ?',
            (folder_name,)
        )
        return dict(row) if row else None

    def create(self, full_name: str, folder_name: str, class_id: int) -> Optional[Dict]:
        """Create a new student."""
        try:
            cursor = self.db.execute(
                'INSERT INTO students (full_name, folder_name, class_id) VALUES (?, ?, ?)',
                (full_name, folder_name, class_id)
            )
            student_id = cursor.lastrowid
            logger.info(f"Created student: {full_name} (id={student_id})")
            return self.get_by_id(student_id)
        except sqlite3.IntegrityError:
            logger.warning(f"Student folder '{folder_name}' already exists")
            return None

    def delete(self, student_id: int) -> bool:
        """Delete a student and their attendance records."""
        try:
            # Delete attendance records
            self.db.execute('DELETE FROM attendance_records WHERE student_id = ?', (student_id,))

            # Delete student
            cursor = self.db.execute('DELETE FROM students WHERE id = ?', (student_id,))

            if cursor.rowcount > 0:
                logger.info(f"Deleted student id={student_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting student: {e}")
            return False


class AttendanceDB:
    """Database operations for attendance records."""

    def __init__(self, db: Database):
        self.db = db

    def record_attendance(
        self,
        student_id: int,
        class_id: int,
        date: str,
        confidence: float = None,
        image_path: str = None
    ) -> Optional[Dict]:
        """Record attendance for a student."""
        try:
            cursor = self.db.execute(
                '''INSERT INTO attendance_records
                   (student_id, class_id, date, confidence, image_path)
                   VALUES (?, ?, ?, ?, ?)''',
                (student_id, class_id, date, confidence, image_path)
            )
            record_id = cursor.lastrowid
            logger.info(f"Recorded attendance: student_id={student_id}, date={date}")
            return self.get_by_id(record_id)
        except Exception as e:
            logger.error(f"Error recording attendance: {e}")
            return None

    def get_by_id(self, record_id: int) -> Optional[Dict]:
        """Get attendance record by ID."""
        row = self.db.fetch_one(
            'SELECT * FROM attendance_records WHERE id = ?',
            (record_id,)
        )
        return dict(row) if row else None

    def get_by_date(self, date: str) -> List[Dict]:
        """Get all attendance records for a date."""
        rows = self.db.fetch_all(
            'SELECT * FROM attendance_records WHERE date = ? ORDER BY timestamp',
            (date,)
        )
        return [dict(row) for row in rows]

    def get_by_class(self, class_id: int, date: str = None) -> List[Dict]:
        """Get attendance records for a class."""
        if date:
            rows = self.db.fetch_all(
                'SELECT * FROM attendance_records WHERE class_id = ? AND date = ? ORDER BY timestamp',
                (class_id, date)
            )
        else:
            rows = self.db.fetch_all(
                'SELECT * FROM attendance_records WHERE class_id = ? ORDER BY timestamp DESC',
                (class_id,)
            )
        return [dict(row) for row in rows]

    def get_by_student(self, student_id: int) -> List[Dict]:
        """Get all attendance records for a student."""
        rows = self.db.fetch_all(
            'SELECT * FROM attendance_records WHERE student_id = ? ORDER BY timestamp DESC',
            (student_id,)
        )
        return [dict(row) for row in rows]

    def get_stats(self, class_id: int, date: str = None) -> Dict:
        """Get attendance statistics for a class."""
        if date:
            records = self.get_by_class(class_id, date)
        else:
            records = self.get_by_class(class_id)

        # Get all students in class
        from database import StudentDB
        students = StudentDB(self.db).get_by_class(class_id)

        attended_ids = set(r['student_id'] for r in records)

        return {
            'total_students': len(students),
            'present': len(attended_ids),
            'absent': len(students) - len(attended_ids),
            'attendance_rate': len(attended_ids) / len(students) if students else 0,
            'records': records
        }

    def get_today_stats(self, class_id: int) -> Dict:
        """Get attendance statistics for today."""
        today = datetime.now().strftime('%Y-%m-%d')
        return self.get_stats(class_id, today)


class LessonDB:
    """Database operations for lessons (tiết học)."""

    def __init__(self, db: Database):
        self.db = db

    def get_all(self) -> List[Dict]:
        rows = self.db.fetch_all(
            '''SELECT l.*, c.name as class_name FROM lessons l
               JOIN classes c ON l.class_id = c.id
               ORDER BY l.date DESC, l.created_at DESC'''
        )
        return [dict(row) for row in rows]

    def get_by_id(self, lesson_id: int) -> Optional[Dict]:
        row = self.db.fetch_one(
            '''SELECT l.*, c.name as class_name FROM lessons l
               JOIN classes c ON l.class_id = c.id WHERE l.id = ?''', (lesson_id,)
        )
        return dict(row) if row else None

    def get_active(self) -> Optional[Dict]:
        row = self.db.fetch_one(
            '''SELECT l.*, c.name as class_name FROM lessons l
               JOIN classes c ON l.class_id = c.id WHERE l.status = 'active' LIMIT 1'''
        )
        return dict(row) if row else None

    def create(self, class_id: int, name: str, date: str) -> Optional[Dict]:
        try:
            cursor = self.db.execute(
                'INSERT INTO lessons (class_id, name, date) VALUES (?, ?, ?)',
                (class_id, name, date)
            )
            return self.get_by_id(cursor.lastrowid)
        except Exception as e:
            logger.error(f"Error creating lesson: {e}")
            return None

    def set_status(self, lesson_id: int, status: str) -> bool:
        cursor = self.db.execute(
            'UPDATE lessons SET status = ? WHERE id = ?', (status, lesson_id)
        )
        return cursor.rowcount > 0

    def delete(self, lesson_id: int) -> bool:
        try:
            self.db.execute('DELETE FROM lesson_attendance WHERE lesson_id = ?', (lesson_id,))
            cursor = self.db.execute('DELETE FROM lessons WHERE id = ?', (lesson_id,))
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error deleting lesson: {e}")
            return False


class LessonAttendanceDB:
    """Database operations for lesson attendance."""

    def __init__(self, db: Database):
        self.db = db

    def record(self, lesson_id: int, student_id: int, image_path: str = None) -> Optional[Dict]:
        """Record attendance — INSERT OR IGNORE to keep first check-in only."""
        try:
            cursor = self.db.execute(
                '''INSERT OR IGNORE INTO lesson_attendance (lesson_id, student_id, image_path)
                   VALUES (?, ?, ?)''',
                (lesson_id, student_id, image_path)
            )
            if cursor.rowcount == 0:
                return None  # already recorded
            return self.get_by_ids(lesson_id, student_id)
        except Exception as e:
            logger.error(f"Error recording lesson attendance: {e}")
            return None

    def get_by_ids(self, lesson_id: int, student_id: int) -> Optional[Dict]:
        row = self.db.fetch_one(
            'SELECT * FROM lesson_attendance WHERE lesson_id=? AND student_id=?',
            (lesson_id, student_id)
        )
        return dict(row) if row else None

    def get_by_lesson(self, lesson_id: int) -> List[Dict]:
        rows = self.db.fetch_all(
            '''SELECT la.*, s.full_name, s.folder_name FROM lesson_attendance la
               JOIN students s ON la.student_id = s.id
               WHERE la.lesson_id = ? ORDER BY la.timestamp''',
            (lesson_id,)
        )
        return [dict(row) for row in rows]

    def delete(self, lesson_id: int, student_id: int) -> bool:
        """Remove an attendance record (manual un-tick)."""
        try:
            cursor = self.db.execute(
                'DELETE FROM lesson_attendance WHERE lesson_id=? AND student_id=?',
                (lesson_id, student_id)
            )
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error deleting lesson attendance: {e}")
            return False

    def get_count(self, lesson_id: int) -> int:
        row = self.db.fetch_one(
            'SELECT COUNT(*) as cnt FROM lesson_attendance WHERE lesson_id=?', (lesson_id,)
        )
        return row['cnt'] if row else 0


class DatabaseManager:
    """Main database manager combining all operations."""

    def __init__(self, db_path: str):
        """Initialize database manager."""
        self.db = Database(db_path)
        self.classes = ClassDB(self.db)
        self.students = StudentDB(self.db)
        self.attendance = AttendanceDB(self.db)
        self.lessons = LessonDB(self.db)
        self.lesson_attendance = LessonAttendanceDB(self.db)

    def initialize_demo_data(self, data_dir: str):
        """Initialize with demo data (default class and students from folders)."""
        # Create default class
        class_record = self.classes.create('Lớp Demo', 'Lớp mặc định cho demo')
        if not class_record:
            class_record = self.classes.get_by_id(1)

        if not class_record:
            logger.error("Failed to create/get demo class")
            return

        class_id = class_record['id']

        # Scan data directory for student folders
        data_path = Path(data_dir)
        if not data_path.exists():
            logger.warning(f"Data directory not found: {data_dir}")
            return

        student_folders = [
            d for d in data_path.iterdir()
            if d.is_dir() and not d.name.startswith('.')
        ]

        for folder in sorted(student_folders):
            folder_name = folder.name
            # Convert folder name to display name (replace underscore with space)
            full_name = folder_name.replace('_', ' ')

            # Check if student already exists
            if not self.students.get_by_folder_name(folder_name):
                self.students.create(full_name, folder_name, class_id)

        logger.info(f"Initialized demo data with {len(student_folders)} students")

    def close(self):
        """Close database connection."""
        self.db.close()
