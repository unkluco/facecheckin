---
name: installer-packaging
description: Create, update, validate, troubleshoot, and release Windows EXE/MSI installers for FaceCheckin or similar Python/web-localhost desktop apps. Use when packaging with PyInstaller, WiX/MSI, system tray launchers, bundled AI models, runtime data beside the exe, hidden terminals, auto-open browser behavior, installer upgrades/uninstalls, distribution to other PCs, Windows Defender/SmartScreen warnings, or release-risk review.
---

# Installer Packaging

## Goal

Package the app so a non-developer can install and run it without installing Python, Python libraries, model files, or developer tools.

For this repo, the preferred shape is:

- PyInstaller `onedir`, not `onefile`.
- Hidden console app with a System Tray icon.
- Local server on fixed port `8080`.
- Browser opens automatically to `http://localhost:8080`.
- Runtime data lives beside the installed exe.
- InsightFace model files are bundled.
- MSI is generated from the PyInstaller output with WiX.

## Default Workflow

1. Inspect current packaging files before editing:
   - `deploy/FaceCheckin.spec`
   - `deploy/build_msi.ps1`
   - `backend/tray_launcher.py`
   - `backend/config.py`
   - `backend/face_engine.py`
   - `backend/requirements.txt`
2. Verify runtime paths:
   - Source mode may use `backend/`.
   - Frozen mode must use the exe folder for `attendance.db`, `data`, `cache`, `received`, `processed`, `models`.
   - Static bundled UI should come from the PyInstaller bundle, not user-writable runtime data.
3. Build PyInstaller first. Run PyInstaller from inside `deploy/`; otherwise PyInstaller may place output in repo-root `dist/`/`build/` instead of `deploy/dist`/`deploy/build`:
   ```powershell
   cd C:\Users\ADMIN\Desktop\ff\final\facecheckin
   Push-Location deploy
   ..\.venv\Scripts\pyinstaller.exe --noconfirm FaceCheckin.spec
   Pop-Location
   ```
4. Smoke-test the exe before building MSI:
   - Run `deploy/dist/FaceCheckin/FaceCheckin.exe`.
   - Confirm server binds `localhost:8080`.
   - Confirm browser opens.
   - Confirm System Tray menu can open dashboard and stop server.
   - Confirm runtime folders/files appear beside the exe after first run.
5. Clean runtime files created by smoke tests before building MSI, or the installer may accidentally ship a non-empty database/cache:
   ```powershell
   $dist = "deploy\dist\FaceCheckin"
   "attendance.db","attendance.db-wal","attendance.db-shm","data","cache","received","processed","models" |
     ForEach-Object { $p = Join-Path $dist $_; if (Test-Path $p) { Remove-Item $p -Recurse -Force } }
   ```
6. Build MSI:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\deploy\build_msi.ps1 -Version 0.1.1
   ```
7. Smoke-test MSI on a clean or throwaway Windows user profile before calling it releasable.

## FaceCheckin Packaging Contract

Respect these decisions unless the user explicitly changes them:

- Use `--onedir`: AI/CV dependencies and ONNX model files are large; `onefile` slows startup and creates extraction issues.
- Keep port `8080`: do not auto-switch ports unless requested.
- Hide terminal: packaged entrypoint should use `console=False` and `backend/tray_launcher.py`.
- Keep tray controls: users must be able to stop the server from the System Tray.
- Bundle model: include at least `buffalo_l/det_10g.onnx` and `buffalo_l/w600k_r50.onnx`.
- Start empty: do not bundle the developer database or existing student/class data as initial user data.
- Store runtime data beside installed exe: this is intentional for this project, but it has installer/uninstall implications.
- Prefer per-user install location if writing beside exe: `LocalAppData` is safer than `Program Files` because it avoids admin-write problems.

## Validation Checklist

Run or verify all applicable checks:

- Python syntax:
  ```powershell
  python -m py_compile backend/config.py backend/face_engine.py backend/tray_launcher.py backend/server.py
  ```
- PyInstaller result exists:
  - `deploy/dist/FaceCheckin/FaceCheckin.exe`
  - `deploy/dist/FaceCheckin/_internal`
  - `deploy/dist/FaceCheckin/_internal/models/insightface/buffalo_l/det_10g.onnx`
  - `deploy/dist/FaceCheckin/_internal/models/insightface/buffalo_l/w600k_r50.onnx`
- Runtime data is created beside exe after first run:
  - `attendance.db`
  - `data`
  - `cache`
- `received`
- `processed`
- Runtime data is absent from `deploy/dist/FaceCheckin` immediately before MSI build unless the user explicitly wants seed data.
- Server responds at port `8080`.
- UI loads static files.
- Camera permissions work in browser on `localhost`.
- Recognition can load model without internet.
- Tray stop shuts down the server cleanly.
- MSI appears in Windows Settings → Apps → Installed apps.
- Uninstall behavior matches the user-facing promise.

Use `scripts/inspect_package.ps1` for a quick local package report.

## Build Commands

Use these commands from the repo root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt pyinstaller
Push-Location deploy
..\.venv\Scripts\pyinstaller.exe --noconfirm FaceCheckin.spec
Pop-Location
powershell -ExecutionPolicy Bypass -File .\deploy\build_msi.ps1 -Version 0.1.1
```

Do not use `.\.venv\Scripts\pyinstaller.exe --noconfirm .\deploy\FaceCheckin.spec` from the repo root unless the spec explicitly sets `distpath` and `workpath`; it can create/update root-level `dist/` and `build/`.

If WiX is installed but `candle.exe`/`light.exe` are not on `PATH`, update `deploy/build_msi.ps1` to find common WiX install paths before telling the user to reinstall.

## Troubleshooting

- `candle.exe/light.exe not found`: detect `C:\Program Files (x86)\WiX Toolset v3.14\bin` and `v3.11\bin`; WiX v4/v5 uses a different CLI and may need a different script.
- PyInstaller missing imports: add explicit `hiddenimports` in `deploy/FaceCheckin.spec`.
- PyInstaller output appears in repo root: rerun from `deploy/` and remove root `dist/`/`build/` if they are accidental outputs.
- MSI unexpectedly contains `attendance.db` or runtime folders: clean `deploy/dist/FaceCheckin` after smoke tests and rebuild MSI.
- Bundled model check fails: in PyInstaller onedir, data files normally live under `_internal`; verify `_internal/models/insightface/buffalo_l`, not only root `models`.
- Model downloads on user machine: bundled model path or `FACECHECKIN_INSIGHTFACE_ROOT` handling is wrong.
- Browser opens but API fails: check fixed port conflict, auth token, and server startup logs.
- No tray icon: check `pystray`, `Pillow`, `console=False`, and Windows notification overflow area.
- Uninstall leaves files: this is normal for runtime-generated user data unless MSI explicitly removes them.
- Huge installer: inspect unnecessary packages in `_internal`; avoid bundling dev/test/docs if safe.
- False positive antivirus: unsigned PyInstaller apps can trigger warnings; signing is required for serious distribution.

## Risk Review

Always mention meaningful risks when preparing a build:

- Data loss: uninstall or upgrades may remove, preserve, or orphan user data depending on MSI rules.
- Data privacy: face images and attendance DB are sensitive biometric/education records.
- Security: local server listens on `0.0.0.0` by default in source config; verify exposure is intended before release.
- Port conflicts: fixed `8080` can fail if another app already uses it.
- Camera permissions: browser may block camera except on `localhost`/HTTPS.
- Firewall: Windows may prompt if LAN/mobile access is used.
- Model licensing and size: bundled ONNX model files increase installer size and may have license obligations.
- CPU/RAM: recognition can be slow on weak machines.
- GPU/CUDA: do not assume CUDA; default CPU provider is safer.
- SmartScreen/Defender: unsigned installers/exes can scare users.
- Upgrade compatibility: schema migrations and cached embeddings must tolerate old data.
- Installer scope: per-user install is safer for runtime writes but only installs for that Windows user.
- Logs/debugging: hidden terminal improves UX but makes failures harder to diagnose; provide a debug run path when needed.

## Release Notes Template

When delivering a build, report:

- EXE path and MSI path.
- Version.
- Install scope and install location.
- Data location.
- Whether model is bundled.
- Whether initial database is empty.
- Known warnings from build tools.
- What was smoke-tested.
- What still needs testing on another clean machine.
