# FaceCheckin Agent Instructions

## Packaging / Installer Work

When the task involves building, modifying, validating, troubleshooting, or explaining the Windows EXE/MSI installer, use the repo skill at:

`C:\Users\ADMIN\Desktop\ff\final\facecheckin\.agents\skills\installer-packaging\SKILL.md`

This includes work related to:

- PyInstaller `deploy/FaceCheckin.spec`
- WiX/MSI script `deploy/build_msi.ps1`
- hidden-console desktop launcher `backend/tray_launcher.py`
- system tray behavior
- bundled InsightFace models
- runtime data beside the installed exe
- installer upgrades, uninstall behavior, versioning, release notes, and distribution to other PCs

Default packaging decisions for this repo:

- Use PyInstaller `onedir`, not `onefile`, unless the user explicitly changes this.
- Keep server port `8080`.
- Hide the terminal in packaged builds.
- Provide a System Tray icon with a way to stop the server.
- Bundle the InsightFace model files for offline use.
- Start with an empty runtime database for release builds.
- Store runtime data beside the installed exe; prefer per-user install locations so the app can write without admin rights.

Always call out installer risks clearly, especially:

- whether uninstall keeps or deletes user data;
- whether developer data may accidentally be bundled;
- SmartScreen/Defender warnings from unsigned binaries;
- port conflicts on `8080`;
- camera/firewall/browser permission issues;
- privacy risks around face images and attendance data;
- upgrade compatibility for database schema/cache changes.
