# EVC GUI Release Checklist v1.0.2

## 1. Pre-check
- [ ] Confirm `version.py`, README, checklist, window title, and EXE name use the same version.
- [ ] Confirm approved `ASM-logo-small.gif` and `smithchart.ico` are present.
- [ ] Confirm clean virtual environment and `pip install -r requirements.txt` succeeds.
- [ ] Run `python -m compileall .`.
- [ ] Confirm no credentials, COM captures, customer data, tlogs, or generated logs are staged.
- [ ] Confirm target Windows PC and EVC connection are authorized for testing.

## 2. Quick run validation
- [ ] Run `python main.py`.
- [ ] Splash appears immediately, is borderless, centered, topmost, and remains for at least 5 seconds.
- [ ] Logo, app name, version, department, company, author, and contact render correctly.
- [ ] Progress and module status update without freezing the UI.
- [ ] Main window opens and splash closes after loading/minimum duration.
- [ ] Title bar and taskbar show the approved icon.
- [ ] Closing the app creates no unhandled exception.

## 3. Feature validation
- [ ] Product list contains Quantum, Tykon, Triton, and Chronos.
- [ ] COM refresh lists available ports.
- [ ] Start/Connect reports success and failure clearly.
- [ ] Probe does not freeze the GUI and logs the result.
- [ ] State transitions follow declared transition rules.
- [ ] Invalid transitions are rejected and logged.
- [ ] Run and Abort return controls to a safe state.
- [ ] Serial port closes during cleanup.
- [ ] `logs/evc_gui.log` rotates and `python_fault.log` is writable.
- [ ] Power Scope updates chart and current values in real mode.
- [ ] Demo Mode generates synthetic data and updates chart/current values.

## 4. Git commit and tag
- [ ] `git status` is reviewed.
- [ ] `git diff --check` passes.
- [ ] Commit: `git add . && git commit -m "Release EVC GUI v1.0.2"`
- [ ] Annotated tag: `git tag -a v1.0.2 -m "EVC GUI v1.0.2"`
- [ ] Confirm tag points to the intended commit: `git show v1.0.2`.

## 5. Push
- [ ] `git push origin <release-branch>`
- [ ] `git push origin v1.0.2`
- [ ] Confirm remote commit and tag are visible.

## 6. Create single EXE
- [ ] Delete old `build/`, `dist/`, and `.spec` after preserving required records.
- [ ] Run the documented PyInstaller command.
- [ ] EXE filename is exactly `EVC_GUI_v1.0.2.exe`.
- [ ] EXE properties, File Explorer, title bar, and taskbar show the assigned icon.
- [ ] Launch on a clean Windows validation PC without Python installed.
- [ ] Confirm corporate endpoint/security scanning completes according to local process.
- [ ] Record SHA-256: `Get-FileHash .\dist\EVC_GUI_v1.0.2.exe -Algorithm SHA256`.

## 7. Post-release verification
- [ ] Download/copy the released artifact from the approved release location.
- [ ] Recalculate SHA-256 and compare with the recorded value.
- [ ] Repeat splash, launch, COM failure, approved COM success, probe, run, abort, and exit tests.
- [ ] Confirm logs are created in the expected writable folder and contain version/startup/state details.
- [ ] Confirm version is displayed consistently in GUI and documentation.
- [ ] Record known limitations: Phase 3 Smith Chart is not yet implemented.
- [ ] Archive verification evidence and rollback artifact according to team process.
