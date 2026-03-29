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
PORT = 8080
HOST = '0.0.0.0'

# Face detection settings
FACE_DETECTION_THRESHOLD = 0.4
FACE_MIN_CONFIDENCE      = 0.85
FACE_EXPAND_PERCENTAGE   = 15

# Create directories if they don't exist
for dir_path in [DATA_DIR, RECEIVED_DIR, PROCESSED_DIR, STATIC_DIR]:
    os.makedirs(dir_path, exist_ok=True)
