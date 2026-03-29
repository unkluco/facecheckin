#!/usr/bin/env python3
"""
FaceCheckin Server Startup Script.
Entry point for starting the backend server.
"""

import sys
import os

# Add parent directories to path to allow imports
backend_dir = os.path.dirname(os.path.abspath(__file__))
facecheckin_dir = os.path.dirname(os.path.dirname(backend_dir))

sys.path.insert(0, backend_dir)
sys.path.insert(0, facecheckin_dir)

from server import AttendanceServer

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 FaceCheckin Server Startup")
    print("=" * 60)

    server = AttendanceServer()

    try:
        server.start()
        print("\n⏳ Server is running. Press Ctrl+C to stop.\n")
        input()
    except KeyboardInterrupt:
        print("\n\n⏸️  Shutting down...")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
    finally:
        server.stop()

    print("\n" + "=" * 60)
    print("✅ Server stopped")
    print("=" * 60)
