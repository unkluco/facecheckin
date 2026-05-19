"""
Desktop/tray launcher for packaged FaceCheckin builds.

Runs the aiohttp server without a console window, opens the browser, and exposes
a small System Tray menu so users can open the dashboard or stop the server.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser


backend_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(backend_dir)
sys.path.insert(0, backend_dir)
sys.path.insert(0, project_dir)

from config import PORT
from server import AttendanceServer


def _make_icon_image():
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (64, 64), (24, 23, 21, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((7, 7, 57, 57), radius=14, fill=(204, 120, 92, 255))
    draw.ellipse((20, 14, 44, 38), fill=(250, 249, 245, 255))
    draw.rounded_rectangle((16, 39, 48, 53), radius=8, fill=(250, 249, 245, 255))
    return image


def main() -> int:
    import pystray
    from pystray import MenuItem as Item

    server = AttendanceServer(port=PORT)
    server.start()
    url = f"http://localhost:{PORT}"

    def open_dashboard(_icon=None, _item=None):
        webbrowser.open(url)

    def stop_app(icon=None, _item=None):
        server.stop()
        if icon:
            icon.stop()

    def delayed_open():
        time.sleep(1.2)
        open_dashboard()

    threading.Thread(target=delayed_open, daemon=True).start()

    icon = pystray.Icon(
        "FaceCheckin",
        _make_icon_image(),
        "FaceCheckin đang chạy",
        menu=pystray.Menu(
            Item("Mở FaceCheckin", open_dashboard),
            Item("Tắt server", stop_app),
        ),
    )
    icon.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
