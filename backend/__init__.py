"""
FaceCheckin Backend Package.
Complete backend for face attendance system.
"""

from .database import DatabaseManager
from .face_engine import FaceEngine
from .server import AttendanceServer

__version__ = '1.0.0'
__all__ = ['DatabaseManager', 'FaceEngine', 'AttendanceServer']
