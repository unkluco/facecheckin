"""
Database module for FaceCheckin.
Manages SQLite database with classes, students, and attendance records.
"""

import os
import shutil
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class Database:
    """Thread-safe SQLite database wrapper using WAL mode + single connection + lock."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            db_path,
            check_same_thread=False,
            timeout=30,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=10000")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.commit()
        self._init_db()
        self._migrate_schema()

    def _get_connection(self) -> sqlite3.Connection:
        return self._conn

    def _init_db(self):
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS classes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS students (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT NOT NULL,
                    folder_name TEXT NOT NULL,
                    class_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(class_id) REFERENCES classes(id) ON DELETE CASCADE,
                    UNIQUE(class_id, folder_name)
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS attendance_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER NOT NULL,
                    class_id INTEGER NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    date TEXT NOT NULL,
                    confidence REAL,
                    image_path TEXT,
                    FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE,
                    FOREIGN KEY(class_id) REFERENCES classes(id) ON DELETE CASCADE
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS lessons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    class_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    date TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(class_id) REFERENCES classes(id) ON DELETE CASCADE
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS lesson_attendance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lesson_id INTEGER NOT NULL,
                    student_id INTEGER NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    image_path TEXT,
                    FOREIGN KEY(lesson_id) REFERENCES lessons(id) ON DELETE CASCADE,
                    FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE,
                    UNIQUE(lesson_id, student_id)
                )
            ''')

            conn.commit()
        logger.info("Database tables initialized")

    def _foreign_keys_have_cascade(self, table: str) -> bool:
        rows = self._conn.execute(f'PRAGMA foreign_key_list({table})').fetchall()
        return all(row['on_delete'].upper() == 'CASCADE' for row in rows)

    def _students_has_class_scoped_unique(self) -> bool:
        rows = self._conn.execute('PRAGMA index_list(students)').fetchall()
        for row in rows:
            if not row['unique']:
                continue
            cols = [r['name'] for r in self._conn.execute(f"PRAGMA index_info({row['name']})").fetchall()]
            if cols == ['class_id', 'folder_name']:
                return True
        return False

    def _needs_schema_migration(self) -> bool:
        required_tables = ['students', 'attendance_records', 'lessons', 'lesson_attendance']
        if not self._students_has_class_scoped_unique():
            return True
        return not all(self._foreign_keys_have_cascade(table) for table in required_tables)

    def _backup_db(self) -> Optional[str]:
        if not os.path.exists(self.db_path) or os.path.getsize(self.db_path) == 0:
            return None
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = f'{self.db_path}.bak_{stamp}'
        shutil.copy2(self.db_path, backup_path)
        logger.info(f"Created database backup before schema migration: {backup_path}")
        return backup_path

    def _migrate_schema(self):
        with self._lock:
            if not self._needs_schema_migration():
                return

            self._backup_db()
            conn = self._conn
            logger.info("Migrating database schema for cascade FKs and class-scoped folder names")

            try:
                conn.execute('PRAGMA foreign_keys=OFF')
                conn.execute('BEGIN')

                conn.execute('''
                    CREATE TABLE classes_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        description TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                conn.execute('''
                    CREATE TABLE students_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        full_name TEXT NOT NULL,
                        folder_name TEXT NOT NULL,
                        class_id INTEGER NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(class_id) REFERENCES classes_new(id) ON DELETE CASCADE,
                        UNIQUE(class_id, folder_name)
                    )
                ''')
                conn.execute('''
                    CREATE TABLE attendance_records_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        student_id INTEGER NOT NULL,
                        class_id INTEGER NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        date TEXT NOT NULL,
                        confidence REAL,
                        image_path TEXT,
                        FOREIGN KEY(student_id) REFERENCES students_new(id) ON DELETE CASCADE,
                        FOREIGN KEY(class_id) REFERENCES classes_new(id) ON DELETE CASCADE
                    )
                ''')
                conn.execute('''
                    CREATE TABLE lessons_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        class_id INTEGER NOT NULL,
                        name TEXT NOT NULL,
                        date TEXT NOT NULL,
                        status TEXT DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(class_id) REFERENCES classes_new(id) ON DELETE CASCADE
                    )
                ''')
                conn.execute('''
                    CREATE TABLE lesson_attendance_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        lesson_id INTEGER NOT NULL,
                        student_id INTEGER NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        image_path TEXT,
                        FOREIGN KEY(lesson_id) REFERENCES lessons_new(id) ON DELETE CASCADE,
                        FOREIGN KEY(student_id) REFERENCES students_new(id) ON DELETE CASCADE,
                        UNIQUE(lesson_id, student_id)
                    )
                ''')

                conn.execute('INSERT INTO classes_new SELECT id, name, description, created_at FROM classes')
                conn.execute('''
                    INSERT OR IGNORE INTO students_new (id, full_name, folder_name, class_id, created_at)
                    SELECT s.id, s.full_name, s.folder_name, s.class_id, s.created_at
                    FROM students s
                    JOIN classes_new c ON c.id = s.class_id
                    ORDER BY s.id
                ''')
                conn.execute('''
                    INSERT INTO attendance_records_new (id, student_id, class_id, timestamp, date, confidence, image_path)
                    SELECT ar.id, ar.student_id, ar.class_id, ar.timestamp, ar.date, ar.confidence, ar.image_path
                    FROM attendance_records ar
                    JOIN students_new s ON s.id = ar.student_id
                    JOIN classes_new c ON c.id = ar.class_id
                ''')
                conn.execute('''
                    INSERT INTO lessons_new (id, class_id, name, date, status, created_at)
                    SELECT l.id, l.class_id, l.name, l.date, l.status, l.created_at
                    FROM lessons l
                    JOIN classes_new c ON c.id = l.class_id
                ''')
                conn.execute('''
                    INSERT OR IGNORE INTO lesson_attendance_new (id, lesson_id, student_id, timestamp, image_path)
                    SELECT la.id, la.lesson_id, la.student_id, la.timestamp, la.image_path
                    FROM lesson_attendance la
                    JOIN lessons_new l ON l.id = la.lesson_id
                    JOIN students_new s ON s.id = la.student_id
                ''')

                for table in ['lesson_attendance', 'lessons', 'attendance_records', 'students', 'classes']:
                    conn.execute(f'DROP TABLE {table}')
                for table in ['classes', 'students', 'attendance_records', 'lessons', 'lesson_attendance']:
                    conn.execute(f'ALTER TABLE {table}_new RENAME TO {table}')

                fk_rows = conn.execute('PRAGMA foreign_key_check').fetchall()
                if fk_rows:
                    raise sqlite3.IntegrityError(f'foreign_key_check failed: {fk_rows}')

                conn.commit()
                logger.info("Database schema migration completed")
            except Exception:
                conn.rollback()
                logger.exception("Database schema migration failed")
                raise
            finally:
                conn.execute('PRAGMA foreign_keys=ON')
                conn.commit()

    @contextmanager
    def transaction(self):
        with self._lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute('BEGIN')
                yield cursor
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(query, params)
            self._conn.commit()
            return cursor

    def fetch_one(self, query: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchone()

    def fetch_all(self, query: str, params: tuple = ()) -> List[sqlite3.Row]:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass


class ClassDB:
    """Database operations for classes."""

    def __init__(self, db: Database):
        self.db = db

    def get_all(self) -> List[Dict]:
        rows = self.db.fetch_all('SELECT * FROM classes ORDER BY created_at')
        return [dict(row) for row in rows]

    def get_by_id(self, class_id: int) -> Optional[Dict]:
        row = self.db.fetch_one('SELECT * FROM classes WHERE id = ?', (class_id,))
        return dict(row) if row else None

    def create(self, name: str, description: str = '') -> Optional[Dict]:
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
        try:
            with self.db.transaction() as cursor:
                cursor.execute('DELETE FROM classes WHERE id = ?', (class_id,))
                deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted class id={class_id}")
            return deleted
        except Exception as e:
            logger.error(f"Error deleting class: {e}")
            return False


class StudentDB:
    """Database operations for students."""

    def __init__(self, db: Database):
        self.db = db

    def get_all(self) -> List[Dict]:
        rows = self.db.fetch_all('SELECT * FROM students ORDER BY full_name')
        return [dict(row) for row in rows]

    def get_by_class(self, class_id: int) -> List[Dict]:
        rows = self.db.fetch_all(
            'SELECT * FROM students WHERE class_id = ? ORDER BY full_name',
            (class_id,)
        )
        return [dict(row) for row in rows]

    def get_by_id(self, student_id: int) -> Optional[Dict]:
        row = self.db.fetch_one('SELECT * FROM students WHERE id = ?', (student_id,))
        return dict(row) if row else None

    def get_by_folder_name(self, folder_name: str, class_id: int = None) -> Optional[Dict]:
        if class_id is not None:
            row = self.db.fetch_one(
                'SELECT * FROM students WHERE folder_name = ? AND class_id = ?',
                (folder_name, class_id)
            )
        else:
            row = self.db.fetch_one(
                'SELECT * FROM students WHERE folder_name = ? ORDER BY id LIMIT 1',
                (folder_name,)
            )
        return dict(row) if row else None

    def get_by_class_and_folder(self, class_id: int, folder_name: str) -> Optional[Dict]:
        return self.get_by_folder_name(folder_name, class_id)

    def create(self, full_name: str, folder_name: str, class_id: int) -> Optional[Dict]:
        try:
            cursor = self.db.execute(
                'INSERT INTO students (full_name, folder_name, class_id) VALUES (?, ?, ?)',
                (full_name, folder_name, class_id)
            )
            student_id = cursor.lastrowid
            logger.info(f"Created student: {full_name} (id={student_id})")
            return self.get_by_id(student_id)
        except sqlite3.IntegrityError as e:
            logger.warning(f"Failed to create student '{folder_name}' in class {class_id}: {e}")
            return None

    def delete(self, student_id: int) -> bool:
        try:
            with self.db.transaction() as cursor:
                cursor.execute('DELETE FROM students WHERE id = ?', (student_id,))
                deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted student id={student_id}")
            return deleted
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
        row = self.db.fetch_one(
            'SELECT * FROM attendance_records WHERE id = ?',
            (record_id,)
        )
        return dict(row) if row else None

    def get_by_date(self, date: str) -> List[Dict]:
        rows = self.db.fetch_all(
            'SELECT * FROM attendance_records WHERE date = ? ORDER BY timestamp',
            (date,)
        )
        return [dict(row) for row in rows]

    def get_by_class(self, class_id: int, date: str = None) -> List[Dict]:
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
        rows = self.db.fetch_all(
            'SELECT * FROM attendance_records WHERE student_id = ? ORDER BY timestamp DESC',
            (student_id,)
        )
        return [dict(row) for row in rows]

    def get_stats(self, class_id: int, date: str = None) -> Dict:
        records = self.get_by_class(class_id, date) if date else self.get_by_class(class_id)
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
            with self.db.transaction() as cursor:
                cursor.execute('DELETE FROM lessons WHERE id = ?', (lesson_id,))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error deleting lesson: {e}")
            return False


class LessonAttendanceDB:
    """Database operations for lesson attendance."""

    def __init__(self, db: Database):
        self.db = db

    def record(self, lesson_id: int, student_id: int, image_path: str = None) -> Optional[Dict]:
        try:
            cursor = self.db.execute(
                '''INSERT OR IGNORE INTO lesson_attendance (lesson_id, student_id, image_path)
                   VALUES (?, ?, ?)''',
                (lesson_id, student_id, image_path)
            )
            if cursor.rowcount == 0:
                return None
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
        self.db = Database(db_path)
        self.classes = ClassDB(self.db)
        self.students = StudentDB(self.db)
        self.attendance = AttendanceDB(self.db)
        self.lessons = LessonDB(self.db)
        self.lesson_attendance = LessonAttendanceDB(self.db)

    def initialize_demo_data(self, data_dir: str):
        class_record = self.classes.create('Lớp Demo', 'Lớp mặc định cho demo')
        if not class_record:
            class_record = self.classes.get_by_id(1)

        if not class_record:
            logger.error("Failed to create/get demo class")
            return

        class_id = class_record['id']
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
            full_name = folder_name.replace('_', ' ')
            if not self.students.get_by_class_and_folder(class_id, folder_name):
                self.students.create(full_name, folder_name, class_id)

        logger.info(f"Initialized demo data with {len(student_folders)} students")

    def close(self):
        self.db.close()
