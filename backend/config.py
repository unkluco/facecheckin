"""
Configuration file for FaceCheckin backend server.
Fully isolated: all paths are inside final/backend/
"""

import os

# Directory of this file = final/backend/
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Fully isolated paths — no dependency on parent folders
MODEL_DIR = BASE_DIR          # image_object.py, utils.py are here
DATA_DIR  = os.path.join(BASE_DIR, 'data')   # face photo database (MSSV/img_XXXX.jpg)

# Database and file storage
DB_PATH      = os.path.join(BASE_DIR, 'attendance.db')
RECEIVED_DIR = os.path.join(BASE_DIR, 'received')
PROCESSED_DIR= os.path.join(BASE_DIR, 'processed')
STATIC_DIR   = os.path.join(BASE_DIR, 'static')

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
for dir_path in [DATA_DIR, RECEIVED_DIR, PROCESSED_DIR, STATIC_DIR]:
    os.makedirs(dir_path, exist_ok=True)
