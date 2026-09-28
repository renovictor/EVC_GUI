# Smith Chart New Features

## Overview
The Smith Chart widget has been enhanced with two major new features:

1. **Hover Impedance Display** - Shows real-time impedance information when hovering over the chart
2. **Z-Parameter Contour Plotting** - Plots the impedance locus based on Z-parameters from the EVC device

## Feature 1: Hover Impedance Display

### Description
When you move your mouse over the Smith Chart, a tooltip appears showing:
- **Z (Impedance)**: Real and imaginary parts in ohms (R + jX format)
- **|Gamma| (Reflection Coefficient Magnitude)**: Normalized value (0 to 1)
- **Angle of Gamma**: Phase angle in degrees

### How It Works
- The custom `SmithChartView` class overrides the `mouseMoveEvent` to track mouse position
- Converts chart coordinates to impedance values using the inverse of the Smith Chart transformation
- Updates tooltip in real-time as the cursor moves

### Example Tooltip
```
Z = 75.34 + j-23.45 ohms
|Gamma| = 0.234, angle = -18.5 deg
```

## Feature 2: Z-Parameter Contour Plotting

### Description
Plots the impedance locus (contour) on the Smith Chart based on Z-parameters obtained from the EVC device at the **edge/boundary positions** of the capacitor tuning range.

### How to Use
1. Connect to an EVC device via COM port
2. In the Smith Chart tab, check the "Plot Contour" checkbox
3. The application will automatically query Z-parameters for the edge positions (4 boundary lines)
4. The contour will be displayed as an orange line on the Smith Chart

### Implementation Details

#### Z-Parameter Position Format
- **C1 Position**: Coarse (0-6) and Fine (0-63) components
  - 0% = (0, 0) → Minimum
  - 100% = (6, 63) → Maximum
- **C2 Position**: Same format as C1

#### Edge Lines Plotted
The contour consists of 4 boundary lines, each sampled at 51 points (0%, 2%, 4%, ..., 100%):

1. **Line 1**: C1=0% (fixed at 0,0), C2 varies 0%→100%
2. **Line 2**: C1 varies 0%→100%, C2=100% (fixed at 6,63)
3. **Line 3**: C1=100% (fixed at 6,63), C2 varies 0%→100%
4. **Line 4**: C1 varies 0%→100%, C2=0% (fixed at 0,0)

#### Position Mapping
For each percentage (0%, 2%, 4%, ..., 100%):
- **Coarse position** = round(percentage × 6 / 100) → 0-6
- **Fine position** = round(percentage × 63 / 100) → 0-63

Example: 50% → coarse=3, fine=31

#### Z-Parameter Query
- Queries the device using: `zpar show f1 [c1_coarse] [c1_fine] [c2_coarse] [c2_fine]`
- Samples f1 band (fixed frequency point)
- For each line: 51 sample points (0%, 2%, 4%, ..., 100%)
- Total queries: 4 lines × 51 points = 204 queries

#### Impedance Calculation
Uses the formula:
```
Z_L = -(Z12 * Z21) / (Z0 - Z11) - Z22
where Z0 = 50 ohms
```

- Z11, Z21, Z12, Z22: Complex S-parameters from device response
- Result is converted to reflection coefficient (gamma) for Smith Chart display

#### Response Parsing
Parses the Z-parameter response in format:
```
(C1: x, f1) (C2: x, f2)   Z11 = (r, i)  Z21 = (r, i)  Z12 = (r, i)  Z22 = (r, i)
```

### Contour Display
- Orange line (RGB: 255, 136, 0) with width of 2
- Rendered on top of the Smith Chart grid
- Only points with |Gamma| <= 1.0 are plotted (on the Smith Chart boundary)

## Technical Implementation

### Files Modified

#### `evc_gui/ui/smith_chart.py`
- Added `ZParameters` dataclass to hold Z-parameter values
- Added `calculate_load_impedance_from_z_params()` function
- Added `SmithChartView` custom class for hover tooltip support
- Added "Plot Contour" checkbox to the UI
- Added `plot_z_parameter_contour()` method to display contours
- Added `_clear_contour()` method to remove contours

#### `evc_gui/ui/main_window.py`
- Imported `ZParameters` from smith_chart module
- Connected contour checkbox `toggled` signal to `_on_contour_toggled()` handler
- Added `_on_contour_toggled()` method to handle contour checkbox state changes
- Added `_load_and_plot_contour()` method to query device and plot contours
- Added `_parse_zpar_response()` static method to parse Z-parameter responses

### New Signals/Slots
- `SmithChartWidget.contour_requested` - Signal for requesting contour data
- `MainWindow._on_contour_toggled()` - Handles contour checkbox toggle

## Error Handling
- If Z-parameter query fails, error message is logged
- Invalid/missing Z-parameters are skipped (not plotted)
- If no valid Z-parameters are found, contour checkbox is unchecked
- Contour plotting is disabled in demo mode
- Contour plotting requires active device connection

## Performance Considerations

- Z-parameter queries are done sequentially (not parallel)
- Total of 44 queries for contour (4 boundary lines × 11 sample points)
- Each query has a 3-second timeout
- Total expected contour load time: ~2-3 minutes

## Future Enhancements
- Parallel Z-parameter queries for faster loading
- Adaptive sampling based on contour shape
- Caching of previously loaded contours
- Export contour data to file
- Interactive contour adjustment
