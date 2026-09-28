# EVC GUI Release Checklist v26.0.2

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
- [ ] Start/Connect auto-recovers from wrong baud by scanning and validating `ver` content.
- [ ] Chronos product label resolves correctly (`Chronos 1` vs `Chronos 2.0`) from SN prefix.
- [ ] Chronos contour range rule applies correctly (`0..12/0..12` vs Tykon-style range).
- [ ] Quantum `pdat1`/`psum1` parsing works for combined HF/LF lines.
- [ ] Quantum Power Scope toggles between HF and LF and updates chart/current values correctly.
- [ ] Quantum Smith Chart shows HF (red) and LF (blue) impedance points on the same chart.
- [ ] Quantum contour downloads both `hf` and `lf` zpar bands and overlays both contours.
- [ ] Troubleshoot tab Diagnostic flow reads `stat` and lists active faults in the text box.
- [ ] Demo mode and contour guardrails remain correct.

## 4. Git commit and tag
- [ ] `git status` is reviewed.
- [ ] `git diff --check` passes.
- [ ] Commit: `git add . && git commit -m "Release EVC GUI v26.0.2"`
- [ ] Annotated tag: `git tag -a v26.0.2 -m "EVC GUI v26.0.2"`
- [ ] Confirm tag points to intended commit: `git show v26.0.2`.

## 5. Push
- [ ] `git push origin <release-branch>`
- [ ] `git push origin v26.0.2`
- [ ] Confirm remote commit and tag are visible.

## 6. Create single EXE
- [ ] Run `.\build_exe.ps1`.
- [ ] EXE filename is exactly `EVC_GUI_v26.0.2.exe`.
- [ ] Record SHA-256: `Get-FileHash .\dist\EVC_GUI_v26.0.2.exe -Algorithm SHA256`.

## 7. Post-release verification
- [ ] Confirm version is displayed consistently in GUI and documentation.
- [ ] Archive validation evidence and rollback artifact according to team process.
