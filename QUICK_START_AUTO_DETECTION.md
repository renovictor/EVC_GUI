# Quick Start: Auto-Detection Feature

## What's New?
The app now **automatically finds and connects to EVC devices** without requiring manual port selection!

## How to Use

### Simple Flow (Recommended)
1. **Connect your EVC device** to the computer via USB
2. **Click "Start / Connect"** button
3. **Wait for device scan** (~1-2 seconds)
4. **Select your device** from the dialog that appears
5. **Done!** The app is now connected and ready to run

### What You'll See
- A progress indicator showing scanning in progress
- A device selection dialog showing:
  ```
  COM Port | Product      | Serial Number | Firmware | Baud Rate
  COM3    | Tykon        | T12345        | FW 1.0   | 57600
  COM5    | Quantum      | Q09876        | FW 2.1   | 230400
  ```

### Manual Selection (Optional)
If you prefer the old workflow:
1. Click "Start / Connect"
2. In the device dialog, click "Use Manual Selection"
3. Manually choose COM port and baud rate
4. Click "Start / Connect" again

## Features

✓ **Automatic port scanning** - No manual port selection needed
✓ **Device detection** - Identifies product, serial number, and firmware
✓ **Smart baud detection** - Finds correct baud rate automatically
✓ **Multiple devices** - Supports multiple EVC devices connected at once
✓ **Manual fallback** - Still supports manual mode if needed
✓ **Fast** - Scans complete in 1-2 seconds

## Troubleshooting

### No Devices Found
- Check device is powered on
- Check USB cable is connected
- Try different USB port
- Check device is responding (use another tool to verify)

### Slow Scanning
- This is normal (1-2 seconds for full scan)
- If extremely slow, check USB connection quality

### Want to Connect to Specific Port?
- Click "Start / Connect"
- Click "Use Manual Selection" in the dialog
- Choose your port and baud rate manually

## See Also

- `AUTO_DETECTION_FEATURE.md` - Detailed technical documentation
- `README.md` - Application overview
- `logs/` - Check logs if you need to debug connection issues

## Tips

💡 The app remembers the port you were last on - it's displayed in the combo box after connection
💡 "Refresh Ports" button still works for manual port listing
💡 Multiple devices? The dialog shows all of them - pick the one you want!
💡 Baud rate is auto-detected - no guessing needed
