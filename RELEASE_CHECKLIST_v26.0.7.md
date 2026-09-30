# EVC GUI Release Checklist v26.0.7

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
- [ ] Log1 (`pdat1 + psum1`) runs and benchmark reports expected baseline.
- [ ] Log2 (`tlog 1`) runs and benchmark output is stable.
- [ ] Log3 (`tlog rt`) runs on supported families and delivers high-rate data.
- [ ] Chronos family fallback from Log3 to Log2 occurs cleanly with user-visible message.
- [ ] Raw log filename uses detected product format (`<SN><Product>_GUI_...`), not hardcoded Tykon.
- [ ] Log mode button tooltips display correct descriptions.

## 4. Git commit and tag
- [ ] `git status` is reviewed.
- [ ] `git diff --check` passes.
- [ ] Commit: `git add . && git commit -m "Release EVC GUI v26.0.7"`
- [ ] Annotated tag: `git tag -a v26.0.7 -m "EVC GUI v26.0.7"`
- [ ] Confirm tag points to intended commit: `git show v26.0.7`.

## 5. Push
- [ ] `git push origin <release-branch>`
- [ ] `git push origin v26.0.7`
- [ ] Confirm remote commit and tag are visible.

## 6. Create single EXE
- [ ] Run `.\build_exe.ps1`.
- [ ] EXE filename is exactly `EVC_GUI_v26.0.7.exe`.
- [ ] Record SHA-256: `Get-FileHash .\dist\EVC_GUI_v26.0.7.exe -Algorithm SHA256`.

## 7. Post-release verification
- [ ] Confirm version is displayed consistently in GUI and documentation.
- [ ] Archive validation evidence and rollback artifact according to team process.
