# EVC GUI Release Checklist v26.0.10

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
- [ ] Main window opens and splash closes after loading/minimum duration.
- [ ] Title bar and taskbar show the approved icon.

## 3. Feature validation
- [ ] Auto-scan identifies available EVC units and Start/Connect reaches IDLE on Tykon and Quantum.
- [ ] Triton baud normalization (to 57600 for identity) succeeds even when the device re-enumerates to a different COM port.
- [ ] High-speed switch (`baud 7`) survives COM-number changes; when unsupported/unverified it cleanly falls back to verified 57600.
- [ ] Activity log shows COM re-enumeration trace (`Detected COM re-enumeration: COMx -> COMy`) when port migration occurs.
- [ ] USB state field displays the actual active COM port and baud after reconnect.
- [ ] Scope popup chart window can be closed and reopened repeatedly without getting stuck.

## 4. Git commit and tag
- [ ] `git status` is reviewed.
- [ ] `git diff --check` passes.
- [ ] Commit: `git add . && git commit -m "Release EVC GUI v26.0.10"`
- [ ] Annotated tag: `git tag -a v26.0.10 -m "EVC GUI v26.0.10"`
- [ ] Confirm tag points to intended commit: `git show v26.0.10`.

## 5. Push
- [ ] `git push origin <release-branch>`
- [ ] `git push origin v26.0.10`
- [ ] Confirm remote commit and tag are visible.

## 6. Create single EXE
- [ ] Run `.\build_exe.ps1`.
- [ ] EXE filename is exactly `EVC_GUI_v26.0.10.exe`.
- [ ] Record SHA-256: `Get-FileHash .\dist\EVC_GUI_v26.0.10.exe -Algorithm SHA256`.

## 7. Post-release verification
- [ ] Confirm version is displayed consistently in GUI and documentation.
- [ ] Archive validation evidence and rollback artifact according to team process.
