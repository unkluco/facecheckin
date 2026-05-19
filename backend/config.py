"""
Configuration file for FaceCheckin backend server.
Fully isolated: all paths are inside final/backend/
"""

import os
import sys

def _is_frozen():
    return bool(getattr(sys, 'frozen', False))

if _is_frozen():
    # PyInstaller onedir:
    # - sys.executable lives in the installed app folder.
    # - sys._MEIPASS contains bundled code/assets.
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
    BUNDLE_DIR = getattr(sys, '_MEIPASS', APP_DIR)
    BASE_DIR = os.path.join(BUNDLE_DIR, 'backend')
    RUNTIME_DIR = APP_DIR
else:
    # Directory of this file = final/backend/
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    RUNTIME_DIR = BASE_DIR

# Bundled/static code paths
MODEL_DIR = BASE_DIR
STATIC_DIR = os.path.join(BASE_DIR, 'static')

# User runtime data. In packaged exe builds this is intentionally next to the exe.
DATA_DIR = os.path.join(RUNTIME_DIR, 'data')

# Database and file storage
DB_PATH = os.path.join(RUNTIME_DIR, 'attendance.db')
RECEIVED_DIR = os.path.join(RUNTIME_DIR, 'received')
PROCESSED_DIR = os.path.join(RUNTIME_DIR, 'processed')
CACHE_DIR = os.path.join(RUNTIME_DIR, 'cache')
INSIGHTFACE_ROOT = os.path.join(BUNDLE_DIR if _is_frozen() else RUNTIME_DIR, 'models', 'insightface')
RECOGNITION_SETTINGS_PATH = os.path.join(RUNTIME_DIR, 'recognition_settings.json')

# Server settings
PORT = int(os.environ.get('FACECHECKIN_PORT', '8080'))
HOST = os.environ.get('FACECHECKIN_HOST', '0.0.0.0')
AUTH_TOKEN = os.environ.get('FACECHECKIN_TOKEN', '')
CORS_ORIGINS = [o.strip() for o in os.environ.get('FACECHECKIN_CORS_ORIGINS', '').split(',') if o.strip()]

# Face detection settings
FACE_DETECTION_THRESHOLD = 0.35
FACE_MIN_CONFIDENCE      = 0.9
FACE_EXPAND_PERCENTAGE   = 15

# Create directories if they don't exist
for dir_path in [DATA_DIR, RECEIVED_DIR, PROCESSED_DIR, CACHE_DIR]:
    os.makedirs(dir_path, exist_ok=True)
