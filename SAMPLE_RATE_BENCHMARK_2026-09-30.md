# Sample Rate Benchmark (2026-09-30)

## Scope
- Build line: v26.0.6 development state with Log1 / Log2 / Log3 modes.
- Measurement method: in-app 10-loop rolling benchmark (`Sample rate (10-loop)`).

## Measured Results

| Mode | Acquisition Path | Measured Rate (Hz) | Loop Time (ms) |
| --- | --- | ---: | ---: |
| Log1 | `pdat1 + psum1` | 3.18 | 314.5 |
| Log2 | `tlog 1` | 2.21 | 452.5 |
| Log3 | `tlog rt` | 68.39 | 14.6 |

Loop time conversion: `ms = 1000 / Hz`.

## Key Findings
- **Log3 (`tlog rt`) is the clear high-speed path** and already exceeds the 50 ms target by a wide margin.
- **Log1** provides legacy compatibility but is much slower than streaming mode.
- **Log2** (single-command polling) is slower than Log1 in current implementation and needs further optimization/tuning if kept as a primary mode.

## Step 6.5 Device Compatibility Capture

| Device Family | `tlog 1` | `tlog rt` | Notes |
| --- | --- | --- | --- |
| Quantum | Supported | Supported | `tlog` payload is HF/LF paired lines per timestamp (`HF PS1` + `LF PS1`). |
| Triton | Supported | Supported | Wider column set than Tykon; includes additional PA/fan/current mask fields. |
| Chronos 2.0 | Supported | Not supported | `tlog rt` unavailable on unit sample. |
| Chronos 1 | Supported | Not supported | `tlog rt` unavailable on unit sample. |

## Next Focus
1. Keep Log1 as compatibility baseline.
2. Prioritize Log3 stability + data quality validation across device families.
3. Revisit Log2 only if a non-streaming intermediate mode is still required.
