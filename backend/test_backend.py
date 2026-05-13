#!/usr/bin/env python3
"""
Test script for FaceCheckin backend.
Validates all modules and database functionality.
"""

import sys
import os
import sqlite3
import tempfile
from pathlib import Path

# Add backend to path
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, backend_dir)

from config import DB_PATH, DATA_DIR, MODEL_DIR, RECEIVED_DIR, PROCESSED_DIR
from database import DatabaseManager
# Note: FaceEngine imported only when needed due to DeepFace dependencies


def test_imports():
    """Test all imports."""
    print("=" * 60)
    print("Testing Imports...")
    print("=" * 60)

    try:
        from config import (
            BASE_DIR, MODEL_DIR, DATA_DIR, DB_PATH, RECEIVED_DIR, PROCESSED_DIR,
            STATIC_DIR, PORT, HOST
        )
        print("✅ config.py - OK")
    except Exception as e:
        print(f"❌ config.py - FAILED: {e}")
        return False

    try:
        from database import DatabaseManager
        print("✅ database.py - OK")
    except Exception as e:
        print(f"❌ database.py - FAILED: {e}")
        return False

    try:
        from face_engine import FaceEngine
        print("✅ face_engine.py - OK")
    except Exception as e:
        print(f"⚠️  face_engine.py - WARNING: {e}")
        print("    (DeepFace may not be installed - this is OK for testing)")

    try:
        from server import AttendanceServer
        print("✅ server.py - OK")
    except Exception as e:
        print(f"❌ server.py - FAILED: {e}")
        return False

    return True


def test_paths():
    """Test all required paths."""
    print("\n" + "=" * 60)
    print("Testing Paths...")
    print("=" * 60)

    paths = {
        'Model': MODEL_DIR,
        'Data': DATA_DIR,
        'Received': RECEIVED_DIR,
        'Processed': PROCESSED_DIR,
    }

    all_ok = True
    for name, path in paths.items():
        if os.path.exists(path):
            print(f"✅ {name}: {path}")
        else:
            print(f"❌ {name}: NOT FOUND - {path}")
            all_ok = False

    return all_ok


def test_data_dir():
    """Check student folders in Data directory."""
    print("\n" + "=" * 60)
    print("Testing Data Directory...")
    print("=" * 60)

    if not os.path.exists(DATA_DIR):
        print(f"❌ Data directory not found: {DATA_DIR}")
        return False

    folders = [d for d in Path(DATA_DIR).iterdir() if d.is_dir()]
    print(f"✅ Found {len(folders)} student folders:")

    for folder in sorted(folders):
        images = list(folder.glob('*.jpg'))
        print(f"   - {folder.name}: {len(images)} images")

    return len(folders) > 0


def test_database():
    """Test database operations."""
    print("\n" + "=" * 60)
    print("Testing Database...")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        test_db_path = os.path.join(tmpdir, 'attendance_test.db')
        test_data_dir = os.path.join(tmpdir, 'data')
        os.makedirs(os.path.join(test_data_dir, 'Demo_Student'), exist_ok=True)
        print(f"✅ Using isolated test database: {test_db_path}")

        db_manager = DatabaseManager(test_db_path)

        print("\nTesting Classes...")
        cls1 = db_manager.classes.create('Test Class 1', 'First test class')
        print(f"✅ Created class: {cls1['name']} (id={cls1['id']})")

        all_classes = db_manager.classes.get_all()
        print(f"✅ Got all classes: {len(all_classes)} total")

        cls_by_id = db_manager.classes.get_by_id(cls1['id'])
        print(f"✅ Got class by ID: {cls_by_id['name']}")

        print("\nTesting Students...")
        student1 = db_manager.students.create('John Doe', 'John_Doe', cls1['id'])
        print(f"✅ Created student: {student1['full_name']} (id={student1['id']})")

        student2 = db_manager.students.create('Jane Smith', 'Jane_Smith', cls1['id'])
        print(f"✅ Created student: {student2['full_name']} (id={student2['id']})")

        cls2 = db_manager.classes.create('Test Class 2', 'Second test class')
        same_folder_other_class = db_manager.students.create('Other John', 'John_Doe', cls2['id'])
        duplicate_same_class = db_manager.students.create('Duplicate John', 'John_Doe', cls1['id'])
        assert same_folder_other_class is not None
        assert duplicate_same_class is None
        print("✅ folder_name unique per class, not globally")

        class_students = db_manager.students.get_by_class(cls1['id'])
        print(f"✅ Got students in class: {len(class_students)} total")

        print("\nTesting Attendance...")
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')

        record1 = db_manager.attendance.record_attendance(student1['id'], cls1['id'], today, confidence=0.95)
        print(f"✅ Recorded attendance for {student1['full_name']} (record_id={record1['id']})")

        record2 = db_manager.attendance.record_attendance(student2['id'], cls1['id'], today, confidence=0.92)
        print(f"✅ Recorded attendance for {student2['full_name']} (record_id={record2['id']})")

        lesson = db_manager.lessons.create(cls1['id'], 'Test Lesson', today)
        db_manager.lesson_attendance.record(lesson['id'], student1['id'])

        today_records = db_manager.attendance.get_by_class(cls1['id'], today)
        print(f"✅ Got today's attendance: {len(today_records)} records")

        stats = db_manager.attendance.get_stats(cls1['id'], today)
        print(f"✅ Statistics: {stats['total_students']} total, {stats['present']} present, {stats['absent']} absent")

        assert db_manager.students.delete(student1['id'])
        conn = db_manager.db._conn
        assert conn.execute('SELECT COUNT(*) FROM lesson_attendance WHERE student_id=?', (student1['id'],)).fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM attendance_records WHERE student_id=?', (student1['id'],)).fetchone()[0] == 0
        print("✅ Student delete cascades attendance rows")

        assert db_manager.classes.delete(cls1['id'])
        assert conn.execute('SELECT COUNT(*) FROM students WHERE class_id=?', (cls1['id'],)).fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM lessons WHERE class_id=?', (cls1['id'],)).fetchone()[0] == 0
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
        print("✅ Class delete cascades related rows")

        print("\nInitializing Demo Data...")
        db_manager.initialize_demo_data(test_data_dir)
        demo_classes = db_manager.classes.get_all()
        demo_students = db_manager.students.get_all()
        print(f"✅ Demo data initialized: {len(demo_classes)} classes, {len(demo_students)} students")

        db_manager.close()

    return True


def test_face_engine():
    """Test face engine initialization."""
    print("\n" + "=" * 60)
    print("Testing Face Engine...")
    print("=" * 60)

    try:
        from face_engine import FaceEngine
        engine = FaceEngine(DATA_DIR, threshold=0.4)
        print(f"✅ FaceEngine initialized")

        db_info = engine.get_db_info()
        if 'error' not in db_info:
            print(f"✅ Database has {db_info['num_people']} people")
            for person in db_info['people'][:3]:
                print(f"   - {person['name']}: {person['num_images']} images")
        else:
            print(f"⚠️  {db_info['error']}")

        return True
    except ImportError as e:
        print(f"⚠️  FaceEngine skipped: {e}")
        print("    (DeepFace dependencies not installed)")
        return True  # Skip is OK
    except Exception as e:
        print(f"❌ FaceEngine initialization failed: {e}")
        return False


def test_syntax():
    """Test Python syntax of all files."""
    print("\n" + "=" * 60)
    print("Testing Python Syntax...")
    print("=" * 60)

    files = [
        'config.py',
        'database.py',
        'face_engine.py',
        'server.py',
        'start.py',
        '__init__.py',
    ]

    import py_compile

    all_ok = True
    for filename in files:
        filepath = os.path.join(backend_dir, filename)
        try:
            py_compile.compile(filepath, doraise=True)
            print(f"✅ {filename}")
        except py_compile.PyCompileError as e:
            print(f"❌ {filename}: {e}")
            all_ok = False

    return all_ok


def main():
    """Run all tests."""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 15 + "FaceCheckin Backend Test Suite" + " " * 13 + "║")
    print("╚" + "=" * 58 + "╝")

    results = []

    # Run tests
    results.append(("Python Syntax", test_syntax()))
    results.append(("Imports", test_imports()))
    results.append(("Paths", test_paths()))
    results.append(("Data Directory", test_data_dir()))

    try:
        results.append(("Database", test_database()))
    except Exception as e:
        print(f"\n❌ Database test failed: {e}")
        results.append(("Database", False))

    results.append(("Face Engine", test_face_engine()))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name:.<40} {status}")

    passed = sum(1 for _, r in results if r)
    total = len(results)

    print("\n" + "=" * 60)
    if passed == total:
        print(f"✅ All {total} tests passed!")
        print("\n🚀 Backend is ready to run:")
        print(f"   python3 /sessions/festive-bold-newton/mnt/facecheckin/final/backend/start.py")
        return 0
    else:
        print(f"❌ {total - passed} out of {total} tests failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
