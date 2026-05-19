# Installer Release Risk Checklist

Use this checklist before handing a FaceCheckin installer to another machine/user.

## User Data

- Confirm whether uninstall should keep or delete generated data.
- Back up `attendance.db`, `data`, and `cache` before testing upgrade/uninstall.
- Do not bundle the developer's real `attendance.db` unless explicitly requested.
- Treat face images and attendance records as sensitive data.

## Runtime Paths

- Confirm frozen builds write to the installed exe folder, not the source repo or PyInstaller temp folder.
- Confirm static UI is bundled read-only and runtime data is separate.
- Avoid `Program Files` for writable runtime data unless the app writes to `%ProgramData%` or `%LOCALAPPDATA%`.

## Recognition Model

- Confirm `det_10g.onnx` and `w600k_r50.onnx` are present.
- Confirm recognition works offline.
- Confirm the installer size is acceptable.
- Check model/license obligations before public distribution.

## Windows Behavior

- Test on Windows 10/11 64-bit without Python installed.
- Expect SmartScreen/Defender warnings until code signing is added.
- Verify camera permission in the browser.
- Verify firewall behavior if LAN/mobile access is used.
- Verify fixed port `8080` is free or document the conflict behavior.

## App Lifecycle

- Confirm auto-open browser works.
- Confirm System Tray icon appears and can stop the server.
- Confirm no terminal window remains visible in normal mode.
- Keep a debug mode or source-mode command available for diagnosing startup failures.

## MSI Lifecycle

- Increment MSI `Version` for each release.
- Verify the app appears in Windows Settings → Apps.
- Test install, repair, upgrade, and uninstall.
- Document whether uninstall preserves user-generated files.
