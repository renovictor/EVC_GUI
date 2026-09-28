# Auto-Detection COM Port Scanning Feature

## Overview

The EVC GUI has been enhanced with an intelligent auto-detection feature that automatically scans all available COM ports and detects connected EVC devices. When users click "Start / Connect", the application now:

1. **Automatically scans all available COM ports** in parallel for efficiency
2. **Detects device information** including:
   - Product name (Tykon, Quantum, Chronos, etc.)
   - Serial number
   - Firmware version
   - Optimal baud rate
3. **Displays a device selection dialog** showing all detected devices
4. **Intelligently handles multiple devices** - users can choose which device to connect to

## How It Works

### Auto-Detection Process

When you click **"Start / Connect"**:

1. **Port Scanning Phase**
   - All available COM ports are scanned in parallel (up to 8 concurrent connections)
   - Each port is tested at multiple baud rates: 57600, 230400, 19200, 38400, 115200, 9600
   - The scan completes quickly due to parallel processing (~1-2 seconds typical)

2. **Device Detection Phase**
   - For each successful connection, the app queries:
     - `ver` command to get product type and firmware
     - `sn` command to get serial number
   - Product names are resolved (e.g., Chronos variants based on serial number prefix)

3. **Device Selection Phase**
   - A dialog displays all detected devices with:
     - COM Port
     - Product name
     - Serial number
     - Firmware version
     - Detected baud rate
   - User selects which device to connect to (first device pre-selected)

4. **Connection Phase**
   - Selected device is connected using detected port and baud rate
   - Handshake is validated
   - Application transitions to ready state

### Device Detection

The auto-detection feature:
- **Does not require manual port selection** anymore
- **Automatically finds the correct baud rate** for each device
- **Resolves product variants** (e.g., Chronos 1 vs Chronos 2.0 based on serial number)
- **Is non-blocking** - scanning happens in a background thread
- **Provides feedback** via status messages in the activity log

## UI Changes

### Before Enhancement
- User had to manually select COM port
- User had to manually select baud rate
- User clicked "Start / Connect" to try to establish connection

### After Enhancement
- User clicks "Start / Connect"
- Scanning begins (progress indicator shows activity)
- Device selection dialog appears automatically
- User selects from detected devices
- Connection is established with auto-detected settings

## Error Handling

If no devices are detected:
- User is shown a warning message with possible reasons:
  - Device not connected
  - Device is not responding
  - Wrong baud rate (unlikely, as all rates are scanned)
- User can check the device and try again
- Manual port selection is still available if needed (via Refresh Ports button)

If multiple devices are detected:
- All devices are shown in the selection dialog
- User can choose which one to connect to
- This is useful when multiple EVC devices are connected to the computer

## Performance

- **Scanning time**: 1-2 seconds typical for 4 COM ports
- **Parallel scanning**: Up to 8 concurrent port/baud attempts
- **Response timeout**: 500ms per port/baud combination (configurable)
- **Thread safety**: Each scan attempt uses its own SerialService instance

## Configuration

Scanner settings are defined in `evc_gui/services/port_scanner.py`:

```python
BAUD_CANDIDATES = (57600, 230400, 19200, 38400, 115200, 9600)  # Baud rates to try
SCAN_TIMEOUT = 0.5          # Timeout per port/baud attempt (seconds)
MAX_WORKERS = 8              # Maximum concurrent scanning threads
```

## Implementation Details

### New Files Added

1. **`evc_gui/services/port_scanner.py`**
   - `DetectedDevice`: Dataclass representing a detected device
   - `PortScanner`: Main scanner class with parallel port detection

2. **`evc_gui/ui/device_selection_dialog.py`**
   - `DeviceSelectionDialog`: Dialog for device selection

### Modified Files

1. **`evc_gui/ui/main_window.py`**
   - Added `port_scanner` attribute
   - Modified `start_connection()` to use auto-detection
   - Added `_scan_and_select_device()` for background scanning
   - Added `_on_auto_scan_complete()` for dialog display
   - Added `_connect_to_device()` for selected device connection

## Backward Compatibility

- All existing functionality is preserved
- "Refresh Ports" button still works to list available ports
- Manual port/baud selection is still available if needed
- All existing commands and workflows remain unchanged

## Future Enhancements

Potential improvements:
1. **Caching**: Remember last used device for quick reconnection
2. **Favorites**: Allow users to mark favorite devices
3. **Auto-Reconnect**: Automatically reconnect to last used device if available
4. **Device Nicknames**: Allow users to assign friendly names to devices
5. **Scan History**: Keep history of connected devices

## Troubleshooting

### No devices detected
- Ensure device is powered on and connected
- Check USB cable is secure
- Try a different USB port
- Check device firmware is compatible
- Manually verify COM port in Device Manager

### Slow scanning
- Reduce number of baud rates to test (modify `BAUD_CANDIDATES`)
- Increase `MAX_WORKERS` for more parallel scanning
- Check for noisy/flaky USB connection

### Dialog not appearing
- Check logs in `logs/` directory
- Verify device is actually connected and responding
- Try clicking "Refresh Ports" first, then "Start / Connect"

## Technical Notes

- Scanning runs in a background thread to prevent UI freezing
- Each port scan attempt uses a dedicated SerialService instance (thread-safe)
- Device detection uses `ver` and `sn` commands (standard EVC commands)
- Chronos product variant resolution uses serial number prefix logic
- Dialog styling matches the application theme
