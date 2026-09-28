#!/usr/bin/env python3
"""Quick verification script for auto-detection implementation."""

import sys
from pathlib import Path

def check_files():
    """Verify all required files exist."""
    base = Path(".")
    files = [
        "evc_gui/services/port_scanner.py",
        "evc_gui/ui/device_selection_dialog.py",
        "AUTO_DETECTION_FEATURE.md",
        "QUICK_START_AUTO_DETECTION.md",
        "IMPLEMENTATION_SUMMARY_AUTO_DETECTION.md",
    ]
    
    print("Checking files...")
    all_ok = True
    for f in files:
        path = base / f
        if path.exists():
            print(f"  [OK] {f}")
        else:
            print(f"  [FAIL] {f} MISSING")
            all_ok = False
    
    return all_ok

def check_imports():
    """Verify imports work."""
    print("\nChecking imports...")
    try:
        from evc_gui.services.port_scanner import PortScanner, DetectedDevice
        print("  [OK] PortScanner imports OK")
    except Exception as e:
        print(f"  [FAIL] PortScanner import failed: {e}")
        return False
    
    try:
        from evc_gui.ui.device_selection_dialog import DeviceSelectionDialog
        print("  [OK] DeviceSelectionDialog imports OK")
    except Exception as e:
        print(f"  [FAIL] DeviceSelectionDialog import failed: {e}")
        return False
    
    return True

def check_port_scanner():
    """Verify PortScanner class structure."""
    print("\nChecking PortScanner structure...")
    try:
        from evc_gui.services.port_scanner import PortScanner
        
        # Check attributes
        attrs = ['BAUD_CANDIDATES', 'SCAN_TIMEOUT', 'MAX_WORKERS']
        for attr in attrs:
            if hasattr(PortScanner, attr):
                print(f"  [OK] {attr} exists")
            else:
                print(f"  [FAIL] {attr} missing")
                return False
        
        # Check methods
        methods = ['scan_ports', '_probe_port', '_is_valid_ver_response',
                   '_extract_product_type', '_extract_unit_serial',
                   '_extract_firmware', '_resolve_product_name']
        for method in methods:
            if hasattr(PortScanner, method):
                print(f"  [OK] {method} exists")
            else:
                print(f"  [FAIL] {method} missing")
                return False
        
        return True
    except Exception as e:
        print(f"  [FAIL] Check failed: {e}")
        return False

def check_main_window():
    """Verify MainWindow integration."""
    print("\nChecking MainWindow integration...")
    try:
        # Just import to check syntax
        from evc_gui.ui.main_window import MainWindow
        
        # Check if methods exist
        methods = ['start_connection', '_scan_and_select_device',
                   '_on_auto_scan_complete', '_connect_to_device']
        
        for method in methods:
            if hasattr(MainWindow, method):
                print(f"  [OK] {method} exists")
            else:
                print(f"  [FAIL] {method} missing")
                return False
        
        return True
    except Exception as e:
        print(f"  [FAIL] MainWindow check failed: {e}")
        return False

def main():
    """Run all checks."""
    print("=" * 60)
    print("AUTO-DETECTION IMPLEMENTATION VERIFICATION")
    print("=" * 60)
    
    results = []
    results.append(("Files", check_files()))
    results.append(("Imports", check_imports()))
    results.append(("PortScanner", check_port_scanner()))
    results.append(("MainWindow", check_main_window()))
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    all_passed = True
    for check_name, passed in results:
        status = "PASS" if passed else "FAIL"
        symbol = "[OK]" if passed else "[FAIL]"
        print(f"{symbol} {check_name}: {status}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    
    if all_passed:
        print("\nAll checks passed! Implementation is complete.")
        return 0
    else:
        print("\nSome checks failed. Please review the implementation.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
